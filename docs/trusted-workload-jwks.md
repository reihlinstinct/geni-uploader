# Fixed-issuer workload key retrieval

Related: #293, #233, #236. Integration component, NOT a released service,
owner-approval authority, permanent replay store or create executor. No route,
credential, setting, deployment or Geni call is introduced. Success retains
owner_approval_verified:false, production_enabled:false and no replay protection.

`verifyTrustedWorkload(token, pins)` obtains public keys from one fixed HTTPS
GitHub JWKS URL. It never follows token jku/x5u/issuer URLs. Redirects are refused,
there is one fetch and no retry; an unknown kid fails closed. A five-second
async operation deadline and AbortController bound waiting for fetch/body/key/signature work;
synchronous parsing cannot be preempted by a JavaScript timer and is separately
bounded by the byte/depth/key-count caps;
no caller clock is accepted. Body is limited to 64 KiB both by declared length
and actual stream bytes. Reject duplicate JSON object keys, nesting over eight,
more than sixteen keys, duplicate kids, private key material and external key URLs.
The selected key must be RS256/RSA/signing, 2048-4096-bit modulus byte length,
canonical base64url and exponent65537; optional key_ops is verify only. Invalid
headers are refused before fetching. Errors are fixed and contain no token,
response, header, key or underlying exception content. No cache is provided;
callers need a separately reviewed rate/availability policy before production.

Source inspected 29 October2026:
https://token.actions.githubusercontent.com/.well-known/openid-configuration
returns issuer https://token.actions.githubusercontent.com and jwks_uri
https://token.actions.githubusercontent.com/.well-known/jwks, with RS256 supported.
GitHub claim documentation:
https://docs.github.com/en/actions/reference/security/oidc

The existing strict offline claim verifier remains unchanged. It accepts a
narrow synthetic reviewed claim shape and rejects legitimate extra GitHub claims.
This is not yet a drop-in live GitHub authentication service. A separately
approved real-token claim-shape audit, exact effective environment/reviewer audit,
private owner/payload approval provenance, immutable release pins and permanent
jti/run/owner consumption remain release blockers. Key retrieval cannot turn
workload identity into owner consent or an execution permit.

Tests use generated synthetic keys and mocked fetch, including no-settling fetch,
stream cap without Content-Length, duplicate JSON/kid, invalid key/header/algorithm,
unknown key, redirects, malformed data and fixed errors. The existing runtime
test entry point imports these tests, so CI runs them without workflow changes.
No real identity token or live key request is used in the test suite.

## Isolated bound regression (#298)

Valid-JSON declared oversize uses a small valid body with an excessive declared
length, isolating the header bound from streaming. Streamed oversize is valid
JWKS JSON plus whitespace, so JSON parsing cannot mask the byte guard.
Oversized modulus and exponent3 fixtures sign matching JWTs with their own RSA
private keys, so signature verification cannot mask rejection of the key policy.
The17-key fixture includes the valid pinned key. Removing each of those five
bounds independently fails its named regression (five mutants killed).
All keys are generated synthetic test keys; no workload token is retrieved.
