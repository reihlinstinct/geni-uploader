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
