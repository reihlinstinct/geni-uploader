# Explicit-pair profile merges: offline proposal, live release closed

9 November 2026. Issue #821. This is an engineering design and offline validator,
not permission to run a merge. No live merge adapter or installed workflow is
included. Existing upload, token and creation workflows remain unchanged.

## Request and approval flow

1. The human names both exact profiles and which must survive. Prepare an ordered
   request file in private data storage and a private PR. Each pair records both
   canonical profile links, GUIDs, expected names, evidence and unresolved conflicts.
   Public code, issues, workflows and examples contain no real people or private
   storage references. A private request is data, never authority by itself.
2. Resolve each GUID using a separately authorized read-only plan. Require exact
   GUID/name equality and a canonical API node ID. Capture merge/claimed/locked
   status, relationships and timestamps privately. Never infer a partner from
   matches, requested_merges, spouse names or a nearby search result.
3. Human reviews a private plan with direction and effects. Bind approval to the
   exact request digest, ordered pairs, survivor choices, resolved IDs, private
   data commit/blob, executor and workflow commit, owner and expiration. A PR merge
   is not execution approval. An environment button is not exact payload approval
   unless its immutable run is demonstrably bound to that reviewed payload.
4. The proposed manual-only Actions run has a preflight job without vendor secrets
   and a separate execution job behind a dedicated protected environment. Only the
   verified human owner can dispatch and approve. Pin repository, master ref,
   executor SHA, workflow bytes, run ID and attempt 1. Reject reruns, stale plans,
   wrong actor/triggering actor, schedule/push/PR/repository_dispatch events and
   missing/expired approval. Inputs carry hashes, not living-person data.
5. Verify effective environment settings, human required reviewer, prevent
   self-review, no admin bypass and branch policy. Because prevent-self-review
   may conflict with the human dispatching and approving the same run, resolve
   that actual GitHub behavior before release. Do not silently weaken protection
   or substitute an agent dispatcher. YAML alone proves none of these settings.
6. Before each pair, re-read owner and both exact profiles. Require identity and
   fresh-plan equality. Claim a durable single-use operation key before POST,
   bound to the entire approval. Persist it outside ephemeral runner state.
   Concurrent runs serialize; neither concurrency nor an artifact is a durable
   no-replay ledger. Abort if the durable claim/store is unavailable.
7. One POST per approved pair, no fallback direction, retry, automatic field-conflict
   resolution, partner discovery or profile creation. No timeout/429/5xx retry.
   An uncertain write becomes UNKNOWN and stops the batch. Reconcile with separate
   authorized reads before any new approval. Never label HTTP 200 as verified merge.
8. Verify the intended survivor and source merged_into relationship using the
   released response/postcondition contract. Anything pending, hidden, redirected,
   already merged, changed or unresolved stops for private review. Repeated survivor
   is allowed, source reuse/chains are not. If a later pair becomes moot, record
   ALREADY_MERGED_REVIEW_REQUIRED and stop; never silently replace or re-order it.

## Offline schema and limits

`geni_uploader.core.merge_request.validate` accepts only schema
`geni-explicit-merge/v1`, an opaque request_id, canonical owner node, expires_at and
1-10 ordered pairs. Each has an opaque pair_id, left/right objects with url, guid,
expect_name, one explicit survivor_guid, evidence source/reason entries and a
conflicts note. Canonical URLs have no query/fragment. The validator admits data
only; it does not verify evidence, expiration against a clock, ownership or consent.
The digest is a content binding, not an approval token. Bounds count the original
string, including padding. Text rejects controls (except newline/tab in notes),
format controls, surrogates and line/paragraph separators. URLs additionally reject
all whitespace, have a 512-character cap and require a lowercase HTTPS prefix.
Expiration is a positive integer below 2**63. Repeated profile GUIDs must carry
identical URL/name expectations across the batch.

