# Canonical SQLite issuance exclusion, free-only revision (#402)

Design only. No route, namespace, secret, account setting, budget or workflow is
installed. The shipped gate remains rejecting. No billing upgrade or money is
approved. This revision supersedes the private-Git-ref authority assumption in
#380/#382: Git remains private evidence, NOT the authoritative exclusion store.

## Reason for revision

Official GitHub docs make private protected branches a paid-plan feature. An
unprotected private create-ref can be mutated by broad repository writers/admins;
add-only application code does not enforce permanent exclusion against those
credentials. The authoritative slot therefore belongs in the same new canonical
owner SQLite Durable Object already chosen for permanent execution consume and
opaque progress. No extra paid database/service/account is needed by this design.
Actual account plan, free capacity and nonbillable execution still need checking.

## Authority and ordering

The future private issuer is a DISTINCT workload principal from the public
protected runner. A public runner OIDC token cannot call issuance reservation,
sign policy, install config or delete state. Never select the issuer solely by a
request body boolean/repository name or by sharing a bearer deploy credential.

A separately reviewed entrypoint must verify the issuer's signed workload against
fixed issuer repository/workflow/source/run/attempt/audience pins and the original
approved public run/operation pins. That is identity plus scoped operational
checks, not a substitute for the owner's approval. The original one-human public
Review deployments ceremony remains unchanged. No second human review is added.

Before signing/config mutation, issuer calls a receipt-only issuance-reserve route
which addresses ONLY the canonical owner object. Inside one SQLite transaction,
validate the exact static operation identity, original public run, namespace and
issuer/source pins, reject any existing issuance-attempt slot, and store the
permanent reservation. Return only bounded opaque receipt/digest, never a signing
key/token/provider response. No Geni access is needed by reserve or inspection.

One owner-global slot, independent of run/plan/key/grant ID. Concurrent calls have
one winner. A lost response or failed subsequent Git evidence/sign/config step is
uncertain/spent, never a retry grant. Read-only inspection can establish what was
committed but cannot reset, overwrite, extend, resume or issue another grant.
No TTL, delete, owner reroute or namespace replacement can erase the slot. The
existing signed-grant execution slot and permanent create-intent consume remain
separate independent barriers. None may be cleared to recover another layer.

After authoritative reservation is verified, persist a private Git evidence copy
and opaque receipt using the existing add-only code, without claiming that its
ref is immutable. Signing may proceed only after all required private evidence
and approval/source/deployment checks pass. Failure at any later boundary stops.
A private Git write must never be treated as the authority to retry a DO reserve.

## Installation and bootstrap constraints

Issuer verification pins cannot be caller-chosen or inferred from unsigned JWT
claims. The closed installation must pin actual issuer identity and a reviewed
run-specific issuance path, preserve no-create behavior, and independently read
back deployed bytes/config/namespace. Per-run approval policy and source pins
must not be changed by a public caller. A missing bootstrap value is a blocked
installation, not permission to weaken identity checks.

The DO itself holds no Ed25519 private key in this design. No general deploy
credential enters a public runner. If the provider cannot scope an issuer's
configuration capability to the father-only service, do not claim isolation;
resolve a capability-limited config adapter or disclose and separately approve
the broader risk. Do not alter the existing OAuth service.

## Nonbillable issuer execution remains unresolved

Private hosted runner included credit is not a zero-spend guarantee. Official
GitHub billing docs say additional usage is billed unless a stop-usage budget is
enabled. Do not create/change budgets, enable billing, add a card, upgrade a plan
or run a potentially billable private job under the free-only assumption.

A separately verified existing nonbillable execution route must satisfy private
key custody, exact source review, bounded run, no public key material leakage,
private durable receipts and separation from the public runner. Candidates need
actual evaluation; naming a local runner or free service is not proof that it is
available, persistent, safe or nonbillable. If no route can be established, stop
that work and ask the user through the existing decision path. This design does
not solve that blocker by assumption or silently move the key to a public job.

## Required implementation tests

- Real SQLite concurrent reserve/restart: exactly one permanent winner.
- New plan/run/key/issuer identity cannot bypass the owner-global occupied slot.
- Public workload identity, wrong namespace/source/run and unknown fields reject
  before storage mutation; no Geni/network mutation during reserve/inspect.
- Lost response and persistence failure never retry; inspection is read-only.
- Issuer composition requires authoritative DO receipt before evidence/signature.
- Signed grant, execution consume and issuance slot survive partial failure and
  remain distinct. Existing recovery never creates or guesses an unknown ID.

## Current official sources checked 2026-10-29

Private branch protection availability:
https://docs.github.com/en/rest/branches/branch-protection

Private usage/overage and stop-budget behavior:
https://docs.github.com/en/billing/reference/product-usage-included

SQLite Durable Objects are available on Workers Free; exceeding a free limit
fails that operation. Actual account eligibility/capacity still needs checking:
https://developers.cloudflare.com/durable-objects/platform/pricing/
