# Offline created-profile result contract

Related: #244, #240. This is a pure content validator, not a released writer,
transport, authenticated receipt, persisted status or permission to execute.
It performs no I/O. Production remains disabled. The complete #244 integration
is still open: authenticated private persistence and source-stage composition
are not implemented by this contract.

`profile_result.validate(value, expected_pins)` requires exact owner, payload,
run, artifact and approval content pins. All hash references are opaque SHA256
ciphertext/evidence descriptors supplied by a caller; they do not prove that
bytes exist or that an approval is authentic. The caller must authenticate
provenance, readback and authority before persisting any real result. Its output
explicitly keeps `production_enabled` and `provenance_authenticated` false.

Record the vendor-returned API `profile_id` separately from the vendor-returned
`profile_url`. Do not construct a URL from the API id: URL GUID and API profile
id are distinct identifiers. Equal digits in those identifiers are not proof
of identity either. The URL checker accepts only an HTTPS www.geni.com
people path with a nonempty name segment and positive numeric GUID, with no
credentials, port, query, fragment or encoded path separator. It does not fetch
that URL or prove that it resolves to the API id. Other vendor URL formats are
blocked for separate review, not silently rewritten. A future authenticated
writer must verify the id/URL relationship from the actual response/readback.

The supplied stages distinguish:

- `created_unverified`: acknowledgment reference and returned id/URL only;
  no readback or source refs. Never report this as verified success.
- `profile_verified_sources_pending`: distinct readback reference, no sources.
- `profile_verified_sources_attached`: readback plus distinct source refs.
- `profile_verified_sources_cited`: readback plus distinct source refs.

These labels are caller claims, not evidence of actual sources, tags or facts.
The validator cannot upgrade an attachment to a citation. Source upload, tagging
and field citation each need their own exact approval and authenticated readback;
profile creation alone authorizes none of them. Upload each document once and
reuse its verified id for all approved tags/citations. No source upload or other
Geni call happens here. No transition/reset/retry function is exposed. Uncertain
outcomes remain consumed in the separate intent authority and are reconciled
GET-only, never by recreating a profile. Private status and raw evidence must
stay private; never put living data or receipt references in public logs.

All keys and scalar types are strict, references bounded and distinct, and
output is a deep copy. Tests use invented identities only. Offline structural
consistency does not close release, deployment, shared-intent, encryption,
current graph, human-run or approval-provenance gates.
