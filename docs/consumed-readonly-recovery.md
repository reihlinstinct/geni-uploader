# Gated read-only consumed-operation recovery (#356)

The dormant authenticated `/recover` route uses the same fixed signed workload,
plan, run and expiry, canonical owner object and existing consumed intent. The
unchanged unconditional release gate blocks before storage or vendor requests.
In test-only released rehearsal it snapshots the existing intent/ledger/receipt
and collects fixed GETs only: token-self, owner immediate family, and if a created
ID was durably acknowledged, that profile plus its observed matching union.
No arbitrary URL or request-supplied created ID is accepted.

The private result preserves partial evidence and known created ID, no retries,
no reset and no VERIFIED transition. With a lost acknowledgment, an observed new
parent is not assigned as created ID. Identity remains unresolved even if family
observations contain a plausible parent. Read success is not reconciliation of
identity, correct private fields or intended relationship. No intent/ledger state
is changed by collecting observations. Returned private evidence still needs a
separate encrypted recovery storage handoff before any durable result claim.

Three focused tests prove the shipped gate blocks before effects, and real SQLite
rehearsal both with/without acknowledged ID performs only bounded GETs and retains
identical intent across restart. Authenticated service test also proves no vendor
call under the shipped gate. Actual external calls, config, deploy and recovery
permission are not performed. Original workload expiry is not extended; later
recovery requires separately reviewed explicit recovery authority, not recycling
an expired approval. Persistent storage/recovery handoff remains open.
