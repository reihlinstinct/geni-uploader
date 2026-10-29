# Envelope and local consumption layout (#467)

Moves envelope content review to evidence/envelope after its pure dependency
closure was extracted. Local synthetic ledger composition moves to
workflow/consumption, not core. Canonical imports and temporary same-object
aliases preserve existing callers. No ledger/state/approval behavior changes.
Both remain offline, content consistency is not source authentication or grant.

Exact source hashes permit only the one mapped envelope dependency path.
Existing ledger/envelope mutation fixtures remain unchanged. Added identity
checks, explicit installed workflow package and wheel inventory/isolated imports.
Pure dependency-direction guard follows actual envelope source, not its facade.
No executable GitHub workflow, CLI, gate resource, Docker, live or deploy change.
