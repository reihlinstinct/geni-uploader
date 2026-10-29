# Offline ciphertext evidence descriptors, caps and readback

For #257. Pure module `ciphertext_evidence.py`. It follows
`intent-storage-decisions.md` (Decision 2). There is no network access, no
repository writer, no key, no storage service and no gate change. Tests use
synthetic bytes only.

## What it checks

- **Descriptor:** exact keys, schema `geni-evidence-ciphertext-v1`, and a known
  stage (`pre_write`, `acknowledgment`, `readback`, `reconciliation`). It also
  carries:
  - the SHA256 (64 lowercase hex);
  - the exact byte length, 1 byte to 1 MiB;
  - the recipient fingerprint and operation binding (64 hex each);
  - the run ID, with run attempt 1;
  - the git blob ID and commit (40 hex each);
  - `production_enabled` False.
- **Bytes:** the supplied local bytes must match the length, the SHA256 and the
  git blob ID exactly. Empty, oversize and plaintext-shaped bytes are rejected.
  Plaintext-shaped means a JSON/XML/PEM/PDF/ZIP/BOM prefix, or mostly printable
  UTF-8 text.
- **Accounting:** an immutable per-operation ledger, bound to one exact
  operation, run and recipient.
  - Objects are only ever added.
  - Duplicate or conflicting objects (same SHA256 or blob ID) are rejected.
  - The running total is checked against the 8 MiB operation cap.
- **Readback:** the read-back bytes must pass the byte checks, and the remote
  commit must equal the descriptor's commit exactly.
  - The result is fixed: `content_consistent: true`, `ciphertext_proved: false`,
    `retention_proved: false`, `authority: false`.

## Caller responsibilities and known limits (#277)

- **Binding.** `check_bytes` and `verify_readback` check only that the
  descriptor is well-formed and matches the supplied bytes (and, for readback,
  the exact commit). They do not compare stage, operation binding, run ID or
  recipient against any expected value: the caller pins those before relying on
  a result. `account()` compares operation binding, run ID and recipient
  against the ledger; it does not check stage. No result is authority.
- **False rejection.** The plaintext screen is a heuristic. Under an explicit
  model of independent uniformly random bytes (real formats carry fixed
  headers, so this is a model, not a claim), the single-byte prefixes `{`, `[`
  and `<` reject about 3/256 (1.17 %) of objects of any size. The other
  prefixes are negligible (BOM 2^-24, `%PDF` and the ZIP header 2^-32 each,
  `-----BEGIN` 2^-80). The mostly-printable branch is bounded by the chance
  that strict UTF-8 decoding succeeds: 9.4e-5 at 16 bytes, 1.0e-8 at 32 bytes
  and 1.1e-16 at 64 bytes. So the whole false-rejection rate is the 1.17 %
  prefix contribution plus these terms, which are negligible from about 32
  bytes up and large for very small objects. Passing the screen is never
  proof of encryption.
- **Scalar contract.** Scalars are checked by exact type, never by
  truthiness or equality alone: `production_enabled` must be the bool
  `False` (0, 0.0, None, empty values and `True` are rejected);
  `schema_version`, `run_attempt`, `byte_length` and the ledger's
  `total_bytes` must be `int` and never `bool` (`False == 0` and
  `True == 1` are still rejected). LF, CR and TAB count as printable in the
  plaintext screen.
- **Object dedup.** The ledger counts unique stored objects per operation, so
  the same bytes cannot be accounted twice under different stages. That is
  intended. Readback verification does not go through the ledger, so an
  accounted object can still be read back and verified.

## What it does not prove

It does not prove that the bytes are real ciphertext, that the recipient can
decrypt them, that the object is privately retained remotely, who uploaded it,
or any authority. Header screening is not proof of encryption or of the
correct recipient. Upload acknowledgment or metadata alone is not readback.

A failure after intent keeps the consumed or uncertain state. It never leads to
a retry, reset, delete or merge, and never falls back to plaintext. The 1 MiB
and 8 MiB caps are candidates that still need reviewed real-schema and
encryption-overhead validation before release.
