# Protected one-parent runner (#580)

This is separate from the existing parent and sibling workflows. Merging it does
not authorize execution. Each run needs a reviewed immutable package, fresh
approval, the human environment gate and an unspent stable operation marker.

The workflow pins its checkout to the matching reviewed master commit. Its own
secret and confirmation string prevent accidental reuse of an older family
package. Actor, triggering actor, event, branch, attempt, executor SHA, raw config
hash, source commit/path and canonical decoded-plan hash are checked before vendor
construction. Owner, anchor, expected name, merge-unknown policy and expiry must
match across config and plan. There is no recovery or marker-reset option.

The runner retains the existing human gate and cross-workflow concurrency group.
Diagnostics are mandatory. Every snapshot and remote receipt is encrypted before
storage. Public logs have fixed success/stop text; failure diagnostics contain
only fixed stage/type enums and allowlisted structural status values. Artifacts
expire after one day; immutable private receipts and consume refs remain.

## Scoped effects

Only the authenticated profile, pinned existing profiles and anchor family can be
read initially. At most 24 vendor request starts are allowed, separated by at least
15 seconds. Expiry is checked again after the wait. One POST is allowed, only to
the pinned anchor's add-parent route. The original uploader and older pilots are
not changed. Fixed HTTPS host, finite response bounds, no redirects and no retry
are inherited from the reviewed transport.

A unique syntactically valid acknowledgment admits only the created profile and
its family routes. It does not verify the result. The model then validates the
profile and complete anchor graph, followed by the new parent's reciprocal graph.
Immediately before a direct union read, the runner independently revalidates the
saved full post-create anchor graph and admits exactly its one derived parent
union. Response URLs are never routes. A changed existing union, extra relative,
extra union, missing reciprocal edge or malformed node stops the run.

Permanent consume precedes the POST. Any uncertain send or failure after consume
stays consumed. No edit, delete, merge, repair or automatic retry exists.

## Unknown facts

The model can preserve null source life status, but this protected runner blocks
it before vendor construction. The vendor's omitted-field behavior has not been
proved. This is a narrow live-effect limit, not a demand for more family data:
known-status profiles can proceed, other source preparation remains unblocked.
Never replace source-unknown with a fabricated alive/deceased assertion to get
past the limit. Unknown dates and surnames are simply omitted from a reviewed
payload where its schema permits that omission.

## Before each run

1. Independently review the exact executor head and green CI, then signed merge.
2. Prepare the exact private source and config. Existing snapshots are expectations,
   not claims of current remote state; the runner rechecks them live.
3. Replay that actual package offline through this runner's real PrivateGit content
   base64 decoder and canonical decoded-plan hash checks, stopping at the vendor
   construction boundary. Raw-file ASCII escaping and Unicode canonical bytes can
   differ. Check hashes using the executor functions, never a parallel serializer.
4. Review pins, target, payload, expiry, hidden-duplicate/union-selection risks and
   permanent single-use semantics with the user. Install the reviewed secret only
   within that execution approval, then dispatch once and require the human gate.
5. Read and decrypt evidence, verify final result and remote receipts, report exact
   profiles/relations. On any uncertain outcome, stop for read-only reconciliation.

Synthetic ZZ tests exercise route admission, one POST, pacing and expiry, malformed
acknowledgments, graph-gated union discovery, entry gates, immutable-source decode,
Unicode canonical hashes, unknown-status rejection and encrypted local evidence.
They do not establish vendor behavior or constitute execution approval.

## Environment surface

`PARENT_CONFIG_JSON` contains the private config; `PARENT_CONFIG_SHA256` pins its
raw bytes. `PARENT_EXECUTOR_SHA` must equal the checked-out workflow commit.
`PARENT_CONFIRM` must be CREATE_APPROVED_ONE_PARENT. `PARENT_DEBUG` must be 1 or
true, never absent/false. `PARENT_OUTPUT_DIR` is a new absolute encrypted-output
directory. `PARENT_TREE_PAT` is the private immutable-source/evidence credential,
not a vendor credential. The shared secondary vendor token remains separately
scoped to the fixed vendor host. None of these secret values belongs in public
logs, issue prose or review messages.

The model's non-runnable metadata is overridden in encrypted runner snapshots:
mode=protected_one_parent and production_enabled=true identify a real protected
attempt, including stopped attempts. That flag describes the execution context,
not authority or success. Terminal phase and receipts determine verification.
