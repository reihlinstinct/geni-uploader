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
private readback. No uncertain write is retried. Any post-attempt exception or
undetachable readback is UNKNOWN and stops the batch, regardless of survivor flag.
Readback is JSON-detached with finite values and a 1 MiB bound before status checks.
A false, missing or non-boolean survivor flag retains that bounded raw private
JSON and stops with SURVIVOR_FLIP_REVIEW_REQUIRED, never VERIFIED. This conservative
review stop makes no claim of verified identity, data, conflict shape, remaining ID,
or a user's survivor choice. A future reviewer UI must treat this evidence as raw
unverified JSON, not a validated result. UNKNOWN may also retain raw readback.

Only with an explicitly True survivor flag can the VERIFIED checks proceed:
identity/data verified, Conflict Center checked, pending false, remaining ID one of
the two resolved IDs, and at most 256 conflicts each with exactly field, kept and
alternative and a non-empty field name at most 128 characters. Failed checks are
UNKNOWN and stop the batch. Conflicts are retained for human choice, never selected
or cleared. HTTP200 alone is not verification. Private evidence failure stops work.

The injected preflight/readback contracts still need a reviewed implementation.
Boolean assertions by an untrusted provider or caller are not source evidence.
Identity/data-preservation coverage, retained conflicts, permission-pending and
redirect semantics must be settled in that adapter before release. This slice
does not assert that the service supplies those guarantees.

## Private Git claims

The claim protocol uses a private Git branch with hash-only operation records.
An operation key binds the approval event and sorted exact proposed pair GUIDs,
not run ID, timestamps, plan digest or mutable pair label. A new run or binding
cannot reuse a consumed approval for the same pair, including after UNKNOWN.
The record still retains the full run-binding digest for private audit.
The future backend must read the current immutable head and append a child commit
with a non-force atomic reference update. Creating a blob/tree/commit is not a
claim. Concurrent writers from the same head cannot both acquire the reference.
Contention stops the current run; no retry or branch reset is exposed here.
Repository privacy, ref policy, trusted store binding, persistence after failure
and actual remote atomicity remain release checks, not simulated facts.

Tests use an in-memory backend, not a production ledger. Restart recovery and
cross-run exclusion must be tested against the released durable backend before
live effects. A local test or merged PR is neither approval nor release.
