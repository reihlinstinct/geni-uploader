# Image release descriptor and provenance check (#100)

`geni-upload.yml` runs `IMAGE`, a container image pinned by digest. Before this
change, the readiness and pin tests only inspected literal workflow strings.
Nothing linked that digest to the engine code that was reviewed, so a fix could
merge while the workflow kept running an older image. `tools/image_provenance.py`
closes that gap offline, against a release descriptor.

## Descriptor (schema 1)

A JSON object with exactly these keys:

| Key | Value |
|---|---|
| `schema` | `1` |
| `image` | `ghcr.io/reihlinstinct/geni-uploader@sha256:<64 lowercase hex>`. Tags are refused. |
| `engine_revision` | the full 40-hex commit the image was built from |
| `entrypoint` | the image `ENTRYPOINT` path |
| `files` | `{ "<path in image>": "<sha256 hex>" }` for every Dockerfile `COPY` |

## What the check refuses

`python tools/image_provenance.py <descriptor>` exits 1 on the first mismatch:

1. A malformed descriptor: unknown or missing keys, a tag instead of a digest, another
   registry path, a short or upper-case revision, a bad hash.
2. The workflow's single `IMAGE` pin is not the descriptor digest.
3. The descriptor's file set is not exactly the Dockerfile's `COPY` destinations.
   Only plain `COPY <file> <path>` is accepted (no `ADD`, flags or multi-source).
4. A `COPY` source in the repo doesn't hash to the descriptor. This means the image
   is **stale**: the engine, a helper or `entrypoint.sh` changed and the image wasn't rebuilt.
5. `ENTRYPOINT` (exec form, one path) differs from the descriptor, or isn't
   where `entrypoint.sh` is copied.
6. Routing in the upload workflow:
   - every `docker run` targets `"$IMAGE"` exactly once and names no other image
   - every `/opt/*.py` it calls is in the image
   - `--entrypoint` is only `python` with such a script, and it only appears literally
     on a `docker run` line, never hidden in an argument array
7. The descriptor's files don't match `git show <engine_revision>:<path>`. When the
   commit isn't in the local clone the check fails closed. `--allow-missing-revision`
   downgrades this to an explicit "NOT verified" note.

Messages name paths and reasons, never file contents or token values.

## Tests

`tests/test_image_provenance.py` builds synthetic repositories in a temporary git repo.
Matching cases pass, and each refusal above has a failing case. A further test runs
the routing half against the shipped `Dockerfile` and `geni-upload.yml`. A local
mutation run that disables each guard in turn was killed by the suite every time.

## Limits and follow-ups (not in this change)

- **No descriptor is committed for the currently pinned digest.** Its baked file hashes
  can't be established offline without pulling or building that image, so the full
  check doesn't run against the live pin yet. Only the routing half does.
- The intended follow-up is for `publish-image.yml` to emit the descriptor from the
  image it just built, using `docker run --entrypoint sha256sum` over each `COPY`
  destination. The descriptor would then be committed with the next `IMAGE` pin PR,
  and CI would run the check. Both are workflow changes and need their own review.
- Verifying the digest itself, meaning that the registry serves those bytes under that
  digest, needs registry access and stays out of offline CI.
- No change to `geni_upload.py`, the Dockerfile, `entrypoint.sh` or any workflow.
  No Geni, dispatch, token or publishing.
