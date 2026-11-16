# Human-run two-parent creation: production release contract

Status: design and offline release-gate fixture only. Production creation remains
disabled. This does not release a live Plan, transport, workflow or image.
Related: #190, #188, #195, #196, #207. No private data or real IDs in this document.

## Outcome and boundary

A human eventually reviews an exact private Plan, then personally starts a
separate human-only executor for at most two parent creations on one canonical
owner. Agents prepare data, develop/test offline and review human-supplied
outputs. Agents never authorize OAuth, call Geni, dispatch the runner or schedule
its execution. No automatic run when a credential arrives, PR merges, File
button wakes, chat approval occurs or monitoring fires.

The first release is a private local human CLI, not a model-callable MCP write
tool. A future GitHub Action is a separate release with an authenticated human
approval environment and cross-run lock. Neither is released by this design.
The local executor must independently verify the signed release, artifact digest
and exact Plan signature. Interactive TTY confirmation is a UX check, not
cryptographic proof of a human. Do not advertise that a TTY alone prevents agents.
No executor credential is exposed to an LLM client/tool endpoint.

## Vendor facts and open questions

Sources fetched 28 October 2026:

- https://www.geni.com/platform/developer/help/api?path=profile/add-parent
  documents POST, form or JSON inputs, return of the added profile, fields
  first_name/last_name/maiden_name/names/gender/is_alive/public. It does not
  document a parent-slot selector, idempotency key, transactional pair create,
  hidden-parent completeness or default-locale behavior.
- https://www.geni.com/platform/developer/help/api?path=profile/immediate-family
  documents focus and nodes (unions/profiles). It says blank fields are omitted.
  It does not certify that an empty/omitted parent list proves no private parent.
- https://www.geni.com/platform/developer/help/api?path=union documents
  partners/children/adopted_children/foster_children/status. It does not say this
  graph is complete for hidden/private edges, or that an absent field is empty.
- https://www.geni.com/platform/developer/help/api?path=profile distinguishes
  id from guid and documents public, names, merge_pending and merged_into.
  Blank-field omission does NOT establish missing merge_pending=false.

Source examples with legacy endpoint quirks are not production commands. Use
fixed HTTPS documented routes, bearer headers, no query credentials, redirects,
proxies, retries or guessed alternate endpoints. Do not treat schema fixtures as
vendor proof. No mutation experiment is disguised as a read-only check.

## Separate evidence states

1. Credential custody: exact pinned owner, possibly unknown merge status under
   explicit secondary-only custody policy. This is not permission/readiness.
2. Identity discovery: human confirms returned canonical ID/name. Unknown merge
   remains unknown. It cannot certify existing-parent graph or write safety.
3. Read-only preflight: human runs bounded fixed GET collection, encrypted output.
   All requests and fields reviewed; no create calls. Existing #195 probe is an
   initial collector, not a completeness oracle. It presently requires explicit
   merge_pending:false and must not silently inherit the custody exception.
4. Vendor proof: reviewed documentation or separately authorized human evidence
   establishes parent visibility, slot choice, privacy and locale behavior.
5. Live Plan: current graph+authority+artifacts bound and short-lived. Only then
   can a separate human write decision be considered. Unproved is blocked.

## Proof matrix and read-only work

| Gate | Read-only evidence to collect | What still cannot be inferred |
|---|---|---|
| owner | token-self exact canonical id vs private pin, no redirect/merge target | unknown merge does not prove clear for creation |
| parent completeness | focus id, every returned union/profile, all explicit next-page links only after route validation, hidden/redaction markers, parent links | no parents returned does not prove no hidden parents |
| parent slots | returned union membership and existing parents; vendor documentation review | gender alone cannot select a free slot, second add-parent cannot be assumed to reuse first union |
| private | current profile public flags and vendor contract | requested public:false does not prove create honored it |
| bilingual/default | returned names.he/names.en plus main-name fields, locale metadata if documented | populated main English fields do not prove English default for every UI/viewer |

Read-only collector design: accept only exact reviewed routes, bounded counts,
size/depth, ten-second spacing, no retries after 429/challenge/error; classify
missing/inconsistent/redacted/partial graph as UNKNOWN. Follow no arbitrary
response URL. A next-page URL is data, must match fixed host/owner route and
allowed parameters before any human-run client uses it. Store a graph hash and
collection time; raw family data encrypted, public summary value-free.

