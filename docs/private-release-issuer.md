# Dormant private approval-to-signature composition (#385)

No installed caller, real key creation, deployment or vendor access. The private
Node module validates fixed canonical config and v2 approval bytes with the full
existing Python validator. Operation/run/service/executor/workflow pins must
match. It correlates the current sole approved public job and immutable workflow
with the existing live capture checks, then verifies the private persistent
issuance reservation before signing. Public output is never produced.

A separately provisioned exclusive-purpose Ed25519 key is opened with
O_NOFOLLOW/O_NONBLOCK. The same descriptor must report a regular file owned by
the process uid, exactly mode0600 including no special bits, and size1..4096. A
bounded <=4097-byte read from that descriptor rejects growth/size mismatch. Raw
bytes are zeroed and the descriptor closed on success or failure. Public SPKI
and digest must match exact issuer config. These checks avoid pathname
substitution after open; they do not prove safe parent-directory custody, prevent
a same-uid process modifying the inode, or establish deployment provenance. The
in-memory parsed key remains sensitive. This is not a key-provisioning path. Synthetic tests generate ephemeral
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


## Expiry and descriptor regressions (#387)

Approval issued_at <= server now < expires_at is required before capture,
again before reservation and again immediately before signature. Expiry during
capture causes no reservation; expiry during reservation stops with the slot
spent, no signature or retry. Generated release expiry is capped by the approval
expiry as well as the configured <=15-minute duration. Zero clock skew applies.
Tests spy on the actual crypto sign function on failure paths, use syntactically
valid but different pins, and cover remote reservation readback failure, key uid,
symlink, pathname substitution, special permissions, oversized/growing reads and
read errors with byte zeroing/descriptor close checks. No live key was used.
