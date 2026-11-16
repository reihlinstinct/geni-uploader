# Deployment release-context wiring (#372)

The dormant signed-policy adapter reads the namespace ID and reviewed
service/executor/workflow SHAs only from deployment-owned environment bindings.
It uses the fixed approved run passed by the service's Durable Object wrapper.
The executor and read-only recovery now pass those values into the release guard
before storage or network work. No request body supplies a release key, namespace,
source pin or run to this adapter.

The shipped guard STILL unconditionally rejects and does not import the adapter.
Even a valid signed release context cannot enable execute or recovery. Synthetic
rehearsals can replace the guard only in their explicit test bundle. This PR does
not provision resources, activate a gate, change configuration or call Geni.

Matching env values and a valid signature do not prove deployment provenance.
The namespace ID pin must be checked against the actual installed binding, source
pins against the reviewed deployed artifact, and the signing issuer against the
owner-authorized exact-run approval. Those checks, key issuance and the no-write
compatibility probe remain required before a separate reviewed gate replacement.
The returned verifier diagnostics still say post_permitted:false and
production_enabled:false; this adapter is not an execution permit or user grant.

## Review follow-ups (#373, #374, #375, #376)

The signature verifier alone does NOT enforce single-use. The dormant adapter
atomically writes one permanent signed-release-consumption slot in the canonical
owner DO before execution. A second execute fails even with the same grant or a
new run. Recovery requires that exact stored grant/run/policy/binding and does
not write it. Storage failure or response loss never triggers a retry. A spent
grant remains spent if payload validation or a later step fails before the POST.
This state and the existing permanent intent consume are separate safety layers.
No namespace replacement/reset is allowed to remove either layer.

Clock skew allowance is zero: issued_at must be <= current server time and
expires_at strictly greater. The issuer must account for that when issuing a
short-lived grant; the verifier never extends validity to compensate for skew.

The signature message has no domain-separation prefix. Therefore the dedicated
Ed25519 release key must sign NOTHING ELSE: no other policy type, arbitrary
message, credential, artifact or protocol. The exact issuer manifest must name
this exclusive key purpose and concrete custody/public pin before approval.

Re-signed mutations exercise all policy fields independently of signature
failure, including schema/mode/operation/count, all identity/context pins,
validity, key ID and grant format. Key-ID mismatch, wrong key types and
non-canonical envelope JSON are covered. A different well-formed grant_id is
valid for the verifier; one-use and owner-global exclusion belong to the adapter.
