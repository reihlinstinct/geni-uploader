# Isolated deceased English-name update

Design and implementation for #778. No live operation is authorized by this code.
Existing living surname and alternate-name runners are unchanged.

One exact private, deceased, explicitly unclaimed profile per run. Pin profile ID,
GUID, full English/Hebrew name maps, primary name fields, aliases, display name,
title, suffix, safety booleans and union references. Unexpected locales, redirects,
public/living/claimed profiles or positive/malformed merge metadata block. Missing
merge metadata remains UNKNOWN and requires explicit package risk acceptance.
No hidden-merge guarantee is implied.

The only update body is `{"names":{"en-US":{...}}}`. Only English
first_name/last_name may differ from the baseline. Send the complete existing
English map with those two replacements; never send the Hebrew map, primary
(top-level) name keys, display_name or user/account language settings. Exact
readback must prove the Hebrew map and other English fields are unchanged.
No maiden-name inference, nickname, display-name, date, relationship, privacy,
source or other field is writable. Case and spelling are exact, not normalized.

The server may leave primary first_name/last_name unchanged or reflect the exact
new English pair. Both are explicitly modeled, never silently ignored: encrypted
readback reports `primary_projection` with before/after values, no written keys,
and classification UNCHANGED or ENGLISH_DERIVED. A partial pair or third value
is UNEXPECTED and stops without final verification. Other primary name fields
remain pinned. These permitted observations are not a claim that the API's
undocumented projection semantics have been experimentally established.

Vendor documentation:
- Update accepts a names locale map independently; it does not require primary
  keys alongside it: https://www.geni.com/platform/developer/help/api?path=profile%2Fupdate&version=1
- Profile `name` is the display for the current user; primary component projection
  semantics are not specified: https://www.geni.com/platform/developer/help/api?path=profile
- en-US is English (default): https://www.geni.com/platform/developer/help/locales
- Interface language chooses the displayed name; English is fallback, then first
  available language. Other names can appear below in smaller font:
  https://help.geni.com/hc/en-us/articles/229704207-How-do-I-add-multilingual-names-and-biographies-to-a-profile
- Explicit display names have their own fallback behavior:
  https://help.geni.com/hc/en-us/community/posts/34475084799511-MultiLanguage

An English-only map update still intentionally changes English/default-fallback
views. Preserving Hebrew data is not a guarantee that every display surface stays
identical; missing fields or custom display names may affect rendering. No API
readback substitutes for inspection of the approved result's English/Hebrew views.
The required `accept_english_default_projection: true` package field records
acceptance of this display intent and the two possible
primary projections before execution. Undocumented nested-map omission behavior
is guarded by exact readback, not assumed safe: any loss of Hebrew stops, with no
automatic retry or repair. No live experimental write is part of building this path.

Read-only plan: owner, target and immediate-family GETs. Update: those three GETs,
one exact POST, independent profile GET and family GET. Six calls maximum, at
least 15 seconds apart. A changed baseline stops before POST. Store encrypted
before evidence, atomically consume a stable owner/target/proposed-English-name
intent, then retain acknowledgement and final receipt. Changing baseline, GUID,
source, executor or expiry cannot rearm the same intent. Unknown sends, storage
failure or readback mismatch stop without retry, rollback or repair.

Private source admission pins decoded canonical plan hash, source commit/path,
owner, target, expiry and encryption recipient. The protected workflow uses
ENGLISH_NAME_UPDATE_JSON and the existing father-create gate. Check required
reviewer, no self-review, master-only and no admin bypass live. Each target has
its own reviewed package and fresh applicable run approval. No identifying family
data belongs in this public repository; examples/tests are synthetic ZZ data.

A package cannot be finalized from an older creation receipt. Collect a fresh
read-only baseline including aliases/display/title fields, replay the exact
private-source decode/hash path offline to the vendor boundary, obtain independent
exact-head review and green CI, then request the separately approved protected
run. Separate private intake review or its billing state grants no live effect.
