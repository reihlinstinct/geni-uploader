# Single-father risk-accepted release design

Status: DESIGN ONLY. Related: #231, #240. No executor, workflow, deployment,
configuration change or live operation is released here. The default
`human_parent_gate.require_production_release()` stays unchanged and always
blocks. This separate contract cannot be used as a toggle or proof object.

## Narrow outcome

A future separately reviewed executor may make one `profile/add-parent` POST
against one exact canonical secondary owner using one approved father payload.
Count is exactly one. Require gender male, explicit living status, public false,
main English names and approved Hebrew/English locale names. No mother, partner,
child, merge, delete, invitation, relationship event or existing-profile edit.
No inferred dates, places or other fields. No automatic later operation.

The original all-proofs path remains available only under its existing rules.
This design proposes a distinct risk-accepted path, not fabricated satisfaction
of those rules. It requires a new reviewed implementation and explicit named
release approval before any executable route can exist.

## Evidence and risks stay separate

The public contracts inspected on 28 October 2026 document POST add-parent,
form or JSON payloads, names locale maps, explicit is_alive/public and return of
the added profile:
https://www.geni.com/platform/developer/help/api?path=profile/add-parent

The graph contracts are:
https://www.geni.com/platform/developer/help/api?path=profile/immediate-family
https://www.geni.com/platform/developer/help/api?path=union

They do not prove hidden-parent completeness, a free parent slot, merge-clear
status when fields are absent, default locale presentation or absence of an
auto-created blank partner. Zero observed parents is not proof of absence.
Requested privacy is not proof of honored privacy. A post-write readback can
find a privacy failure but cannot prevent its initial exposure.

An exact private review must name these residual risks: duplicate/hidden parent,
unexpected union/blank partner, UNKNOWN merge status, incorrect private/name
behavior, partial success and difficult manual repair. Risk acceptance does not
change evidence values. Explicit adverse evidence still blocks: known pending
merge or merge target, wrong owner, observed existing parents, redaction,
malformed/partial bounded collection, pin mismatch or scanner failure. Unknown
custody policy alone is not create approval.

## Approval and immutable binding

Before release: signed implementation, independent review, exact-head green CI,
named merge approval, then separate deployment/release approval for the precise
route, credential scope and environment audit. No normal merge implies release.
No bypass, automatic control reset or control-file edit to make a run pass.

Before each run: authentic owner authority and data consent, explicit risk
acceptance for this exact one-father payload, exact run approval and protected
human environment review. Existing approvals of read-only work do not cover it.
A reviewer cannot approve their own run; administrative bypass is disabled.
The review identifies the sending account/secondary connection and every field.

Bind canonical owner and connection, exact payload and graph hashes, data pin,
executor/workflow commit, immutable released artifact digest, reviewed policy
version, encryption recipient, shared intent namespace/version, operator,
approval evidence, one-use unpredictable plan ID, creation/expiry (at most
15 minutes), count one, and excluded operations. A JSON boolean, unsigned hash,
chat phrase parser or self-selected signer cannot authenticate this envelope.
No credential or key is placed in an envelope or public output.

## Ordered runtime design, not an implementation

1. Before any request, validate release pins, owner authority, protected
   environment settings and exact envelope. Reject reruns/attempts other than
   the approved first attempt. Pin/EXPECT_SHA mismatch or scanner trip: STOP.
2. Acquire shared exclusive owner/connection exclusion across every approved
   execution surface. Existing local synthetic SQLite is not a shared lock.
   Choose and separately approve the durable storage backend before release;
   missing shared exclusion blocks release. Coordinate credential changes too.
3. Use bounded secondary-only GET preflight. Token-self, owner and focus must
   agree exactly. Preserve absent merge fields as UNKNOWN only under the exact
   named policy. Reject explicit adverse signals, observed parents and graph
   drift. Bound response size/time/depth and request counts. Follow no arbitrary
   response URLs or redirects. No token refresh, alternate host or retry.
4. Immediately before POST, revalidate freshness and exact graph/payload/pins.
   Commit durable intent atomically using compare-and-set. Persist owner,
   connection, operation, payload, plan and artifact bindings. If persistence
   or exclusion is uncertain, do not send. Intent consumption is one-way.
5. At most one fixed HTTPS POST, with the exact approved payload. No generic
   caller URL, query credentials, redirect, proxy, retry or fallback. A transport
   failure after intent consumption leaves it consumed, even if send is unknown.
6. Persist acknowledgment/returned ID without a second write to Geni. Encrypt
   evidence before upload. Bounded fixed GETs may verify exact returned profile,
   names, living/private flags and child-parent union edges under approved scope.
   Unexpected IDs/partners, blank nodes, absent fields or failed readback stop.
7. Report VERIFIED only when all required postconditions are read back. Otherwise
   report UNCERTAIN/FAILED with encrypted reconciliation evidence. Never infer
   success from HTTP/exit status alone. If output encryption/storage fails after
   POST, the consumed durable intent must survive and block another create.

The actual GET request/field/count budget and route encoding are release inputs,
not loose permissions in this design. Post-write readback must include union
membership and enough nodes to detect unexpected partners; additional exploratory
GETs require a separately approved scope. Do not promise a blank-mother diagnosis
from incomplete output.

## Recovery and future family steps

Uncertain intent remains consumed across new plan IDs, changed payloads, expired
receipts, process restarts and fresh runners. No replay, reset, delete, merge or
rollback. A separate approved reconciliation is GET-only and never authorizes a
repair. Report any created profile even if verification or later persistence
failed. Ordinary cancellation is not a safe undo strategy.

Stop after father readback. An unexpected blank partner is not automatically the
mother and must never be overwritten without verified identity and exact edit
approval. If the actual parent union has only the verified father partner and
exact child, a separately approved mother design may use union/add-partner:
https://www.geni.com/platform/developer/help/api?path=union/add-partner
This creates a new profile, not an existing-ID connector. Its table does not
list locale names maps. Existing profile locale updates and marriage events are
separate operations with separate approvals:
https://www.geni.com/platform/developer/help/api?path=profile/update
https://www.geni.com/platform/developer/help/api?path=union/update
No second parent, child or marriage action follows automatically.

## Release-blocking acceptance checklist

- Immutable authenticated plan/release policy and environment audit, not JSON
  approval flags; unrelated account/owner, stale data and changed pins fail.
- Shared durable CAS/intent proven by concurrency and interruption tests across
  supported surfaces, not only process-local tests.
- Synthetic transport tests prove one POST maximum, no retries/redirects/refresh,
  exact fields/routes, unknown/adverse merge separation and bounded graph checks.
- Fault injection before/after durable intent, during POST, after acknowledgment,
  during readback/encryption/upload: no replay or false success.
- Public summaries contain no family values, token, key, payload, graph hash or
  private approval references. Raw evidence is encrypted; temporary plaintext
  cleanup is tested, and failure paths preserve durable consumption.
- Independent review and exact-head CI precede named merge approval. Release,
  environment changes and exact-run approval remain separate human decisions.
