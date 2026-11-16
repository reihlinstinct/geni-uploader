# Isolated workload compatibility probe (#378)

The standalone no-argument CLI requests one bounded OIDC token and verifies it
against fixed reviewed claims/key ID and the official issuer's JWKS. Its import
graph contains no create entrypoint, executor, service, release gate, evidence
writer or collector. It cannot call Geni or unlock a release. Installation and
actual dispatch still require explicit approval of the exact action.

The create entrypoint shares only the extracted bounded token-request module.
Existing fixed-origin/audience/size/timeout/duplicate-field checks are preserved.
The probe additionally binds run/attempt/ref/event/repository/source/workflow SHA
to the hosted environment. Missing or wrong pins fail rather than being inferred
from an unsigned token. A successful receipt proves workload compatibility only,
not owner consent, protection-review capture, deployment provenance or permission
to create. Clock skew remains zero.

Configure canonical FATHER_PROBE_CONFIG_JSON and its SHA256 with exact mode,
production_enabled:false, reviewed workload request origin, audience, all required
workload pins and an existing 0700 private receipt directory. The CLI exclusively
reserves a 0600 run-specific file before HTTP; success writes/fsyncs only reviewed
origin/pins/config digest and value-free status, never a token or credential.
Failure leaves the reservation for private inspection and never retries. Public
stdout/stderr is fixed, without run IDs, claims, secrets or raw errors. This local
receipt is NOT persistent recovery backing for a create. Preserve it privately
through a separately approved durable handoff before ending an actual probe run.

Actual request origin, signing key ID and current hosted claims must be observed
under an approved no-write installation/inspection scope, not guessed. This
module intentionally cannot bootstrap missing pins from token contents. A stale
key or changed platform claim blocks; review the signed evidence before a pin
update. No active workflow or provisioning is included in this PR. The next
installable package must pin tools/source, provide the exact private config and
receipt handoff, and name its own approval scope before dispatch.
