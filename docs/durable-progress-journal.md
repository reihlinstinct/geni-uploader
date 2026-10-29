# Canonical durable progress journal (#367)

The receipt-only `/journal` and `/journal-read` routes require the same signed
fixed workload/run/plan, expiry and canonical owner namespace as execution.
Append-only SQLite records bind all six operation fields and run. Start is
exclusive, then sequence and previous-entry SHA256 must match. At most100 entries,
4096 request bytes each, fixed stage/receipt keys and typed opaque hashes/flags/ID.
No raw genealogy, approval, provider response or token is accepted. No overwrite,
reset/resume/delete route. Read-only inspection does not authorize execution.

The journaled Node wrapper now commits a remote start before any private writer,
and commits each opaque partial receipt and execute/completion-attempt before
continuing. Local fsynced journal remains a secondary record. A failed/lost remote
journal response stops without a retry; the committed entry may already exist.
Known consumed intent is never cleared. Later inspection after workload expiry
still needs separate recovery authority; no expiry bypass is added. Cloudflare
provisioning, namespace identity and effective retention remain release checks.

Tests exercise actual SQLite concurrency/restart, duplicate/reorder/run mismatch,
forbidden private/secret fields, signed service append/read before consume,
actual age/journaled runner flow and failed remote start with no execute request.
The create release gate is unchanged. No real hosted request, configuration,
provisioning, secret, deploy or workflow change occurs. Lower-level unjournaled
runner remains for tests; the installable CLI uses only the journaled entrypoint.
