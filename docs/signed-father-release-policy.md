# Signed exact-run policy verifier (#370)

Dormant `verifySignedFatherRelease` verifies canonical exact policy bytes with an
Ed25519 signature and deployment-pinned SPKI public key/key digest. It accepts no
request-supplied key. The policy binds owner/connection/plan/payload/artifact/policy,
run/attempt1, canonical namespace ID, source service/executor/workflow SHAs,
random grant ID, count1/single-father operation and <=15-minute validity. Required
fields, key type, canonical encoding and expiry fail closed. Returned diagnostics
still say post_permitted:false/production_enabled:false.

It is NOT wired to or a replacement for the unconditional production gate yet.
No private release key, public key pin, signing account or grant is provisioned by
this PR. Test keys exist only inside synthetic tests. Signature verification proves
key possession, not the owner's consent, independent review or the authenticity of
deployment config. Those checks and the exact signing/issuance workflow remain
required before a reviewed gate adapter can use this module.

Proposed signing custody for the later exact manifest: a dedicated Ed25519 release
key stored as a private secret in a separately authorized private release-issuer
job, not the public runner, Worker or request body. The Worker holds only public
SPKI/key ID. Issuance must verify actual signed workload identity, the single human
protected-environment approval, exact reviewed immutable source/artifact/static
plan, namespace and expiry before signing one run. That issuer is NOT implemented
or approved here. Do not repurpose the PR GPG key or mint a private key in chat.
The final provisioning manifest must resolve issuer identity/repo/job, secret
custody, public pin and revocation/one-use behavior, not merely name this design.

23 tests cover field/signature/key/expiry mutations, attacker self-signed envelope,
valid signed overlong expiry, and real workerd Ed25519 verification. No external
HTTP, production signing, configuration, deployment, gate or workflow changes.

## Enforcement limits clarified (#373-#376)

This verifier does NOT enforce single-use. The dormant adapter consumes the
signed grant/run atomically in the canonical owner's SQLite object, separately
from permanent intent consume. The shipped rejecting guard still does not invoke
that adapter. Clock skew allowance is zero. The signed message has no domain
prefix, so the issuer's dedicated key must sign nothing except this exact policy
format. The issuer identity, exclusive-purpose key custody and pinned public key
must be concrete in the approval manifest. Additional tests re-sign each invalid
field, check key-ID mismatch/wrong key types, and reject non-canonical JSON.
