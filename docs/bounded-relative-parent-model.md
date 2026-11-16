# Bounded relative-parent pure model

Refs #758. First implementation slice of the accepted relative-parent design.
The module is effect-injected only: no credential, HTTP adapter, workflow,
command-line dispatch or release is supplied. Existing executors are unchanged.

The closed plan pins owner, anchor, up to five path profiles/four distinct union
hops, complete expected family graphs, context boundary edges and explicit union
members. Each hop is independently pinned at both endpoint family baselines and
read back through the union. Exact profile fields include boolean life status,
privacy and claimed state; public/claimed context profiles are read only. The
new parent's source life status must be known, privacy must be false and its
served claimed state must be false. No dates, invitations, photos or merges.

One create follows a fresh anchor check, encrypted-before seam and permanent
consume. Marker identity reuses the old owner/anchor/entry semantics. ACK is
saved before interpretation, then profile, complete anchor graph, reciprocal
new-parent graph and direct union membership must pass. Changed graph, unknown
critical field, invalid ACK or uncertain send stops. No retry/reset/repair.
The request budget is the exact planned read inventory plus one POST.

Synthetic offline tests cover spouse and multihop anchors, first/second parent,
status/privacy/claimed changes, missing path evidence, consume/storage failures,
wrong union, saved malformed ACK and no repeated send. They do not prove vendor
compatibility, hidden duplicate absence or consent. Package review must still
reconcile stable keys with earlier consumed operations.

Protected wiring, immutable private source admission, canonical-hash replay,
real transport guards, effective deployment protection and exact-run approval
remain separate work. This slice cannot create a live runnable package.
