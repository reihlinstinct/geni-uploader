# Geni merge adapter: approved-plan preflight, one POST, combined readback

9 November 2026. Issue #829. This slice implements the provider
adapter the explicit merge engine (#823) calls per approved pair, using the
pinned transport from #827. It installs no runner, workflow, CLI or credential
source, and it does not open the merge engine's unconditional release gate. No
live Geni call is made while the provider rate block stands: all tests use a
fake opener behind the pinned transport. No Geni support outreach.

## Adapter contract

`GeniMergeAdapter(transport, proposal, binding, trusted, approved_plan)` holds
the admitted proposal, the exact binding, the constructor-held trusted release
data and the approved private plan. Trusted expectations are never accepted from
a proposal, a provider body or a caller's own copy.

- `now()` returns a UTC epoch int for the engine's fresh admission check.
- `preflight(pair, binding)` re-runs `admit` against the constructor-held trusted
  data with a fresh clock, requires the presented binding to equal the
  constructor-held one, and requires the approved plan digest to equal
  `binding["plan_sha256"]` and the plan to be unexpired. It re-reads the owner
  (`GET /api/user` must serve the proposal owner) and both exact profiles
  (`GET /api/profile-g<guid>`): GUID, expected name, explicit false
  merge_pending/claimed/locked, no merged_into, resolved node ID equal to the
  approved plan, and tracked-field snapshot equal to the approved plan. Any
  mismatch, redirect, hidden or changed identity blocks the pair before any
  claim. It returns `ready`, the exact `pair_id`, `binding_sha256` (the fresh
  admit result), `plan_sha256` (the exact binding value), `resolved_ids` in
  approved path order and the canonical before-snapshot.
- `post_once(plan)` sends exactly one `POST /api/profile-<A>/merge/profile-<B>`
  per the official merge documentation, with `<A>`/`<B>` taken from the approved
  plan's path order as captured by this adapter's own preflight artifact. The
  pair is consumed before the attempt: a consumed pair can never POST twice. No
  retry, no fallback direction, no partner discovery, no profile creation, no
  field resolution. Which path position survives is not
  documented by the provider; the adapter maps the approved order mechanically
  and direction semantics remain a release gate, settled only by reviewed
  human-observed evidence.
- `readback(pair, plan, response)` re-reads both profiles by canonical node ID.
  Only the adapter's own preflight artifact is honored; a caller-supplied plan
  that differs from it is rejected. Both profiles must survive: exactly one
  remaining with no merged_into, the other retired with merged_into pointing at
  it. If the actual remaining profile is not the approved survivor, the
  readback returns the explicit outcome `remaining_is_approved_survivor=false`
  with the actual remaining ID and the adapter fails closed
  (`identity_verified=false`): a flip is never VERIFIED. The engine
  prioritizes the flag over the generic booleans and records the distinct
  SURVIVOR_FLIP_REVIEW_REQUIRED state with the readback evidence, stopping the
  batch for private review. Stopping on a
  flip is the conservative first-run policy choice; relaxing it to
  report-without-stop is a documented one-line change in the engine if the
  owner later decides direction does not matter. Identity (ID, GUID, name)
  must match the before-snapshot, and false
  flags are never assumed from omitted fields: merge_pending must be explicitly
  false on both, claimed/locked explicitly false on the remaining profile.
  Tracked data is preserved exactly or fully enumerated as retained conflicts
  (below). Anything missing, hidden, partial, redirected, pending or changed
  fails verification; the engine records UNKNOWN and stops the batch.

## Approved plan schema `geni-explicit-merge-plan/v1`

The adapter owns and strictly validates this schema; the plan-producing lane
generates the private plan from verified reads. ID-only approval is rejected so
data drift cannot hide behind unchanged IDs.

```json
{"schema":"geni-explicit-merge-plan/v1","request_id":"ZZ-request",
 "request_sha256":"<proposal digest>","owner":"profile-990001",
 "expires_at":1999999999,"policy_sha256":"<policy digest>",
 "pairs":[{"pair_id":"ZZ-pair","path_order":["profile-990002","profile-990003"],
 "survivor_guid":"101",
 "resolved":{"101":{"id":"profile-990002","expect_name":"ZZPersona","tracked":{"...":"..."}},
             "102":{"id":"profile-990003","expect_name":"ZZPersona","tracked":{"...":"..."}}}}]}
```

- Top level: exact keys `schema`, `request_id`, `request_sha256`, `owner`,
  `expires_at`, `policy_sha256`, `pairs`. `request_id`, `request_sha256`
  (the offline proposal digest) and `owner` must equal the admitted proposal;
  `expires_at` must be positive and within the proposal's expiry; the plan
  digest (canonical JSON SHA256, identical canonicalization to the engine's
  binding hash) must equal `binding["plan_sha256"]`.
- `pairs` mirrors the proposal's ordered pairs one-to-one. Each pins
  `pair_id`, the two distinct canonical node IDs in `path_order` (the approved
  POST order), the `survivor_guid`, and `resolved`: both proposal GUIDs mapped
  to their resolved node ID, expected name and exact tracked-field snapshot.
- `tracked` holds exactly the released coverage keys; absent provider fields
  are recorded as null. The released coverage: display_name, first_name,
  middle_name, last_name, maiden_name, suffix, nicknames, names, gender,
  occupation, about_me, birth, death, baptism, burial.
- `policy_sha256` pins the adapter's conflict/readback policy identity
  (tracked coverage plus `report-only-conflict-center-v1` plus
  `exact-preserved-or-conflict-v1`), so a coverage or policy change is a plan
  mismatch, never a silent behavior change.

## Preservation and Conflict Center policy

After the single POST, both profiles survive on the provider; conflicting field
values are retained by the provider for human choice in its Conflict Center.
The adapter only enumerates and reports conflicts; it never selects, clears or
resolves one, and conflicts never stop the executor. For each tracked field,
the remaining profile's post-merge value must equal its own pre-merge value or
the retired profile's. When both pre-merge values were non-blank and differ,
the value that did not survive is reported as a conflict alternative.
`conflict_center_checked` is a real postcondition, never hard-coded: the
retired profile must still carry its exact pre-merge tracked values, because
those retained values are the Conflict Center alternatives; if any of them is
lost or changed, the check reports unchecked and the engine records UNKNOWN.
Any other outcome - lost, hidden or partial data - is unverified, never
success, and the engine records UNKNOWN and stops the batch.

## Rate block and one-attempt rules

The pinned `BoundedJSONHTTP` transport (#827) allows one attempt per call with
fixed messages. Any transport failure, including 429, latches the adapter: every
later preflight, post or readback fails without issuing a new request, so a rate
block can never be fed more calls, and the engine stops the batch at the first
failure. No call is retried; an uncertain write is UNKNOWN.

## Remaining release gates

Unchanged from #821/#827 and still open: settled merge direction/postcondition
contract from reviewed human-observed evidence, human reconnection and owner
verification, immutable private approval binding, durable claim storage,
effective environment and dispatch/self-review settings, encrypted result
persistence and reconciliation, independent review and green tests. This slice
is code plus synthetic tests; merging it neither approves nor releases a merge.
