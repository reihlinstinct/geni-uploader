# Protected-job age encryption and private persistence

Integration choice: keep the existing age CLI encryption and private Git write
in the protected GitHub job. The Durable Object service will own authenticated
routing, permanent intent and the single vendor POST. That service must validate
immutable pre-write evidence and its credential/run binding before any POST.
Neither part is released here, and no executable workflow is installed.

This is compatible with `intent-storage-decisions.md`: public hosted runner,
existing private Git ciphertext storage and independent owner-global intent.
It does not use the OAuth custody sealed box as an evidence cipher or add a new
cryptography dependency. The reviewed job must supply the existing pinned age
binary through a controlled PATH. Merely finding a binary named age is not
proof of its provenance. Existing pin: v1.3.2 with SHA256
`cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10`.

`persistProtectedJobEvidence` reads canonical reviewed configuration, recipient,
storage pins and private credential from the job environment. It checks run
context and recipient fingerprint before spawning age with a fixed argument
list, sends bounded private plaintext only through stdin and captures bounded
ciphertext in memory. No plaintext file or log is created by this function.
Age failures, timeout and oversized ciphertext stop before Git persistence. No
plaintext fallback exists. Ciphertext is passed to the existing bounded private
Git writer, which reads the exact remote bytes back before returning the opaque
descriptor. Partial persistence receipts survive error wrapping; there is no
retry, reset or Geni route here. A failure never clears permanent intent.

The local joined test generates a synthetic age identity, runs actual age
encryption, mocks the eleven private Git API requests, verifies remote byte
readback and decrypts the resulting bytes back to the exact synthetic plaintext.
It makes no live Git writes. Without an explicit test identity and age binaries,
that crypto rehearsal is skipped, not reported as passed. The ordinary invalid
config test still runs. The existing offline CI job installs the exact pinned age release, creates a
synthetic identity, runs the joined test and removes the test identity on exit.
It adds no permission or production credential, and does not install the
protected approval workflow.

Remaining integration: durable intent stage transitions, authenticated cumulative
byte ledger, private approval record writer, immutable evidence admission and
credential binding at the service, then fixed vendor POST/readback. Configuration
hash equality and a returned descriptor do not authenticate those missing parts.
