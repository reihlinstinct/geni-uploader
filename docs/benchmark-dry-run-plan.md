# Blocked synthetic benchmark dry-run provisioning plan (#441)

This local function returns a candidate two-write plan, never an HTTP request,
installer, permission check, resolved action manifest or proof of readiness.
It verifies supplied bundle bytes against a supplied digest and checks the exact
small input shape. It cannot authenticate source/review/CI hashes or prove that
arbitrary bytes are the reviewed synthetic package. A later installer must bind
the closed builder output, source inventory and independent review before use.

The proposed new synthetic script has zero bindings, migrations, real keys or
storage. The candidate methods are the documented multipart script PUT and a
POST setting workers.dev and preview exposure false. Upload descriptor hashes
cover exact metadata and module bytes, NOT final multipart wire encoding. Wire
bytes still need to be closed before approval. Body hashes are not credentials.
The plan never permits overwrite/update of an existing target. A403/ambiguous
inventory is not evidence of absence. Verify account and absence independently
immediately before any approved create, and stop on races or changes.

Crucially, disabling exposure after upload does not prove the initial upload was
never exposed. Current plan stays blocked until supported creation semantics or
another reviewed method establishes this guarantee. Public fetch returns403 in
the benchmark, but that is not equivalent to having no public endpoint. No
routes/domains/dispatcher are added by this proposal. No arbitrary management
path, HTTP method or bindings are accepted from input.

The two writes are only candidate provisioning steps, not complete execution
counts. No invocation, CPU collection, audit, credential change or cleanup is
included. Required readbacks and internal invocation remain named blockers,
not fabricated GET/POST paths. No real resource version/namespace is invented.
The synthetic bundle uses no DO namespace; it does not provision the future
issuer/father pair. Earlier preparation schemas and this microbenchmark plan
are separate non-executable components, not a complete shared installer schema.

Failure stops and preserves evidence. Deletion, namespace replacement, budget
changes, upgrade and automatic retry are not cleanup permissions. Exact private
receipt retention and credential revocation need a verified route and separate
approved custody. The caller gets executable/approval/provider/CPU flags false
and explicit blockers. A zero cost ceiling is a requirement, not a cost promise.

This slice cannot justify asking the owner to provision yet: actual product
entitlement/capacity, initial exposure guarantees, internal invoker, exact-run
CPU/version observation, readback and private evidence are unresolved. It does
not create or change any account resource, permission, setting or credential.

## Official contracts checked 2026-10-29

- Multipart script PUT and metadata fields:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
- Multipart metadata semantics:
  https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/
- Script subdomain and previews disable POST:
  https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/subdomain/methods/create/

Official tracing documents list invocation CPU and version attributes, but that
alone does not establish availability, complete sampling, retention, exact
retrieval or authorization on the target Free account. Those remain open:
https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/
