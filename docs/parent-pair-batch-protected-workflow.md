# Protected parent-pair batch workflow

Refs #772. Separate manual entry point for the reviewed model and adapter.
Code merge is not live authority. No package is installed by this change.

## Gates and private admission

The exact actor, repository, master branch, first attempt, executor SHA, raw config
SHA256, required debug mode and CREATE_APPROVED_PARENT_PAIR_BATCH confirmation
are checked before effects. The isolated package secret (named in the workflow) binds an
immutable private source commit and canonical decoded plan/audit hashes. The real
PrivateGit/base64 source boundary checks all identities, operation payloads,
risk policies, exact budget, source and prior-operation audit references before
vendor construction. A changed source or config fails closed.

Use the existing father-create human environment and shared mutation concurrency.
Verify its effective human reviewer, no self-review, no admin bypass and master-only
branch restriction live before an approved package installation. Neither a merge
nor a GitHub environment approval approves facts or risks by itself. Each exact
package needs independent review, actual-package replay and user approval first.
Existing/new omitted-merge allowances remain separate. Positive state always stops.

PAIR_DEBUG, PAIR_CONFIRM, PAIR_CONFIG_JSON, PAIR_CONFIG_SHA256, PAIR_EXECUTOR_SHA,
PAIR_TREE_PAT and PAIR_OUTPUT_DIR are isolated runner inputs. The secondary vendor
credential remains fixed-host only. No secret or private source value is logged.
Encrypted fsynced local evidence and create-only private receipts survive STOP.
No retry, resume, reset, repair, rollback or compensating deletion is available.

## Budget and runtime inventory

At most 120 vendor request starts include POSTs, repeated context reads and all
proofs. Each exact package must fit the model inventory and configured maximum,
not just the hard ceiling. Fifteen-second minimum start spacing makes a full
120-call run take at least 1785 seconds of waiting, about 30 minutes before other
latencies. Smaller packages use their own count. This is not a completion promise.

Conservative transport accounting per request allows 20 seconds socket/header
work and 30 seconds whole-response deadline. A maximum vendor run therefore has
120 * 50 seconds plus 119 * 15 seconds, or 7785 seconds (129.75 minutes).

Immutable plan and audit admission take four private GitHub GETs. Each of at most
nine people has before/ack/final receipts: each receipt uses POST tag, POST ref,
GET ref and GET tag, or twelve requests; consume uses POST ref and GET ref, adding
two. Thus private-store inventory is 4 + 9 * 14 = 130 calls, at most 6500 seconds
(108.34 minutes) under the same conservative per-call allowance. Total nominal
transport/pacing bound is 14285 seconds (238.09 minutes). A 20-minute setup/artifact
margin brings it to 258.09 minutes, inside the 300-minute job timeout.

The timeout is a bounded slow-response safety margin, not expected runtime and
not permission to retry. Expiry is checked through the model, transport and waits.
The final package expiry must cover its approved window and execution margin.
Timeout or any uncertain/storage/proof failure stops permanently consumed items;
report partial verified results and acknowledged IDs. Retain encrypted artifacts
with always() and one-day retention, and durable private receipt references.

## Tests and release sequence

Offline tests cover exact workflow gates, no credential construction for invalid
entry inputs, real immutable/base64 decode before vendor construction, source
mismatch, simulated complete execution with encrypted snapshots and fixed public
output. Adapter tests separately prove the independent next-send latch and route,
payload, budget, pacing and proof checks. Installed-wheel tests include the runner
and import it outside the checkout without network.

After exact-head independent review and green CI, merge normally with a signed
merge. That still does not install/dispatch a package. Prepare fresh source facts,
complete path evidence and overlap audit; replay the actual source/config through
this entry point to the vendor boundary offline. Review exact pins, operations,
uncertainties, time budget and permanent consumption with the user. Only their
approval permits secret installation and one manual dispatch. The human then
approves GitHub's environment gate. Monitor, decrypt and reconcile exact results.

## Explicit claimed field (Refs #774)

The batch-local profile projection explicitly requests `claimed`, including the
owner, path profiles and created-profile proof reads. The historical pilot field
constant omits it and remains unchanged for legacy runners. Route admission and
the batch IO use the same local projection. A response that still omits claimed
continues to stop: it is never filled from an older receipt or treated as false.
No boolean checks, exact pins, budgets, proof latches or retry rules are relaxed.
A transport projection fix needs a newly reviewed executor and a fresh exact
package approval before another protected run; no automatic rerun is authorized.
