# Geni protected - household partner or children

Separate exact create workflow, not an extension of earlier sibling routes.
Engineering-only until independent exact-head review, green CI, package audit,
fresh exact user go and GitHub human approval. Names describe protection intent;
this does not migrate environments or restore held credentials. Existing
father-create environment remains, with required human reviewer, no self-review,
no admin bypass, master-only. Check live before any install/dispatch. Any missing
private evidence writer remains a blocker, never bypass it.

## Scope and unknowns

A plan is either one add-partner at a pinned profile, always a NEW spouse union,
or1-4add-child at one pinned parent with an existing two-partner union. No merge,
existing-profile edit, invite/email, dates, places, marriage date, parent addition,
adopt/foster or automatic repair. Each payload has bilingual he/en-US names and
one documented about_me string containing Hebrew+English paragraphs. This is not
an unsupported per-locale about_me parameter. Readback requires exact about_me.
English spellings are transliterations unless source verified. Unknown gender,
surname and dates omitted, never inferred. Living true/private false mandatory.
Unknown gender can be omitted because vendor add API documents gender optional.
Source: https://www.geni.com/platform/developer/help/api?path=profile/add-child
Source: https://www.geni.com/platform/developer/help/api?path=profile/add-partner

Pinned complete visible anchor graph and explicit current profile fields,
including owner identity, are checked before any send. Existing public/claimed
profiles can be read but never edited. Every created profile must read back
private/living/unclaimed, names/description exact, no merge conflict except a
separately accepted missing merge indicator. Existing anchor graph must match
exactly, including separately pinned boundary edges for non-anchor relatives.
No omission allowed for anchor edges. Direct union reads use explicit fields;
missing partners/children are UNKNOWN_OMITTED, never empty. Proceed despite a
vendor-omitted union field ONLY when exact visible bidirectional graph passes
AND accept_omitted_union_fields is explicitly true in the approved plan. Full
visibility remains UNPROVED. Hidden duplicate and union-selection risks require
approval. A wrong present list always stops. An unknown field does not override
a graph mismatch. This is acceptance of incomplete service evidence, not absence
proof or a guarantee of correct parent union chosen by vendor.

## Durability and transport

Create-only stable consume markers ignore expiry and union ID; no reset/retry.
Before/ack/final encrypted receipts use existing immutable private Git evidence.
Consumption precedes send, ack persists ID before readback. Partial success is
retained. Wrong union, payload mismatch, failed privacy/description/graph,
uncertain send or storage failure stops immediately. No rollback or merge.
Transport pending latch stays closed until exact profile, complete anchor graph,
reciprocal new-profile graph and direct union proof all pass. New spouse union
GET admitted only after complete anchor graph identifies exactly one new union.
No arbitrary discovered routes, no redirect, refresh or retry.60requests max,
15sec minimum spacing,25minute timeout, first attempt only, exact actor/ref/hash.
Each admission consumed before wait/transport. Existing mutation concurrency
shared. Fixed stdout, encrypted structural failure diagnostics only.

## Config and operational sequence

HOUSEHOLD_CREATE_CONFIG_JSON pins immutable private source, canonical decoded
plan SHA256, owner, anchor, optional target union, expected owner name, recipient,
expiry and risk flags. HOUSEHOLD_CREATE_CONFIG_SHA256 pins exact raw config bytes;
HOUSEHOLD_CREATE_EXECUTOR_SHA equals run SHA. HOUSEHOLD_CREATE_CONFIRM must be
CREATE_APPROVED_HOUSEHOLD. HOUSEHOLD_CREATE_DEBUG=1ortrue mandatory.
HOUSEHOLD_CREATE_TREE_PAT is existing private evidence writer, not vendor token.
GENI_SECONDARY_ACCESS_TOKEN is isolated vendor credential.
HOUSEHOLD_CREATE_OUTPUT_DIR is an absolute new encrypted-output directory.
New isolated workflow secret HOUSEHOLD_CREATE_PACKAGE_JSON holds config. Never reuse another plan.

Build/review/merge does not approve a run. Prepare exact list and payload hashes,
source+executor+config pins, expiry and risks. Replay actual private base64 source
load, Unicode canonical decoded-plan hash and cross-scope checks to vendor
construction offline. Simulate post-create proofs too. Independent exact-package
audit, then fresh exact user go permits config install and one dispatch only;
human GitHub deployment approval still required. Monitor exact run, archive
ciphertexts/provenance and inspect durable refs. On stop never rerun/reset;
read-only reconciliation and newly reviewed remaining package are separate work.
