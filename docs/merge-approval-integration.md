# Protected merge approval integration draft

Issue #827. This slice adds a bounded JSON HTTP transport, a fresh protected-run
snapshot reader and a workflow draft under docs, not installed workflows. It does
not dispatch, approve a deployment, change environment settings, initialize a
ledger, install credentials or open the merge engine's unconditional release gate.

## Exact source and content checks

The transport pins one of the two expected HTTPS origins, rejects redirects,
non-success statuses, pagination, oversized bodies, duplicate JSON keys, invalid
UTF-8 and non-finite JSON numbers. Credentials enter privately as a constructor
argument, never from a proposal or URL; exceptions have fixed messages. Calls are
one attempt only. A 429 stops that call; orchestration must stop the whole task,
not continue a batch of other calls.

The reader uses the pinned GitHub transport and existing strict run/environment/
approval/branch snapshot checks. It also requires an active attempt-one run title
bound to the reviewed private intent digest and exact workflow bytes fetched at
the run's executor commit. The dispatcher and sole human reviewer differ; required
human review, prevent-self-review, no admin bypass and exact branch policy remain
mandatory. Approval-looking text is not a grant.

The returned record explicitly keeps post_permitted=false and lists unresolved
release gaps. A fresh matching snapshot is not by itself production authority.
Reviewed immutable pins, full private intent matching, job/attempt correlation,
revocation/TOCTOU handling and effective rule protection still need integration.
Caller-supplied pins must never be accepted as trusted expectations.

## Workflow draft

The draft has only workflow_dispatch and hash/commit inputs. Its run title binds
one private intent digest, which must cover exact profiles, order, data snapshot,
owner, code, workflow, private commit and expiry. Runtime run/attempt/approval
identity complete the binding after dispatch. The human reviews that same private
intent before approving its protected execution job. No living-person data belongs
in workflow inputs, public logs or public artifacts.

The first and only step exits with the release closed. It has no secrets or effect
path. The final release must install reviewed validation, durable signed claims,
private encrypted evidence, one-attempt provider transport and identity/data/
Conflict Center readback before that stop can be replaced. No automatic field
resolution is allowed. Failure to prove preserved data is UNKNOWN, not success.

## Transport and source regressions

JSON float parsing rejects overflow to infinity as well as non-finite literals;
ordinary finite floats remain valid. Independent cases cover the active run's
null conclusion, exact HTTP client type and GitHub origin, workflow encoding,
path and file type, lowercase hexadecimal intent shape, and GET bodies before
any request. A real urllib opener is tested against an ephemeral loopback-only
redirect server: one request, a fixed HTTP error, and no follow-up. No external
service or credential is used by that test.

The transport explicitly disables environment-derived proxies with
`ProxyHandler({})`. Its actual client opener must install the no-redirect handler;
a regression sets ambient proxy variables and checks the constructed client.
Only direct requests to the configured allowed origin are supported. This is
not certificate pinning or evidence of a reviewed live connection.
