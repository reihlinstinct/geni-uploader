# Installation audit and internal issuer boundary (#433)

Design only. No audit principal, key, secret, namespace, Worker, permission,
setting, benchmark deployment or live call is created. This document is not a
resolved action manifest. OAuth service and existing namespaces remain untouched.

## Provider facts versus supplied assertions

A config hash proves bytes match supplied expectations. A service binding is a
capability to invoke a target. Neither proves actual deployed source/version or
canonical namespace. Environment namespace strings and caller-supplied audit
hashes are assertions, not provider readback. The v2 reservation checks shape,
not those facts. No public reserve/inspect route may wrap it before the audit
and internal-caller boundary are implemented and independently reviewed.

A separate audit authority reads the provider API over authenticated HTTPS,
with fixed account/script targets, bounded responses, no redirects/retries and
freshness/deadline limits. It must independently establish:

- issuer and father exact deployed versions and complete script/module bytes,
  compared to the closed reviewed bundle/module digest, including compatibility
  date/flags and bindings/config; no missing module accepted as matching;
- active deployment version and traffic allocation, not merely an uploaded but
  inactive version or a matching friendly Worker name;
- canonical owner SQLite namespace ID, class, storage backend, script and exact
  owner routing relation, service binding target/entrypoint and absence of
  extra bindings/unsafe migrations; installed readback, not local wrangler.json;
- issuer signing-secret name/presence metadata only, never secret value, and no
  signing secret or broad management credential in father/public runner;
- immutable package/source/executor/workflow/run/attempt relation, approved
  purpose and observation/benchmark versus release mode, time/expiry and plan;
- actual Free account eligibility and capacity separately from the source/config
  audit. Official Free pricing does not prove this account's subscription.

Provider source/settings/version endpoints are documented, but exact response
contracts, active deployment relation, namespace lookup and account-plan access
must be verified before implementation. Missing field/access is a blocker.
Never invent a successful audit from an upload response or environment string.

## Authority and custody split

The signing Worker holds only its exclusive signing secret and scoped runtime
capabilities. It holds no broad Cloudflare management token. The public runner
holds neither signing key nor provider credential. Audit and install are separate
capabilities; a read credential must not silently become a deploy credential.

Official current Cloudflare roles permit selected-Worker Content Read-Only for
source/metadata audit and selected-Worker Editor for existing-script updates.
But a nonexistent Worker cannot have per-Worker scope. Initial Worker creation
requires product-level Workers Admin. The exact first provisioning approval must
therefore disclose a one-shot broader bootstrap authority, fixed account/targets
and bounded writes, followed by removal from the execution path. No long-lived
broad credential may be left in an issuer/public job merely for convenience.
Actual token assignment/revocation is itself a separately approved action, not
something this design performs or assumes already available.

Selected-Worker Editor can deploy bindings without separate permissions on the
bound resources. Thus that role is NOT a sandbox against binding escalation.
The approved binding allowlist and independent readback must reject extras;
privileged installer/account administrators remain trusted. A compromised admin
can replace audit/issuer code or delete/replace state. No tamper-proof claim.

## Authenticated audit receipt and internal call

Choose an actually supported audit principal/custody mechanism before claiming
authentication. No new key or third Worker is selected by this file. Candidate
receipt must be bounded/canonical, versioned and domain-separated, binding exact
account/scripts/deployed versions/module hashes/config/bindings/namespace/owner,
package/source/run/attempt, approved mode, issued/expiry and revocation scope.
Signature/authenticated transport verifies origin only if its key/capability is
outside untrusted caller control and installed/read back under approved policy.
A body carrying the same digest is never sufficient. Audit principal compromise
and provider admin replacement remain explicit trust assumptions.

The future internal DO wrapper verifies that receipt, exact pinned issuer identity
and original approval before addressing only the canonical owner object. No body
owner reroute or namespace selector; reserve and read-only inspection are distinct
methods. Service binding is a least-exposed transport, not proof of which code
invoked it. Same-account binding creation is an admin capability. Resolve a
supported authenticated caller/receipt mechanism before exposing the method.

Audit must be fresh immediately before reserve/sign/config handoff and installed
config must be independently re-read afterward. A later provider change is a
TOCTOU risk; either re-audit/reject or use an explicitly reviewed immutable-version
binding mechanism with real provider support. No claim of atomicity across APIs.
Lost response or failed audit leaves the workflow stopped; permanent slots are
never reset. Inspection never authorizes another issuance or create.

## Exact first provisioning/benchmark manifest fields

Before asking the owner, resolve every nongenerated field:

- schema/action mode, fixed account ID, actual Free-plan evidence/time/capacity;
- exact issuer/father script/class/binding/secret names and exposure: internal
  entrypoints, workers.dev/routes/custom domains disabled unless explicitly named;
- reviewed source/head/CI/review references, closed bundle/module hashes and
  compatibility/date/flags, migrations and explicit create/update method counts;
- initial namespace creation and owner routing, allowed SQLite backend and no
  delete/reset/rename/transfer of any existing namespace; OAuth exclusion;
- initial non-issuing/no-Geni/no-real-signing-key benchmark mode, synthetic inputs,
  max request/subrequest count/deadline, CPU measurement/readback method and stop
  condition; no public log/trace containing private data or credentials;
- exact secret/key provisioning excluded from this first benchmark action unless
  separately and explicitly shown; public SPKI not fabricated in advance;
- one-shot bootstrap permissions, later selected-Worker audit/install scopes,
  private evidence destination/retention, rollback/revocation and verification;
- cost ceiling0, no upgrade/card/budget/settings changes, required outcome and
  unresolved checks that prevent execution.

Generated version/namespace IDs may be pending only in the closed provisioning
phase fields explicitly allowed by its reviewed schema. Record actual provider
results and independently verify before building the later resolved release
manifest. Pending IDs are not wildcards for release, and provisioning approval
is not approval of signing, activation or Geni calls.

## Rollback and later approvals

Failure stops. Revoke execution/issuance while preserving all owner-global
issuance/grant/intent slots and private receipts. Do not replace namespace or
redeploy a fresh owner to regain a spent operation. Rollback plan must use exact
supported provider routes and verified installed state, not deletion as cleanup.

After non-issuing provisioning/measurement, actual provider CPU/Free status,
canonical installation and capacity must pass before any activation proposal.
Exclusive key generation/installation needs exact approved custody steps. A
later release approval names the resolved package/run/operation and actual IDs/
SPKI plus all risks. Source-upload actions remain separate from father-only first
create. None of those approvals is supplied by merging code or this document.

## Next implementation gates

Closed installer/manifest + local profiler; read-only account/scope grounding;
authenticated bounded provider readback adapter; audit receipt verifier; internal
DO wrapper; signer composition; private durable evidence/config handoff; complete
end-to-end no-Geni rehearsal and exact-bundle provider CPU test after approval.
Independent-review trust choice remains parked as #425 describes. No time estimate
is implied: these are missing outcome capabilities, not a list of trivial edits.

## Official sources checked 2026-10-29

- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/content/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
