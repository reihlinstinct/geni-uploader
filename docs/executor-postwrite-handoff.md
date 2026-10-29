# Authenticated executor route and encrypted post-write job handoff

Issue #336. The local service now exposes a dormant `/execute` route alongside
its consume-only rehearsal. Both require the same fixed-issuer workload JWT,
bounded immutable upload descriptors, private v2 approval/live capture, exact
pre-write readback and token-self/current graph preflight. Only afterward does
the canonical owner Durable Object receive the validated pre-write descriptor.
Payload and secondary credential come from deployment environment, not the
request. The executor's unconditional release gate still rejects before intent
or any vendor POST. No environment flag or new route releases it.

The executor returns bounded private acknowledgment/profile/family/union evidence
in its authenticated response, along with known created ID and consumed status.
It does not log those objects or declare remote evidence durable. No vendor
profile URL is invented. An interrupted response may strand evidence at the
service; consumption must remain permanent and a separate read-only recovery
path is still required. The authenticated service/runner remains a private-data
trust boundary, not an end-to-end encrypted channel to the ultimate recipient.

`persistPostWriteHandoff` runs in the protected Node job. It accepts only the
consumed/evidence-pending service-result shape, binds operation and run to fixed
readback-stage storage configuration, passes the result through actual existing
age encryption, then the private Git writer and exact remote byte readback. It
returns an opaque descriptor and a completion-pending status, not VERIFIED. No
raw result is written to a local file or printed by this function. An encryption
or Git failure throws a no-replay error; it does not send another create.

The real age test encrypts the synthetic full post-write evidence, exercises the
eleven mocked private Git requests and decrypts the remote bytes back to the
exact input. CI uses the already pinned age binary and synthetic key. The actual
service test supplies a valid authenticated approval/preflight chain to
`/execute` and proves the shipped gate leaves durable intent empty and sends no
POST. Existing test-only gate-replacement SQLite tests still prove the dormant
executor's one-POST/fault behavior. No live external mutation was executed.

Still open before operational release: one protected job runner wiring all these
steps, immutable post-write descriptor admission and durable ledger finalization
at the service, loss/recovery evidence path, authenticated release provisioning,
reviewed exact response/GET budgets, real emitted OIDC compatibility and separate
immutable release/deployment/exact-run approval. The new handoff does not mark
intent VERIFIED or remove consumed history. No production permissions, secret,
configuration or deployment changes are included.
