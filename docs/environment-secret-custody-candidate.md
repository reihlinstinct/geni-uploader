# Fake-only environment-secret custody candidate (#475)

Dormant storage candidate for option A of
[click-only-oauth-custody.md](click-only-oauth-custody.md). It is NOT imported
by `oauth-bootstrap/worker.mjs` or any live path, has no network default and is
exercised only with an injected fake `fetch` and fake `seal`. No secret, key,
setting, callback, OAuth exchange, deployment, workflow permission or live API
call is added or approved here.

## What it does

`createEnvironmentSecretCustody(config, { fetch, seal })` takes a closed
registry from trusted construction config only. Each slot fixes the canonical
owner, repository owner/name, numeric repository ID, environment name and secret
name. Two slots cannot share one destination. A callback, query or request body
can choose only a slot name that already exists. It can never choose a
repository, environment, secret, owner or URL. The registry is copied and frozen
at construction, so later mutation of the config object cannot redirect a write.

`storeBundle({ slot, bundleJson })` accepts exactly those two fields. Both
strings are captured before any await. The bundle must be compact canonical JSON
with exactly the bundle keys of `scoped-custody-policy.mjs` (#477), and its slot,
owner, repository ID, environment and secret must equal the registry entry. One
call makes exactly two requests to the fixed origin `https://api.github.com`:

1. `GET /repos/{owner}/{repo}/environments/{environment_name}/secrets/public-key`,
   `redirect: manual`. Only status 200 with exactly `key_id` and a base64
   32-byte `key` is accepted, with a bounded body.
2. The whole bundle is sealed with the injected `seal`. The ciphertext must be
   exactly the sealed-box size (message + 48 bytes). Then one
   `PUT /repos/{owner}/{repo}/environments/{environment_name}/secrets/{secret_name}`
   with `{encrypted_value, key_id}`, `redirect: manual`. Only 201 (created) or
   204 (updated) counts as stored.

There is no raw access-token route and no second secret: the stored value is
always the complete versioned bundle.

## Results are fixed and value-free

Every outcome is a frozen object `{status, slot, authenticated: false,
write_permitted: false}`. `status` is one of `stored_created`, `stored_updated`,
`input_rejected`, `slot_busy`, `public_key_failed`, `seal_failed` or
`write_state_unknown`. No token, raw provider body, exception text or log line
is returned or emitted.

`write_state_unknown` covers any PUT error, redirect or other status. The PUT may
have committed, so this is never reported as success or failure of storage, and
the module never retries, falls back to another slot or displays a secret. A
second concurrent call for the same slot returns `slot_busy`; nothing queues.

## What it does not do

- It is not authentication. A stored result proves only that GitHub accepted a
  write; it does not prove who connected, and it never permits a Geni write.
- It does not validate custody policy, expiry or revocation. That is
  Instinct-owned (#477). `checkCustodyContent` is a consumption-time check and is
  not called or imitated here. A truthy callback is not accepted as a policy
  decision. Admission before storage waits for an agreed narrow interface.
- It does not hold the writer credential. Authorization is the injected
  `fetch`'s responsibility, and its custody stays a separate reviewed decision.
- It does not prove deployment, environment protection rules, reviewer or
  bypass settings, or that any consumer enforces freshness.

## Official contract checked 2026-10-29

From [REST API endpoints for GitHub Actions Secrets](https://docs.github.com/en/rest/actions/secrets):

- Get an environment public key: `GET .../environments/{environment_name}/secrets/public-key`,
  response `key_id` and `key`, status 200. Fine-grained token: "Environments"
  repository permission (read).
- Create or update an environment secret: `PUT .../environments/{environment_name}/secrets/{secret_name}`,
  body `encrypted_value` and `key_id`, status 201 when created and 204 when updated.
  Fine-grained token: "Environments" repository permission (write). Classic
  tokens need `repo`.
- `environment_name` must be URL-encoded; the module encodes every path part.

From [Encrypting secrets for the REST API](https://docs.github.com/en/rest/guides/encrypting-secrets-for-the-rest-api):
values are encrypted with libsodium sealed boxes against the base64 public key,
and the ciphertext is base64-encoded.

The docs name a fine-grained "Environments" permission for these calls, not a
narrower per-secret one. A writer with that permission can replace any
environment secret in the repository. That replacement power must be disclosed
and is not described as isolated. GitHub App permission names for these
endpoints are not stated on the page and remain to be verified.

## Tests

`oauth-bootstrap/environment-secret-custody-candidate.test.mjs`, synthetic only:

- an exact two-call trace;
- the whole bundle is sealed;
- no `Authorization` header or sentinel appears in any request or result;
- no global `fetch`, and no default dependency;
- the closed registry, and mutation after construction;
- unknown slots, including `__proto__`, and every bundle leaf missing or changed;
- non-canonical JSON;
- bad public-key status, redirect and shape;
- bad seal output;
- ambiguous writes;
- request mutation across await;
- same-slot concurrency.

The suite is run directly with `node --test`. It is not yet in the
`runtime.test.mjs` aggregator; adding it waits for agreement (#475).
