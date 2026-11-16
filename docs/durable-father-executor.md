# Durable ledger and dormant one-POST acknowledgment/readback

Issue #334. This is an unreleased executor, not a production route or a switch.
`requireFatherRelease()` unconditionally throws before storage or network. No
environment flag can bypass it. The test bundler replaces only that imported
module in its local test bundle; the shipped module remains closed. No live
Geni call, permission, configuration, credential or deployment is installed.

The executor composes the existing permanent owner intent transaction with an
atomic durable evidence ledger. It derives cumulative bytes from stored objects,
not a caller's total, rejects duplicate ciphertext hashes and wrong operation/
run/recipient, and caps each object at one MiB and the operation at eight MiB.
Consumption survives ledger failure. The ledger accounts descriptors already
validated by the future authenticated entrypoint; a caller descriptor alone is
not remote persistence proof. Binding the validated pre-write receipt and
post-write ciphertext writer to this executor remains required before release.

After the unconditional release gate and exact payload checks, consume is
permanent before the only fixed `profile-ID/add-parent` POST. The response parser
accepts a bounded full added profile rather than the former exact `{id}` fixture.
Returned ID is journaled immediately. A response loss never retries. Fixed GETs
then read that ID, the owner's immediate family and the observed parent union.
Exact private/living/gender/main and locale names, child/father IDs, one parent
union and no extra partner/child are required. No returned URL is followed.
Unexpected blank/extra partners stop without repair.

Even consistent readback ends `consumed_readback_consistent_evidence_pending`,
not VERIFIED: encrypted acknowledgment/readback persistence is not joined yet.
Failure ends consumed/uncertain, preserving a known returned ID when possible.
A journal write failure can leave consumption without a saved ID, so read-only
reconciliation remains necessary. A vendor profile URL/result is deliberately
not fabricated from the API ID. No automatic rollback, delete, refresh or reset.

Real local workerd SQLite tests drive concurrent attempts through the actual
ledger, one mocked POST, full-profile acknowledgment and fixed readbacks, then
restart with the same storage and prove no second POST. Four vendor response-loss
boundaries leave consumed/uncertain state; accounting duplicate and total-cap
checks run against durable storage. The shipped gate separately rejects before
any state/network. The runtime invokes these suites through the corrected
isolated child runner.

Remaining operational joins: authenticated service-owned preflight/approval to
this gated executor, remote-evidence-derived durable accounting, encrypted
post-write job/service handoff and immutable receipt readback, complete result
storage, exact released artifact/config/namespace/credential provenance, actual
OIDC emitted-token check, and separate release/deployment/exact-run approval.
The existing local service only consumes; it does not call this dormant executor.

Official contracts inspected:
- https://www.geni.com/platform/developer/help/api?path=profile/add-parent
- https://www.geni.com/platform/developer/help/api?path=profile
- https://www.geni.com/platform/developer/help/api?path=profile/immediate-family
- https://www.geni.com/platform/developer/help/api?path=union
