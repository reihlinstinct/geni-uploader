# Preserve failed graph proof evidence

The adapter now sends a raw family response to the existing encrypted checkpoint
writer before inspecting graph proof. A failed exact anchor graph check also
retains a fixed failure code, node-set equality boolean, expected graph and
approved external edges. No exception text or raw values enter public logs.
The encrypted raw response permits private comparison of edges and identities.

Failure to encrypt/save is itself terminal. The pending send latch remains shut,
consumed marker and acknowledged receipts are unchanged, and no next create,
retry, automatic repair, merge or profile update follows. This change does not
fix route choice or already-created relationships. Synthetic regressions prove
raw mismatch capture before STOP and storage failure preventing another send.
Closes #674.
