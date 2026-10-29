# Source package layout and migration

Status: staged migration design, issues #291 and #455. Updated 2026-10-29. No file moves or behavior changes in this
PR. Creation release work remains higher priority. A layout change does not
satisfy an authentication, storage, deployment or human-run release gate.

## Why change

The current tree has 29 top-level Python modules, an intentional test-enforced `geni_offline/` package (#93),
and a separate Node Worker project. This grew through small feature PRs without
a package boundary. Root scripts now mix source upload, offline parent models,
network candidates, evidence validation, rendering and workflow adapters.
Direct sibling imports and paths relative to `__file__` couple that structure to
Docker, tests and workflows. Moving files without those consumers is unsafe.

## Target ownership

Use one installable Python package under `src/geni_uploader/`, with explicit
subpackages by responsibility. Keep Node's dependency/build boundary separate.
Names below are a destination map, not a claim that monolithic code has already
been split internally.

```
src/geni_uploader/
  __init__.py
  core/                 # pure shared validation, data and intent semantics
    people.py           # current people_core.py, initially moved intact
    intent.py           # parent_intent_model.py
    outcome.py          # profile_outcome_model.py
    snapshot.py         # parent_snapshot.py
    father_once.py      # father_once_simulation.py
    parent_contract.py  # parent_adapter_contract.py, PURE wire descriptors
    proof_requirements.py # pure PROOFS constants, separated before envelope move
    proposal_review.py  # pure verify_proposal + proposal + payloads + BLOCKERS closure
  client/               # explicit network boundary; never imported by pure core
    upload.py           # geni_upload.py, initially moved intact
    source_details.py   # source_details.py, initially moved intact
    probe.py            # parent_probe.py (human read-only collector)
    closed_parent.py    # parent_http_candidate.py, gate remains always closed
  evidence/             # content contracts, not authenticated authority
    single_human.py     # single_human_approval_record.py
    approval.py         # approval_record.py
    ciphertext.py       # ciphertext_evidence.py
    github_review.py    # github_review_evidence.py
    workflow_content.py # workflow_content_contract.py
    profile_result.py   # profile_result.py
    parent.py           # parent_evidence.py
    envelope.py         # parent_envelope.py
  workflow/             # small workflow-facing glue, not domain decisions
    release_package.py  # father_release_package.py, reviewed file packaging
    protected_job.py    # protected_father_job.py, composes protected evidence
    father_executor.py  # father_executor_composition.py, still closed
    secondary_probe.py  # secondary_probe_action.py
    release_gate.py     # human_parent_gate.py, includes always-closed gate
    consumption.py      # parent_consumption.py (local prototype; composes evidence)
    runner.py           # parent_runner.py (synthetic only; composes release gate)
  cli/                  # thin argument/exit adapters, extracted separately
    upload.py
    source_details.py
    parent_plan.py
    parent_output.py
  presentation/
    plan_report.py
    visual_plan.py
  resources/            # reviewed machine contracts, packaged explicitly
    human-parent-release-gates.json
```

`parent_plan.py` and `parent_output.py` currently combine CLI and pure logic.
First move them intact to CLI modules; only a separate reviewed PR may extract
pure planning/output review into core/evidence. Likewise do not split
`geni_upload.py`'s HTTP and source orchestration while moving it. Each source
file has one authoritative implementation, never a copied second implementation.
The `client/` name marks the network boundary, not permission to call it.

Keep `docs/` for human documents, `tests/` for tests/fixtures/mutant harnesses,
`.github/` for GitHub-owned glue, and `tools/` for truly standalone audited tools.
Keep `oauth-bootstrap/` intact for now: its Worker, Wrangler/build and Node test
paths form a separate package. Its eventual directory rename is another issue,
not part of this Python migration. No private family data enters this tree.

## Dependency direction and compatibility

- Core must not import CLI/workflow/client. Current father_once_simulation
  imports the PURE parent_adapter_contract, so both belong in core, not client. Pure evidence may import shared
  validation but must not fetch or grant authority.
- Workflow/CLI may compose reviewed components; no import-time request, token
  retrieval, deployment, dispatch or gate bypass is introduced.
- Preserve existing public commands, flags, output bytes and exit codes. Do not
  invent a new live creation command. New package entry points mirror existing
  commands only after equivalence tests pass.
- During migration, root modules can be temporary compatibility facades. A
  facade aliases the real module where monkeypatch/import identity matters;
  a naive star-import wrapper changes globals and is not equivalent. Executed
  scripts need explicit main dispatch preserving argv and exit status.
- Facades cannot stay forever. Remove each only after all imports, docs,
  container paths, static guards and external entry points are mapped/tested.
  Do not rewrite an approved release pin silently; a new image still requires
  its ordinary separate build/release approval.

## Staged PRs

1. This design plus inventory and acceptance plan. No implementation moves.
2. Packaging foundation: explicit build backend/package discovery, test import
   setup and a no-side-effect package. Prove built wheel includes reviewed
   resources and imports from outside the checkout. Do not execute data-repo
   code or add `.`/the data checkout to import search paths.
3. Move one pure leaf evidence module with its direct dependencies resolved;
   update its callers/tests in the same PR. Keep temporary compatibility only
   where required. Prove old/new behavior and monkeypatch identity. Repeat in
   small dependency-ordered PRs, not a whole-repo rename.
4. Move shared core/model modules as small dependency clusters. Before moving
   parent_envelope into evidence, extract pure PROOFS from human_parent_gate into
   core/proof_requirements and the COMPLETE pure proposal closure into core/proposal_review:
   verify_proposal and proposal and BLOCKERS from parent_plan, plus payloads from
   parent_runner. verify_proposal reconstructs via proposal(), which calls
   payloads(); moving only the first function would retain upward imports.
   Their remaining imports are copy/re plus pure people_core validation, digest,
   exact/require/warnings. No protected_file, CLI/render, simulation/transport or
   require_production_release moves into core. Keep parent_plan and parent_runner
   callers/re-exports compatible and prove recursive local imports are pure.
   Defer the envelope move until this ENTIRE closure is extracted and verified.
   Preserve gate behavior and caller compatibility; then
   evidence/envelope imports only those pure core modules, never workflow or CLI. Update packaged
   resource resolution using `importlib.resources`, including the always-closed
   gate fixture; test missing/drifted package resources still block.
5. Move workflow glue explicitly: secondary_probe_action to workflow/secondary_probe
   and human_parent_gate to workflow/release_gate, updating read-only workflow
   script paths and imports in a separately independently reviewed path-only PR.
   workflow/secondary_probe may import client/probe for bounded read-only
   collection; this is composition toward a network adapter, never core -> client.
   Keep its temporary compatibility import until client/probe moves in stage7.
   Move parent_runner and parent_consumption into workflow in this same stage:
   runner imports require_production_release from release_gate; consumption imports
   evidence/envelope.review. These are composition, not pure core. Do not move
   these implicitly with CLI. PROOFS extraction precedes this stage.
   client/closed_parent also imports the always-closed release gate; client may
   depend on workflow/release_gate only for this fail-closed boundary, never the
   reverse. Preserve the gate check before network work.
6. Move presentation and CLI adapters, retaining all argument/error/exit and
   offline side-effect guards. Test execution from a non-repository directory.
7. Move client modules intact. Update Docker COPY/install, entrypoint paths,
   baked-source equivalence and read-only workflow paths in the same PR.
   Workflow changes are path-only and require explicit independent review.
8. Remove obsolete root facades; retain or deliberately migrate the intentional
   geni_offline package only with its #93 tests and purpose preserved, only after a repository-wide
   consumer scan is empty. Update README architecture and supported commands.

Steps may be split further. Every PR has its issue reference, docs, signed
small commits, exact-head independent PASS and green CI. No parallel worker
moves the same module or changes a branch while its exact-head review runs.
Coordinate with active creation work before touching its imports; integrate its
behavior first rather than overwrite it with an older file.

## Acceptance checklist for every move

- Full Python 3.11/3.12/3.13 suites and lint remain green; all Node/runtime
  suites still run with the same meaning. New import smoke tests are additive.
- Keep behavior fixtures and mutation cases independent and unchanged in
  meaning. A test path update cannot turn a mutation test into a skipped test.
  Source/AST/digest guards point to the real implementation, not a facade.
- Coverage still measures the same production logic. Update the two current
  production paths in `.github/coverage_report.py` and CI include filters in
  one reviewed PR when those implementations move; preserve floor/denominator
  semantics and reject unexpected/missing files. Never count wrappers instead.
- Docker image carries only reviewed tool code and packaged resources. Runtime
  data repository remains data only. Verify baked implementation bytes and
  entrypoint behavior after path updates, without publishing/deploying by merge.
- `__file__` resource lookups, `python script.py`, `python -m`, test imports,
  subprocess invocations and `.github` helper paths are all explicitly mapped.
  Keep isolation flags and no-network/credential guards; do not drop `-I` to
  make an import work.
- No secret, workflow permission, environment, OIDC, production gate setting or
  release policy changes. Public summaries remain value-free. No live Geni run.
- Inventory root names, Docker paths, entrypoints, coverage paths and test count
  before and after. Any lost check or unexplained output change blocks merge.

## Rollback and boundaries

Each migration PR is independently revertible with ordinary signed Git changes.
Do not force-push/rewrite consumed intent or deployed evidence history. Package
layout is not an authority boundary by itself; the current offline models and
closed transport remain offline/closed after moving. Real profile creation
requires the separate implementation, approval, deployment and human-run work.

## Current pin and source identity constraints (#455)

The first implementation slice adds explicit setuptools package discovery for
`src/geni_uploader` plus the intentionally separate `geni_offline` package. Do
not replace or accidentally omit the latter. No runtime install/path change is
made by the design. Prove wheel import outside checkout with isolated Python;
no `.pth` injection, data-repo search path or `sys.path` workaround in production.

Move `people_core.py` first only after packaging is independently green. It has
no sibling imports, but contains SQLite/journal behavior and must be moved intact,
not labeled a trivial data module. A temporary root compatibility alias must
preserve module object/class identity and monkeypatch propagation in both import
orders. Source/AST guards must inspect the authoritative package implementation,
not the facade. If an isolated script caller cannot import the installed package,
stop rather than dropping `-I` or importing untrusted checkout code.

Current callers also include `father_executor_composition`,
`father_release_package`, `protected_father_job` and
`single_human_approval_record`. Keep their release/transport/evidence graph intact;
no extraction that reclassifies a composing network boundary as pure core.
`father_release_package` uses local imports and filesystem/source inventory, so
its dependency map must include function-local imports and file path strings.

The closed Worker builder, fixed expected-module inventory and literal synthetic
benchmark module/bundle/record hashes are source identity contracts. Keep the
Node package intact in this Python migration. Python parity harness module paths,
Node subprocess cwd, package lock and source SHA pins must still execute. Any
later Node move needs a separate reviewed inventory/hash update, not an automatic
search-and-replace or regenerated expected output.

`tools/image_provenance.py` checks Docker COPY paths, image descriptor files and
engine revision. The existing image must not be declared compatible merely
because a root facade exists. A client/presentation move changes the baked import
closure and needs explicit Docker/path/descriptor tests, followed by a separately
approved image build/pin. Coverage filters and per-file floor still measure real
implementations, not compatibility facades. No workflow trigger, permission,
actor, environment or secret change is permitted as part of path updates.

No package move is bundled with #453 OAuth custody. Finish/rebase active root
module PRs before moving their source. Every implementation slice is independently
reviewed at its exact green head; docs approval alone is not blanket move review.

## Current local import graph (AST inventory)

Generated from root modules using Python ast Import/ImportFrom (including local
function imports). External imports omitted. This is an inventory of CURRENT
filenames, not a claim that destinations already exist. Repeat at each move.

```text
approval_record -> people_core
ciphertext_evidence -> people_core
father_executor_composition -> human_parent_gate, parent_adapter_contract, people_core, profile_result
father_release_package -> (no local project imports; filesystem inventory requires review)
protected_father_job -> github_review_evidence, people_core, single_human_approval_record
single_human_approval_record -> approval_record, people_core
father_once_simulation -> parent_adapter_contract, parent_intent_model, people_core
geni_upload -> plan_report, visual_plan
github_review_evidence -> people_core
human_parent_gate -> people_core
parent_adapter_contract -> people_core
parent_consumption -> parent_envelope, people_core
parent_envelope -> human_parent_gate, parent_plan, people_core
parent_evidence -> people_core
parent_http_candidate -> human_parent_gate, parent_adapter_contract, parent_intent_model, people_core
parent_intent_model -> people_core
parent_output -> parent_probe, parent_snapshot, people_core
parent_plan -> human_parent_gate, parent_probe, parent_runner, people_core
parent_probe -> people_core
parent_runner -> human_parent_gate, people_core
parent_snapshot -> people_core
people_core -> (no local imports)
plan_report -> (no local imports)
profile_outcome_model -> parent_intent_model, people_core
profile_result -> parent_intent_model, people_core
secondary_probe_action -> parent_probe, people_core
source_details -> geni_upload, plan_report
visual_plan -> (no local imports)
workflow_content_contract -> people_core
```
