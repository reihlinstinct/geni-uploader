# Fake-only provider readback correlation (#495)

The next content-correlation slice of #433. Not imported by a live Worker,
issuer, callback, installer or runner. No real account, credential, secret,
namespace, settings change, signing, deployment or vendor request is involved.

`createFakeProviderReadback(configJson, deps).inspect()` snapshots a canonical
constructor JSON string. Config accepts only synthetic ZZ script/class/binding
names and fixed account/version/deployment/SQLite namespace expectations.
Dependencies are exactly injected fetch/setTimeout/clearTimeout. There is no
network or credential default. Each constructed inspector has one attempt.
Failures cannot retry or resume through it.

The five fixed GET steps are:

1. Read deployments with per_page=1. The first entry is documented as the
   latest deployment actively serving traffic. Require one fixed deployment
   with exactly one expected version at 100 percent, never split traffic.
2. Read that exact version's complete expected resource object. Match all
   bindings, script etag/handlers and runtime/export metadata byte-equivalently
   under sorted-key canonical comparison. Extra resources fail closed.
3. Read fixed settings and compare the complete expected settings object.
4. Read namespace inventory with per_page=1000, requiring complete pagination
   metadata and exactly one matching namespace with fixed class/script/SQLite.
5. Read deployments again. Require unchanged exact deployment identity and
   traffic. This brackets the observations but is not an atomic provider read.

Each GET has a ten-second deadline, manual redirects, no retries, and a streamed
64 KiB body cap. Unexpected keys, response/error/redirect shapes, incomplete
namespace inventory, malformed UTF-8/JSON and changed state stop. A matching
version that is uploaded but not serving cannot pass the first step.

Success returns only a fixed phase, snapshot digest, authenticated:false,
installation_verified:false and write_permitted:false. No raw provider
response, target identity or exception text is returned or logged. The injected
fetch seam is not an authenticated provider principal.

## Boundaries still open

This is not full installation audit, authority or a release permit. Script etag
is compared as provider metadata, not asserted to be the reviewed bundle's
SHA-256. Exact complete deployed bytes still require the supported content and
multipart/version relation to be grounded and implemented. Changes between API
reads, changes after the final read and historical namespace rollback remain
unproven. A matching namespace record does not prove continuity of its data.
No audit receipt signer or authenticated internal issuer wrapper is supplied.

The closed candidate schema intentionally rejects extra/unknown provider fields,
capabilities, runtime flags and migration/export states rather than inferring
that they are safe. Future provider contract changes need explicit review.
Current limited binding types are fixed secret-name metadata, named service
bindings and one exact SQLite namespace. No secret values are read or accepted.
Free entitlement, account usage/capacity, provider CPU, exposure, credential scope
and eventual provisioning/run approvals remain separate blockers.

## Regressions

26 offline tests cover the fixed trace, single attempt, split/inactive versions,
redeploy during await, altered bindings/runtime/settings, wrong backend/namespace,
duplicates, incomplete pagination, errors, redirects, oversized streamed input,
UTF-8/JSON failures, deadlines and constructor snapshot. A real local workerd test
verifies the exact two-module import set and rejects outbound network.
No existing tests are skipped or loosened.

## Official contracts checked 2026-10-29

- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/
  documents the actively serving first deployment and version traffic shares.
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
  documents exact version resources, bindings and runtime metadata.
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/
  documents script/version settings and bindings, not Free entitlement.
- https://developers.cloudflare.com/api/resources/durable_objects/subresources/namespaces/methods/list/
  documents namespace class/script/SQLite metadata and pagination.

Official documentation supports route contracts, not account access, source
review, authentication or an approved installation.
