# Dormant SQLite issuance reservation (#404, #405)

Isolated storage component only, no public route, authenticated caller or deployed
namespace. A future reviewed wrapper must verify distinct issuer workload,
original public approval, deployment-owned pins and actual canonical owner binding
before invoking it. Caller-supplied pins alone do not establish authority.

Reserve atomically rejects any existing owner-global permanent slot, stores exact
operation/public run/namespace/issuer repository/run/source/workflow pins and an
opaque digest. New plan/run/key cannot reuse the occupied storage. Inspection
checks the exact record and returns bounded value-free status/digest, no write.
No expiry, delete, reset, vendor access or retry operation exists. Response loss
can mean committed/spent; read-only inspection cannot resume issuance.

Tests include real SQLite concurrency/restart plus valid-but-different pins,
unknown fields, storage failure and committed response loss. This module is not
yet wired to the private issuer, which must not treat the older private Git ref
as authoritative. No code or namespace is deployed by this PR. Revocation must
preserve all permanent slots. Cloudflare admins can delete namespaces: no claim
of tamper-proof state against provider/account administrators. Actual identity
pinning and credential restrictions remain required before an approved release.

## Value-free boundaries and remaining wrapper work (#408)

Exported reserve and inspect await all validation and storage work inside a fixed
error boundary. No raw storage error, cause, value or provider diagnostic escapes.
A rejection does not prove rollback: a lost response may follow commit. There is
no internal retry, and read-only inspection never authorizes another issuance.
Tests cover synchronous throw, rejected transaction, get/put failure, committed
response loss, validation proxies and inspection's no-write behavior. Real SQLite
tests reject changed plan and issuer/namespace pins after a persisted reservation
and verify the original receipt survives another restart.

No authenticated wrapper is implemented here. Before wiring these exports, the
wrapper must verify the actual installed namespace and distinct issuer against
independent provider readback plus complete approval/source evidence. Merely
matching env namespace strings or caller-provided pins is not that verification.
The separate Worker design (#407) must replace legacy GitHub issuer identity
fields through a reviewed versioned schema before integration. Until then no
route/caller is installed and the release gate remains closed.
