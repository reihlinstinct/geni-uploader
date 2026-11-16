# Worker signed release verification (#417)

Dormant verification-only port of the existing Node exact father-policy verifier.
No signing, private key, route, issuer composition, namespace authentication,
account change or replacement of the closed gate. A valid signature proves key
possession and matching content, not owner authority or installed provenance.

The Worker module has no imports and uses only WebCrypto, TextEncoder and base64
primitives. Exact binding/run/attempt/namespace/source pins, canonical wire JSON,
bounded body, count1, expiry<=900s, key digest, canonical Ed25519 SPKI and signature
are checked. Public-key import is non-extractable and verify-only. Canonical
RFC8410 SPKI is exactly44bytes with parameter-free Ed25519 algorithm identifier.
Errors disclose fixed text only. Expiry is checked again after all crypto awaits;
no clock-skew grace or queued pre-expiry request extends the window. Inputs must
come from deployment-owned config, not caller body keys/pins.

Synthetic ephemeral-key envelopes are evaluated by the existing Node verifier
and inside real workerd, no Node compatibility. Cases cover valid900s boundary,
wrong key/signature/config/context, every policy field, changed operation pins,
unknown fields, malformed/noncanonical wire and expiry/window failures. Test
harness uses Node crypto to make synthetic fixtures; Worker bundle does not.
The Worker intentionally uses strict string-end matching and final freshness
recheck; it need not reproduce Node regex trailing-newline edge behavior or
allow expiry while asynchronous crypto is pending.

This establishes runtime/signature compatibility only. Full issuer workload,
complete approval/source/review/CI verification, authenticated installation audit,
versioned Worker identity, SQLite internal wrapper, bounded total subrequests,
private receipts/handoff, key provisioning and whole-bundle CPU proof remain
required. No provider deployment or real key is used by these tests.

## Await-expiry regression (#419)

A real-workerd synthetic test pins time within the valid window, awaits actual
Ed25519 verification, then advances its test-only clock to exact expiry before
returning the crypto result. The unmodified verifier rejects with fixed text.
A still-valid control succeeds; a test-only bundled mutation deleting only the
final freshness check incorrectly succeeds on the crossing case, proving that
the regression exercises that check. Crypto verification is actually called once
in each control/crossing path. No production clock injection or code change.
