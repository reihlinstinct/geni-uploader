# Existing source descriptions: acceptance reconciliation (#65 / #101)

Audit base: master db610bf. Offline only. This document does not close either
issue, authorize execution, or claim a production source was repaired.

## Evidence checked

`src/geni_uploader/client/source_details.py`, English rendering in the upload
client, `tests/test_description_repair.py`, `tests/test_english_description.py`,
`tests/test_source_details.py`, `tests/test_source_details_branches.py` and
`tests/test_source_details_e2e.py`. The five listed test files were run together: 102 tests passed at this audit base.
All transport behavior here is synthetic, including the loopback end-to-end test.

## #101 acceptance

| Requirement | Current evidence | Remaining distinction |
|---|---|---|
| Author-declared English for new document/photo; optional original follows | English schema and rendering tests | English declaration is not language detection or native review |
| Separate existing-description-only path | description_only schema and apply_description_plan | Do not confuse with the general metadata/tag repair path |
| Exact identity, expected state and old description hash | checked_plan, schema, concurrent-edit tests | Hash alone is explicitly not an identity anchor |
| Durable pending; uncertainty recovers by GET, never repeated POST | journal/checkpoint, lag and lost-response tests | Full #65 acknowledgement and fresh-container requirements remain separate |
| No create/tag/delete for description-only repair | payload-only update test and preservation checks | Existing general repair capabilities are not removed |

The implementation is substantial; an independent acceptance review should decide
whether #101 can close as an offline feature without conflating it with #65.
This reconciliation alone is not that decision. No live evidence is required to
assert an offline test, and no live readiness is implied by one.

## #65 acceptance gaps

| Requirement | Current state | Next offline slice |
|---|---|---|
| Preflight exact API ID/title/URL/target/deceased | checked_plan and mismatch/living tests exist | Map each precondition to named regression cases before closeout |
| Description-only and metadata/tag preservation | dedicated updater and preserved-field equality | Confirm citation state is unsupported, not 'verified' |
| Pending write-ahead checkpoint pushed before POST | checkpoint fsync+replace+directory fsync, optional sync and sync-failure tests | geni-upload.yml passes --sync-state; retain this invariant |
| Acknowledged result persisted before readback | NOT implemented: pending checkpoint, POST, GET, then verified checkpoint | Separate acknowledged phase and crash-after-ack tests, without replay |
| Bounded lag-tolerant rate-aware readback | mismatch currently stops immediately; GET-only later reconciliation exists | Specify bounded reads/pacing and 429 stop without repeated writes |
| Fresh-container multi-document resume | plan binding and per-item pending/verified records exist | Prove clean-clone synced-journal recovery and never-attempted-only continuation |
| Fixed public-safe status and useful private diagnosis | fixed category diagnostics exist | Define private actionable stage/record reference without payloads |

Binding currently hashes the proposed items; verify it covers every expected
identity and field before considering the exact-input requirement complete.
Do not infer crash-after-ack durability from 'pending exists'. Preserve the safe
current no-replay behavior while filling the finer-grained journal states.

## Next PR boundaries

Design the acknowledgement/readback state machine first, with an explicit
failure table for crashes before and after each durable write and sync. Separate
implementation/tests from workflow or image readiness. Require synthetic tests
for every listed missing case and mutants disabling checkpoint-before-write,
no-replay, bound identity, tag preservation and 429-stop, all killed. No release,
workflow dispatch, token change or live Geni call belongs to this reconciliation.
