# Inner NFC collision regression

Test-only follow-up to #800's post-merge review. A stored alias can have
noncanonical combining-mark order even though additions must be NFC. Inner NFC
orders marks before casefold maps U+0345 to U+03B9; outer NFC alone can then
compose a different vowel and miss the collision.

The regression uses escaped synthetic text, checks rejection against the NFC
spelling, and verifies that input bytes remain unchanged. Removing only inner
NFC makes this behavioral test fail. No source-hash test is counted as the kill.
Production code, normalization policy, stored/proposed text, workflows and
permissions are unchanged. No credentials, network, live calls or dispatch.
