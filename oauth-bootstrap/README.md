# Gated OAuth bootstrap (not deployed)

Tracking: #162

Draft implementation only. No real credential, host URL, identity, deployment or
live OAuth test belongs in this directory. Existing local-copy callback is unchanged.
This worker must not be deployed until independent security review and human
approval, then verified identity-gate/logging/secrets setup.

## Shape

GitHub OAuth login is the identity gate, with no requested scopes and S256 PKCE.
A dedicated login app is separate from the repository secret writer. A same-origin
POST starts login and sets a Secure, HttpOnly, SameSite=Lax browser-binding cookie.
A one-time Durable Object state stores the verifier, binding hash and expiry for
ten minutes. Callback atomically consumes the state, exchanges the GitHub code
at the fixed endpoint and checks the numeric GitHub user ID against private
configuration. Login names and email addresses do not grant access. Unexpected
scopes, refresh tokens, wrong identities and failed revocation stop the flow.
The transient GitHub identity token is revoked immediately after identity lookup,
including wrong-account responses. No GitHub user token is persisted or refreshed.
GitHub owns the user's password and 2FA; neither is collected here.

The Worker issues a ten-minute HS256 signed session with fixed issuer/audience,
expiry, subject and random session ID. The cookie is Secure, HttpOnly, SameSite=Lax.
The session is reusable within its ten-minute lifetime; it is not a one-use credential.
Only OAuth state/codes are consumed once. A stale landing-page cookie is cleared
and shows GitHub login again. Expired identity at a protected callback fails closed.
Geni start requires that session and a separate same-origin POST. Geni state is
scoped to the authenticated numeric ID plus session ID and a second browser-binding
cookie. Invalid bindings do not consume another session's state. Replays, duplicate
fields and cancellations are rejected. Expired data is removed by DO alarms.
No paid Access/Zero Trust subscription or payment method is required or allowed.

The server exchanges a code by POST to the fixed documented Geni endpoint; POST
support still needs a human test. Passwords and 2FA stay in the human's Geni browser.
Only fixed GitHub secret names can be written. A pinned TweetNaCl sealed-box library seals each value with
GitHub's public key, using a narrow secret-writer credential, never browser JS.
The refresh bundle is saved before compatibility access token and pending marker
is cleared last. Partial failure may need manual refresh recovery or re-consent;
no automatic token request retry. No profile API, user data tree, upload, dispatch,
log output, external analytics or token display exists here.

## Required setup after review

- Existing Cloudflare account, Workers Free only, no paid subscriptions/domain.
  Confirm current free plan before deployment. A payment-method requirement or
  potential usage-charge commitment is a stop, even if the base fee is zero.
- No Cloudflare Access subscription. Its Free activation checkout can require a
  payment method and contingent monthly usage charges, which are outside this
  project's no-money constraint. Do not activate it.
- A new dedicated free GitHub OAuth app for identity only, with exact deployed
  origin + /login/callback, wildcard callbacks disabled, device flow disabled,
  no requested scopes. Keep this distinct from repository-writer credentials.
- Vars CALLBACK_ORIGIN (HTTPS origin only), ALLOWED_GITHUB_ID (verified numeric
  account ID), GITHUB_LOGIN_CLIENT_ID, GENI_CLIENT_ID. Secrets SESSION_SIGNING_KEY
  (independent random 256-bit hex), GITHUB_LOGIN_CLIENT_SECRET, GENI_APP_SECRET and
  GITHUB_WRITER. Real identities and credentials are private deployment settings.
- Live compatibility checklist, not established by offline tests: GitHub returns
  token scope as the exact empty string for this no-scope app, accepts
  prompt=select_account and S256 PKCE, and revokes the transient token with204;
  Geni accepts the documented token exchange by POST. Stop if any check differs.
- Verify unauthenticated /start and /callback fail, wrong GitHub identity cannot
  establish a session, correct identity succeeds, code/query logs are disabled,
  and browser cookies have required flags. Do not start real Geni authorization
  before these checks and fresh security review + exact-head human approval.
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
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- https://docs.github.com/en/rest/apps/oauth-applications#delete-an-app-token
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://developers.cloudflare.com/workers/platform/pricing/

Documentation contains outdated/inconsistent example endpoints; use parameter
contracts, not copied PHP examples. Free-tier availability is documented, current
account billing and deployed logging must still be verified independently.

## Runtime regression

The initial libsodium dependency probes randomness at module import and its WASM
fallback expects browser facilities unavailable in Workers. Node-only tests and a
bundle dry-run do not establish runtime support. Production uses the pinned
TweetNaCl sealed-box library; libsodium remains a test-only independent decryption
oracle. The local workerd regression boots the real Worker, checks fail-closed
unconfigured behavior, then seals synthetic bytes inside Workers and decrypts the
ciphertext with libsodium in Node. CI runs both tests without credentials or remote
resources. `runtime-fixture.mjs` is synthetic-only and is never the deployed entry.
Run `node --test runtime.test.mjs` after `npm ci --ignore-scripts`.

## Provider-reporting limitation

Provider query retention and NEL cannot currently be certified disabled on the
selected shared host. The operator explicitly accepted the residual hosting-provider
URL-reporting risk after disclosure. Geni does not use PKCE here; its vendor code
lifetime and reuse semantics remain unverified. This is not a claim of zero provider
retention, and does not authorize other operators or deployments. Secrets and private
approval evidence stay out of the public repository.

Only query-free form pages use `strict-origin`, which permits real browser form
POSTs to retain their exact Origin without sending a path or query as Referer.
Callbacks, redirects and errors keep `no-referrer`; null Origin stays rejected.
The real Chrome regression runs against loopback HTTPS with synthetic credentials,
captures the authorization redirect without following it, and makes no live OAuth call.

Source: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy

## Safe failure stages

The stop page shows one fixed allowlisted stage label, never dynamic exception
text or provider response data. Labels distinguish setup, GitHub cookie/state,
exchange/shape/user/revocation/identity, Geni session/state/exchange/shape and
secret-writer key/bundle/access/finalization failures. They describe where the
flow stopped, not a proven root cause. They add no persistent logging. Share only
the stage, never the callback address. Do not replay codes or retry blindly.
