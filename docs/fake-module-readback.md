# Exact module inventory in fake provider readback (#499)

Extends #495's content-correlation adapter, not a live provider audit or installer.
New mode `fake_provider_module_readback` adds one fixed content/v2 GET inside
the unchanged deployment bracket. The original mode and its five checks remain.
Constructor module inventory has exact name, MIME type, byte length and SHA-256.
No token, provider credential or network default exists.

The content GET uses the same ten-second deadline, no retry, manual redirect and
one-attempt rule. It streams at most 2 MiB before parsing. The strict candidate
multipart format accepts one unquoted ASCII boundary, no preamble or epilogue,
exact Content-Disposition and Content-Type headers, matching name/filename and
exactly the inventoried parts. Missing, extra, duplicate, traversal, ambiguous
headers or malformed delimiters fail. Binary module bodies are hashed directly,
never decoded as text. Boundary changes alone do not change the inventory digest.
The limited format is deliberate: other legitimate provider variants block until
explicitly supported and reviewed; this is not a generic multipart parser.

The quoted response ETag must equal the fixed version's script etag. This
correlates provider metadata only. ETag is NOT assumed to be SHA-256 of a module,
bundle or multipart body. Module hashes independently match expected bytes.
Multipart raw response hashes are not used because random boundaries differ.
The unchanged final deployment read rejects a version/deployment/traffic change
observed during the sequence. Success still says authenticated:false,
installation_verified:false and write_permitted:false.

## Remaining boundaries

No atomic cross-API snapshot is claimed. A deployment can change away and back
between reads, or after the bracket. ETag semantics and cryptographic binding to
an immutable version are not promoted beyond provider metadata. Namespace data
history, audit-principal authentication, source/review/install provenance, Free
plan/capacity, CPU, exposure, issuer custody and approval remain separate gaps.
No live service imports this candidate, and no gate is loosened.

15 new tests cover changed boundary/same bytes, exact binary modules, two parts,
extra/duplicate/missing parts, wrong name/type/filename/hash/ETag, malformed close,
traversal/header ambiguity, oversized streams, six-call bracket composition and
redeployment rejection. A real local workerd test checks closed imports with
outbound network denied. All 26 original readback regressions remain unchanged
apart from adding the newly required helper to the closed import inventory.

## Official contracts checked 2026-10-29

- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/content/methods/get/
  documents content/v2 and Content Read-Only access.
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/get/
  documents original raw script download, not JSON.
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
  documents script etag metadata. Its text does not establish etag equals SHA-256.
- https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/
  documents multipart module naming. It is an upload contract, not proof of every
  download header/byte variant or version-atomicity.

No account metadata, code bytes, credential or private project data is included.
