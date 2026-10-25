# geni-uploader: container usage guide

A generic container that uploads sources (documents, photos) to Geni
profiles from a manifest in YOUR git repository. You run it; nothing runs
for you. The image is immutable and carries a pinned, reviewed uploader;
your repository supplies DATA only (manifest, scans, status) and its code
is never executed.

Everything below reflects the actual published image. Where behavior is
known from observation rather than Geni documentation, it says so.

## 1. Install and pull

Requirements: Linux (or macOS with a Linux VM) with Podman. Check your
architecture first - the published image is linux/amd64:

    uname -m        # x86_64: run natively. arm64 (Apple Silicon): see below.

Pull the image BY DIGEST (a tag can be repointed; a digest cannot):

    podman pull quay.io/reihlinstinct/geni-uploader@sha256:<pinned-digest>

Verify what you got before running:

    podman inspect quay.io/reihlinstinct/geni-uploader@sha256:<pinned-digest> \
      --format '{{.Digest}} {{.Architecture}}'

On Apple Silicon, run with `--arch amd64` (emulated) or build locally from
this repository's Dockerfile instead.

## 2. Credentials: local files only

Two credentials, both mounted read-only at runtime; neither is baked into
the image, printed, or committed:

- GitHub token (read+write on your data repo): save in `~/.gh-token`,
  mode 600. Mounted at `/run/gh-token`. Inside the container it reaches
  git only through an ask-pass helper that answers github.com prompts
  exclusively; interactive prompts are disabled.
- Geni access token: save in `~/.geni-token`, mode 600 (see
  docs/geni-token.md). Mounted at `/run/geni-token`.

Create the files with a restrictive umask, and if a file already exists
with wider permissions, fix them explicitly:

    umask 077
    touch ~/.gh-token ~/.geni-token
    chmod 600 ~/.gh-token ~/.geni-token
    # then write each secret with your editor or the helper in geni-token.md

Never pass secrets via `-e NAME=value` on the command line: command lines
are visible in shell history and process listings. The image accepts the
Geni token only as a file mount (or a GENI_ACCESS_TOKEN environment
variable if you deliberately choose it).

## 3. Code vs data: image, repo, ref, pin

- The IMAGE is immutable: `quay.io/reihlinstinct/geni-uploader@sha256:...`
  always means the same bytes. The uploader code lives ONLY in the image.
- Your REPO (`GENI_UPLOAD_REPO`) is cloned fresh into an in-memory tmpfs
  on every run and supplies data: the upload manifest, the scanned files,
  and the status file. Code in the repo is never executed.
- `GENI_UPLOAD_REF` (optional) selects the branch to clone. If your
  manifest is not on the default branch, you MUST set it.
- The repo URL must be an https github.com URL; anything else is refused.
- `GENI_UPLOAD_EXPECT_SHA` (optional but recommended) pins the exact
  commit: after cloning, the container compares the checked-out HEAD and
  refuses to run on a mismatch. This protects you from silent branch
  moves.

IMPORTANT for repeat/resume runs: the pin is a point in time. After a
successful run, the tool commits and pushes the updated status file back
to the same branch - so the branch head MOVES and the old EXPECT_SHA no
longer matches. Before re-running, re-derive the pin:

    git ls-remote https://github.com/<you>/<repo>.git refs/heads/<branch>

and use the printed SHA as the new GENI_UPLOAD_EXPECT_SHA (or omit it,
trusting the branch). Never assume a previously used SHA is still the head.

## 4. The manifest and packaging assets

One YAML file in your repo, for example
`packages/my-batch/upload-manifest.yaml`:

    targets:
      - profile_id: "1234567890123456789"   # the Geni profile number
        expect_name: "Full Distinctive Name" # >= 2 words; checked against Geni
        documents:
          - title: "Short descriptive title"
            source_url: "https://example.org/source-page"  # or use file:
            description: "What this source is, dated and attributed"
            labels: "source"
        photos:
          - title: "Another scan"
            file: "scan-page-12.jpg"        # relative to THIS manifest file

Rules enforced by the loader (it fails loudly, before any network call):

- `profile_id` and `expect_name` are required for every target;
  `expect_name` must be a distinctive full name, not a bare first name.
- `profile_id` is the number from the profile's website URL. That
  number is usually the profile's **guid**, not its API node id; the
  tool resolves it automatically (fail-closed, with the name guard)
  before any other call. See [guid-resolution.md](guid-resolution.md).
- Every item needs a `title`. Documents need `source_url` or `file`;
  photos need `file`.
- `file:` paths resolve relative to the MANIFEST's own directory (not the
  repository root), must stay inside that directory, and must exist. Keep
  scans next to the manifest and reference them by bare filename.
- Large binary scans belong in the repo as plain files; the tool reads
  whatever the clone contains.

## 5. Dry run: plan (read-only)

    podman run --rm --tmpfs /work \
      -e GENI_UPLOAD_REPO=https://github.com/<you>/<repo>.git \
      -e GENI_UPLOAD_REF=<branch> \
      -e GENI_UPLOAD_EXPECT_SHA=<full-40-char-sha> \
      -v ~/.gh-token:/run/gh-token:ro,Z \
      -v ~/.geni-token:/run/geni-token:ro,Z \
      quay.io/reihlinstinct/geni-uploader@sha256:<pinned-digest> \
      --token-file /run/geni-token plan \
      --manifest packages/my-batch/upload-manifest.yaml

