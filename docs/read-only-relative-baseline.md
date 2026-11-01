# Read-only relative baseline

Refs #629. This separate entrypoint captures an exact approved owner/anchor graph before preparing a parent package. It does not create profiles, traverse discovered relatives, change credentials, consume intents, write receipts remotely, dispatch a run or authorize a later upload. Existing execution and diagnostic runners are unchanged.

The private plan pins expected profile fields, an exact bounded family graph and explicit external edges to omitted unions. Those edges are checked for equality, not followed. Owner identity, reciprocal edges and direct union memberships must match. A verified baseline is evidence at its capture time, not proof of duplicate absence or permission to create. Unknown shapes stop.

A private config pins source repository/commit/path, canonical decoded-plan SHA256, owner, anchor, expected name, encryption recipient and expiry. Raw config SHA256 and executor SHA must match dispatch inputs; protected environment approval remains required. No secret or live package is provisioned by this change.

The workflow runs only on master, exact reviewed executor SHA, first attempt, fixed actor and explicit READ_ONLY_RELATIVE_BASELINE confirmation. It uses the existing protected environment and separately named private config. A missing or invalid config stops. GitHub reads are limited to private repository metadata and the exact source file; vendor reads are fixed profile/family/union routes, at most 16 admitted routes, 15 seconds apart, once per route, with expiry rechecked after waiting. No retry, writes or automatic repair.

Each bounded parsed response is encrypted to a new local evidence file before validation. A storage failure stops; already encrypted evidence is retained by the workflow. Output and logs stay fixed/value-free. No real names, IDs or data belong in this public repository. Tests use invented fixtures and injected I/O only.

## Environment contract

- BASELINE_CONFIG_JSON: exact private config from the separately named protected workflow secret. Never print it.
- BASELINE_CONFIG_SHA256: SHA256 of the raw UTF-8 config bytes approved for this run.
- BASELINE_CONFIRM: must equal READ_ONLY_RELATIVE_BASELINE.
- BASELINE_EXECUTOR_SHA: reviewed executor commit matching GITHUB_SHA.
- BASELINE_OUTPUT_DIR: fresh absolute local directory for encrypted evidence, never an existing path.
- BASELINE_TREE_PAT: protected private-repository credential, used only for the two exact GitHub GET routes. No writes are admitted by this entrypoint.
- GENI_SECONDARY_ACCESS_TOKEN: existing protected vendor credential; token-self must match the pinned owner. This change does not assert the token is read-scoped; the transport is GET-only.

The standard GITHUB_RUN_ATTEMPT, GITHUB_EVENT_NAME, GITHUB_REPOSITORY, GITHUB_REF, GITHUB_ACTOR, GITHUB_TRIGGERING_ACTOR, GITHUB_SHA and GITHUB_RUN_ID values bind the protected first-attempt run and encrypted evidence.

## Stopped-read diagnostics

A stopped read preserves failure_code as a fixed transport enum or validation_or_storage. Transport failures retain only bounded HTTP status, allowlisted structural enums, booleans and numeric counters in http_failure, encrypted with the rest of the evidence. No raw error text, exception strings, headers, URLs, credential values or arbitrary evidence fields are copied. A first-read failure can have an empty responses list while retaining these diagnostics. This does not prove token validity; an authentication error needs separate interpretation. No retry, credential refresh or follow-up read is added.
