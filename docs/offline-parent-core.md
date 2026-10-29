# Offline parent core

`people_core.py` is a synthetic, local-only prototype for #184, based on the
v0.5 design in #144. It is not imported into the source uploader, copied into
its image or wired to a workflow. There is no Geni HTTP client, token input,
account setup, service deployment or executable create command. Calling the
production adapter always returns a fixed disabled error.

The core validates an exact parent-only schema (one or two entries, explicit
living/privacy/owner-storage flags), canonical hashes and complete receipt
bindings. Receipt checks assume an independently authenticated envelope and OIDC
identity: they do not authenticate anything themselves or create consent.
Private data approvals must come from source-grounded owner/operator evidence.

The local SQLite journal is an append-only CAS prototype. It persists intent,
acknowledged ID, verified or blocked events with a per-owner version. An intent
blocks other operations across new manifest hashes. Acknowledged IDs return
GET-only resume instructions. There is no reset/delete/retry interface. The
prototype is not a deployed Durable Object, an authorization boundary or proof
against a malicious runner/database administrator.

Receipt validation and journal transitions are separate building blocks, not an
end-to-end write gate. A later reviewed coordinator must bind them, check count,
expiry and remote graph before each intent/POST, enforce service-side allowlists,
validate actual readback and never call the disabled production adapter. A direct
journal transition by itself authorizes no write. Unknown-intent retries remain
out of scope. SQLite file permissions, encryption, backup/recovery and production
OIDC/service authentication belong to later reviewed integration work.

Run synthetic tests with `python -m pytest tests/test_people_core.py`. They cover
schema mutations, every receipt binding, expiry, CAS races, durable crash/restart,
changed-manifest attempts to evade an old intent, acknowledged GET-only resume
and no reset/delete interface. Tests are not evidence of vendor API behavior.

Outstanding vendor proof remains complete parent visibility, add-parent union/slot
selection and explicit privacy readback. Current-user endpoint discovery is
publicly documented but its concrete production response must still be validated.
Broader relative creation, dates, images, invitations, edits, merges and deletion
are not implemented. No capability release or live creation is implied by this PR.

## Review hardening

`bind(data, receipt, expected, now)` orders schema validation, canonical manifest
hash comparison, count/owner comparison and full receipt/time binding. Journal
transitions separately bind receipt digest, run ID/attempt and anchor. They do not
replace this binder or independently authenticate a receipt. Integration must call
both under the reviewed coordinator.

The lock is per canonical owner/anchor, not per manifest or operation name: any
unverified intent blocks all new owner operations. Even a verified parent cannot
be created again with the same manifest/payload hash under a fresh operation ID.
New receipt/attempt bindings cannot take over an old operation. Acknowledged
GET-only resume does not authorize another POST or alter the original binding.

SQLite triggers reject UPDATE/DELETE of events, and transitions require the
owner version to equal the highest event version. This catches common raw-state
corruption, not a database administrator who can drop triggers or rewrite files.
A bounded busy timeout becomes a fixed Blocked error. Text fields require NFC and
reject controls, DEL and format/bidi characters. Duplicate/same-gender parent
names/genders produce review warnings, not guesses about vendor slot behavior.

The journal accepts a new payload hash under an already-used manifest only after
prior operations are verified. This is safe only when the caller derives each
payload deterministically from that validated manifest; arbitrary payload hashes
are not an authorization boundary. `Journal.owner` is free text, not a validated
vendor ID. The coordinator must supply the canonical validated owner/anchor and
must not use alternate owner strings to evade its lock. Database failures in
initialization, transition and resume map to a fixed Blocked error.
