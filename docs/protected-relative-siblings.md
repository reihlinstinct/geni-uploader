# Protected relative-sibling executor (#590)

Separate entry point for the reviewed bounded relative-sibling model (#588).
No old pilot or parent entry point is widened. Engineering tests use only invented
ZZ fixtures; merging this code does not approve or dispatch a live package.

## Admission

The manual workflow requires master, exact executor SHA, exact private config
SHA256, debug enabled, first attempt, the expected repository and dispatcher
identity, and CREATE_APPROVED_RELATIVE_SIBLINGS. Its father-create environment must
retain the required human reviewer, prevent self-review, disallow admin bypass,
and allow master only. Verify those live settings before installation/dispatch.
Shared concurrency prevents overlapping family effects and never cancels a run.

RELATIVE_SIBLINGS_JSON is isolated from earlier package secrets. It binds private
repo, immutable signed source commit/path, owner, child anchor, parent union,
expected owner name, recipient, expiry, risk flags and canonical decoded plan hash.
The runner checks source privacy and decoding/hash/schema, then cross-checks all
shared scope fields before constructing vendor credentials. Existing profiles
must have explicit status; new siblings must be living/private. No omission-based
unknown-status behavior is introduced.

## Finite effects and evidence

Only fixed-host GET routes for approved profiles, the anchor, acknowledged new
profiles and the pinned union are admitted. Only add-sibling at the approved child
anchor may POST. Payloads must match entries in order, with at most one send per
entry and at most 40 vendor requests per run. Fifteen-second minimum pacing and
expiry are checked again after waits. Unknown or malformed sends leave the pending
latch closed; no retry exists. A later send is admitted only after exact complete
anchor graph, reciprocal graph and direct union readback complete for the prior ID.

The model persists before/consume/ack/final receipts, stable across expiry changes.
Encrypted local snapshots are fsynced and uploaded even after a stop; remote
receipts use the existing create-only private evidence store. GET failure details
are structural and encrypted only. POST failure details do not retain response
bodies, provider text or exact status. Fixed stdout messages contain no data.

## Required operational sequence

1. Review and merge signed exact-head code with green CI; inspect live protection.
2. Ground private family data and approvals, pin the exact fresh baseline, source
   commit, expiry and hashes. Preserve unknowns rather than guessing.
3. Replay actual source/config decoding and canonical hashes through this runner
   to the vendor-construction boundary without network; simulate post-create
   verification separately. Independent exact-package review is required.
4. Obtain fresh owner approval of that package and risks. Only then install its
   isolated environment secret and dispatch once; the human approves GitHub's gate.
5. Monitor the exact run, decrypt final evidence and inspect durable receipt refs.
   On uncertainty stop and report, never reset a marker or rerun the create.

No production secret is installed, deleted or changed by this PR. The current
private proposals remain non-runnable until the operational sequence is complete.

## Environment contract

`RELATIVE_CONFIG_JSON` contains the isolated private config; `RELATIVE_CONFIG_SHA256`
pins its raw bytes. `RELATIVE_EXECUTOR_SHA` must equal GITHUB_SHA.
`RELATIVE_CONFIRM` is CREATE_APPROVED_RELATIVE_SIBLINGS; `RELATIVE_DEBUG` must be
1 or true. `RELATIVE_OUTPUT_DIR` is an absolute new directory for encrypted files.
`RELATIVE_TREE_PAT` is the private evidence credential used only by GitHub reads
and create-only receipt/consume writes. No value belongs in public logs or docs.


## Exact spouse boundary pins

An optional `external_edges` map may pin one omitted parent-union `child` edge
for the anchor's existing spouse in the owner union. It never admits owner,
anchor or other-relative boundaries, partner roles, known unions or traversal.
Plans without the field retain their behavior. Full anchor graph equality checks
preserve the pin before send and after every create. The protected transport
also revalidates the cached pin before a successful direct union read can reopen
the next-send latch. Missing, changed, extra or materialized boundary edges stop
the batch. Existing route sets, request caps, pacing, approval gates and stable
consumption markers are unchanged. Earlier verified creates remain created if a
later item stops; no retry, rollback or automatic resume is introduced.
