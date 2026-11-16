# Pure parent-pair batch model

Refs #768 and design #766. This module has only effect-injected seams: no HTTP,
credential construction, workflow, environment or live deployment. Old models
and protected runners are unchanged. No source package or run is released.

The validated immutable plan contains one through four explicit anchor groups,
exactly two opposite-gender parent entries per group and at most one dependent
sibling. Unknown life status, public new payloads, duplicate names/keys/anchors,
conflicting existing profiles/path graphs and budgets outside the hard 200-request
ceiling are rejected. Existing context status and claimed/privacy values are
pinned. Existing omitted merge and new-profile omitted merge have separate exact
boolean policies. Positive or malformed merge state always stops. Any allowance
for new-profile omission needs separate owner approval before a future live run.

Initial preflight covers every group before the first send. Each group then
revalidates its profiles, path families and path unions before effects. Each
operation has one fresh anchor-family check, one POST and four proof GETs:
new profile, full anchor family, reciprocal created family and direct parent union.
Thus the exact complete-run inventory is the sum, over groups, of twice the
profile/path/path-union read count plus six per creation. Repeated GETs count.
The model stops before an over-budget seam call. A later adapter must independently
enforce the inventory, start spacing, transport bounds, expiry and reviewed job
runtime; this model's number is not a live budget grant.

A parent's stable marker is byte-compatible with the old parent model. Sibling
markers are stable before parent/union IDs exist; an overlapping earlier sibling
operation requires external reconciliation before admission. It is not safe to
reuse this new namespace as a reset for an old spent operation. Package admission
and protected source cross-pins for that overlap check are a later release gate.

Encrypted receipt seams precede consume/send; ACK is saved before ID validation.
Consumption survives every failure. Each next send follows exact private/unclaimed
profile, reciprocal/full graph and direct union proof. The new union is derived
only from the first validated parent result and remains fixed for the second
parent and sibling. Derived child-role boundary updates propagate into later
explicit context graphs, without adding route permission. Earlier verified items
remain created if a later group stops. No retry, resume, repair or rollback exists.

The model validates sequential proof before it calls the next write seam. A future
transport must separately keep its next-send latch shut until independently
rechecking those same saved proofs. A pure-model pass cannot release that latch
or stand in for protected adapter tests, exact-source replay or user approval.
