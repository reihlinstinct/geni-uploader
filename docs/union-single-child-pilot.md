# Protected one-child union-target experiment

Closes #681. This is a separate workflow and secret, not a change to the old
household executor. No live action is authorized by a merge. Exact private
source/config/executor pins, owner approval of the real one-child effect and
protected human GitHub approval are required. New configs must have fresh
reviewed expiry; expired packages are never extended automatically.

Official union/add-child prose describes adding a child to an existing union:
https://www.geni.com/platform/developer/help/api?path=union%2Fadd-child&version=1
Its returned-fields table is union-shaped and locale-name support is unspecified.
This experiment does not claim those ambiguities are settled. An offline fake
transport can prove local guards, not live compatibility. A real creation is not
known reversible. Wrong placement may require owner manual correction; no
automatic repair, deletion or second attempt exists here.

Only child mode, one entry and explicit union partners/children proof are admitted.
The POST targets the exact plan union, never profile/add-child. The existing
household model supplies identity/profile/graph proofs and its original consumed
marker, deliberately unchanged across workflow, union, expiry or executor changes.
The parent union must already contain exactly two partners; the baseline includes
all visible family edges and profiles. GET reads are fixed to admitted identities,
family nodes and unions, with a finite60-call budget and15-second pacing inherited
from the household transport. Fixed HTTPS host, no redirect/retry/429 loop.

Decoded successful ACK is encrypted locally before any ID/body interpretation.
Only an explicit new profile ID is accepted. Union-shaped/unknown ACK is terminal,
not permission to infer a profile from list deltas or discover extra profiles.
Transport loss, timeout or storage failure after consumption is uncertain and
terminal; the consumed marker is never reset. Malformed/oversize raw bytes cannot
be retained by the existing JSON transport; this limit is unchanged and must not
be described as raw-wire preservation. Artifact retention is one day; archive
retained encrypted evidence promptly even for stopped runs.

After one POST, read back exact payload/private/living/unclaimed profile, exact
anchor graph, reciprocal child graph and explicit target union partners/children.
Any omitted critical field or wrong relationship stops, never success. A separate
owner-authorized follow-up would be required for manual correction verification
or more children. No further send exists within this one-entry workflow.

Workflow: geni-union-child-create.yml. Environment father-create retains its
sole human reviewer, no self review/admin bypass and master-only protection.
Separate secret UNION_CHILD_PACKAGE_JSON; existing evidence-writer and Geni token
remain scoped to the protected job. Token OAuth scope is not independently
verified; fixed route/method admission is the effect boundary. Merge and setup
are not authority to dispatch. No secrets or identifying fixtures in this repo.

## Entrypoint environment

UNION_CHILD_CONFIG_JSON is the exact private package; UNION_CHILD_CONFIG_SHA256
is its approved UTF-8 hash. UNION_CHILD_EXECUTOR_SHA must equal GITHUB_SHA.
UNION_CHILD_CONFIRM must be CREATE_ONE_UNION_CHILD and UNION_CHILD_DEBUG must
be true or1. UNION_CHILD_OUTPUT_DIR is a new absolute encrypted-evidence directory.
UNION_CHILD_TREE_PAT is the protected private evidence-writer credential, never
printed. GENI_SECONDARY_ACCESS_TOKEN is the protected Geni credential.

## Hebrew-only names (#683)

The single-child wrapper explicitly enables Hebrew-only names. Both the names
map and top-level name fields use the supplied Hebrew values. It sends no
English names and invents no transliteration. The API's treatment of such a
payload is not independently verified by offline tests: extra auto-generated
locales fail the exact read-back proof and stop after the consumed create.
The existing household workflow keeps its bilingual-only default. The shared
model's opt-in is explicit per call, with no mutable global policy switch.
Gender is independent of name locale and must have owner-approved provenance.
All one-send, proof, marker and protected approval rules stay unchanged.

## First-child baseline omission policy (#685)

Optional plan field accept_first_child_omission defaults false and is admitted
only by the single-child wrapper. True is valid only when the exact target union
graph contains exactly two partners and no visible children. Before creation,
partners must still be explicit and exact; only children may be omitted. That
omission is retained as UNKNOWN_OMITTED, never interpreted as absence proof.
The owner must explicitly approve hidden-child risk in the exact package.

Once the new child is part of the expected graph, the exception no longer
applies. Direct union children including the new child must be explicit, as must
both parents, and all existing profile/anchor/reciprocal proofs still apply.
Missing children after a consumed creation means STOP, not success or retry.
Old household plans reject the new field. No marker, send count, route, expiry,
source/config hash or protected approval requirement changes.

## Explicit N-child package (#687)

Optional plan integer declared_children defaults1 and must exactly equal the
number of distinct entries in the approved immutable plan. It is not a boolean,
count guess, or open-ended request to discover more children. Every entry targets
the same verified two-parent union. The wrapper no longer imposes the previous
one/two/four-entry cap. Existing graph/node response bounds,20-member union proof
capacity,25-minute job deadline and exact expiry remain technical safety limits;
no claim of unlimited size or indefinite execution. Request budget is derived
exactly from initial identity/profiles/family/unions plus7requests per entry.
The existing workflow name/confirmation remain compatibility labels, not size
permissions. Exact owner-approved plan/config hash fixes the count and words.

Each entry has its own unchanged consumed marker, ACK and final receipt. Exact
profile, anchor, reciprocal and explicit union proof must finish before another
POST is admitted, including the independent IO proof latch. After any uncertain
effect or proof/storage failure, remaining entries are not sent. No retry,
marker reset or automatic repair. Re-run does not resume a partly completed
package: a fresh separately approved remaining-entry plan would be needed.
First-child omission applies only before any child exists in the expected target
graph, never after the first create or before any subsequent entry. Old household
workflow keeps its earlier default and rejects this opt-in field. Every payload,
the joint effect, expiry and hidden-child risk need owner approval before dispatch.
