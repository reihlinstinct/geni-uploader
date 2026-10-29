# Dormant private approval-to-signature composition (#385)

No installed caller, real key creation, deployment or vendor access. The private
Node module validates fixed canonical config and v2 approval bytes with the full
existing Python validator. Operation/run/service/executor/workflow pins must
match. It correlates the current sole approved public job and immutable workflow
with the existing live capture checks, then verifies the private persistent
issuance reservation before signing. Public output is never produced.

A separately provisioned exclusive-purpose Ed25519 key must be in a 0600 regular
file (not symlink); derived public SPKI and digest must equal exact issuer config.
Temporary raw key bytes are zeroed after parsing; the in-memory key remains
sensitive. This is not a key-provisioning path. Synthetic tests generate ephemeral
keys only. The key signs only the exact father policy format, no other protocol.

The <=15-minute canonical policy is generated with a random grant ID and
zero-skew expiry, then independently checked by the existing signed verifier.
The returned envelope is PRIVATE bearer-like release material in memory, never a
public log/output/artifact. No service configuration is installed by this module.
Receipt status remains post_permitted:false/production_enabled:false. A signature
alone is not a grant from the user or proof of installed deployment provenance.

The issuer still needs separately reviewed deployed-source/review/CI verification,
actual private workflow/key custody, protected journal refs, exact installed
service/namespace/config audit and private handoff adapter. The current capture
reports historical_protection_verified:false and shared_identity_limit:true; do
not turn current API correlation into historical or independent-review proof.
Failure after reservation leaves it spent. Fixed errors intentionally disclose no
key, token, raw approval or provider response. Inspect private state; never retry
issuance automatically. Late-expiry recovery remains separately authorized.
