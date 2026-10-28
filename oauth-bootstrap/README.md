# Gated OAuth bootstrap (not deployed)

Tracking: #162

Draft implementation only. No real credential, host URL, identity, deployment or
live OAuth test belongs in this directory. Existing local-copy callback is unchanged.
This worker must not be deployed until independent security review and human
approval, then verified identity-gate/logging/secrets setup.

## Shape

Cloudflare Access signed identity JWT is verified by jose against a fixed team,
audience, RS256 algorithm and exact configured email. Missing JWT fails closed,
even if someone reaches workers.dev directly. All pages, including callback,
require the same allowed identity. Start uses same-origin POST, then sets a Secure,
HttpOnly, SameSite=Lax five-minute browser-binding cookie. Cryptographic nonce state
is scoped to subject+binding hash, stored in a free SQLite Durable Object and
consumed atomically before code exchange. Invalid bindings do not consume another
session's state. Replays, duplicate fields and cancellations are rejected.

The server exchanges a code by POST to the fixed documented Geni endpoint; POST
support still needs a human test. Passwords and 2FA stay in the human's Geni browser.
Only fixed GitHub secret names can be written. libsodium seals each value with
GitHub's public key, using a narrow secret-writer credential, never browser JS.
The refresh bundle is saved before compatibility access token and pending marker
is cleared last. Partial failure may need manual refresh recovery or re-consent;
no automatic token request retry. No profile API, user data tree, upload, dispatch,
log output, external analytics or token display exists here.

## Required setup after review

- Existing Cloudflare account, Workers Free only, no paid subscriptions/domain.
  Confirm current free plan before deployment. Access Free approval and allowed
  identity are private configuration, not committed. A new provider term requiring
  more than approved free Access is a stop.
- Configure Access application for this Worker's actual deployed hostname, allow
  only the approved email. Verify JWT rejection directly on workers.dev and that
  Access protects callback navigation as well as start. No fabricated URL is a setup
  instruction. Allowed email/identity should never become a public repo example.
- Vars CALLBACK_ORIGIN (HTTPS origin only), ACCESS_TEAM (HTTPS cloudflareaccess.com
  team origin), ACCESS_AUD, ALLOWED_EMAIL, GENI_CLIENT_ID. Secrets GENI_APP_SECRET and
  GITHUB_WRITER. Server holds no account password/2FA. Session store holds identity
  subject+hash+expiry only, five minutes. Alarm deletes expired data.
- GITHUB_WRITER: separate credential scoped Actions-secrets write on this code repo
  only, no contents/issues/other repositories. The built-in workflow token is not
  sufficient. Repository secret-writer permission can affect all repository secrets,
  not literally just one secret. Keep credential expiry/rotation records privately.
- Backend requires App Secret, writes App Secret+refresh token to the encrypted
  workflow bundle, transiently receives code/access/refresh; approved custody must
  cover both Cloudflare and GitHub. No shared credentials with another account.
- Configure exact deployed origin + /callback as matching Geni redirect and Site
  Domain if needed, by the human only. Current app compatibility/mode is unverified.
  The user may need one-time app metadata change; cannot promise zero setup.
- Disable and verify provider request URL/query logging, tail, Logpush, observability,
  analytics and any Access callback query retention before real authorization.
  Code arrives in the URL query. Application no-store/no-referrer/redirect cannot
  erase provider logs. If redaction cannot be confirmed, do not enable real flow.
- Bootstrap can replace stored authorization: only the approved human starts it;
  do not run two bootstrap sessions concurrently with refresh/upload. A later
  human-run identity plan must confirm the intended Geni account; successful OAuth
  is NOT identity proof. There is no account profile lookup in the callback.

No deploy command here: setup and final host are intentionally gated. The
wrangler file declares a candidate Worker and DO without real identifiers.

## Offline tests

`npm ci --ignore-scripts && node --test test.mjs`. Fixtures are synthetic only.
Tests inject identity and network dependencies into an internal handler. Production
export calls the real JWT verifier. Real service compatibility is not established
by offline success. CI executes tests without secrets. No e2e Geni activity.

## Sources

- https://www.geni.com/platform/developer/help/oauth_server_side
- https://docs.github.com/en/rest/actions/secrets
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- https://www.cloudflare.com/plans/zero-trust-services/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://developers.cloudflare.com/workers/platform/pricing/

Documentation contains outdated/inconsistent example endpoints; use parameter
contracts, not copied PHP examples. Free-tier availability is documented, current
account billing and deployed logging must still be verified independently.
