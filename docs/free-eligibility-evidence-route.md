# Read-only Free-eligibility and capacity evidence route (#437)

Design and official-source research only, checked 2026-10-29. This file performs
no account request, credential creation, subscription change or deployment.
Actual account plan, capacity and exact-run CPU evidence remain unverified.
A preparation manifest saying `free` is an assertion until authenticated evidence
is independently checked. A zero-cost proposal must stay blocked on UNKNOWN.

## Separate the evidence layers

1. **Account/product plan:** official `GET /accounts/{account_id}/subscriptions`
   lists account subscriptions and accepts Billing Read or Billing Write. Use
   Billing Read only, fixed to the approved account, if an authorized credential
   exists. A Workers-only credential is not documented as sufficient. A403 is
   not proof of a paid plan, Free plan or exact missing permission. Never expand
   scope, mint a token or switch credentials silently to get past it.
2. **Workers settings:** `GET /accounts/{account_id}/workers/account-settings`
   returns optional `default_usage_model` and `green_compute`. Neither the schema
   nor an arbitrary string such as `standard` establishes a Free subscription.
   Do not infer plan from it, from script availability, or from Free defaults in
   pricing prose. These settings are useful configuration evidence only.
3. **Usage/capacity:** current plan limits and actual shared-account consumption
   are separate. Authenticated plan evidence does not prove remaining requests,
   storage, row writes/reads, Worker count or execution capacity. Inventory,
   measurement completeness/delay and concurrent use must be accounted for.
4. **Exact-workload CPU:** official Workers CPU graphs use reservoir-sampled
   quantiles. GraphQL `workersInvocationsAdaptive` exposes request/error/subrequest
   sums and CPU P50/P99 grouped by time/script/status. This does not by itself
   identify every invocation's source version or certify a maximum CPU bound.
   Wall-clock/local timing is not provider CPU time.

## Closed read-only collection proposal, not an executable client

An eventual collector needs a fixed account and provider origin, authenticated
HTTPS, no redirects/retries, bounded pages/body/aggregate bytes/deadline, and a
private source receipt with collection time, interval and credential scope label
but no secret. Verify success, errors, complete pagination and account identity.
Missing fields, partial pages, truncation, unexpected schema or ambiguous product
mapping produce UNKNOWN and stop. Do not send billing details to a public log.

The documented subscription response has optional `rate_plan` fields including
id/public_name/scope/sets, state, price and period. Its generic example contains
inconsistent-looking names and prices; examples are not real account evidence.
Do not treat any `id: free` row as Workers entitlement, or an empty list as proof
of Free. Before implementation, recover the actual supported product mapping or
an authenticated dashboard entitlement readback. Preserve source and rationale
for that mapping and independently review it. No guessed product IDs.

If API access cannot establish the plan, an authorized dashboard account read
may establish the same fact, including selected account and Workers plan. A
challenge is a blocker, not permission to bypass or repeatedly retry it. Do not
upgrade, downgrade, add a card, change budget or delete old namespaces to make
Free eligibility true. Any such action needs its own approval and is outside
this route.

## Current public limits and what they do not establish

Official Workers pricing/limits list Free100,000 requests/day,10ms CPU per
invocation,50subrequests/request and100Workers. Durable Objects Free supports
SQLite-backed namespaces only; its compute/storage quotas are separate and
shared. Re-check official limits and actual entitlement before an action.
The design's synthetic one-request/no-network profile is a smaller bound,
not proof the complete future issuer fits10ms. Per-invocation CPU observation
and exact deployed version correlation still need a verified provider-supported
route before calling a full benchmark ready. Sampled aggregates are supporting
evidence, never substituted silently for an exact-run requirement.

A valid future evidence record must bind the account/product, complete current
plan readback, current quota definitions and actual capacity observation,
collection/freshness/deadline, exact benchmark source/installed version, and
remaining ambiguities. A hash alone authenticates none of that. Re-read before
execution and stop if plan/capacity changes; no API-level atomicity is claimed.
No cost guarantee can be made from this research alone.

## Official sources

- Subscriptions schema and Billing Read acceptance:
  https://developers.cloudflare.com/api/resources/accounts/subresources/subscriptions/methods/get/
- Workers settings schema:
  https://developers.cloudflare.com/api/resources/workers/subresources/account_settings/methods/get/
- Billing Read description and account scope:
  https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Workers Free/Paid pricing and default access:
  https://developers.cloudflare.com/workers/platform/pricing/
- Free resource and CPU limits:
  https://developers.cloudflare.com/workers/platform/limits/
- SQLite-only Free Durable Objects and quotas:
  https://developers.cloudflare.com/durable-objects/platform/pricing/
- Sampled CPU metrics and aggregation delay:
  https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
- GraphQL tutorial and exposed aggregate dimensions/quantiles:
  https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/
