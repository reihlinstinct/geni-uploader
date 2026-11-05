# Independent parent-pair adapter proofs (#789)

Test-only follow-up to the post-merge review of #771. Synthetic fixtures only;
no credentials, real transport, workflow dispatch or vendor effects.

Independent faults target the plan hash, audit plan hash, owner, schema, risk
references, operation count, anchor, kind and payload hash. Audit bytes are
re-signed in each case so a mismatching audit hash cannot mask the intended
check. Config tests cover overlap with data path, request range and boolean
policy typing. Request budget tests isolate inventory, configured and hard
ceilings. Later-operation anchor and pending union-target tests assert a closed
latch and exact POST counts. ACK tests assert rejection but are not claimed as
independent mutation kills when the model checks mask the adapter checks.

Cross-group boundary propagation needs a fixture with overlapping anchor
visibility. A separate assertion below checks the resulting boundary state;
existing disjoint four-group success alone does not prove this branch runs.
