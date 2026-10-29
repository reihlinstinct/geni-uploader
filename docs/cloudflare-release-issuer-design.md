# Separate Cloudflare release issuer (#407)

Design only. No Worker, key, secret, namespace, service binding, workflow,
permission, budget or deployment is created. The shipped father gate still
rejects. This replaces the private GitHub-hosted Node issuer as the intended
production route. That module remains dormant, not a fallback to execute.

## Trust split and custody

Use a separate issuer Worker with an exclusive-purpose Ed25519 private key held
only in that Worker's secret binding. Import with WebCrypto, non-extractable,
usage sign only. No Node crypto/fs/process/Python dependency is permitted in its
production bundle. The key signs only the existing exact father-policy format,
never arbitrary caller bytes. Do not reuse a GPG/OAuth/general signing key.
Public SPKI/key ID are verified against approved fixed config. Key generation,
secret installation, and recovery custody need their own exact approved action;
no real key is generated during implementation tests.

The canonical owner SQLite DO holds the permanent issuance-attempt slot, signed
grant consume and create-intent consume as separate barriers. It never receives
the private signing key. A public runner gets neither a key nor any Cloudflare
management credential. Keep existing OAuth service bytes/config untouched.

The issuer has no general deployment token and cannot replace Workers, bindings
or namespaces. Any installer/config adapter is a separate, explicitly approved
capability, restricted to the father service where the provider permits. Wider
provider permissions must be disclosed, not described as isolated. An installed
secret is protected from ordinary callers, not account administrators or an
administrator who replaces issuer code. A non-extractable CryptoKey does not
hide the original secret binding from malicious code running in that Worker.

## Entry and internal authentication

A public issuer entrypoint, if installed, verifies official GitHub OIDC signature,
issuer/audience, numeric repository identity, exact source/workflow hashes,
original public run/attempt1 and bounded token time against fixed reviewed config.
The signed public identity may request evaluation only: it is NOT the exclusive
issuer identity and can never directly reserve or sign. Independently capture
and verify the current exact-run human approval and immutable workflow/job,
source signature, independent review and exact-head green CI. Port the complete
v2 approval validator semantics, not a subset, to Worker-compatible code.

Only a deployment-owned service binding may invoke the owner DO's internal
issuance method. Do not expose reserve/inspect on the public father fetch route.
The internal request binds exact approved operation/run, verified issuer code
identity, owner and installed canonical namespace. A body flag, caller-selected
pins or an environment namespace string proves none of those facts. A service
binding is a capability, not a signed attestation of deployed source/namespace;
any same-account administrator may create another binding. Receiver-side fixed
pins and independent installation readback are both required.

The current reservation module uses GitHub issuer repository/run/source/workflow
pins. Those are NOT a Cloudflare issuer identity. A separate versioned schema
must use actual Worker/script/version/bundle identity and installation audit
reference before integration. Do not fill old fields with invented GitHub IDs.
Keep legacy modules unconnected until the new schema and wrapper pass review.

## Installation provenance gate

Before issuance, independently read back actual issuer and father deployed bytes,
versions, fixed config, service bindings, canonical namespace ID and owner routing.
Match the exact approved package and verify no namespace replacement. Missing
provider access is a blocker. An application cannot discover or prove its actual
namespace from its own configuration string. The reviewed audit adapter must
supply authenticated, bounded, fresh, exact-run installation evidence; neither
an unsigned caller report nor a matching digest alone proves provenance.

Audit mechanism, credential scope and historical evidence remain implementation
blockers. Do not activate a route while these are unresolved. Current GitHub API
checks still cannot prove historical protection, and shared app identity remains
a disclosed limit. Nothing here upgrades those checks into independent proof.

## Ordered one-approval handoff

1. Separately approve exact provisioning with generated IDs/public pin pending
   only where the closed provisioning schema explicitly allows it. Verify actual
   resulting IDs/config/public key before constructing the release manifest.
2. Perform only the separately approved no-write OIDC observation/probe action;
   unknown origin/key/bootstrap values stay unresolved until verified.
3. Agent dispatches the exact reviewed public job; sole human reviewer uses
   Review deployments for that run. The job waits at a bounded handoff stage,
   not a second human approval. A generic chat approval never permits a POST.