`verify_resolution` checks a captured profile record offline and returns a node
only after GUID, expected name and explicit unmerged/unclaimed/unlocked flags match.
Missing merge_pending, claimed or locked flags fail closed. An absent or empty
merged_into is accepted in this offline shape check, but is not proof that a live
profile is unmerged. A live adapter must establish the released status contract
against fresh GETs, validate the token owner and revalidate before each effect.
`require_live_release` always raises. No environment variable or proposal can
open it. The module has no HTTP client, credential reader, CLI or workflow.

Synthetic shape:

```json
{"schema":"geni-explicit-merge/v1","request_id":"ZZ-request","owner":"profile-990001",
 "expires_at":2000000000,"pairs":[{"pair_id":"ZZ-pair",
 "left":{"url":"https://www.geni.com/people/ZZPersona/101","guid":"101","expect_name":"ZZPersona"},
 "right":{"url":"https://www.geni.com/people/ZZPersona/102","guid":"102","expect_name":"ZZPersona"},
 "survivor_guid":"101","evidence":[{"source":"ZZ-source","reason":"ZZ-synthetic evidence only"}],
 "conflicts":"ZZ-review conflicts explicitly"}]}
```

## API contract: what is and is not known

Official [merge documentation](https://www.geni.com/platform/developer/help/api?path=profile%2Fmerge&version=1)
shows a POST with canonical profile node IDs in both path positions, but does not state which
profile survives, GUID acceptance, permission behavior, response shape, pending
merge behavior, conflict handling or rollback. Do not invent an unmerge API from
an undocumented path. Survivor direction and final-state contract need official
clarification or independently reviewed human-observed evidence before release.

Official [profile fields](https://www.geni.com/platform/developer/help/api?path=profile&version=1)
distinguish id and guid and document merge_pending/merged_into. Blank fields may
be omitted. The offline validator requires explicit false merge_pending, claimed
and locked flags, but accepts absent merged_into. That asymmetry is not a verified
live API contract, and absence must not be treated as proof of an unmerged profile. [GUID resolution](guid-resolution.md) records GET-only
`profile-g<guid>` resolution and canonical-node checking. That is not proof that
merge accepts a GUID on either path segment. Use resolved node IDs only after the
merge contract is settled. No live POST is allowed just to test support.

## Private results and public silence

Persist per-pair states: NOT_ATTEMPTED, CLAIMED, UNKNOWN, VERIFIED,
ALREADY_MERGED_REVIEW_REQUIRED or BLOCKED. Include run/attempt, operation key,
request/executor digests, both before identities, intended survivor, timestamps,
POST attempted boolean and readback evidence. Encrypt private IDs, names,
evidence and vendor responses to the approved recipient. Public logs and summary
show fixed status/counts only. Capture exceptions privately; no raw exception,
token, redirect, URL or provider body in public output. Persist the pre-POST claim
and reconcile UNKNOWN even if artifact upload or evidence encryption later fails.

## Credential repair and remaining release gates

An invalid access token requires human reconnection, not guessed credentials or
an agent OAuth login. Follow the reviewed deployment's fixed primary-owner
connection route only after verifying its current deployment, owner pin and slot.
The human signs into their own intended account and completes provider consent.
The callback stores credentials in the approved protected secret custody and
returns value-free status. A controlled user-run token probe then verifies owner
identity. Do not use another owner's session/token, send secrets through chat,
register another app, refresh blindly or change existing upload credentials.
See [connection custody](../oauth-bootstrap/CONNECTIONS.md) and the caveats in
[token setup](geni-token.md). The older desktop guide is not a verified current
app-registration recipe. A previously observed invalid local token does not prove
all current Actions secret slots are invalid; probe the intended slot separately.

Before installing a live workflow: settle API direction/postconditions; human
reconnection/owner verification; immutable private approval binding and durable
claim storage; effective environment and dispatch/self-review settings; encrypted
result persistence and reconciliation; independent review and green tests. Code
review or merging this offline model does not close any of those gates.
