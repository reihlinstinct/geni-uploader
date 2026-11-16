# Boundary edges and existing-parent reconciliation (#585)

An immediate-family response contains its focus, relatives and relevant unions.
A relative node may retain edges to known unions whose nodes are outside that
response. The old reciprocal-parent check wrongly rejected the existing child's
already-pinned spouse-union edge after successful creation. The create cannot be
retried: an acknowledged profile and permanent consume marker already exist.

The fixed check accepts only exact external edges derived from the approved full
family graph, for profiles present in the smaller response. Node membership and
internal edges stay exact. Missing known edges, unknown union edges, changed
roles, extra relatives and extra union nodes still stop verification. No response
can expand this approved boundary. Synthetic regressions cover these cases.

The separate reconciliation runner cannot create, consume, reset or write remote
receipts. It checks immutable source/config/executor pins, existing consume and
acknowledgment refs, and exact configured existing profile/union IDs. Ref presence
is not proof of a correct profile. It reads owner identity, every pinned existing
profile, the created profile, full anchor graph, reciprocal parent graph and direct
union, checking all fields/roles/members before READ_ONLY_VERIFIED. It preserves
the original failed-run receipts rather than replacing their history.

Its vendor routes are fixed GET-only, one use each, bounded to 20 request starts,
with 15-second start pacing and expiry checked after waits. It uses the same human
environment gate, concurrency group and mandatory encrypted local snapshots.
Fixed logs contain no response values. A successful reconciliation is evidence of
existing state, not a second creation, retry permission or a hidden final receipt.

The config adds created_id and union_id to the exact original parent config. The
source remains the original consumed immutable plan. A new executor/config hash
and fresh explicit read-only go are needed before dispatch. A different source
expiry cannot silently masquerade as the consumed plan. If that original window
expires, stop and design a separate reviewed verification window rather than
changing the original package or resetting its marker.

`RECONCILE_CONFIG_JSON` is the private config; `RECONCILE_CONFIG_SHA256` pins raw
bytes. `RECONCILE_EXECUTOR_SHA` pins the reviewed workflow commit.
`RECONCILE_CONFIRM` is READ_ONLY_EXISTING_PARENT; `RECONCILE_DEBUG` must be true or
1. `RECONCILE_OUTPUT_DIR` must be a new absolute encrypted-output directory.
`RECONCILE_TREE_PAT` provides the private immutable-source/ref reads, not vendor
access. The separate secondary token is sent only to the fixed vendor host.

After independently reviewing/decrypting the result, a later new-parent proposal
can pin the verified profile and union. It still requires its own source/config,
offline replay, review and user approval. Never rerun the already-created parent.