4. Issuer verifies workload, complete approval, source/review/CI, installation
   evidence and freshness before calling the internal owner issuance reserve.
   The DO validates its fixed wrapper context and atomically reserves once.
5. Verify committed receipt, persist required private evidence, recheck freshness
   and sign a canonical count1 policy. Expiry is the earlier of approval expiry
   and issuer now plus at most 900 seconds. No clock-skew grace. Random grant ID
   comes from WebCrypto. Validate resulting envelope against the existing wire
   verifier before handing it to a separately reviewed config adapter.
6. The adapter installs only the exact authorized father config/envelope, then
   independently verifies deployed bytes/config/bindings. Issuer itself has no
   broad deploy token. Handoff to the public runner is opaque status only, never
   the signing key, envelope, token, raw provider response or private evidence.
7. Runner obtains fresh OIDC after the wait and calls once. Service independently
   checks current graph/approval, signed release and both execution barriers.
   A signature or issuance receipt is not proof of create permission/completion.

One global issuance slot remains spent after lost response, evidence failure,
signing failure, config uncertainty or expiry. Never auto-retry reserve/sign,
reset, reroute owner, replace namespace or reissue under another key/run/plan.
Inspection is read-only, exact-attempt, no resume. Revocation closes issuance and
execution while preserving every slot and private receipt. Late recovery and
unknown created-profile IDs remain separately authorized and read-only.

## Free-runtime proof, not an assumption

Official Workers Free limits are 10ms CPU per invocation, 100k requests/day,
128MB memory and 50 subrequests/request. Network waiting is not CPU; elapsed
local wall time is not provider CPU measurement. Authentication workloads may
exceed 10ms. SQLite DO Free usage has separate daily limits; exhausting them
fails operations. Actual account plan/capacity is still unverified.

Before proposing activation, require:

- Closed Worker bundle/import allowlist and workerd integration tests with no
  Node compatibility/file/process helpers, synthetic ephemeral keys only.
- Complete validator parity fixtures, official JWT/JWKS verification, Ed25519
  import/sign/verify, real SQLite concurrency/restart and receiver-boundary tests.
- Exact bounded API plan: cap subrequests below 50 including redirects/retries,
  reject oversized bodies/arrays/pagination, fix deadlines; incomplete evidence
  stops rather than truncates into success. No unbounded polling or retries.
- Profile cold and warm valid/invalid paths and maximum accepted evidence using
  workerd profiling, with a safety margin below 10ms. Splitting phases requires
  authenticated state binding and renewed freshness checks, never weaker checks.
- After separately approved non-issuing benchmark deployment, collect actual
  provider CPU for the exact bundle on actual Free plan, including cold path.
  A local pass alone cannot establish production fit or plan eligibility.

No benchmark deployment, account API access or resource creation is approved by
this design. If CPU does not fit, optimize or revise the design with review;
never upgrade, add billing or silently fall back to paid/private compute.

## Small implementation sequence and exact-action blockers

First fix value-free SQLite errors (#408). Then port pure validators/capture
boundaries, add WebCrypto policy builder/verifier tests, introduce versioned
Cloudflare issuer identity and authenticated internal wrapper, and add bounded
installation/config/handoff adapters. Each focused PR needs independent review,
exact-head green CI and normal signed merge. Merge is not deploy approval.

An exact action is NOT ready: unresolved actual Free plan/capacity, final bundle
and CPU proof, authenticated namespace audit, narrowed installer permissions,
key provisioning/custody, durable private evidence, probe bootstrap and handoff
must be resolved. Provisioning and later release/live create each need their own
exact approval. No money, settings changes or live Geni call follows this file.

## Official sources checked 2026-10-29

- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://docs.github.com/en/actions/reference/security/oidc

## Reviewer account assurance (#415)

The selected one-approval ceremony is GitHub account approval plus account2FA,
not proof of interactive human presence. Preserve all fixed reviewer/User/id,
exact-run, no-self-review and no-admin-bypass pins. No automation may hold or use
the reviewer's PAT/OAuth/session for this ceremony. No extra challenge is added.
See [github-reviewer-account-assurance.md](github-reviewer-account-assurance.md)
for token attribution, review-payload limits and the remaining assurance boundary.
