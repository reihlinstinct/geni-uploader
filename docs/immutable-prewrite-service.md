# Immutable pre-write evidence service join

The local-only intent service now requires immutable private pre-write evidence
readback before routing to the owner Durable Object consume transaction. It
checks the evidence's exact owner, connection, plan, payload, artifact, policy
and run binding against its own reviewed configuration. The exact service-held
secondary credential fingerprint must match the evidence configuration too;
a matching token hash does not independently prove its Geni owner identity.

`verifyImmutablePrewriteEvidence` reads only four fixed GitHub API resources:
private repository by numeric ID, immutable commit, root tree and exact blob.
It verifies private status, expected full name, ordinary root blob membership,
immutable commit and blob IDs, ciphertext byte length, SHA256, Git SHA1, exact
base64 bytes and an age header. Manual redirects are never followed. Bounded
streams, no pagination, a ten-second deadline and no retry apply. No request
supplies a destination, token, repository or evidence descriptor.

The returned result proves remote byte consistency and the configured credential
binding only. The age header is not encryption provenance or proof that the
recipient can decrypt. Configuration provenance, authenticated protected-job
capture, private record creation, token-self owner proof and an authenticated
cumulative byte ledger remain release requirements. This module does not give
a POST permit, and the joined service remains explicitly local-only.

The real local workerd SQLite rehearsal now makes mocked fixed-issuer JWKS and
private immutable Git reads through the actual service before consume. Valid JWT
with mismatched credential/evidence blocks without consuming. Concurrent calls
still consume once and restart still cannot consume again. All external data is
synthetic; no private repository or Geni write occurs. Tests of header/byte
checks are distinct from the real age encrypt/decrypt test in the protected-job
boundary. No production namespace or configuration is installed by this work.
