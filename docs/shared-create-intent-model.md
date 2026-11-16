# Shared create-intent semantics, offline model

Part of #233. Status: pure model only. It has no durable backend, network client,
credentials, encryption, POST, executor hook or permission to run. Both release
gates stay closed. A Python dictionary, content hash or synthetic lock is not
shared durability or authenticated authority.

## Proposed state machine

One permanent namespace per exact canonical owner, across every connection and
plan variant, starts empty (version 0). A future trusted backend atomically
commits consumed (version 1) with exact owner/connection/operation/plan/payload/
artifact/policy bindings. Atomic compare-and-set must check owner-global absence,
not just a caller-selected plan or connection key. The pure `consume` function
only proposes data; it neither checks a store nor permits sending.

Transitions:

- consumed -> acknowledged (version 2): canonical created ID plus first encrypted
  evidence descriptor, after the single POST acknowledgment.
- consumed -> uncertain (version 2): transport/crash uncertainty, no known ID.
- acknowledged -> verified (version 3): encrypted verified readback descriptor.
- acknowledged -> uncertain (version 3): preserve known created ID, failed check.
- uncertain -> verified (version 3 or 4): separately authorized GET-only
  reconciliation identifies the exact result. A known ID cannot change.
- verified is terminal. No transition releases, resets or retries a creation.

An ID equal to owner is invalid. No timeout, receipt expiry, new plan ID, changed
payload, connection label or fresh runner clears consumption. Missing backend
response means stop and inspect, never infer no intent. A crash after consumption
but before send can require manual diagnosis and still cannot permit replay.
Only trusted backend atomic success, under approved authority, can eventually
permit the one fixed POST; this model returns no execution permit.

## Ciphertext and authority limits

Evidence descriptors are opaque lowercase SHA256 values of ciphertext, never
caller URLs, plaintext, profile names or private graph data. This syntax check
does not prove encryption or object existence. The eventual backend must verify
durable ciphertext retention, encryption recipient binding, storage provenance,
authenticated operator and immutable approved run binding. Hashes identify
content; they do not authenticate it. No credentials or private evidence in the
public ledger. Even owner IDs and bindings must be private in production.

The model has no public error-value echo, reset API, mutable state reference or
clock. Input objects are copied. Semantic validation rejects extra fields,
noncanonical IDs, changed binding hashes, noninteger versions, invalid phase
shapes, repeated evidence descriptors and stale expected versions. It cannot
detect an attacker recomputing hashes or forging a valid-looking entire state;
authentication and write authority belong to the approved backend.

## Still release-blocking

Select and approve a backend with atomic owner-scoped CAS, authenticated narrowly
scoped callers, verified encrypted object storage and one-way audit history.
Test real cross-process/cross-run concurrency, durable restart/crash recovery,
timeouts/unknown acknowledgments, unauthorized updates, service rollback/restore,
retention and administrative trust limits. Never claim a mock or local SQLite
proves those properties. Backend/service creation and deployment need separate
approval. No new remote service is created here.

Synthetic concurrent fake-backend tests demonstrate the desired namespace
contract only. Failure paths must retain consumed state even when acknowledgment,
encryption or report upload fails. Future network/runtime work is separately
reviewed; it cannot treat this module as an authenticated production gate.
