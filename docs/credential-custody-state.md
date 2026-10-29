# Dormant credential generation state (#478)

Credential-only transaction primitive, not a public route or authenticated
custody service. It stores no token. Every method uses one fixed storage key,
separate from permanent issuance/grant/intent slots. Deployment must supply a
dedicated credential namespace and authenticate fixed owner/slot and callers;
this primitive cannot prove binding identity or monotonic historical truth.

Begin uses expected generation/epoch compare-and-set, increments generation and
marks it pending BEFORE a separate remote secret write. Pending means revoked
for policy consumption. Acknowledge activates only an exact generation/epoch/
connection/bundle digest. Concurrent reservation loses. A pending or revoked
record is never silently reused or deleted. Rotation requires a new connection
and makes the old bundle unavailable immediately. This module does not refresh,
write or delete a remote secret, or perform automatic retry/recovery.

Revoke changes pending/active state to revoked and increments epoch immediately;
a late remote write cannot commit under the previous epoch. Old bundle copies
therefore fail a fresh state check. Local revocation does not prove provider app
revocation, remote-secret deletion or historical erasure. All those need their
own supported route/readback/authority. Never erase permanent execution barriers.

Transactions are a dependency seam, not an authenticated namespace attestation.
A failed/ambiguous remote write remains pending/unavailable. A future orchestration
must preserve exclusive attempt receipts and hold for inspection, not retry the
remote side effect because this primitive exposes an exact acknowledgement.
Rollback of the whole namespace or malicious admin remains outside this content
primitive. Missing/corrupt records block reads; no reset/delete method exists.

8synthetic transaction tests exercise concurrent CAS, revoke-during-persistence,
late acknowledgement, rotation, wrong owner/hash/schema, corruption, transaction
rollback/error redaction and untouched issuer/grant/intent keys. Not imported by
worker, runner or writer. No token, settings, account mutation or deployment.
