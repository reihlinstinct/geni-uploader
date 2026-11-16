# Protected parent-pair batch with one dependent sibling

Refs #766. Design only: no implementation, adapter, workflow, secret, release
or live-effect authorization. Existing runners keep their contracts unchanged.

## Scope and stages

Proposed maximum: four distinct existing child anchors, exactly two new parents
per anchor, and at most one new sibling for one selected anchor. At most nine
people may be created. Source plans must state known life status and private
creation for every new person. Dates, photos, places, edits, merges, invitations,
attachment of existing profiles, adoption/foster links and repairs are excluded.

Use separate reviewed stages: design, pure effect-injected model, isolated
protected adapter/source admission, protected manual workflow, then exact private
package review and owner approval. Do not relabel the existing single-parent or
relative-sibling runner as accepting this capability. Their anchor and family
contracts differ. No stage implicitly approves the next one.

## Explicit evidence and identities

The immutable source plan pins owner, operator, anchor identities, expected
profile fields, exact visible graphs and boundary edges. Each owner-to-anchor
path has two through five distinct profile nodes and one through four distinct
unions. Both endpoint family graphs and a direct union read must prove each hop.
Names never select a profile. Context-only nodes add no route permission.
All returned visible nodes and edges belong in the baseline; do not trim them.
An oversized baseline fails validation before any vendor connection.

All anchors must initially have no visible child-role parent union. This first
batch design does not support an existing single parent, hidden parent detection,
a parent shared between two anchors, or merging two anchors into the same newly
created parent union. Reject duplicate entry keys and identical proposed persons
across groups. Shared existing context may be pinned once; distinct source
baselines for the same existing node must be identical.

The package records that missing visible relatives are not proof of absence from
the service. Hidden or disconnected duplicate risk must be explicit. Parent and
sibling identity, relationship, life-status and spelling claims retain their
source references and uncertainty. A relationship path proves connection, not
authority to act on another account.

Unknown merge indicators remain unknown. A source-grounded explicit policy may
permit only the named existing profiles with omitted merge state. It is neither
an API false value nor permission for another anchor. Positive pending or merged
state always stops; wrong types and conflicting merge indicators also stop.
New-profile validation must not silently inherit a broader policy. The exact
policy for newly created profiles, if omission occurs, needs separate review and
owner approval. Existing field, identity and graph comparisons remain strict.

## Ordered state machine

Validate the whole source/config, operation list, dependency graph, route budget
and all immutable cross-pins before constructing credentials or transport.
Read and validate all existing context and paths before any POST. Recheck the
current group's full anchor graph immediately before its first send. Groups
execute in explicit source order, never sorted by service results.

For each group:

1. Persist encrypted before receipt and permanent atomic consume marker for the
   first parent. Only then allow one exact add-parent POST at that group's anchor.
2. Preserve the acknowledgment before interpreting it. Admit the new profile ID
   only from one canonical, unique, syntactically valid acknowledgment, never a
   graph difference or URL. Verify its exact payload, privacy and claimed state.
3. Verify the complete anchor graph, reciprocal new-parent family and direct
   unique new parent union. Exactly one parent partner and the original anchor
   child must occur in that new union; existing edges remain unchanged.
4. Close over that verified parent ID and union as runtime bindings. They are
   outputs of the first operation, not arbitrary IDs supplied by an external
   source. The second parent uses the same anchor add-parent endpoint; after the
   second ACK prove exactly the same parent union contains both new parents and
   the original anchor, with no unexpected member or edge.
5. If this is the selected sibling group, send its one add-sibling operation only
   after both parent proofs pass. Verify the new child profile, exact anchor graph,
   reciprocal child graph and the same direct parent union with exactly that one
   additional child. The payload has explicit known life status and private mode.
6. Save verified completion before moving to the next group. A later failure does
   not undo earlier verified creations. Final reporting lists each item's exact
   phase and acknowledged ID, with unattempted items distinct from uncertain sends.