No known public endpoint currently proves all hidden-parent visibility or slot
semantics. Vendor clarification or a separately approved, human-performed sandbox
experiment may be needed. That future experiment is a mutation needing its own
approved identities, scope and cleanup plan; it is not authorized here. If no
safe reversible test exists, leave gate closed. No real family profile is a test
fixture. Privacy cannot be learned by exposing a living person's test profile.

## Exact private Plan envelope

Bind owner+connection id+custody attestation, named human operator, original
consent references and exact scope, full normalized manifest+payload hashes,
canonical graph snapshot/hash+completeness proof, slot decision/proof, private and
locale proof versions, data commit, signed workflow/executor commit, immutable
image/binary digest, shared journal state version, count<=2, creation/expiry times
(max 15 minutes) and unpredictable one-use Plan id. No fabricated release pins.
Sign using a reviewed trusted Plan authority, not a self-supplied JSON hash.
Proof references must be authenticated, scope-specific and immutable; a boolean
"approved" in data is never proof. Any changed data/account/graph/artifact,
expired Plan or mismatched digest invalidates it. Show every proposed field and
excluded scope; no names/dates/places inferred. Review English main plus Hebrew
locale explicitly. An offline hash identifies content, not authorization.

## Write ordering, locks and uncertainty

The production adapter must not reuse SyntheticTransport. Add a separately
reviewed fixed-endpoint adapter only after release gates. Deny its construction
unless all authenticated proofs+human approval match. Use a shared exclusive
owner/connection lock across local instances and any future Actions; credential
refresh also coordinates with this lock. Local sqlite/file lock alone cannot
protect a remote concurrent executor. If no shared lock service/authority is
approved, support one local-only operator with remote runners disabled and
explicitly report the resulting limitation, never claim global exclusion.

Revalidate short-lived receipt and current graph immediately before EACH POST.
Durable intent precedes request and includes exact owner/operation/payload/Plan/
artifact hashes. POST at most once. Record returned canonical ID before further
operations. Human-run fixed GET verifies created identity, public:false, alive,
full names/maiden fields and exact parent link/union membership. First parent must
verify before the second starts; take fresh graph/slot evidence again. A timeout,
HTTP failure after send, unknown acknowledgement or failed readback means
UNCERTAIN and stops. Never replay create, silently clear intent or use a fresh
journal to evade a stop. Recovery is human-reviewed read-only reconciliation;
no automatic delete/merge/unlink/rollback promised. A created first parent may
remain if second stops; disclose this partial-outcome risk before approval.

## Ordered issue-sized implementation slices

1. Closed release gate + contract tests (this design): offline only, always false.
2. Canonical owner/graph evidence parser with UNKNOWN propagation, independent
   tests for hidden/redacted/partial/absent/null/wrapper/redirect/mismatched graph.
3. Human-run read-only collector/output adapter; preserve custody unknown status
   without promoting it; separately decide whether unknown blocks any read-only
   identity collection. Do not relax parent creation safety by accident.
4. Vendor evidence pack for slots/privacy/default language. Design/code/tests may
   proceed offline while human evidence is pending; no fabricated live proof.
5. Signed exact Plan authority, immutable artifacts and one-use short receipt,
   stale graph/tamper/account/operator/image/data mismatches tests.
6. Shared lock/intent+reconciliation across approved execution surfaces, process
   kill tests and fork/concurrency simulation. No remote service created silently.
7. Fixed live adapter behind closed feature gate, contract fake-server tests for
   exact routes/headers/timeouts/429/redirects/uncertain POST, no production call.
8. Human executor UX/release+independent security review. Still disabled pending
   verified proof matrix, explicit named release approval and exact live Plan.
9. User personally performs exact approved run; agents inspect its encrypted
   report under existing output-read scope. Report outcome, not inferred success.

Each slice gets issue+PR+regression tests, signed commits, independent review,
exact-head green CI, explicit merge approval; deploy/release/actual human write
approvals remain distinct. An implementation being merged is not a release gate.
Do independent offline slices while evidence blocks others. No firm live-create
ETA until external proof and actual executor contract are settled.
