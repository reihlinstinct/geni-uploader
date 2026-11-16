# Independent parent-pair model proofs (#788)

Test-only follow-up to the post-merge review of #769. Each fault targets one
check without relying on a second layer to reject the same input. Synthetic
fixtures only; no credentials, network, workflow dispatch or vendor effects.

The tests pin schema and entry count, unique anchors, sibling count, entry keys,
sibling payload validation, owner name binding, path-union baseline, pre-send
and later-operation anchor checks, reciprocal created-family checks and ACK
errors that also include a valid ID. Runtime failures assert exact POST counts.

The known-name locale mismatch requires a separate source fix and regression
suite. This test-only change does not claim that guard is fixed or that live
execution is ready. Masked or unreachable request-count checks are not counted
as independently pinned.
