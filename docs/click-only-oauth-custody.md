# Click-only browser OAuth and credential custody

Design only, 2026-10-29. No live OAuth, Geni request, credential, setting,
callback change, deployment or publication is authorized. The human's target is
clicking on a site, not copying a token or building an iPhone Shortcut.
The temporary fake-only Shortcut experiment is dropped and being removed.

## Intended journey

1. Human opens a verified HTTPS landing page and chooses the intended isolated
   account. If needed, GitHub identity login and Geni login/2FA/consent occur in
   their own provider pages. No password or code is collected by our page.
2. The browser returns to a supported registered callback. A one-time state,
   browser binding, authenticated numeric identity and fixed destination bind
   the exchange. Tokens are never displayed or returned to browser JavaScript.
3. The server saves credentials to the fixed isolated destination and returns
   a value-free connected/failed status. Wrong/unknown owner stops storage.
4. Human opens the exact approved write workflow and clicks Run/Approve. A login
   does not dispatch a run. A connected token is not permission for any write.
   No auto-run, comment trigger, agent-written Geni call or generic write proxy.

"Click only" means no token pasting. It does not promise one literal click:
provider login, consent, 2FA and separate run/environment approvals may require
several actions. First father creation remains unreleased. Login cannot bypass
its always-closed gate, private exact payload consent or deployment conditions.

## Current implementation, not verified installation

`oauth-bootstrap/worker.mjs` and CONNECTIONS.md already implement a browser login,
code exchange, bounded state and fixed primary/secondary/tertiary secret names.
Current code stores sealed credentials via a scoped GitHub secret writer into
repository Actions Secrets. It has a discovery-only mode and optional owner-pin
compatibility behavior. Current upload workflow consumes primary only; no new
secondary write consumer is supplied by this proposal. The observed landing
page proves neither exact deployed bytes/config nor a successful provider POST
exchange. Do not build another unrelated OAuth system or assume this is ready.

The static `docs/oauth-callback.html` is different: it displays tokens, accepts
query tokens and has no new server custody. Query values already reach hosting
before clearing. Do not repurpose it silently. The separate Cloudflare release
issuer signs exact approvals; it is not a token vault, OAuth callback or Geni
write executor. Maintain these boundaries.

## Options and recommendation

| Option | No paste | Benefit | Missing work / risk |
| --- | --- | --- | --- |
| A: existing bootstrap to fixed GitHub environment Secrets | Yes | Reuses implemented flow and current workflow secret consumption | Convert repository-secret writer to exact environments, fail-closed expiry/revocation, narrow writer custody and installed audit |
| B: Cloudflare SQLite encrypted credential vault and run-bound broker | Yes | Explicit credential lifetime/revocation, no broad GitHub secret writer | New vault, encryption key custody, authenticated run handoff, broker audit, budget/CPU and recovery proof |
| C: display-once browser token | No | Small client callback | Clipboard/screenshots/history risk; contradicts selected no-paste goal |

Recommend A as the first bounded implementation path, not permission to configure
it. B is a later alternative if its stronger lifetime controls justify extra
machinery. C stays unselected, never automatic fallback on storage failure.
No assumption that source-upload or father workflow can consume a new slot
until its exact consumer is separately implemented/reviewed.

## A: required custody contract before implementation

- Fixed environment IDs/names and slot-to-owner mapping, private; callback input
  cannot select repository/environment/secret names. Enforce canonical owner
  pins in every slot; no legacy unpinned mode for new deployment.
- Narrow GitHub writer with only required repo/environment-secret scope outside
  public jobs and release issuer. Environment Secrets are encrypted via GitHub's
  public-key interface; verify actual endpoint/permission semantics first.
  A scoped writer still has replacement power. Admins can replace code/rules.
- Each credential bundle includes schema, slot, canonical owner, authenticated
  connection event, issue time, provider expiry if supplied and an independent
  maximum accepted lifetime. Missing expiry does not mean unlimited lifetime.
  Exact duration remains a reviewed policy choice before rollout.
