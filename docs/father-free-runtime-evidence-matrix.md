# Father free-runtime evidence matrix (#474)

Research only, checked 2026-10-29. No account, API, CLI, browser, deploy,
setting, billing, secret or workflow action was taken or is approved here.
Every row separates what official product documentation says from what this
project would still need as evidence about its own account. Product limits are
not this account's entitlement or usage: no row below claims a plan, capacity,
installed resource or measured CPU for any real account.

Status words: **documented** (an official page states it), **conflict**
(official pages disagree), **unknown** (no official statement found). Unknown
stays unknown; it is never read as supported.

## Evidence matrix

| # | Fact | Status, source (checked 2026-10-29) | Proof still required | Gap / blocker |
| --- | --- | --- | --- | --- |
| 1 | Workers Free CPU limit is 10 ms per HTTP request and 10 ms per Cron Trigger. CPU time counts code execution; waiting on fetch/KV/database does not count. | documented: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) | Provider CPU for the exact bundle on the target account, cold and warm, valid and invalid paths | Whether a full issuer request fits 10 ms is unproven |
| 2 | Workers Free allows 100,000 requests/day, reset at 00:00 UTC; above it Error 1027 (fail open bypasses the Worker, fail closed returns the error). | documented: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) | Actual account daily usage, if any other Worker shares the allowance | Other workloads on the account are unknown |
| 3 | Memory is 128 MB per isolate; startup (global scope) must finish within 1 s; Free Worker size 64 MiB uncompressed; 100 Workers per Free account. | documented: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) | Final bundle size and startup measured in workerd | None blocking at design stage |
| 4 | Free subrequests: 50 external and 1,000 to Cloudflare services per invocation. The 2026-02-11 change raised only Paid plans. | documented: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [changelog 2026-02-11](https://developers.cloudflare.com/changelog/post/2026-02-11-subrequests-limit/) | Exact counted call plan (GitHub API, JWKS, redirects, retries) below 50 | Which calls count as "Cloudflare services" for a given binding must be checked per binding |
| 5 | Exceeding CPU or memory produces Error 1102. Higher CPU quantiles in metrics "may appear to exceed" limits without errors because of a rollover mechanism. | documented: [Error 1102](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1102/), [Metrics and analytics](https://developers.cloudflare.com/workers/observability/metrics-and-analytics/) | Design must assume a hard 10 ms per request | Rollover rules are not specified; never budget on them |
| 6 | Workers Free supports only SQLite-backed Durable Objects. Free daily: 100,000 requests, 13,000 GB-s duration, 5 million rows read, 100,000 rows written (deletes count as writes); 5 GB stored total. Exceeding a limit fails further operations of that type; reset 00:00 UTC. | documented: [DO pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/) | Actual account DO usage; rows read/written per issuance from a real SQLite test | A failed write after the slot reserve must leave a stopped, value-free state |
| 7 | DO CPU on Free. The DO limits table lists 30 s default CPU (configurable to 5 min) for SQLite-backed objects, and also says Workers limits apply "according to your Workers plan". | conflict / unknown: [DO limits](https://developers.cloudflare.com/durable-objects/platform/limits/) | A documented statement or a measured, separately approved benchmark | Plan the owner DO against 10 ms until resolved |
| 8 | DO storage per object: the limits table says 10 GB, the FAQ says 1 GB on Free. Free accounts have 5 GB total DO storage. Max 100 DO classes on Free. | conflict: [DO limits](https://developers.cloudflare.com/durable-objects/platform/limits/) | None needed for the small slot records, but do not cite 10 GB | Use the lower figure |
| 9 | Workers Web Crypto supports Ed25519 sign/verify/generateKey/importKey/exportKey (standard name `Ed25519`; `NODE-ED25519` is a legacy variant without raw private import). RSASSA-PKCS1-v1_5 and ECDSA sign/verify are supported. Native crypto is described as "significantly faster" than pure JavaScript; no numbers. | documented: [Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/) | workerd micro-profile of one Ed25519 sign plus JWT verify with synthetic keys, then provider CPU | No published CPU cost for either operation |
| 10 | JWT `RS256` is RSASSA-PKCS1-v1_5 with SHA-256, so an RS256 OIDC token maps to a supported Web Crypto verify. | documented: [RFC 7518 §3.1/§3.3](https://www.rfc-editor.org/info/rfc7518/) | Read the actual GitHub OIDC `alg`/JWKS `kty` from a fixture captured under its own approval; no assumption | Base64url decode, JSON parse, claim checks and JWKS import also cost CPU |
| 11 | A Worker reachable only through a service binding can be kept off the public Internet. The binding is what grants permission to call Worker B's public methods; Worker B must be on the same account. Each call counts toward subrequests; one request allows at most 32 Worker invocations. | documented: [Service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/) | Installed binding readback and receiver-side fixed pins | Any same-account administrator can add another binding; a binding is not a source attestation |
| 12 | Whether service-binding invocations count toward the 100,000/day request limit or have their own CPU budget. | unknown: [Service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/) | Official statement or measured, approved benchmark | Count each hop as a full request and its own 10 ms until resolved |
| 13 | All Workers are assigned a `workers.dev` route when created or renamed, and it is public when the subdomain is enabled. Disabling `workers.dev` does not disable Version, Preview or Deployment URLs. A dashboard-only disable is re-enabled by the next Wrangler deploy unless the config sets `workers_dev = false`. | documented: [workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/) | A supported creation method that is never exposed, or an accepted residual | Initial upload exposure stays a blocker (matches the #441 plan); no exposure window is documented either way |
| 14 | Invocation traces carry `cloudflare.cpu_time_ms`, `cloudflare.wall_time_ms` (root span), `cloudflare.script_version.id`, `faas.version`, `cloudflare.script_tags`. | documented: [Spans and attributes](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/) | Availability on the account, sampling rate, retention and an authorized read route for the exact run | The page says nothing about plan availability or completeness |
| 15 | Free observability allowance. One page: Workers Logs on Free, 200,000 events/day, 3 days retention. Another: 0.5 GB ingestion/day, 7 days retention, ingestion stops at the limit until 00:00 UTC. | conflict: [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/), [Observability pricing](https://developers.cloudflare.com/observability/pricing/) | Which allowance applies to this account | Retention may be as short as 3 days; capture evidence within it |
| 16 | Telemetry query API exists (keys, values, run a query, live tail). | documented (index only): [Telemetry API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/) | Exact method/path/permission per endpoint, read from its own page | Not confirmed in this pass |
| 17 | Read-only readback: `GET /accounts/{account_id}/workers/scripts/{script_name}/versions` lists `id`, `number`, metadata (no bindings in the schema). `GET .../script-settings` returns logpush, observability, tags, tail consumers (no bindings). `GET /accounts/{account_id}/workers/durable_objects/namespaces` returns `id`, `class`, `name`, `script`, `use_sqlite`. All accept read-only Workers permissions, including per-Worker "Metadata Read-Only"/"Content Read-Only". | documented: [List versions](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/list/), [Script settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/), [DO namespaces](https://developers.cloudflare.com/api/resources/durable_objects/subresources/namespaces/methods/list/) | Deployed module bytes and the binding list for an exact version | No confirmed read route for bindings or deployed bytes in this pass (version detail, content and deployments pages not read) |
| 18 | Per-Worker roles (Metadata Read-Only, Content Read-Only, Editor, Admin) apply to account-owned API tokens scoped to "Specified Workers"; Durable Objects inherit the implementing Worker's permissions. | documented: [changelog 2026-09-15](https://developers.cloudflare.com/changelog/post/2026-09-15-granular-worker-permissions/) | Whether a Specified-Workers token can call account-level reads (namespace list, subscriptions) | Narrow audit-token shape is a candidate, not verified |
| 19 | Subscriptions: `GET /{accounts_or_zones}/{account_or_zone_id}/subscriptions` needs Billing Read or Billing Write; returns `rate_plan`, `state`, `price`, `frequency`, period dates. | documented: [List subscriptions](https://developers.cloudflare.com/api/resources/accounts/subresources/subscriptions/methods/get/) | Owner-held read of the account's rate plan | Billing Read exposes billing data beyond Workers; must be disclosed, not described as narrow. No documented "entitlement" endpoint was found |

## Why local wall clock is not provider CPU

Local wall time (Node, Miniflare or workerd on a laptop or CI runner) includes
scheduler noise, a different CPU and JIT state, and no provider isolate reuse.
It also mixes I/O waiting, which the provider excludes (row 1), with execution.
The provider measures CPU inside its own isolate and may apply rollover rules
(row 5). A local pass can show that a path is far from 10 ms or clearly over
it; it cannot show that the exact bundle fits on the target account. Only the
provider's own per-invocation CPU for the exact version (row 14), from a
separately approved benchmark, counts as that evidence.

## Minimal next read-only checks (not run)

Each needs its own approval, an owner-held credential and no write. None is
requested here.

1. Plan: the account's `rate_plan` and `state` (row 19). Needs account ID and
   a Billing Read token held by the owner; the owner may instead share a
   value-free statement "Workers Free, no paid add-on".
2. Usage: today's Workers requests and DO requests/rows for the account
   (rows 2, 6). Needs read access to account analytics; exact query not yet
   chosen.
3. Namespace inventory: `GET .../durable_objects/namespaces` (row 17). Needs
   account ID and a Workers read token; output is IDs, class and script names.
4. Version inventory for an exact script: `GET .../versions` and
   `GET .../script-settings` (row 17). Needs script name.
5. Doc reads still missing: version detail, script content, deployments and
   telemetry endpoint pages (rows 16, 17). These are documentation reads, not
   account access, and can be done in the next research pass.

## Workable choices

- Design the issuer for a hard 10 ms per request, including each service-binding
  hop and the owner DO (rows 1, 7, 12). If one Ed25519 sign plus JWT verify plus
  claim checks does not fit in workerd profiling with margin, revise the design.
- Keep each request under 50 external subrequests with fixed, counted calls
  (row 4) and at most 32 invocations (row 11).
- Use per-Worker read-only roles for any audit token if account-level reads work
  with them (row 18); otherwise disclose the wider scope.

## Blockers that stay open

- Actual plan, usage and capacity of the account (rows 2, 6, 19).
- DO CPU limit on Free (row 7) and service-binding request/CPU accounting (row 12).
- Never-exposed initial creation (row 13).
- Authenticated readback of deployed bytes and bindings (row 17).
- Provider CPU availability, sampling and retention for exact-run evidence
  (rows 14, 15).

These are open facts, not promises. Nothing here creates, changes or approves
any account resource, permission, credential or cost.
