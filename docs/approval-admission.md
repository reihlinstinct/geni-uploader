# Private approval-record admission candidate (#295)

No route, deployed service, owner grant, protected approval writer or production
permit is implemented. This is an unconnected fixed-GitHub-source fetch and
content boundary. The production gate remains closed. Private-source provenance
is not consent: a valid Git blob may have been written by an automated account.

## Interfaces and trust

`fetchPrivateApproval({source, credential})` reads only api.github.com over fixed
GET routes, using reviewed release source pins (numeric repository ID, exact
owner/repo, immutable commit, relative ordinary-file path, Git blob SHA1 and
content SHA256). It checks private visibility/name/ID, exact commit/tree/leaf
identity, ordinary tree and blob modes, no truncated trees or duplicate path,
canonical base64, byte length, Git blob hash and SHA256. No returned URL is used.
No redirects, pagination, retries or writes. At most11GETs,5seconds,128KiB/API
response,64KiB/approval, depth8/path segments8. HTTP bodies use a stream cap as
well as declared length. Async deadline does not preempt synchronous CPU parsing.

The returned object is an opaque in-process WeakMap receipt. Copying flags,
spreading it or supplying a JSON envelope cannot forge provenance. Bytes and
source pins are copied internally. The receipt expires after30seconds of server
clock time. It is not a durable capability and is intentionally not serializable
across processes. Fetch source pins must come from reviewed release config, not
untrusted request JSON. The exported function alone cannot know that config's
authority. Credential access/scope is NOT selected or widened here.

`admitApproval({approvalBytes, expectedPins, authenticatedRecord,
expectedApprovals, nowUnix})` checks the actual retrieved exact bytes against
`approval_record.py`'s content contract. Same field names, fixed exclusions,
role order,40/64hex bounds, owner syntax, attempt1, 15minute window, exact pins
and distinct role/evidence references. `nowUnix` must agree with server clock
within5seconds and never replaces it. JSON duplicate keys/depth/UTF8/size fail
closed. Every failure is the fixed value-free `approval admission blocked`.

Unlike the earlier proposed issue interface, `workload` and `reviewEvidence`
flags are NOT accepted as authentication. No boolean can manufacture trust.
Python's canonical `record_hash` is not exposed as an equivalent JS digest:
`record_sha256` hashes exact original bytes and may differ by whitespace/order.

## Deliberately unresolved release requirements

All results state owner_approval_verified:false, review_provenance_verified:false,
payload_approval_verified:false, post_permitted:false, production_enabled:false.
The3reported gaps are authenticated owner-record creation, protected human
review/run/job correlation, and permanent replay consumption. Revocation and
narrower-scope checks also require that trusted record ceremony and fresh source,
not merely an old immutable blob. This module does not authenticate an actor or
reviewer from their hash reference, treat a commit as consent, verify OIDC, or
consume intent. Those must be composed under separate independent review before
any production route can exist. Original owner approval remains a trusted private
source, not a comment or field claimed by a third party.

The source fetch proves currently observed repository visibility/identity and
immutable referenced bytes, not historical branch protection or safety against
later administrator deletion, takeover or key compromise. No private identifiers,
real family data or credentials occur in code, fixtures or docs. All test HTTP
calls are mocked and all approvals are synthetic.

## Mutation evidence

19individual guard-removal mutants were executed and killed by the synthetic
suite: repository privacy/numeric identity/name, commit/tree/truncation/leaf,
Git blob hash, SHA256, declared/stream cap, exact pins, issued/expiry/window,
distinct role/evidence, freshness, and exact receipt bytes. Isolation fixtures
keep the expected approval hashes equal to the invalid same-person/evidence
record, so adjacent expected-value checks cannot mask distinctness. Equivalent
JSON with added whitespace isolates byte identity. A stalled second read proves
the stream bound stops immediately, independently of the parser byte bound.

The existing runtime.test.mjs CI entry point imports this synthetic test suite;
no workflow trigger, permission, environment or job-step edit is needed.

## Chosen human assurance (design only)

The chosen ceremony has ONE human, not two: the owner approves the exact private
payload fingerprint through their trusted conversation, the agent dispatches a
protected workflow, the owner personally approves its required-reviewer gate,
and an independent agent reviews code. The protected reviewer action must be
bound to that job/run/attempt; a comment, GitHub User-type identity, actor string,
or app-authored action is not evidence of a human click. Some apps use the same
GitHub identity as the owner, so identity alone cannot distinguish them.

This is weaker than two independent human approvals. The future authenticated
record must explicitly identify assurance as single-human-owner approval plus
independent agent code review and agent dispatch, never two-human approval.
The current offline record's owner/human_reviewer distinct references describe
content fields only, not proof of two natural people; do not fabricate distinct
references for one person. A separately reviewed versioned record schema update
must encode the chosen assurance and source-role distinction before production.
No environment, record writer, dispatch, release or live run is authorized by
this document. Existing candidate results remain false for owner/review approval.

Review follow-up (#303) adds7executed/killed mutants: deadline5000->5001,
clock-skew bypass on a fresh receipt, operation policy with matching expectations,
role-slot check with matching hashes, UTF8fatal decoding using real0xff bytes,
and intermediate directory type/mode independently. Deadline value is asserted
outside the rejection catcher, so a thrown mock assertion cannot mimic success.
CI entrypoint runs admission tests in an isolated bounded subprocess: direct
imports let global mocked fetch/clock interfere with concurrent Workers startup.
The isolated entrypoint preserves original runtime checks without retry/sleep.
