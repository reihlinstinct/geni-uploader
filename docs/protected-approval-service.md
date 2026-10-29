# Private v2 approval and pre-write service join

This local integration joins the existing immutable private Git approval fetch,
the module-owned receipt, strict v2 content admission and immutable pre-write
ciphertext verification. The raw record bytes remain inside the admission
module. The service compares owner, connection, exact plan/payload/artifact/
policy/run, recipient and reviewed service/executor/workflow pins from its own
configuration before returning a joined content result.

No caller-supplied receipt, source destination or approval boolean substitutes
for the module-owned byte receipt. Hash-pinned deployment configuration still
needs authenticated provisioning. The private Git byte receipt establishes
where bytes were fetched, not who approved them. This join deliberately keeps
human-action and POST flags false. It cannot be used as a production release.

The joined test executes eight fixed mocked GitHub reads for synthetic private
record/evidence objects. Immutable v2 record content and remote ciphertext are
both checked. Distinct tests reject binding drift before retrieval. Real age
encryption/decryption is tested separately in the protected job, not inferred
from an age header or this test's synthetic evidence bytes.

Do not install this as the production gate before authenticating the protected
capture writer, checking current required-reviewer settings and immutable
single-gate workflow content at the service, binding token-self owner and current
graph/preflight, and preserving consumed history with the actual one-POST and
post-write acknowledgment/readback path. The future capture job must upload its
immutable record privately; a local file is not a published approval record.
