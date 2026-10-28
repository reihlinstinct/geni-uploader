# Human-triggered OAuth renewal

Tracking: #160

Status: implementation and offline tests only. Not deployed, not configured, and
not safe to claim working against the service until a human-run test succeeds.
No profile API, upload, scheduled run, automatic retry or agent authorization is
part of this design.

## Answer

Geni documents real refresh tokens for server-side authorization. Routine renewal
can be one human workflow invocation with no developer-site visit, login, token
copying, or consent prompt. Initial setup needs one user-operated consent flow
and server-side code exchange. Geni login and 2FA, if requested, stay entirely
between the human and Geni. No password, 2FA code, access token or app secret goes
into chat, email, screenshots or public logs. The number of initial taps depends
on whether the user is logged in; do not promise one literal tap.

A current Desktop/client-side access token alone does not contain a documented
refresh token. A 401 means invalid, not necessarily expired. The documented
86400-second lifetime is an example, not a service guarantee.

## Implemented first stage

`oauth_refresh.py` uses a fixed HTTPS OAuth endpoint and POST form body, with no
credential query string, redirects, retries, response-body output or profile API.
POST support still needs a user-run integration check: vendor examples use query
parameters, which this implementation deliberately does not use for secrets.
Parsing rejects missing or malformed access/refresh tokens and expiry. The app
credentials and refresh token are one JSON bundle in `GENI_OAUTH_REFRESH_BUNDLE`:

```json
{"schema":1,"client_id":"ZZCLIENT","client_secret":"ZZSECRET","redirect_uri":"https://example.invalid/callback","refresh_token":"ZZREFRESH"}
```

These are synthetic placeholders, not usable values. Setup uses secure vault or
service secret entry, never repository files or workflow inputs. The refresh
workflow has no inputs, is manual-only, requires the allowed human as actor and
triggering actor, requires the default branch, and uses the `oauth-refresh`
environment. It has no schedule and cannot trigger an uploader. `OAUTH_SECRET_WRITER`
is a separate least-privilege credential with Actions-secrets write on this code
repo only; built-in GITHUB_TOKEN is not assumed to have that authority. The writer
is never disclosed to the browser or Geni.

Rotation order: persist new refresh + pending access token in one encrypted bundle;
update the compatibility access-token secret; clear the pending field. A rerun
with a pending token repairs secret synchronization WITHOUT another OAuth request.
If the first persistence fails after Geni rotates, stop and warn re-consent may be
needed. No claim of atomic cross-service rotation or rollback. A process killed
between remote token rotation and local persistence can still lose the new refresh
token. Concurrency prevents two renewal workflows rotating together; human upload
runs should not overlap renewal. An already-running job retains its initial secret
snapshot. A later plan/run must be a NEW invocation.

## Bootstrap: separate gated component, not yet built or deployed

GitHub Pages is static and cannot hold App Secret, exchange authorization codes,
or safely write repository secrets. Never put a secret-writing PAT in callback JS.
The old local-copy page remains unchanged and is NOT the new bootstrap.

Proposed free HTTPS callback service, subject to provider setup/terms and explicit
secret-custody approval before deployment:

1. Human signs into a bootstrap page bound to their approved GitHub identity. The
   server selects a fixed account/app/secret destination, never browser-supplied
   repo or secret names. It creates cryptographic, short-lived, single-use state
   bound to that browser session and purpose; HTTPS Secure/HttpOnly/SameSite cookie.
2. Human presses Connect once and completes Geni consent/login/2FA themselves.
   Server-side `response_type=code` uses a registered matching redirect URI; state
   is verified before code exchange, consumed atomically, and rejected on replay,
   mismatch, cancellation or timeout. No code or token displayed or returned to JS.
3. Backend exchanges the code, checks required fields, stores refresh bundle plus
   access token via GitHub encrypted-secret REST API, and returns a value-free
   success screen. Browser response: no-store, no-referrer, strict CSP, no third
   party assets or analytics; clear response URL. Query codes are sensitive and
   must be redacted/disabled in provider access logs before deployment.
4. Do not call profile APIs to identify an account. Bootstrap must bind the intended
   app/account explicitly and the human-run existing identity check confirms the
   account before any upload. Separate accounts need separate destinations and
   credentials; never default to replacing another account's secret.

Cloudflare Workers Free is a candidate, not a deployed endpoint. Vendor lists a
free tier; no paid plan, domain purchase or billing activation is authorized here.
No new third-party account/terms acceptance in this change. An existing free
service may be reused only after checking access, privacy, rate limits and the
needed custody. Server requires App Secret and a narrowly scoped GitHub writer;
flag that custody before deployment. Initial registration may need a one-time
app-type/domain/callback change by the human if the existing Desktop app cannot
use code flow. That is an unresolved blocker to the no-developer-site bootstrap
promise, not something this patch silently automates.

## Release gates

- Independent exact-head review, signed commits, green CI and human approval.
- Environment configured as default-branch-only, permitted human reviewer, no
  admin bypass; workflow does not create or weaken its own protections.
- App server-side compatibility, redirect/domain and POST exchange support checked
  by the human. No secrets copied through public logs or agent messages.
- Bootstrap component implemented/tested for state replay, wrong identity,
  concurrent sessions, cancelled consent, stale code, secret write failure and
  query-log redaction before it receives real credentials.
- Human runs first renewal; fixed success only. Then separately human runs read-only
  upload plan to confirm token identity, permissions and duplicates. Renewal success
  alone never means an upload is safe. Token revocation needs new consent, not retry.

## Sources checked 28 October 2026

- Geni server-side OAuth, code/state exchange and refresh parameters:
  https://www.geni.com/platform/developer/help/oauth_server_side
- Geni client-side fields (no documented refresh token):
  https://www.geni.com/platform/developer/help/oauth_client_side
- Geni Desktop fields (no documented refresh token):
  https://www.geni.com/platform/developer/help/oauth_desktop
- GitHub Actions encrypted-secret REST API, permissions and LibSodium envelope:
  https://docs.github.com/en/rest/actions/secrets
- GitHub manual workflow invocation:
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- Cloudflare Workers pricing, free-tier candidate only:
  https://developers.cloudflare.com/workers/platform/pricing/
- OAuth2 standard, refresh and CSRF state context:
  https://datatracker.ietf.org/doc/html/rfc6749

Vendor docs contain inconsistent legacy example URLs (including an unrelated
provider in the PHP example). Use the documented HTTPS Geni endpoint, not copied
example code. Sources establish documented capability, not tested app behavior.
