# Separate private release issuer and one-approval handoff (#380)

> Superseded production route (#407): use the separate Cloudflare Worker design
> in [cloudflare-release-issuer-design.md](cloudflare-release-issuer-design.md).
> This file records dormant Node/private-runner work only. Do not provision or
> execute that route as a fallback. Its old Git journal is not authority.

Design only. No issuer, repository, key, secret, workflow, service configuration,
namespace or account setting is created. The shipped release gate still rejects.
The existing draft workflow still stops. This document is not a resolved
provisioning manifest and grants no authority to install or dispatch anything.

## Split authority

Choose a dedicated PRIVATE issuer repository and a separate workflow-dispatch
job with one narrowly reviewed issuance program. The private job holds the
exclusive-purpose Ed25519 release key and service configuration credential. The
public protected job holds neither. Do not put the key in the father Worker,
public workflow, request body, job outputs or artifacts. Do not reuse the PR GPG
key, a vendor credential or a general-purpose signing key. Because the current
policy signature has no domain prefix, this Ed25519 key signs NOTHING ELSE.

The issuer repository, numeric identity, immutable source/workflow hashes,
credential scopes and actual public SPKI/key ID must be resolved and reviewed
privately before the provisioning action is presented. Naming a proposed
repository is not evidence it exists, is private, has the right protections or
has free usable runner capacity. If any step needs money/card/paid capacity,
stop; do not enable billing. Never print or place a private key in a manifest.

## One human approval, not two

The public run has exactly one protected job and one required human deployment
reviewer. The agent dispatches it. The job name binds static plan/risk, run and
attempt1; the human uses Review deployments for that exact run. The private issuer
is a DIFFERENT run, not another job added to the public run. Its dispatch is an
agent action within a separately approved issuance workflow, not a second human
ceremony or a substitute for the original review.

The issuer independently checks the original public run, current environment
rules, required reviewer and approval, exact sole in-progress job and immutable
workflow bytes against fixed reviewed static config. Reuse the protected-capture
checks rather than trusting dispatch input. Its run selector is untrusted until
these checks pass. It also checks source signature/review/CI evidence and the
installed immutable service code/config/namespace against the approved manifest.
Current protection APIs do not prove historical protection; the existing shared
app-identity and historical-review limitations remain in the risk disclosure.

No OIDC token, private key or vendor token passes through dispatch inputs,
workflow outputs, logs, artifacts or an agent message. The private issuer can
bind the actual workload run from the authenticated GitHub API capture without
receiving the public job's bearer token. The public job separately requests a
fresh token and the service independently verifies issuer/JWKS/claims against
that same exact run configuration. OIDC workload identity is not owner consent.

## Ordered handoff

1. Install only under the exact approved provisioning action. Keep the new father
   service gate closed. Independently verify uploaded bytes, version/config and
   canonical SQLite namespace, private evidence destination and free limits.
2. Run only the separately approved no-write observation/compatibility scope.
   Privately observe request origin, official-key-verified token claims/key ID
   and any platform extras. Do not silently derive trusted claims from unsigned
   JSON, loosen the production verifier or print a debugger token. Pin the
   observed values through review. The strict probe alone cannot discover them.
3. Agent dispatches the reviewed public one-job run. Human approves its exact
   plan/risk/run. The public job then waits at a bounded, reviewed handoff stage
   before any service/create call. A fixed private acknowledgement is not itself
   an execution permit. This stage is not implemented by this document.
4. Agent dispatches the separate private issuer with only the public run selector.
   Issuer performs all checks above, checks no grant has been issued for the
   owner/run, and commits an exclusive private issuance-attempt record BEFORE
   changing service config. Issuance response loss is uncertain, not permission
   to reissue. Store only opaque receipts, no secrets in that record.
5. Issuer builds a canonical exact policy with random grant ID, count1 and the
   six operation identity fields, actual run/attempt1, namespace and immutable
   source pins. Sign with the exclusive key. Set issued_at to current issuer
   time and expires_at no later than 15 minutes afterward. Zero clock tolerance:
   server time must be >= issued_at and < expires_at; never widen on failure.
6. Install only that exact run's reviewed service config and signed envelope.
   Deployment credentials must not allow changing the OAuth service or replacing
   the canonical namespace. If provider scope cannot enforce that restriction,
   disclose the wider credential risk and choose a reviewed restriction before
   approval. Re-read installed code/version/config/binding and private receipt.
   Neither a matching hash nor a successful upload alone proves provenance.
7. Public job obtains a fresh OIDC token only after verified handoff, captures and
   persists exact approval/prewrite evidence, and calls the service once. Service
   verifies token, current approval/graph, signed release and static config. The
   dormant adapter's atomic owner-global grant consume plus permanent intent
   consume prevent replay. Lost acknowledgments never authorize another POST.
8. Preserve encrypted evidence and opaque journal receipts privately. A private
   issuance receipt is not a create receipt or VERIFIED result. A run that stops
   before/after an ambiguous config write remains stopped pending inspection.

Do not poll the user's logged-in browser to perform this handoff. Any API wait
must have an approved bounded cadence/deadline, no secret-bearing response in
public output and no automatic dispatch/config/create retry. A fresh JWT must
not be acquired before a long wait and then treated as still valid afterward.

## Revocation and limits

No new grant may overwrite a consumed grant/intent. Namespace reset, deletion,
replacement, a new run or a new key cannot erase owner-global consumption. Private
issuer records are append-only, bounded and single-owner/single-operation.
Revocation closes the service before issuance or execution, removes the active
signed release configuration, and disables further issuance through a separately
approved change; retain all consumed state and private evidence. Expiry is not a
retry grant. Recovery after expiry needs its own read-only authority and remains
unable to create or infer an unknown created profile ID.

## Remaining package work before an exact manifest

- Implement and independently review actual issuer program, exclusive persistent
  issuance journal and receipt-only handoff. This document is not that program.
- Resolve real private repository/workflow identity, scopes, free runner/storage
  capacity and exact immutable issuer/probe/runner/service artifact digests.
- Provision exclusive key through a secret-safe path only after approval; verify
  actual public key digest and custody, never fabricate them in advance.
- Implement approved private durable probe-receipt handoff. A local hosted-runner
  file alone is not durable evidence after the job ends.
- Resolve approved origin/key observation action, installation paths and deadline.
  Unknown live values stay unknown; do not replace them with plausible strings.
- Verify credential restrictions and canonical namespace identity from the
  installed service before proposing a run. No effective account permissions or
  active workflows change merely because the code and this design are merged.

## Official references checked 2026-10-29

GitHub documents job-scoped id-token:write and the request URL/token environment
variables, supported claims and official issuer. This permission enables token
requesting, not arbitrary resource writes:
https://docs.github.com/en/actions/reference/security/oidc

Cloud providers verify the token before issuing cloud access; the workload token
itself is not deployment or user authority:
https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers

Reusable workflows add job_workflow_ref and can change the claims that must be
pinned. This design does not silently switch the public job to a reusable workflow:
https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows
