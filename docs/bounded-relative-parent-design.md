# Bounded parent addition at a pinned relative anchor

Refs #756. Design only. No implementation, dispatch path, credential, service
request, release or execution approval is added. The existing bounded-parent
model and protected runner keep their current contracts unchanged.

## Problem and target paths

The existing model requires the child anchor to be an existing parent of the
authenticated owner. An explicitly selected spouse or more distant relative
cannot satisfy that contract. Removing the check would discard a relationship
proof without replacing it. A new capability needs its own bounded model and
protected wiring, reviewed separately after this design.

This PR introduces only `docs/bounded-relative-parent-design.md`. Proposed later
paths, subject to implementation review:

- `src/geni_uploader/runners/bounded_relative_parent.py`: pure model.
- `src/geni_uploader/runners/protected_relative_parent.py`: isolated adapter.
- `.github/workflows/protected-relative-parent.yml`: manual protected workflow.
- `tests/test_bounded_relative_parent.py` and
  `tests/test_protected_relative_parent.py`: synthetic offline regressions.

No changes to the generic upload CLI, container, older release gate, existing
parent/household runners or their workflow confirmations are proposed here.

## One operation, explicit identities

One plan creates exactly one new parent of one pinned existing child anchor.
A second parent requires a new plan based on the verified first result. No
multi-parent batch, profile attachment, merge, edit, deletion, invitation,
adoption/foster relationship or repair. No source photos, dates or places.
Known life status is required for the new parent. Unknown stays unknown in
intake and blocks this capability rather than receiving a vendor default.

The authenticated account owner and anchor have separate exact IDs. Approval
must identify the owner, operator, anchor, proposed person, payload hash and
relationship. A relationship path demonstrates observed connection only. It
cannot grant permission to act on someone else's tree or replace consent.

## Bounded connection evidence

The plan pins a simple owner-to-anchor path of at most four existing union hops,
with distinct canonical profile and union IDs. Each hop includes two explicit
member profiles and their exact partner/child roles. Two partner roles mean a
spouse connection; partner/child roles mean parent-child; two child roles mean
shared-union siblings, without asserting legal/biological parentage. No names
select an identity. No service-returned URL becomes a route.

Preflight reads the authenticated owner, all declared existing profiles, the
immediate-family graph of each path profile, and each path union. Validate
canonical identity, expected fields and each hop's reciprocal graph/union
membership. Missing critical membership is UNKNOWN and blocks. The path may
not be extended by discovery, redirect, merge forwarding or name search.

Path-family baselines must include all visible nodes/edges returned by each
focus read, not just the two desired hop members. The plan must distinguish
these context-only nodes from expandable path profiles. Context nodes do not
permit new requests. Existing bounds: at most five path profiles, four path
unions, twelve separately read existing profiles, twenty visible members per
union, and two anchor unions. An oversized or incomplete baseline blocks;
operators do not trim it to fit. These are initial design limits, not guarantees
that every relative can be supported.

## Anchor and parent-union proof

The anchor gets its complete visible family baseline plus explicit expected
profile fields and immutable source references. A first parent requires no
visible existing parent union. This is not proof of no hidden parent. A second
parent requires the exact existing other parent and union. The old union cannot
be replaced. Adding a parent into a union with other existing children is out
of this first design scope.

Before any send, all path proofs and the anchor graph must match. The new
parent POST targets only the pinned anchor's add-parent endpoint. Post-create:
verify exact new-profile payload, privacy and unclaimed state, the entire
anchor graph, reciprocal new-parent graph, and explicit union partners/child.
Only a validated unique new union may be admitted for the first-parent direct
union read. Malformed/ambiguous acknowledgment, extra relative/union, wrong
union, omitted critical membership or changed existing edge means STOP.

