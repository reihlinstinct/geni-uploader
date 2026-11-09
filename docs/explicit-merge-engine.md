# Explicit merge engine: closed implementation slice

Issue #823. This coordinator is not a runnable merge workflow. The public execute
entry point always calls the closed live release gate before any adapter. There
is no network transport, credential reader, installed workflow, authenticated
approval capture, private result writer or configured durable backend here.

## Binding and dispatch

Admission binds proposal digest, private data commit, executor commit, workflow
bytes, resolved-plan digest, owner/dispatcher/reviewer, run/attempt, approval-event
digest and expiry. The dispatcher must differ from the sole human owner/reviewer;
attempt must be one. Caller-supplied equal dictionaries prove content consistency,
not authorship, permission, effective protection or revocation. The future release
adapter must recover trusted expectations and effective GitHub environment rules.
No existing workflow or environment configuration changes in this slice.

## One attempt and private evidence

Synthetic coordinator tests exercise this sequence: fresh admission and exact
pair preflight, durable single-use claim, private CLAIMED evidence, one POST,
private readback. No uncertain write is retried. Any post-attempt exception,
pending result, unverified identity/data or unchecked Conflict Center is UNKNOWN
and stops the batch. A retained conflict is reported for human choice, never
resolved by this coordinator. Remaining ID must be one of the two resolved IDs;
HTTP200 alone is not merge verification. Unavailable private evidence stops work.

The injected preflight/readback contracts still need a reviewed implementation.
Boolean assertions by an untrusted provider or caller are not source evidence.
Identity/data-preservation coverage, retained conflicts, permission-pending and
redirect semantics must be settled in that adapter before release. This slice
does not assert that the service supplies those guarantees.

## Private Git claims

The claim protocol uses a private Git branch with hash-only operation records.
The future backend must read the current immutable head and append a child commit
with a non-force atomic reference update. Creating a blob/tree/commit is not a
claim. Concurrent writers from the same head cannot both acquire the reference.
Contention stops the current run; no retry or branch reset is exposed here.
Repository privacy, ref policy, trusted store binding, persistence after failure
and actual remote atomicity remain release checks, not simulated facts.

Tests use an in-memory backend, not a production ledger. Restart recovery and
cross-run exclusion must be tested against the released durable backend before
live effects. A local test or merged PR is neither approval nor release.
