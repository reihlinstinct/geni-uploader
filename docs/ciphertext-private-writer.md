# Unconnected private ciphertext writer candidate (#296)

This module is not imported by production and never looks up credentials. Tests
mock all HTTP. It grants no owner authority, encryption proof or retention claim.
Only separately approved release config, already-encrypted bytes and a narrowly
scoped private writer credential may eventually call it. Caller config is not
self-authenticating: #304 must bind it to module-owned reviewed release config.

## Contract

`persistCiphertext({bytes,descriptor,storagePins,credential,onProgress})` uses
fixed api.github.com Git routes only. The descriptor mirrors ciphertext_evidence
fields EXCEPT `commit`: that cannot be known until writing, so it is absent on
input and added to the returned descriptor after verification. No hash is faked.
Caps remain1MiB/object and8MiB/operation. existing_total_bytes is an input from
the future authenticated durable ledger, not independently authenticated here.
The plaintext screen is only rejection of obvious plaintext, never encryption
proof, and can reject actual ciphertext. Approved encryption provenance is still
required. Current Git flow supports a single root ordinary filename, not folders.

Before writes: private numeric repository/name, exact current branch ref/parent
commit/tree, no truncation or existing destination. Then one blob, one add-only
tree preserving ALL old entries and no unrelated additions, one commit with
exactly one expected parent, immutable commit inspection, force:false ref update,
exact blob byte/hash/base64 readback and final exact ref inspection. Fixed generic
commit message contains no private values.11requests,10second deadline,
2MiB/response declared+stream bound, depth12. No redirects/pagination/retries,
refresh/reset/delete/force or plaintext fallback. No response URLs followed.
Deadline stops late abort-ignoring responses from issuing subsequent writes.

`onProgress` receives immutable partial object IDs after each object and BEFORE
attempting ref update. Caller must persist them without erasing permanent create
intent. A thrown error carries the known partial receipt. A lost write response
may mean the write happened without a returned ID; this is ambiguous, never a
retry invitation. GET-only reconciliation is separate, not implemented here.
Progress callback failure stops further writes. Callback durability/authorization
is external and mandatory before production. Abort cannot undo an already-sent
write, and a timed-out callback might finish; no success is claimed on timeout.

Repository administrator rewrite/deletion, key loss, credential scope and total
storage/billing/backup retention remain explicit release checks. Git commit/ref
readback does not provide permanent retention. No private destination, token or
family data is included in the repository. Sources and result status persistence
are separate composition work. The existing create intent must remain consumed
on ANY failure; this module never resets it.

## Tests and mutation checks

43mockedHTTP tests cover response loss at each of11boundaries, private identity,
stale ref, truncation/ordinary file modes, parent/commit/tree preservation,
remote bytes, caps, fixed path, partial receipts, no retries, redirect/status,
and late fetch after deadline.17named mutants executed:16killed; removing the
byte-equality readback guard survives because independent exact Git blob SHA1
AND SHA256 checks reject changed bytes. This is redundant absent a dual collision,
not an uncovered acceptance path. All other mutations have isolated fixtures.
