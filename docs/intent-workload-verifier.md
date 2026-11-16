# Strict offline workload JWT verifier

Part of #251. Local PUBLIC key only, using existing jose dependency. No network
JWKS/discovery, credentials, owner grant, route, signing service, production
adapter, environment/configuration or deployment. A successful return says
workload identity only, owner_approval_verified:false, production_enabled:false
and replay_protection_provided:false. Repeated valid JWTs are not one-use here.
Durable jti/run consumption remains separate release-blocking service work.

Current source: https://docs.github.com/en/actions/reference/security/oidc

Exact reviewed claim pins include iss/aud/sub, numeric repository_id and
repository_owner_id, repository, workflow_ref/workflow_sha, sha, ref, environment,
event_name, actor_id, run_id/run_attempt and runner_environment. The exact ref
claim is refs/heads/master; sub does not substitute for it. Synthetic subject
pins are not a real-token subject discovery result. Real-token exact subject and
effective environment/configuration audit remain release-time requirements.

Strict bounded compact JWS, canonical base64url, duplicate-free flat scalar
header/claims, local public key, RS256 only, exact kid/typ, no jku/x5u or algorithm
fallback. Signature and issuer/audience are cryptographically checked by jose;
all other required claim values match exact pins. This narrow offline schema
rejects unknown fields/reusable-workflow context, including legitimate additional
GitHub claims. It is NOT a drop-in production GitHub verifier until an approved
real-token shape review adds only documented necessary fields and new tests.
Never relax this silently to get a token accepted.

Time is an injected trusted server-time fixture in epoch seconds. Require integer
exp/nbf/iat, no tolerance, max300second age and max600second token lifetime,
nbf>=iat and nbf<exp. Caller clocks are not authority in a future service. These
bounds are candidate verifier policy, not claimed GitHub token lifetime promises.

Synthetic tests use generated local keys only. Each pin has mismatch/missing
negative tests. Wrong signature/key/algorithm/header/type, duplicate claims,
reusable context, oversize input and time errors fail with fixed value-free error.
This proves local cryptographic/claim behavior, not live issuer key fetching,
key rotation, environment approval, owner consent, durable replay protection,
encryption or execution authority. Trusted local key/pins can be swapped by a
compromised host; no claim that this module authenticates its own configuration.
