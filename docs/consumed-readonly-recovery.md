# Gated read-only consumed-operation recovery (#356)

The dormant authenticated `/recover` route uses the same fixed signed workload,
plan, run and expiry, canonical owner object and existing consumed intent. The
unchanged unconditional release gate blocks before storage or vendor requests.
In test-only released rehearsal it snapshots the existing intent/ledger/receipt
and collects fixed GETs only: token-self, owner immediate family, and if a created
ID was durably acknowledged, that profile plus its observed matching union.
No arbitrary URL or request-supplied created ID is accepted.

The private result preserves partial evidence and known created ID, no retries,
no reset and no VERIFIED transition. With a lost acknowledgment, an observed new
parent is not assigned as created ID. Identity remains unresolved even if family
observations contain a plausible parent. Read success is not reconciliation of
identity, correct private fields or intended relationship. No intent/ledger state
is changed by collecting observations. Returned private evidence still needs a
separate encrypted recovery storage handoff before any durable result claim.

Three focused tests prove the shipped gate blocks before effects, and real SQLite
rehearsal both with/without acknowledged ID performs only bounded GETs and retains
identical intent across restart. Authenticated service test also proves no vendor
call under the shipped gate. Actual external calls, config, deploy and recovery
permission are not performed. Original workload expiry is not extended; later
recovery requires separately reviewed explicit recovery authority, not recycling
an expired approval. Persistent storage/recovery handoff remains open.

## Reservation failure after execution (#359)

`runProtectedFatherJob` (`oauth-bootstrap/protected-father-runner.mjs`) runs:
journal `execute_attempt`, one `/execute`, then `/reserve`, then the postwrite
age upload (`persistPostWriteHandoff`) and `/complete`. The reservation is after
the executor and before any postwrite ciphertext exists. It fails when the
service rejects it or its response is lost. Either way the runner stops with
`execute_attempted: true` ("create may have been consumed, never replay") and
the journaled job writes a `stopped` event with `execute_attempted: true`,
`retry_allowed: false` ("inspect only, never replay create").

State left behind:

- Intent: consumed by `executeDurableFather` before the vendor POST, then moved
  to `uncertain` on its success and caught-failure paths (if that transition
  itself fails the intent stays `consumed`/`acknowledged`, and `/reserve` then
  refuses because it requires `uncertain`). The create may have happened even
  when the executor response reported `consumed_uncertain`.
- Created ID: known only if the acknowledgment was saved. It is written to the
  durable intent (`advance(..., 'acknowledge', ..., created)`) right after the
  POST response; with a lost acknowledgment `created_id` stays `null`. The
  runner held the ID only in memory: neither its private journal (`created_id`
  appears only in `completed`) nor its thrown error carries it.
- Ledger: only the `pre_write` evidence object and its bytes.
- Reservation: none if rejected or its write fails (the transaction writes
  nothing); `reserved`, with the pre-write total as `prior_total`, if the
  response was lost after commit. There is no release/reset; a second
  `/reserve` is refused.
- No private postwrite ciphertext: no readback journal event, no upload of the
  postwrite object and no `postwrite-receipt`.

Recovery must inspect, never replay. A second execute is refused because the
intent already exists (`consume` requires none), and a fresh journaled
invocation is refused because the private journal directory/file already exists,
before any service or storage request. The read-only path is
`inspectPrivateRunJournal` plus `/recover` (`collectDurableFatherRecovery`,
blocked by the shipped release gate and rehearsed only with the test-only gate
replacement): it snapshots intent/ledger/receipt and makes fixed GETs only,
reports the saved ID if any, and with a lost acknowledgment keeps identity
unresolved even if a plausible new parent is observed. Recovery observations do
not reconstruct a missing acknowledgment or prove a matching new parent is the
one this run created. Original expiry still applies; no expired run is revived.
Recovery evidence does not include the reservation record, so it cannot tell a
rejected reservation from a committed one whose response was lost; nothing here
resumes the postwrite upload.

Rehearsed offline with synthetic values: real SQLite executor tests (saved and
lost acknowledgment, each with a rejected and a lost-response reservation) and
journaled runner tests with the synthetic age key (lost and rejected `/reserve`).
Not verified: the authenticated service routes for this sequence (tests call
the executor functions directly), Worker storage beyond local Miniflare
SQLite, and any live service, vendor or GitHub behavior.

## One-shot reservation after a lost response: deliberate (#808)

Decision: a run whose `/reserve` committed but whose response was lost cannot
admit its postwrite receipt through the reviewed runner. This is intentional
for the release-gated one-shot pilot, not an oversight.

Why it holds today (`oauth-bootstrap/durable-father-executor.mjs`):
`reservePostwriteBudget` refuses when any `postwrite-reservation` exists, and
nothing releases or resets a committed one. The runner
(`oauth-bootstrap/protected-father-runner.mjs`) stops on the lost response,
and the journaled job (`oauth-bootstrap/journaled-father-job.mjs`) refuses a
fresh invocation because its private journal already exists. So the postwrite
upload and `/complete` (`admitPostwriteReceipt`) never run for that run. The
only path left is read-only inspection, as described above.

Two related gaps are pinned by characterization tests, named
"pins current gap (#808 finding N)". A change that removes a gap must flip its
test on purpose:

- Finding 1: the `/recover` snapshot carries intent, ledger and receipt but not
  the reservation, so its evidence is identical whether a reservation committed
  or none exists (`oauth-bootstrap/consumed-readonly-recovery.test.mjs`).
- Finding 3: at this failure point the created ID is in the service-side durable
  intent only. The runner's thrown error, its progress receipts and its private
  and remote journals do not carry it
  (`oauth-bootstrap/protected-father-runner.test.mjs`).

What a future recovery path would need (suggestions, not designed or reviewed):

- An authenticated, read-only reservation status read (phase, `prior_total`,
  `byte_limit`, run and recipient), or the reservation added to the `/recover`
  snapshot, so recovery can tell a committed reservation from a rejected one.
- An idempotent re-admit keyed on the committed reservation (same binding, run
  and recipient, and the ledger total still equal to `prior_total`) instead of a
  second `/reserve`. It must never replay create.
- Evidence for it: the reservation record, the saved created ID from the
  durable intent, and the runner journal showing `execute_attempt` then
  `stopped`. Any such path also needs its own explicit recovery authority; the
  original approval and its expiry are not reused.
