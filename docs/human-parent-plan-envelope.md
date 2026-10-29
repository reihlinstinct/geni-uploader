# Offline exact Plan envelope binding

parent_envelope defines a draft structural/binding contract only. It does not
sign, authenticate, collect, execute, enforce replay protection or call a
service. It is not integrated with any production create path. The shipped
production gate remains closed.

The envelope binds exact supplied canonical owner and connection, operator,
consent reference identifiers, full manifest and ordered payload hashes, graph
hash, scope-bound proof content references, immutable data/executor/image pins,
journal version, 256-bit-shaped Plan identifier, count at most two and lifetime
at most 15 minutes. Draft creation binds the proposal's owner, operator, hashes
and pins. Review compares every field against separate supplied expectations,
checks expiry and rejects a candidate differing from those supplied expectations,
even if its hash is recomputed. Each candidate's strict schema and own content
hash are checked first. The proposal is rebuilt canonically from its supplied
fields to check entry scope, payload/main-name equality and manifest consistency.
That does not verify the original manifest's source, truth or approval.

All references are untrusted input. Their shape and binding are checked, not
source truth, signature, sufficiency or current remote state. A reference hash
is not evidence of completed vendor proof. A caller can fabricate both candidate
and expected inputs and make them match. They still get no permit. Every output
says unsigned, unauthenticated, replay not enforced and creation disabled.
Consent reference syntax does not establish the owner's approval. The Plan ID
format does not prove randomness, uniqueness or one-use consumption. Repeated
offline review is deliberately allowed and grants nothing.

The API takes already supplied bounded-shape objects, no secrets, file paths or
URLs. It returns detached drafts or sanitized fixed-status summaries. Drafts
contain private metadata and must remain private. Content hashes can correlate
private data. No approval source, signing key or trusted service is created.

Trusted signing and signature verification, actual proof validation, shared
one-use Plan consumption, current graph and lock revalidation, durable intent,
fixed adapter, human-only execution surface and named release/write approvals
remain separate requirements before any production operation. An offline
envelope passing its tests does not shorten or waive those requirements.
