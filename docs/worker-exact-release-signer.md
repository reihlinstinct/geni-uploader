# Dormant Worker signing candidate (#480)

Replaces no route and installs no key. Internal Worker-compatible exact policy
signer, using WebCrypto only and the existing verifier/wire format. Input must
be canonical exact count1/father-only/run-attempt1 policy with bounded900second
window, fixed owner/binding/source/namespace/key/grant pins. Future authoritative
issuer constructs these only after complete approval/source/review/installed
provenance checks and permanent reserve. This function does NOT supply them.

Only a nonextractable Ed25519 private sign-only CryptoKey is accepted. Actual
exclusive-purpose key custody must be grounded at deployment; type/usages do
not prove purpose, origin, admin exclusion or owner permission. The key signs
only the current exact wire. Its policy format has no domain prefix, so the
real key must sign nothing else. No private key is exported or returned.
The signed envelope remains a private internal output. Public handlers must
never forward it, key, policy or raw errors. All failures have fixed text.

Time is checked before and after signing and after existing Worker verifier
roundtrip. A different private/public-key pair is rejected by that verifier,
not claimed to have avoided a crypto operation. CryptoKey input is a candidate
seam, not authenticated deployment-owned provenance. No public handler imports
this signer. No reserve, auth, grant, config installation or execution is added.

Local workerd tests use only ephemeral synthetic test keys and17isolated cases:
exact success, unknown keys/binding fields, wrong operation/count/attempt, expiry,
future/long lifetime, newline identifiers, wrong ID/key/usages/extractability,
duplicate JSON and expiry while crypto awaits. Bundle closure has only this
module and existing Worker verifier. Outbound fetch is denied; no Node/fs/Python.
No real key/account/settings/permission/secret/deployment or live Geni action.
