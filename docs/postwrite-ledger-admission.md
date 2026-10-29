# Immutable post-write receipt admission (#341)

Dormant local service adds `/complete`. It accepts a fixed-issuer signed workload
JWT, exact plan and one immutable ciphertext descriptor. The reviewed deployment
policy supplies the private numeric repository, owner/name/root path, full
execution binding, recipient hash and secondary credential hash. The request
cannot choose a destination. All seven binding fields including run must match.
The same bounded four-request immutable Git readback as prewrite admission checks
private repository identity, commit, exact tree entry, canonical blob content,
length, SHA256, Git object SHA1 and age header. Readback is ciphertext identity,
not proof of decryption, recipient or provider-content correctness.

Only the authenticated module's verified descriptor/source reach the canonical
owner object. One SQLite transaction requires the same permanent uncertain
intent and existing prewrite ledger, rejects duplicate receipt/hash, derives the
cumulative total from recorded objects (8MiB cap), appends the receipt and stores
the full immutable source and descriptor for later recovery. Concurrent attempts
admit one receipt. Replay after restart rejects without changing intent or
repeating the create. The receipt returns
`ciphertext_receipt_accounted_reconciliation_required`, never VERIFIED.

This joins post-write persistence back to durable accounting. The original
uncertain intent and known created ID remain authoritative. It does not reserve
remote storage budget before upload, prove decrypted contents, recover a lost
service response, or reconcile a vendor-created profile. Those still need the
joined runner and read-only recovery implementation before release. Expiry stays
fail closed; a late recovery needs a separately reviewed recovery authorization,
not relaxed original workload expiry. There is no reset, delete or replay route.
The shipped create release gate remains unconditional and unchanged.

Synthetic tests cover fixed immutable readback, all seven binding mutations,
wrong stage/recipient/schema/commit, signed authenticated service completion and
real SQLite atomic admission across concurrency/restart and each vendor response
loss boundary. No external mutation, provisioning, workflow permission, credential
change, release or deployment is performed.
