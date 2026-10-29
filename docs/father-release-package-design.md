# Father-only release package design (#362)

Design only. No gate, deployed script, namespace, credential, variable, effective
workflow permission or account setting changes in this PR. The existing
`requireFatherRelease()` still always throws. The workflow draft still exits1.
Merging this design is not release, provisioning or live-run authority.

## Read-only inventory observed 2026-10-29

The account's complete returned Workers list contains five scripts, including the
existing OAuth bootstrap. The complete returned Durable Objects list contains
one SQLite namespace for OAuth one-time state. No father executor script or
father owner-intent namespace was present in those returned lists. OAuth settings
show a one-time-state namespace binding, primary/secondary owner variables and
OAuth secret names. Secret values were not read or exported into documentation.
The active OAuth deployment reports a single version at 100%, created
2026-10-28. Its release annotation is metadata, not independent deployed-code
verification. The existing public landing page is
https://oauth-bootstrap.reihlinstinct.workers.dev/ .

Workers, Durable Objects and KV list reads succeeded using an existing authorized
credential. Account subscription read returned HTTP403, so billing plan was not
verified by that read. The dashboard login remained at a browser-verification
challenge; no password reset or new API token was performed. No account change,
Geni call, credential refresh or deployment occurred. Exact private account,
namespace and version identifiers remain in the private inventory, not this
public document. This snapshot proves neither credential validity nor the
complete provenance of a future deployment.

## Target isolation

Use a NEW father-only Worker and NEW SQLite Durable Object namespace exporting
`FatherOwnerIntent`. Do not reuse OAuth's one-time-state namespace, add father
routes to the OAuth Worker, or modify its secrets/configuration. The owner-global
routing name remains canonical across all runs/plans/connections. A new namespace
is not an allowed way to erase a consumed intent: after initial provisioning its
identity is pinned and changes need separate review and explicit authority.

The deployment package must include the immutable bundled Worker digest, signed
source head, namespace identity/migration, compatibility date/node compatibility,
fixed issuer/audience/workload pins and fixed per-run approval/evidence/preflight
policies. Bundle production separately from test gate replacement plugins. Verify
the uploaded deployed version's bytes/configuration before offering a run.

## Ordered no-write-first release

1. Review an installable no-write compatibility workflow/entrypoint. It must not
   import or expose executor `/execute`, even when all run pins are valid. It may
   acquire and verify an actual OIDC token without printing it. Any live owner/
   graph GET probe requires its own exact approved scope. The hosted token's
   request origin, audience, signed claims and key IDs are observed, not guessed.
2. Present the exact new Worker/namespace/config/secret access and cost limits for
   approval. Nothing is provisioned by this design. Establish private persistent
   journal backing and encrypted recovery evidence destination before a run.
3. Under that explicit approval, provision the closed father-only service,
   inspect installed namespace/version/config and run only the separately
   approved no-write probe. Current secondary-token validity/owner must be
   checked under that named scope; a stored token is not proof it still works.
4. After probe evidence and exact independent review/green CI, propose the
   immutable release-gate replacement. An environment boolean or matching hash
   alone cannot unlock it. Its input must be authenticated deployment-owned
   release policy, checked before consumption, naming owner/connection, payload,
   plan, artifact, policy, run/attempt, expiry, namespace and operation count one.
   Missing/mutated/expired pins remain fail closed. This design does not provide
   a key, signature, issued grant or deployable replacement implementation.
5. Install the reviewed exact-run workflow only under approval. Instinct
   dispatches; the sole required human reviewer uses Review deployments for that
   exact plan/risk/run. Existing capture requires exactly one gated job total.
   Do not silently introduce a second approval ceremony or dispatcher identity.
6. Recheck graph/identity, permanently consume, one POST, acknowledged-ID storage,
   readback, pre-upload reservation, ciphertext persistence and receipt admission.
   Any ambiguity remains consumed/uncertain, never auto-retry. Recovery is GET
   only and must preserve unknown identity. Ciphertext receipt is not VERIFIED.

## Installable job package requirements

A future reviewed CLI should call `runProtectedJobEntrypoint` exactly once and
emit only a bounded value-free status/opaque receipt. No shell-provided service
URL, arbitrary command, secret output or raw provider JSON in logs. Installable
workflow needs pinned checkout/setup/age hashes, required Python/Node dependencies,
fixed private input files, exact config source and job-scoped OIDC permission.
The current draft is deliberately not that installation. Short-lived run pins
cannot be baked before a run exists: use a reviewed authenticated issuance path
binding the actual run to the already approved static plan, not caller JSON.

Run-specific `kid`, request origin, workflow/source hashes and deployed service
artifact cannot be filled with plausible values just to make the workflow pass.
OIDC inspection must preserve required claims and explain any newly rejected
claim; do not widen allowlists from an unsigned token payload. Cross-operation
private storage and journal retention/cost limits need explicit provisioning
scope. Local fsync on an ephemeral hosted runner alone is not durable recovery.

## Acceptance before proposing a create

- Independent review and exact-head CI for actual gate/CLI/workflow changes.
- Exact approved new deployment with verified immutable code/config/namespace.
- Actual signed OIDC compatibility and approved token-self/current graph probe.
- Durable private receipts/recovery handoff, no secret/provider logs.
- Exact father-only names/relationship/privacy payload and risk disclosure shown
  privately, no unrelated genealogy data or extra family operations.
- User's exact run approval through the accepted single-human ceremony.

Until those checks are grounded, an exact deployment/probe proposal may be ready
before an exact create proposal. No fixed live-ready date follows from this design.
