# Upload client boundaries: design (#753)

Status: **proposal only**. This PR adds this document and nothing else. No source,
test, workflow, Dockerfile, image or pin changes; nothing moves here. Every later
step is a separate, independently reviewed PR.

Subject: `src/geni_uploader/client/upload.py` (1509 lines at base
`a404578a8682003533beaddc0bef083b5665f67b`). It combines manifest parsing,
HTTP transport and pacing, GET readback verification, journal/status state and
command orchestration. This doc maps those concerns, lists everything that depends
on the file, names the identities a split must keep, and proposes a move-only order.

Labels: **[repo]** read from the tree at the base SHA; **[measured]** produced by a
local command at that SHA; **guess** is a judgment, not a fact; **not checked** means
nobody verified it for this doc.

## 0. Overlap and existing constraints

- No existing doc is this design. `docs/API-CLIENT-DESIGN.md` covers endpoint coverage
  and an offline MCP companion and excludes edits to the file. `docs/src-layout-plan.md`
  moves files into packages "initially moved intact" and says not to split the
  file's HTTP and source orchestration *while moving it*. This doc is compatible with
  that: it splits in place, and a package move and a split never share a PR. [repo]
- **Byte-synced** [repo]: `CONTRIBUTING.md` states the file "is byte-synced with a
  reviewed private copy: changes to it are synced to both repos identically and pinned
  in a new reviewed image", and that `src/geni_uploader/client/source_details.py` and
  `src/geni_uploader/client/cli_spec.py` are part of the same reviewed unit.
  What enforces what:
  - The private copy: **no check in this repo** compares against it. The sync is a
    process rule. Whether the private repo has its own check: not checked.
  - Image bytes: `.github/workflows/publish-image.yml` ("Verify baked files are
    byte-identical to the repo files") compares the sha256 of every Dockerfile `COPY`
    destination, including `/opt/geni_upload.py`, with the repo file at build time.
  - Release descriptor: `tools/image_provenance.py` checks a descriptor that lists a
    sha256 per COPY destination (`docs/image-release.md`). No descriptor is committed
    for the current pin (that doc's "Limits"), so the strict check does not run in CI yet.
  - Digest pins: `.github/workflows/geni-upload.yml` runs one `IMAGE` pinned by digest;
    `src/geni_uploader/runners/protected_source_approval.py` carries the same digest as
    its own `IMAGE` constant. Whether a test ties the two together: not checked.
  - **No literal hash of `src/geni_uploader/client/upload.py` is committed** anywhere
    in the tree (grep for 64-hex near the path found none). `GENI_UPLOAD_EXPECT_SHA` in
    `entrypoint.sh` pins the cloned *data repo* HEAD, not this file.
  - Consequence: any split changes this file's bytes, so it is a sync event for the
    private copy and needs a new image, a committed descriptor and a coordinated
    `IMAGE` repin. Repin is out of scope here (section 6).
- Stale citations, found in passing [measured]: `docs/API-CLIENT-DESIGN.md` cites
  `execute()` at line 244 and `ALLOWLIST` at 52-58; at the base they are 250-309 and
  58-64. Not fixed here.

## 1. Source inventory

Generated with a Python `ast` walk over the module's top-level nodes at
`a404578a8682003533beaddc0bef083b5665f67b` (`ast.parse`, `lineno`/`end_lineno` per
node). The concern assignment is a judgment (**guess** where a symbol sits on a seam).
Imports are lines 22-42 (stdlib plus `cli_spec`, `plan_report`, `visual_plan`).
The module docstring is lines 2-21. † = no consumer outside the module (src and tests).

| Concern | Symbols (line range) |
|---|---|
| Parsing (manifest, payload, response shaping) | `render_description` 120-138, `load_manifest` 141-207, `name_matches` 210-214, `profile_name_surface` 337-359, `observed_name_fields` 363-379†, `observed_response_keys` 382-397, `profile_node_number` 400-405, `source_listing_rows` 461-480, `anchor` 530-531, `upload_payload` 534-546, `_profile_payload_shape` 691-711†, `_extract_served_id` 714-729†, `listing_shape` 1396-1427 |
| Transport/pacing | `_PROD_API` 47†, `API_BASE` 48, import-time base guard 49-57, `ALLOWLIST` 58-64, `_sleep` 68-70, `ApiError` 74-75, `ThrottledError` 78-81, `UncertainWrite` 84-85, `_RATE` 222, `_pace` 225-231†, `_update_rate` 234-247, `execute` 250-309, `get_token` 312-317 |
| Verification (GET readback) | `VerificationError` 88-90, `verify_linkage` 320-334, `verify_profile` 408-458, `list_tagged` 483-527, `diagnose_whoami` 663-676 |
| State (journal, status, log) | `STATE_DEFAULT` 65†, `STATUS_NAME` 71, `label` 93-95†, `RunLog` 98-117, `load_state` 549-556, `save_state` 559-565†, `status_path` 568-569†, `load_status` 572-587, `save_status` 590-598, `repo_sync` 601-632, `preflight_state_writable` 635-648 |
| Orchestration (commands, CLI) | `plan_summary` 651-659†, `cmd_whoami` 679-688, `cmd_contrast` 732-774, `cmd_plan` 777-784, `_cmd_plan` 787-885, `durable_upload` 888-1024, `process_target` 1027-1117†, `cmd_run` 1120-1206, `cmd_auth_url` 1209-1223†, `cmd_guidmap` 1226-1331, `cmd_pguid` 1334-1394, `cmd_listing_shape` 1430-1452, `main` 1455-1505, `__main__` guard 1508-1509 |

Seams (guesses): `list_tagged` and `diagnose_whoami` are reads, filed under
verification because they read back state rather than transport it; `label` is a
log-safe hash, filed under state with `RunLog`; `durable_upload` is the write-ahead
journal plus POST plus readback and stays in orchestration as the composing function.

## 2. Consumer inventory

Found by grep at the base for `client.upload`, `client import upload`, the full path of
the file and `geni_upload` across `src/`, `tests/`, `tools/`, `.github/`,
`geni_offline/`, `Dockerfile`, `entrypoint.sh` and docs. [repo]

Python importers and the names each uses (attribute access on the import alias):

- `src/geni_uploader/client/source_details.py` (`as api`): `ALLOWLIST` (mutated in place
  with `.update`), `API_BASE`, `ApiError`, `ThrottledError`, `UncertainWrite`,
  `VerificationError`, `execute`, `get_token`, `render_description`, `verify_profile`.
  No other module under `src/` imports the file; no root facade module exists.
- `test_geni_upload.py` (largest consumer: 118 tests, 14 `importlib.reload` calls),
  `test_contracts.py`, `test_contracts_behavior.py`, `test_durable_resume.py`,
  `test_acknowledged_reconciliation.py`, `test_object_id_readback.py`,
  `test_english_description.py`, `test_listing_shape.py`, `test_plan_report.py`,
  `test_source_plan_guards.py`, `test_visual_plan.py`, `test_dispatch_mode_matrix.py`
  (`main` parser), `test_doc_manifest_examples.py`, `test_contract_allowlist_photo.py`
  (also in a subprocess). Together with `source_details` they use **42 module names**
  (section 3) plus the stdlib modules `time` and `urllib` reached through the alias.
- Tests **rebind** 16 names on the module object, about 150 sites [measured]:
  `execute` (65), `verify_profile` (14), `verify_linkage` (12), `get_token` (10),
  `_sleep` (10), `list_tagged` (9), `load_manifest` (9), `urllib.request` (8),
  `time.sleep` (8), `repo_sync` (2), `_RATE` (2), and once each `ALLOWLIST`, `API_BASE`,
  `save_status`, `_cmd_plan`, `load_status`.

Path and content consumers:

- `Dockerfile`: COPY to `/opt/geni_upload.py` and to
  `/opt/pkg/geni_uploader/client/upload.py`; `PYTHONPATH=/opt/pkg`.
- `entrypoint.sh`: `exec python /opt/geni_upload.py "$@"` (script mode, `__main__`).
- `.github/workflows/ci.yml` (read only): coverage `--include` names this file and
  `source_details`. `.github/coverage_report.py` `PRODUCTION` names the same two and
  **refuses coverage data that includes any other file**; per-file floor in
  `.github/coverage-floor.txt`.
- `.github/workflows/publish-image.yml`, `.github/workflows/geni-upload.yml` and
  `src/geni_uploader/runners/protected_source_approval.py`: baked-byte check and the
  two digest pins (section 0).
- `test_cli_docs.py`: runs the file as a script for `--help` of every command, and
  asserts the Dockerfile COPY line. `test_cli_env_docs.py`: maps the path to its CLI
  surface. `test_people_src_layout.py`, `test_image_descriptor.py`,
  `test_coverage_report.py`, `test_src_package_foundation.py`,
  `test_dispatch_mode_matrix.py`, `test_entrypoint_sha_guard.py`: path, COPY or
  `/opt/geni_upload.py` assertions.
- `test_offline_zero_network.py`: forbids `geni_offline` from importing the
  `geni_upload` and `source_details` names.
- Docs naming the path: 27 files under `docs/` plus `README.md`, `ARCHITECTURE.md`,
  `CONTRIBUTING.md`; only `docs/API-CLIENT-DESIGN.md` cites line numbers (18).
  `man/man1/` pages derive from `src/geni_uploader/client/cli_spec.py`.

## 3. Identities to preserve

1. **CLI.** Script `python src/geni_uploader/client/upload.py`, image path
   `/opt/geni_upload.py`, program help from the module `__doc__`. Global
   `--token-file`; commands `auth-url` (`--client-id`, `--redirect-uri`), `whoami`,
   `plan`, `run`, `contrast`, `guidmap`, `pguid`, `listing-shape` (each `--manifest`);
   `run`: `--confirm`, `--smoke`, `--no-repo-sync`; `plan` and `run`: `--log`,
   `--state`. Exit codes 2-6 from `cmd_run`, 1 from `main`, `SystemExit` from the base
   guard. Kept by leaving `main`, the parser and the docstring in this file; proved by
   the existing `--help` tests and `test_dispatch_mode_matrix.py`.
2. **Public names.** These 42 must stay importable from
   `geni_uploader.client.upload` as the **same objects** as their new home:
   `ALLOWLIST`, `API_BASE`, `ApiError`, `RunLog`, `STATUS_NAME`, `ThrottledError`,
   `UncertainWrite`, `VerificationError`, `_RATE`, `_cmd_plan`, `_sleep`,
   `_update_rate`, `anchor`, `cmd_contrast`, `cmd_guidmap`, `cmd_listing_shape`,
   `cmd_pguid`, `cmd_plan`, `cmd_run`, `cmd_whoami`, `diagnose_whoami`,
   `durable_upload`, `execute`, `get_token`, `list_tagged`, `listing_shape`,
   `load_manifest`, `load_state`, `load_status`, `main`, `name_matches`,
   `observed_response_keys`, `preflight_state_writable`, `profile_name_surface`,
   `profile_node_number`, `render_description`, `repo_sync`, `save_status`,
   `source_listing_rows`, `upload_payload`, `verify_linkage`, `verify_profile`;
   plus `time` and `urllib` as module attributes. Kept by `from ... import name`
   re-exports (explicit `__all__` or `# noqa: F401`, since ruff flags unused imports).
   Mutable objects (`ALLOWLIST` set, `_RATE` dict) are shared by identity, so in-place
   mutation such as `api.ALLOWLIST.update(...)` keeps working.
3. **Patch reach (the hard one).** A re-export keeps the name, not the lookup. A
   function moved out of this file resolves collaborators in its new module, so a
   test that rebinds `g.execute` no longer reaches it. At the base, the moved callers
   that would lose reach are [measured, `ast` name references]: `_pace` (`_RATE`,
   `_sleep`), `_update_rate` (`_RATE`), `execute` (`ALLOWLIST`, `_RATE`, `_sleep`),
   `verify_linkage` (`_sleep`, `list_tagged`), `verify_profile`, `list_tagged` and
   `diagnose_whoami` (`API_BASE`, `execute`). **Parsing and state functions reference
   no rebound name**, so moving them loses no reach. Functions left in this file keep
   reach, because their bare names bind in this module. Rebinding a replaced object
   (`setattr(g, "_RATE", {...})`) also stops reaching moved code.
4. **Import-time guard and reload.** The `GENI_API_BASE`/`GENI_UPLOAD_E2E` refusal
   runs at import. 14 `importlib.reload(g)` calls in `test_geni_upload.py` rely on
   that. After the transport move, reloading the facade does not re-run a cached
   submodule's guard, and reload no longer replaces the exception classes (see the
   comment in `test_source_details_branches.py`). Those tests must reload the defining
   module.
5. **Content identity.** The byte-sync partner (private copy), the baked-byte check,
   the descriptor and both `IMAGE` pins (section 0). Every new module is a new Dockerfile
   COPY (script mode imports it from `/opt/pkg`), a new descriptor entry, a new
   coverage `--include` and `PRODUCTION` entry, and part of the reviewed unit in
   `CONTRIBUTING.md`. These are workflow, `.github` and release edits. That is why a
   split forces one coordinated sync and repin later, and why it cannot land as
   silent dev PRs.

## 4. Proposed boundaries (proposal; nothing moves in this PR)

Target modules under `src/geni_uploader/client/` (names are a **guess**, open to
review), as dotted module names:

| Module | Takes |
|---|---|
| `geni_uploader.client.upload_errors` | `ApiError`, `ThrottledError`, `UncertainWrite`, `VerificationError` |
| `geni_uploader.client.upload_parsing` | the parsing row of section 1 |
| `geni_uploader.client.upload_state` | the state row |
| `geni_uploader.client.upload_transport` | the transport row except the exceptions, including the import-time guard |
| `geni_uploader.client.upload_verification` | the verification row except `VerificationError` |
| `geni_uploader.client.upload` (stays) | orchestration, `main`, `__doc__`, `__main__`, all re-exports |

Dependency direction (no cycles; checked against the section 1 name references):
`upload_errors` ← `upload_parsing`, `upload_state`, `upload_transport` ←
`upload_verification` (uses transport and parsing) ← `upload`. No new module imports
`upload`. Stdlib use by symbol [measured, `ast` attribute walk]: `http.client` only in
`execute`; `subprocess` only in `repo_sync`; `fcntl` only in `cmd_run` (stays);
`tempfile` only in state; `urllib` in `execute`, `list_tagged`, `cmd_auth_url` and
`cmd_contrast` (whether the last three use only `urllib.parse`: not checked).

Step order. Each step is its own PR, moves only (moved code byte-identical apart from
imports and re-exports), no behaviour change:

0. Tests-only: add the identity tests of section 5 against the current single file,
   so they are green before anything moves.
1. `upload_errors`: zero patch-reach loss. Reload-identity tests adjusted if needed.
2. `upload_parsing`: zero patch-reach loss.
3. `upload_state`: zero patch-reach loss.
4. `upload_transport`: retarget only the rebinds of `_sleep`, `_RATE`, `ALLOWLIST`
   (and the reload calls) that reach `execute`/`_pace`/`_update_rate`; the test diff
   is limited to patch targets.
5. `upload_verification`: retarget the `execute`, `API_BASE`, `list_tagged`, `_sleep`
   rebinds that reach the moved verifiers.
6. Later and separately GO'd: Dockerfile COPY, coverage include and `PRODUCTION`,
   descriptor, private-copy sync, image build and `IMAGE` repin (section 6).

Steps 1-5 change `src/geni_uploader/client/upload.py` bytes. Whether they may merge
before step 6, or must wait and land as one reviewed unit, is open (section 7).

## 5. Offline test and mutation plan (plan only)

Coverage at the base [measured, local `coverage run` with CI's include list,
coverage 7.17.0]: the file is 882/959 statements (92 %). By concern (statements inside
top-level symbols): parsing 170/176, transport 75/81, verification 81/82, state
83/86, orchestration 453/508.

Existing tests per concern (from the consumer map):

- Parsing: `test_english_description.py`, `test_doc_manifest_examples.py`,
  `test_object_id_readback.py`, `test_listing_shape.py`, `test_geni_upload.py`.
  Gaps: `observed_name_fields`, `_profile_payload_shape`, `_extract_served_id` have
  no direct test (exercised only through commands).
- Transport: `test_contracts.py`, `test_contract_allowlist_photo.py`,
  `test_geni_upload.py` (retry, 429, base guard via reload). Gap: `_pace` only
  indirect; `execute` 42/46, `_update_rate` 11/13 statements.
- Verification: `test_acknowledged_reconciliation.py`, `test_durable_resume.py`,
  `test_object_id_readback.py`, `test_contracts_behavior.py`.
- State: `test_contracts_behavior.py`, `test_geni_upload.py`. Gaps: `save_state`,
  `status_path`, `label` only indirect; `repo_sync` 19/22.
- Orchestration: `test_geni_upload.py`, `test_plan_report.py`, `test_visual_plan.py`,
  `test_source_plan_guards.py`, `test_dispatch_mode_matrix.py`, `test_cli_docs.py`.
  Gaps: `cmd_auth_url` 1/9 statements; `process_target` 42/54 and `cmd_run` 51/65.

Identity proofs to add (step 0, then kept):

- Import equivalence: for each of the 42 names, `getattr(upload, n) is
  getattr(home_module, n)`, in both import orders, plus `upload.time`/`upload.urllib`.
- Shared mutables: `upload.ALLOWLIST is upload_transport.ALLOWLIST`, same for `_RATE`.
- CLI: `--help` output of every command unchanged (the existing tests in
  `test_cli_docs.py`), exit codes unchanged.
- Dependency graph: an `ast` test that no `upload_*` module imports `upload`, and
  that the import edges match section 4.
- Byte check per move PR: the moved function bodies hash the same as the cut ranges
  from the base, compared by `ast.dump` of each moved node (not checked that this is
  stable across formatting; **guess**).

Guards to mutate (run in a scratch copy, before and after each move; a mutant must
be killed both times, which also proves patch reach survived):
the `ALLOWLIST` membership check in `execute`; GET-only retry (POST not retried,
raises `UncertainWrite`); 429 raising `ThrottledError` with no retry; the import-time
loopback/`GENI_UPLOAD_E2E` refusal; `_update_rate` header parsing; `render_description`
requiring an English section; `name_matches` requiring every token;
`profile_node_number` refusing a non-numeric node; `durable_upload` never replaying
an intent; `repo_sync` requiring a successful push; `preflight_state_writable`;
`verify_linkage` polling until linkage. Mutants not yet written or run: not checked.

## 6. Non-goals

No wholesale rewrite; no behaviour change. No live Geni call, no network in tests. No
workflow dispatch, image build, release, descriptor commit or `IMAGE` repin; no
private-copy sync. No held-lane implementation. No workflow, `.github`, Dockerfile,
dependency or settings change. This doc is development scope, never external
execution approval.

## 7. Open questions

1. May steps 1-5 merge to master before the coordinated sync and repin, leaving
   master ahead of the private copy, or must they wait and land as one unit?
2. Should the coverage include list and `PRODUCTION` widen to the new modules (a
   `.github` edit), or should coverage keep measuring only the facade until step 6?
   Moving code out silently shrinks what the per-file floor measures.
3. Patch retargeting (steps 4-5) changes test files in a move PR. Is a test diff
   limited to patch targets acceptable, or should retargeting be its own PR?
4. Order against `docs/src-layout-plan.md`: split first, or package move first?
5. Should `geni_offline` (`test_offline_zero_network.py`) also forbid the new
   `upload_*` modules? Not checked whether the current rule already covers them.
6. Does master's copy of the file currently equal the bytes in the pinned image?
   Not checked; no descriptor is committed for the current pin.
7. Module names and the seams in section 1 (`list_tagged`, `label`, `durable_upload`).