- GitHub Secrets have no assumed automatic TTL. A separately reviewed consumer
  must enforce freshness and revocation before use and after asynchronous
  checks. Existing raw-token consumers do not enforce this by magic. Human-run
  attempts are exact-run bound, no fallback to another slot or stale token.
- Revocation needs a supported route, authority and readback. Stop future token
  release immediately, delete/disable fixed local credentials and record a
  revocation epoch without resetting permanent issuance/intent slots. Local
  deletion is not proof the vendor app/token is revoked. Verify provider revoke
  support separately; no guessed endpoint or claim of global deletion.
- Refresh rotation is separate from writes, bounded and fail-closed. New refresh
  bundle must persist before compatibility token update; partial failure stops
  with an exact recovery path. No automatic token retry or stale fallback.
- Before release, actual effective environment branch/reviewer/bypass rules,
  secret scope and source/config/callback must be independently read back.
  Repository secret migration/deletion and new writer installation need exact
  approval; never leave both routes live as an accidental fallback.

## B: vault tradeoffs that must not be hidden

Cloudflare states Durable Object data/metadata are encrypted at rest with
provider-managed keys and TLS in transit. Free supports SQLite-backed DOs only.
This is not end-to-end encryption against Cloudflare or an account administrator.
A dedicated encrypted credential record may add application encryption, but its
key must have defined exclusive custody; colocated key+code remains admin-trusted.

Expiry must be checked on every access; alarms are cleanup only, not a punctual
security boundary. Delete/rotation does not promise historical erasure: SQLite
has point-in-time recovery, and provider backup policies need verification.
Credential storage must be a DIFFERENT object/namespace from permanent issuance,
grant and intent barriers. Never use deleteAll or namespace replacement on those
barriers to clean up credentials. Broker access must authenticate exact workload,
run/attempt/source/owner and approval, not accept a caller's owner/body selector.
No token in URLs, logs, public artifacts or browser storage. No browser run button
until actual human-triggered dispatch/authentication has its own reviewed scope.

## Browser and privacy controls, all options

No analytics/third-party assets, strict header CSP, no-store/no-referrer, escaped
fixed status, no localStorage/sessionStorage credential, no token query URL or
browser-visible token under A/B. Server-side code callback necessarily carries
an authorization code in its initial URL: immediate history clearing cannot undo
provider/edge logs. Verify redaction/retention before approval and disclose any
unavoidable residual. State contains no token or family data. Request bodies,
raw provider errors, exception values and identities stay out of public logs.
A failed connection stops; it does not fall back to displaying a secret.

## Staged implementation and fake-only tests

1. Audit existing bootstrap and exact provider/GitHub endpoint contracts; define
   closed environment destination registry and expiry/revocation schema.
2. Pure policy and synthetic expiry/owner/slot/replay/unknown-field tests; storage
   adapter uses fake endpoints only. No real secret or callback configuration.
3. Offline workerd composition tests for success, wrong identity, stale/revoked
   bundle, concurrent rotation, partial persistence and public-log sentinel leaks.
   Verify no dispatch/write call exists in login flow. Mutate the guards.
4. Independently review exact head, green CI, then propose exact deployment,
   custody migration, callback registration, log controls and zero-cost evidence.
   Free default pricing is not evidence of this account's actual entitlement.
5. After explicit exact approval only, human tests login/consent and connected
   status. Separate exact write-run proposal remains human-triggered and gated.

No action needed from the user to implement these offline stages. The first live
question must name actual reviewed package, fixed slot/environment, permissions,
expiry/revocation, account Free/capacity evidence, logging risks, supported route
and rollback. Do not ask for tokens in chat or guess a settings change now.

## Sources checked

- https://www.geni.com/platform/developer/help/oauth_server_side
- https://www.geni.com/platform/developer/help/oauth_intro?version=1
- https://developers.cloudflare.com/durable-objects/reference/data-security/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/
- https://developers.cloudflare.com/durable-objects/platform/pricing/

These support provider capabilities and constraints, not current installation,
authority, entitlement, safe expiry implementation or production readiness.
