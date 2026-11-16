# Parent-pair batch adapter candidate

Refs #770. Isolated adapter and immutable admission only. No `run`, main entry
point, workflow, installed secret or live release. This candidate depends on the
pure model's separately reviewed head. Existing protected runners are unchanged.

The fixed-host transport caps the package at 120 total vendor requests, including
POSTs and repeated GETs, and also enforces the model's exact inventory and config
maximum. It consumes before wait/transport, keeps 15-second start spacing, checks
expiry after waiting, never follows redirects or retries, and admits only pinned
profiles, path families/unions and validated created IDs/derived unions. POSTs
must match the source-ordered anchor, operation and exact payload.

ACK does not clear the pending latch. Cached profile, full-anchor-family,
reciprocal-created-family and direct-union proofs are independently checked. The
first parent derives one new union from the full validated graph; all later
operations must retain that union and complete existing edges. A failure leaves
the latch shut. The next group also retains explicit derived boundary edges, not
traversal permission. Diagnostics reuse bounded structural GET-only capture; no
raw POST body/error is emitted in diagnostics.

Before vendor construction, real private Git/base64 decoding pins canonical plan
and audit hashes plus exact owner, expiry, merge policies and budget. The separate
immutable audit lists each anchor, operation, key, payload hash, source references,
prior-operation review references and risk-source references. Any overlapping
prior marker is rejected in this first version. Empty overlap is a reviewed
source claim, not proof from an empty remote search, and never self-authorizes
execution. A review must inspect the cited original evidence before package
admission. A later workflow must enforce exact pins, human approval, single-use
remote receipts, complete actual-package replay and live protection checks.

Proposed later job timeout is 180 minutes. At 120 vendor calls, maximum pacing
plus a conservative 20-second socket and 30-second response allowance is about
130 minutes before setup and private receipt writes. The actual workflow release
must inventory private Git receipt calls as well and verify its complete timeout,
expiry and artifact-retention margin. No numeric timeout is deployed here.

Synthetic tests cover nine-operation full proof execution, incomplete or changed
cached proofs, exact payload/order, rejected routes before a real connection seam,
expiry after wait, lower protected cap, immutable hash/risk mismatches, explicit
prior overlap rejection, and the real private Git base64 decoder. Pure tests do
not approve a real source package or any tree change.
