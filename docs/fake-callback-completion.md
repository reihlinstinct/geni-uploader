# Offline callback completion through credential custody (#501)

Fake-only end-to-end rehearsal, not a registered callback or authenticated
production service. The live worker is unchanged. Constructor fixes secondary
owner/destination/run/source policy, browser/state/subject/connection pins and
expected generation/epoch. Input contains only those matching callback pins and
a synthetic ZZ code, never a destination, owner, URL or run selector.

The completion consumes a one-time synthetic state record transactionally before
any exchange. Consumption is preserved after response loss or failure. It then
calls one fixed fake OAuth endpoint and one fixed fake owner endpoint. Owner must
match the pinned profile, with explicit no-merge fields. Provider token shapes
are exact and ZZ synthetic only. Expiry is bounded by provider lifetime, local
policy and approval expiry. Issue time is sampled before exchange so network
waiting never extends the provider lifetime.

The complete canonical bundle goes through the actual merged environment-secret
adapter and guarded pending/commit orchestration. It seals one complete bundle,
never a raw-token compatibility secret. Pending precedes the fake remote write.
Uncertain write, expiry or concurrent revoke cannot activate the generation.
No automatic retry, fallback, dispatch, Geni write or state/namespace reset exists.
One completion object has one attempt; independent objects still share consumed
state and CAS barriers.

The result is only fake_connected_candidate_not_authority or fake_callback_blocked,
with authenticated:false and write_permitted:false. No token, owner, raw response
or exception value is returned or logged. The fake endpoint strings are fixed
.invalid origins. All transport/seal/timer dependencies are explicit injections,
without credential or network defaults. Provider reads are bounded streams with
ten-second deadlines, no redirects and no retries.

## What this does not establish

State storage, subject/browser binding and fake fetch are rehearsal seams, not
proof of principal identity, browser login, provider origin or owner authority.
No claimed upstream verified:true can grant permission here. Dedicated real
credential/state namespaces, caller authentication, registered callback, secret
writer scope, installed source/config/log controls and account capacity remain
required. The local SQLite test uses distinct prefixed stores in one synthetic
object only for rehearsal; this is not a production namespace layout.

Connected-candidate does not mean a live connection or a write grant. A revoke
can follow activation before the status reaches its caller. Final status failure
can coexist with a previously activated generation if the clock expires after
commit; consumers must independently enforce live expiry/revocation before use.
No consumer or atomic revocation-to-vendor-use boundary is changed by this PR.
No provider revocation, remote secret deletion or historical erasure is claimed.

25 tests cover actual adapter/seal trace, one-time state, duplicate callbacks,
wrong owner/merge, stale state/browser/subject/code, malformed/oversized responses,
response loss, deadline, expiry and concurrent revoke. A real local workerd SQLite
rehearsal preserves consumed state and inactive custody across restart; its exact
import inventory is checked and outbound network denied. Existing suites remain.
No real OAuth, credential, callback registration, settings, deployment, publication
or tree action is performed or authorized.

## Review hardening (#506)

Rejected or late provider responses are cancelled unread, including status,
redirect and link-header failures. Late response and late body-read regressions
check that timed-out work cannot reach owner lookup, parsing or custody. The
response byte cap is 49,152, consistent with both maximum accepted synthetic
16,383-byte tokens plus canonical JSON fields. An oversized body still fails
without retry after state consumption. A maximum-token regression persists the
whole bundle through the actual adapter.

Exact synthetic exchange/profile request shapes are asserted in tests. This is
not live exchange parity: the fake request deliberately omits real client_id,
client_secret and redirect_uri, and uses .invalid endpoints and a synthetic ZZ
code. Those real provider/callback/client-auth contracts need separate grounded
implementation and review before live integration. Nothing here claims provider
consent or authenticates a principal.

A same-object attempt regression first rejects wrong input without consuming the
stored state, then proves the object cannot retry valid input. A fresh object can
still consume that untouched state, making the object guard distinct from the
durable consumed-state barrier. No reset route is added.

Additional #506 coverage asserts streaming byte-cap enforcement stops reading at the first over-limit chunk, cancels/releases the reader and never reaches owner lookup or custody. Removing the read-loop cap must fail the regression. Offline only.
