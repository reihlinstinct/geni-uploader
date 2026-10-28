# Single-attempt father seam, synthetic only

Part of #232. This is NOT a live adapter or execution permission. It accepts only
exact-type in-memory transport/store. No URL, token, callback, HTTP client,
production entry, workflow or backend route is supplied. Default gates stay
closed. The fixed ZZ-secondary fixture label is not a real connection identity
or authentication proof. No production connection can use this prototype.

The seam reuses parent_adapter_contract.describe and classify_create from #226,
not a second response parser. It adds exact father gender, exact synthetic
secondary connection label and approved payload-hash comparison before any
intent. Every call copies inputs. It validates and consumes an owner-scoped
in-memory intent before the sole transport invocation. An acknowledged response
is explicitly NOT verified. Readback, Geni URL and source provenance are future
separately reviewed work, including #244.

The store wraps pure parent_intent_model states in a synthetic owner-global lock.
It is volatile and does not provide durable intent or shared cross-run exclusion.
No Durable Object candidate integration or authentication/encryption is supplied.
Fake event hashes identify synthetic events, not encrypted stored evidence.
Neither unsigned binding hashes nor caller state establish authority.

A post-intent error, malformed acknowledgment or known-ID rejection yields
uncertain, never retries or clears intent. If uncertainty cannot be persisted,
return uncertain_storage_unverified and keep consumed state. Failed consume
propagates and sends nothing. Process death may bypass any error handler, so the
future backend must independently persist permanent consumption before sending;
this simulation cannot guarantee that. No reset, refresh, delete, rollback or
merge behavior exists. Repeating a changed plan/connection for the same owner
cannot produce another post on a shared synthetic store. Replacing the store
would evade this test boundary, another reason this is not production protection.

Tests cover ordering, exact request descriptor, before-intent payload/account
rejection, one-winner concurrent proposals, malformed/owner-ID acknowledgment,
post-intent storage failure and no replay. External tests can build on this seam
after review; no real vendor behavior or global durability is claimed.