The transport independently enforces the next-send latch. A model success flag
or a cached target ID alone cannot reopen it. It must revalidate the saved full
post-create anchor graph, exact payload and direct union proof for the preceding
operation. Incomplete storage, malformed ACK, extra edge, wrong union, ambiguous
membership, changed context or any uncertain send stops the whole run. No retry,
automatic resume, rollback, compensating deletion, repair or remaining-items run.

## Stable consumption and crash behavior

Keep the existing parent marker namespace and exact hash semantics for the same
owner, anchor, stable entry key and original payload. Path, runtime union, new
runner, expiry or risk policy cannot mint another permission for the same parent.
The sibling's operation identity must be stable before the first create, derived
from owner, existing anchor, stable key and original payload, not a newly assigned
parent/union ID. Define and test compatibility with earlier sibling markers; when
an overlapping old operation cannot be proved unspent, stop for reconciliation.
Never change entry keys as a recovery mechanism.

Every item's before/consume/ack/proof/final evidence is encrypted and durably
stored. Consume is permanent before POST. A failed save after consume leaves the
operation spent. An acknowledged ID survives an ensuing failed proof. Local
fsynced snapshots and private create-only receipt refs retain run/config/executor
provenance. Public output uses fixed text and allowlisted structural errors only.
No source data, credential, raw POST response/error or private path is public.

## Isolated protected admission and transport

Use a new package secret and confirmation, exact master checkout and executor
SHA, raw config hash, immutable private source commit/path, canonical decoded-plan
hash and expiry. Read actual source through the existing private Git/base64 decode
boundary; validate all cross-scope fields before credentials are constructed.
Replay the actual package offline through that same boundary, not a substitute
serializer. Every group, payload, source reference and risk policy is covered.

The manual workflow shares existing mutation concurrency, never cancels a run,
and requires human review with no self-approval or admin bypass. Verify effective
settings live before installation. Environment approval is necessary but cannot
replace approval of the exact facts, operations, risks and permanent consumption.
One human gate may cover only the complete explicitly approved bounded package.

The fixed HTTPS vendor permits only declared profile/family/union GETs and the
ordered explicit add-parent/add-sibling POSTs. New profile and union reads are
admitted only by validated operation outputs. No discovered URL, search, traversal,
pagination, redirect, refresh, fallback token or retry. Preserve minimum 15-second
request-start spacing, finite socket/response bounds and expiry after each wait.

Implementation review must derive an exact request inventory including initial
context, fresh pre-send checks, all POSTs and all proof reads. Count repeated GETs
rather than pretending they are free deduplication. Set a per-package maximum and
a finite hard ceiling, and prove the job timeout covers its worst-case waits,
transport bounds, setup and artifact retention. The read-only reader's 50-GET
ceiling is not a mutation-run budget grant. No numeric mutation cap is released
by this design. Reject a package that cannot fit the reviewed implementation cap.

## Required regressions and release checks

- Valid synthetic four-pair/one-sibling execution; first/second parent dependency
  bindings; unknown life status rejected; privacy and exact payload readback.
- Disconnected/cyclic/duplicate paths, changed identity or graph, incomplete
  membership, missing critical fields and cross-group baseline disagreement.
- Omitted merge state only under the exact explicit policy; positive/malformed
  merge state always stops, including each newly created person's readback.
- Exactly one created parent union, fixed second-parent target, exact sibling
  parentage; wrong union, duplicate ACK, extra member/edge or missing proof stops.
- Permanent consumption and marker compatibility across expiry/path/runner/policy
  changes; crash before/after each storage/send boundary; no retry or resume.
- Real private-source decoder/canonical Unicode hash and all config/source pins.
- Actual connection seam rejects wrong method/route/order/budget before network;
  late expiry, pacing, redirects,429 and response limits preserve the closed latch.
- Encrypted evidence and fixed public output, including partial results and error
  paths. Mutation tests must kill removed guard, marker, proof and latch checks.
- Old runners retain accepted/rejected shapes and behavior without widening.

Each implementation stage needs its own signed exact-head independent review and
green CI. A later exact package additionally needs fresh source-grounded owner
approval and protected human approval. No live effect follows from this document.