Existing context profiles may be public or claimed if their explicit pinned
values match. They are read only. Relaxing the old private-context predicate
must be confined to the new model and tested; no default or omitted privacy,
life status or claimed state passes as known. Any positive merge state blocks.
A missing merge indicator may pass only under an explicit reviewed risk policy,
never as evidence of no merge. Newly created people always request and must
read back `public=false`, exact known life status and `claimed=false`.

## Stable single-use effects

Reuse the old marker's exact hash semantics and namespace for overlapping
owner/anchor/entry operations: owner, anchor, stable entry key and original
payload determine identity. Path, executor, workflow, expiry, proposed union
and risk flags do not create a new operation namespace. A new path must not
recreate a consumed old operation. New entry keys are not a recovery mechanism;
package review must reconcile prior consumed markers/acknowledgments for the
same proposed person before admission. Local duplicate names are a stop signal,
not remote duplicate-absence proof.

Encrypted before receipt and atomic permanent consume precede the single POST.
Retain the acknowledged profile ID before interpretation/readback advances.
Failure, uncertain send or storage loss stays consumed. No reset, retry, rollback
or automatic remaining-items plan. A follow-up is read-only reconciliation or a
new separately reviewed operation, never changing keys to evade consumption.

## Isolated protected wiring

A later workflow needs a separate package secret and confirmation, exact actor,
repository, branch, first-attempt, config/source/executor hash and expiry checks,
and shared mutation concurrency. Effective human reviewers, no self-approval,
no admin bypass and branch policy must be verified live before any install/run.
An environment approval alone is not approval of private facts or exact payload.

Load immutable private source through the existing base64 decoder and canonical
UTF-8 plan hash functions. Validate schema, cross-scope pins and all source fields
before constructing the vendor. Replay the actual package through that boundary
offline; an alternate serializer or fabricated test plan is insufficient.

Only fixed-host exact GETs for declared profiles/families/unions and one exact
POST are permitted. No redirect, refresh, fallback credential or retry after429.
Proposed request budget derives from the admitted routes: one account read,
one read per nonowner existing profile, one family read per path profile,
one read per path union, one fresh anchor-family pre-send check and four
post-create proof reads, plus the one POST. With the stated maxima this is
at most27requests;
reserve exactly that count for the package, including the one POST. A duplicate
route still consumes a request. Any extra route is rejected before transport.
Fifteen-second minimum request-start spacing, expiry after each wait, finite
socket/response deadlines, response caps and a twenty-minute job timeout remain
mandatory. Recompute the budget from the implementation call inventory before
review; the formula is not permission to add exploratory calls.

Persist responses encrypted before semantic validation or any next effect.
Public output is fixed status text only. Archive encrypted before/consume/ack/
final receipts and executor/run/config provenance even after STOP. No private
identity, source path or raw error text in public logs or examples.

## Required implementation and release tests

- Legacy parent runner accepts/rejects exactly the same inputs as before.
- Accept first/second parent for synthetic spouse and multihop relative paths.
- Reject disconnected/cyclic/duplicate/overlong paths, forged roles, changed
  identity, missing reciprocal membership and hidden/omitted critical evidence.
- Reject changed public/claimed/status fields; preserve existing profiles and
  require new private/unclaimed payload/readback. Unknown new life status blocks.
- Marker compatibility across old/new runner, changed path/expiry/union and
  workflow; permanent consumption and receipt/storage failure behavior.
- Exact source decode/canonical Unicode hash and config/owner/anchor cross-pins.
- Transport guard called before a real connection seam; exact methods/routes,
  budget, timeouts, pacing/expiry, redirects,429 and uncertain-send latch.
- Post-create wrong union, extra child/partner, malformed ACK and partial evidence
  stop without another send. No created ID inferred from a list difference.
- Independent mutations remove each safety guard and must be killed by tests.

The design can merge after independent review and green CI. It does not release
a runnable feature. The later implementation needs its own exact-head review,
green CI and normal signed merge. Every real operation additionally needs fresh
source-grounded owner approval, exact-package review, verified deployment
protections and human GitHub approval. No live run or reversibility is claimed.
