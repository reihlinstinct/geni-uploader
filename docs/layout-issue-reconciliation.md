# Root-layout issue reconciliation (#602 / #291 / #704)

Audit base: master db610bf. This is a documentation-only acceptance map, not
permission to resume frozen migrations or declare all historical work complete.

## Facts from the current tracked tree

`git ls-files '*.py'` has zero top-level Python files. The current layout test
explicitly asserts that result. The active checker is
`tools/check_repo_layout.py`; implementations live under `src/geni_uploader/`,
with the separate `geni_offline` package retained. README references the packaged
client path. These facts supersede historical root-file counts, not historical
release or content-identity evidence.

The root-file tables and 'current' AST inventory in `docs/src-layout-plan.md`
are historical planning snapshots. Some proposed destinations differ from final
ones: for example source_details is in client, not cli; plan_report is in
presentation, not the earlier proposed cli path. Do not use that inventory as a
current allowlist or automatically regenerate protected hashes from it.

## Issue ownership and closure bar

| Issue | Distinct purpose | Evidence still needed before closure |
|---|---|---|
| #291 | Original responsibility-based package migration | Installed-wheel imports outside checkout, package resources and behavior/coverage evidence for final tree |
| #602 | Root entry-point inventory and staged retirement | Final consumer audit, documentation/man reconciliation and explicit facade retirement record |
| #704 | Path-reference guard, workflow/import smoke, remaining root cleanup | Guard scope/completeness audit, final offline container build/smoke and README/architecture acceptance |

Zero root files is a useful fact, not proof that workflow, Docker, exact content
pins, code ownership, package resources or downstream callers are correct. None
of these issues closes automatically from this document. Keep the original
freeze on protected create-package runners and adapters in force; reconciliation
does not restart or reauthorize them.

## One acceptance ledger, no duplicate migration

A future reviewed docs/test PR should record a single final-tree ledger rather
than create three competing move plans. For each consumer category include the
tracked path, current invocation/import, exact test or build receipt, and status:

- workflows and helper scripts, including isolated interpreter invocations;
- Docker COPY/entrypoint and installed `/opt` paths, distinct from repository paths;
- package entry points, resources and clean-wheel imports without checkout access;
- docs/man links and examples, coverage floors and authoritative AST targets;
- CODEOWNERS, protected source inventories and release/evidence identity contracts;
- known external consumers and any unsupported legacy entry points.

The ledger must mark unproven categories pending, not presume an old green PR
covers the current final tree. Existing published image identity is a separate
fact from current source layout. No release, repin, hash relaxation, environment
change or package replay follows from cleanup.

## Small follow-up sequence

1. Mark historical inventories clearly and add the current consumer ledger.
2. Run existing path-reference and workflow smoke guards; test their failures
   with missing-target and wrong-import-path mutants against real tracked inputs.
3. Collect a fresh offline container build/smoke and installed-wheel receipt.
4. Independent exact-head acceptance review decides which issue bars are met;
   close only the proven scopes with links, leaving distinct release gates open.

Do not schedule steps touching held lanes solely because this design merges.
Each implementation slice needs scope review, green CI and normal signed merge.
