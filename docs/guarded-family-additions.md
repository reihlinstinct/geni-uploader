# Guarded family addition core

The core is effect-injected and has no credential or HTTP dependency. The
separately protected wiring described below supplies immutable private source
loading and approval checks. Merging code never authorizes a live dispatch.

The core models either one additional female parent or an ordered batch of four
siblings. Each plan pins the owner, existing parent payloads, union and children.
All names are bilingual; living/private fields are mandatory. Dates, places,
photos, merges and unrelated edits are excluded by the payload schema.

Before a create it checks the owner and parents, then the exact union membership.
Each item has a stable payload-bound consume marker, independent of expiry or run
ID. The store must implement atomic create-only markers and immutable encrypted
receipts. Consumption precedes any possible send. The returned ID is saved before
readback. Raw parsed responses are captured through the encrypted save seam before
validation or another effect. Storage failure stops further effects.

After each create, exact profile fields and union partners/children must pass
before the next entry. Failure stops the batch immediately. Prior successful
items remain created; no automatic retry, repair, rollback, deletion or resumption
exists. A new run must not reset or replace old markers.

The vendor's choice of parent union is a live experiment, not proved by docs.
Wrong-union responses stop without repair. Each final approval must name every
create, ordered payload hashes, source/executor/config pins, expiry, possible
hidden duplicate risk, requested-but-unproved privacy and union-selection risk.
The protected run also needs human deployment approval. Offline PASS grants no
permission to execute.

## Separately protected wiring

The separate `protected_family_additions.py` entry point is wired only through
`guarded-family-additions.yml`, never through the original one-parent workflow.
The original transport's 12-call/one-parent admission remains unchanged. The
separate transport has exact plan-bound GET/POST allowlists, a 40-call cap,
10-second pacing and an uncertain-send latch. Only a valid new-ID acknowledgement
opens the next item's send latch. No redirect, refresh or automatic retry exists.

`FAMILY_CONFIG_JSON` is a private configuration secret. `FAMILY_CONFIG_SHA256`
and `FAMILY_EXECUTOR_SHA` bind its exact bytes and the reviewed master commit.
`FAMILY_CONFIRM` must equal `CREATE_APPROVED_FAMILY_ADDITIONS`.
`FAMILY_OUTPUT_DIR` is a fresh absolute encrypted-output directory. Existing
`FAMILY_TREE_PAT` and `GENI_SECONDARY_ACCESS_TOKEN` supply the private writer and
vendor user credential. The config pins an immutable private plan file and its
`plan_sha256`, owner, source, recipient and expiry. The loaded plan must match
owner, expected name, merge policy and expiry exactly. No public input contains
names or IDs. No secret is printed. Snapshots retain the run/executor and time.

The protected environment, exact actor/ref/run-attempt checks and concurrency
shared with the old parent pilot remain mandatory. Seam exceptions are converted
to a fixed stop without exposing external text. Each sibling also needs a direct
immediate-family readback confirming the pinned parent union and both parents;
its own spouse unions are not misread as parent links.

Stable consume markers deliberately omit union ID and expiry: changing those
must not permit recreating the same approved person. No marker reset is exposed.
A failed batch has no automatic resume operation. A remaining-items plan needs
fresh review and approval, with all earlier markers preserved.

### Fresh remaining-items plans

Sibling plans can contain one to four ordered remaining entries. This is not an
automatic resume: a new immutable plan and fresh human approval are mandatory.
Prior created children require `verified_children` entries with exact IDs,
original stable keys and approved payloads. Every non-owner existing child must
be listed and is checked by profile plus direct family readback before any send.
Prior keys cannot appear among remaining entries. Stable consume markers remain
unchanged and consumed; no retry or reset is exposed.


### Structural failure evidence

Encrypted reports retain the read stage (`read_profile`, `read_union` or
`read_family`) and, for transport failures, a fixed host, fixed error type and
HTTP status class when known. No response body, arbitrary header or exception
text is copied into this failure summary. Already-captured parsed responses stay
encrypted as before. Non-transport seam exceptions become a fixed failure code.
No additional read or retry occurs after a failure.

Remaining names must also differ from verified-child names. A local name match,
reused prior key, unlisted prior ID, or mismatched prior profile/family readback
blocks before any send. This guard does not prove remote duplicate absence.


### Read errors and opt-in debug

Vendor read failures retain exact HTTP status as well as status class. The
protected workflow's optional boolean `debug` input defaults to false and maps
to FAMILY_DEBUG (0/1, or false/true for direct offline tests). Enabling it keeps
only fixed structural body/error-shape/media enums, size/cap flags, numeric rate
headers and retry delay metadata in encrypted reports. It never retains raw
body text, error messages, arbitrary headers or secrets, nor prints them.
No extra read, retry or create follows an error. Debug does not change writes or
create-error evidence. Status class alone never identifies the failure cause.


### Pacing margin

The guarded family transport waits at least fifteen seconds between request
starts, rather than exactly ten, to allow margin around an observed
one-per-ten-second rate window. This is conservative pacing, not a diagnosis of
an earlier unknown 4xx. No retry is added. The finite forty-call budget and
expiry checks remain. If expiry occurs during a wait, admission stops before the
next request is sent.


## Required encrypted diagnostics (#574)

Detailed structural GET-error diagnostics are mandatory for protected family
runs. The workflow requires its boolean debug input, defaults it to true and
will not start the protected job when it is false. The executor independently
requires FAMILY_DEBUG to be exactly the string 1 or true before encryption,
output creation or any transport. Missing, false or invalid values stop.
The full-run wiring passes debug=True to the encrypted-only error wrapper.

This does not log raw private response/error strings publicly. Existing numeric
HTTP status and fixed structural diagnostic filters remain unchanged. Successful
responses are still encrypted before validation. Local validation failures do
not become HTTP failures or receive invented status codes. No new route, retry,
permission, pacing change or execution approval is introduced.