`plan` performs only GET requests: it loads the manifest, checks every
referenced file, fetches each profile and its document/photo listings,
verifies the expected name, and reports which items would upload and
which would be skipped as already present.

Exit codes for plan (currently published image): 0 = the command ran;
note that THIS image build exits 0 even when profile checks fail - judge
the run by the PER-PROFILE lines, not the exit code or header. (Fixed in
the next image build: a neutral header, a verdict printed after the
checks, and exit 1 when any profile check fails.)

NOTE (known issue in the currently published image): it prints
"PLAN (VERIFIED)" in its header before the profile checks run. A line
like `profile <id>: OK (<name>)` is a real verification; a line with
`HTTP 401` or another error means that profile was NOT verified,
regardless of the header.

## 6. Upload: run

Only after a clean plan:

    podman run --rm --tmpfs /work \
      -e GENI_UPLOAD_REPO=https://github.com/<you>/<repo>.git \
      -e GENI_UPLOAD_REF=<branch> \
      -e GENI_UPLOAD_EXPECT_SHA=<full-40-char-sha> \
      -v ~/.gh-token:/run/gh-token:ro,Z \
      -v ~/.geni-token:/run/geni-token:ro,Z \
      quay.io/reihlinstinct/geni-uploader@sha256:<pinned-digest> \
      --token-file /run/geni-token run \
      --manifest packages/my-batch/upload-manifest.yaml \
      --confirm YES

Useful flags: `--smoke` uploads only the first item, then stops (verify it
on Geni before the full run); `--state <path>` relocates the state file;
`--no-repo-sync` skips committing the status file back to the repo;
`--log <path>` relocates the diagnostic log.

Exit codes: 0 = done; 1 = failure (see log); 2 = refused (missing
`--confirm YES` or missing token); 3 = an upload's outcome is UNCERTAIN
(network failure after send - the item may or may not exist on Geni; the
run stops so you can resolve it by hand); 4 = a write was acknowledged but
the read-back verification failed; 5 = uploads verified on Geni but the
status-file push back to the repo failed (the next run retries the sync);
6 = another run holds the lock (concurrent runs are refused).

## 7. What happens on run: verification, status, resume

- Before touching anything, the tool re-verifies each profile by name. A
  failed check (for example HTTP 401) aborts before any write.
- Each upload is followed by a GET read-back: the item must appear in the
  profile's listing, tagged to that profile, or the run stops (exit 4).
- Idempotency: completed items are recorded in a local state file
  (`geni-upload-state.json`, atomically written) AND in
  `upload-status.yaml` next to the manifest, which is committed and
  pushed back to your repo (best effort; exit 5 if the push fails).
  Items already present on Geni are skipped - but only when the profile
  listing actually shows them; a recorded item the listing does NOT
  confirm is marked `uncertain` and the run STOPS - nothing is
  re-uploaded automatically.
- Resume = run the same command again (with a re-derived pin, see section
  3). Completed items are skipped; interrupted items are retried. The
  local state file lives inside the ephemeral clone and is discarded when
  the container exits; the durable record is `upload-status.yaml`, read
  back from your repo on the next run (or pass `--state` on a mounted
  path to keep the local file too).
- Uncertain items (exit 3) stay marked `uncertain` until YOU check Geni
  and set the entry in `upload-status.yaml` to `not_found` (retry) or
  `resolved` (fixed on Geni). Deleting the entry does NOT unblock it -
  the local marker survives. The tool never auto-retries an uncertain
  write, so a duplicate can never be created silently.
- The diagnostic log records progress, exit codes and errors. It never
  contains tokens, headers, payloads, or personal names/titles (items are
  logged as short hashes). It is safe to share when asking for help.

## 8. Failures you may see, and what they mean

- `manifest not found: ...` - wrong `--manifest` path, or the manifest is
  not on the branch you cloned. Set GENI_UPLOAD_REF to the branch that
  carries it.
- `file not found: ...` or `file escapes the manifest directory` - asset
  path wrong relative to the manifest; keep scans beside the manifest and
  use bare filenames.
- `cloned HEAD ... != GENI_UPLOAD_EXPECT_SHA ...` - the branch moved
  (often because a previous run pushed the status file). Re-derive the
  pin (section 3).
- `HTTP 401: Invalid access token` - the Geni token is expired, revoked,
  or was saved incorrectly. Regenerate it with docs/geni-token.md. No
  writes were attempted.
- `HTTP 429` - Geni rate limit. The client paces requests (adapting to
  Geni's rate headers) and STOPS on 429 with no automatic retry - wait
  for the rate window, then re-run as a fresh, deliberate attempt. The
  state file makes resuming safe.
- `PUSH FAILED` / exit 5 - uploads are verified on Geni; only the repo
  status commit failed (read-only GitHub token or a moved remote). The
  next run retries the sync.

## 9. Revoking access when you are done

- Geni: remove the application in your Geni account settings
  (privacy/applications section). That revokes its tokens.
- GitHub: delete the token you created for this tool
  (https://github.com/settings/tokens).
- Local: `rm ~/.geni-token ~/.gh-token`. The container is `--rm` and its
  clone lived in memory (tmpfs); note that a host kernel may swap tmpfs
  pages, so the token files on disk are the only durable copies to remove.
