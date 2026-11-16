# Cloudflare issuer identity and permanent reservation v2 (#431)

Dormant storage component only. No authenticated wrapper, installed route,
namespace, key, deployment or permission. Actual Worker/script/version/bundle
and canonical namespace must be independently verified before any caller exists.
Caller-supplied/deployment-string pins alone do not establish that provenance.

V2 pins contain exact operation binding, original public run, canonical namespace
and issuer script name/version UUID/bundle SHA256/installation-audit SHA256. The
UUID shape and hashes validate content only, not actual provider existence or
issuer authority. A future reviewed installation audit supplies authenticated
fresh evidence; never invent UUIDs or infer deployed bytes from these strings.

Use the SAME permanent-issuance-attempt owner-global key as v1. Any existing
value, including v1, blocks reserve. V2 inspection accepts only exact v2 record
and pins. No migration, overwrite, TTL, reset, retry, delete or replacement owner
is supplied. A new issuer version/audit/run/plan/key does not regain permission.
No legacy GitHub issuer repository/run field is misrepresented as Worker ID.

WebCrypto hashing is computed before entering the storage transaction; only
storage reads/writes are awaited inside. Concurrent reservations have one winner
under real SQLite. Exported fixed error boundaries cover sync/rejected storage
and validation errors. A lost response may mean spent, not rollback; inspection
is read-only and cannot resume signing. Signed-grant and create-intent barriers
remain separate and permanent. Provider administrators can still replace or
delete state; no tamper-proof-against-admin claim.

Real-workerd tests use SQLite concurrency, two restarts, changed operation/
issuer/run/namespace pins, unknown-field rejection before first reservation,
legacy occupied slot refusal and fixed storage-error rejection. Bundle imports
only this pure Worker component, no Node compatibility. Synthetic fixture UUIDs
are test data, not proposed installation values. No live resource or key used.
