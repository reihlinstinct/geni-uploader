# One-parent addition model (#578)

This module is a non-runnable, effect-injected model. It has no credential,
transport, workflow, dispatch or command-line entry point. Existing parent and
sibling executors are unchanged. A later protected wiring change must be reviewed
separately; neither this model nor a passing test grants execution authority.

## One new parent, one existing child anchor

The authenticated owner and target anchor are separate pinned profiles. The
anchor must be an existing parent of the owner in the expected family graph.
The proposal contains complete expected profile payloads and a bounded graph
of one existing owner-family union and optionally one existing parent union.
A first-parent operation requires no observed parent union; absence in a private
graph never proves no hidden parent or duplicate exists. A second-parent
operation pins the already-created other parent and parent union exactly.

Preflight checks owner identity, each expected profile's payload/privacy/merge
state and the exact anchor family graph before creating any receipt or consume
marker. The graph check requires exact node membership, canonical URLs, reciprocal
partner/child edges and no extra unions, relatives, adoption or foster fields.
Names are not used to infer identity. An omitted or private relative is a risk,
not a fact silently filled in.

A stable marker binds owner, anchor, entry key and original payload. It does not
include a new expiry or union-discovery namespace. Consume happens before the one
possible add-parent call. An uncertain result remains consumed. There is no
retry, marker reset, deletion, merge, repair or rollback capability in this core.
The save seam must encrypt and retain every response before validation or further
effects. Receipt or save failure stops progress.

After acknowledgment, verify the new profile, the full anchor graph and the new
parent's reciprocal family graph. For a first parent, extract exactly one new
syntactically valid union from a bounded graph, then validate the complete graph
before allowing a read of that union. For a second parent, the existing pinned
union cannot change. A direct union read must confirm the exact partners and
child. Additional children or spouses stop the model, rather than being ignored.
Only then can the item be marked verified and its final encrypted receipt saved.

## Living, deceased and genuinely unknown

New-parent life status is explicitly true, false or null. Null is local UNKNOWN,
not a claim the person is alive or deceased. The vendor payload omits is_alive
for UNKNOWN and always requests public=false. Readback verifies the supplied
fields and privacy but does not promote a vendor-default life status into a
source-confirmed fact. The item retains source_life_status=null. The later
protected implementation and approval must disclose this limitation before live
use; no behavior of the vendor when this field is omitted has been proved here.
Known existing profiles still require explicit boolean life status and private
visibility. An existing profile without multilingual names is pinned by its
closed scalar snapshot; it is never rewritten to invent a names dictionary.
Unknown surnames/dates are omitted, never invented. A future new parent cannot
be reused as a known anchor payload without an explicit reviewed treatment of
its source and observed status.

## Future protected wiring requirements, not implemented

Keep one POST per fresh approval/run, exact owner/anchor/source/config/executor
pins, a human environment gate, 15-second request-start pacing, expiry rechecked
after waits, mandatory encrypted diagnostics and bounded fixed-host routes.
No route may come from unvalidated response content. Only one validated new
parent union may be added to the read allowlist; redirects and retries remain
forbidden. A true dry replay must exercise the executor's own immutable-source
base64/decode/canonical-hash path offline and stop before vendor construction.

The fixture uses invented ZZ names and synthetic profile IDs only. Tests cover
first/second parent, known living/deceased and unknown, exact graph corruptions,
profile mismatch, permanent consumption, expiry, storage and uncertain sends.
