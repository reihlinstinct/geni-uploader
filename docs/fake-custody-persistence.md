# Fake-only credential persistence composition (#482)

Local orchestration of the scoped custody content policy and credential-only
SQLite CAS. Not imported by the OAuth callback, writer, runner or released gate.
No public route, real credential, network default, deployment or write permission.
The fixed constructor shim now uses the merged #475 environment-secret adapter
with injected fake fetch/seal/timers, never a live credential or network default.

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

Twenty-one synthetic tests cover pending-before-write ordering, response loss,
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
- Authenticated callback ownership, exact provisioning/readback,
  environment-secret scope and consumer integration
  remain required. No live callback or gate is made reachable by these tests.

## Actual adapter composition

`createFakeEnvironmentCredentialPersistence` accepts only constructor policy,
context and a single secondary registry entry. The policy destination and
registry owner/repository ID/environment/secret must match before storage.
The adapter captures and freezes the registry. Invocation cannot select a slot.
The shim checks the exact five-field result, confirmed stored status, secondary
slot, false authority flags and exact bundle digest before forwarding the
acknowledgement to the pending CAS orchestrator. Failure never activates state.

Fake fetch/seal integration tests check complete bundle sealing, exact GET/PUT
paths, constructor snapshot, response loss, non-success status, expiry and
revocation during the actual adapter await. No real API or secret is used.
