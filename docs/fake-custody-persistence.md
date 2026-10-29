# Fake-only credential persistence composition (#482)

Local orchestration of the scoped custody content policy and credential-only
SQLite CAS. Not imported by the OAuth callback, writer, runner or released gate.
No public route, real credential, network default, deployment or write permission.
The environment adapter interface remains subject to agreement under #475.

The constructor freezes canonical policy/context strings. Invocation takes only
the complete canonical bundle and expected generation/epoch, never a destination
selector. The policy checks owner, secondary slot, repository/environment/secret,
run/attempt, source pins, provider expiry and the maximum accepted lifetime.
A SHA-256 digest binds the exact bundle. A pending CAS reservation precedes the
single injected fake persistence call. Pending is unavailable to consumers.

The proposed fake writer acknowledgement has exactly two fields: phase
`fake_environment_bundle_persisted` and `bundle_sha256`. It contains no token.
A result with extra fields, wrong digest/phase or an exception cannot activate
the generation. This acknowledgement checks interface consistency only. It does
not authenticate a remote writer, prove installation or grant permission.

After the writer returns, freshness and the exact pending snapshot are checked
before activation. Guarded storage transactions check the clock before and after
all awaited reads/writes and before returning from the transaction. Expiry inside
a commit transaction throws, so transactional storage rolls activation back.
A concurrent revoke increments the epoch and defeats a late acknowledgement.
No automatic retry, rollback to the old token, deletion or namespace reset exists.
An ambiguous write remains pending/unavailable. Explicit recovery is not provided.

Thirteen synthetic tests cover pending-before-write ordering, response loss,
expiry, concurrent revoke, malformed acknowledgement, immutable input/config,
concurrent reconnect, transaction-time expiry and untouched permanent barriers.
A real local workerd SQLite composition checks eight competing reconnects,
expiry/revocation/response loss, persistence across restart and blocked repeats.
An import allowlist and denied outbound service make external calls fail.

## Deliberately unresolved

- The injected writer and storage seams are not proof of caller identity,
  authoritative namespace history, fixed installed destination or remote success.
- This rehearsal does not solve the revocation-to-vendor-use atomicity gap.
  Active state is credential availability, never permission to perform a write.
- A revoke can occur after activation or before a returned status reaches a
  browser. This function is not a connected-status or credential-release route.
- Provider revocation, remote-secret deletion and historical erasure are not
  claimed. Permanent issuer/grant/intent records are never erased by this code.
- Actual #475 adapter composition, authenticated callback ownership, exact
  provisioning/readback, environment-secret scope and consumer integration
  remain required. No live callback or gate is made reachable by these tests.
