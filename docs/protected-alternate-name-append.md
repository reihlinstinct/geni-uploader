# Guarded alternate-name append

Design and implementation for #776. No live effect is authorized.

## Isolated contract

One exact existing private, deceased, explicitly unclaimed profile per run. A
second target needs its own package and protected run. Existing surname runners
and create runners are unchanged. The only POST body is `nicknames`, containing
all existing aliases followed by the exact approved additions. Primary names,
localized names, display name, title, suffix, life status, gender, privacy and
family edges must remain unchanged. No creation, merge, invitation or source edit.

Geni documents `nicknames` as "Also known as", returned as an array and settable
as a comma-delimited string. The transport sends the exact joined value, not a
Python list representation. Commas and controls within aliases are rejected.
Source: https://www.geni.com/platform/developer/help/api?path=profile/update
Blank fields can be omitted by Geni. An omitted nickname field is treated as an
empty list only for computing additions; its original omission stays in the
expected snapshot. Non-array, duplicate, empty or malformed alias values block.
An already present requested alias blocks, rather than silently reapplying it.

## Safety and effects

Private source admission pins the reviewed source commit, path, canonical decoded
plan hash, target, owner guard, expiry and recipient. Explicit
`accept_unknown_merge_metadata=true` acknowledges only omission of merge metadata;
positive, malformed or conflicting metadata blocks. This does not prove no hidden
merge exists. Fresh expected values are mandatory, never synthesized from an old
receipt. A plan run is three GETs: owner, target, family. It consumes no marker and
writes no vendor data or receipt tags. Update repeats them, retains encrypted
before evidence, atomically consumes a stable target/additions intent, sends one
POST, retains acknowledgement, then reads profile and family independently.
Final remote encrypted receipt is required for VERIFIED. Six vendor calls maximum,
15 seconds minimum spacing. Closed ordering rejects any other route or body.
Changing expiry, source, executor or baseline cannot rearm the same additions.
Unknown sends, storage failures and any readback mismatch stop without retry,
resume, rollback or repair. Inspect evidence before any separately approved work.

## Privacy and release

`nicknames` has no separately documented audience control. Private does not mean
owner-only: authorized family users, managers, curators and employees can access
private profiles. Public profiles are viewable by anyone. No guarantee is made
about alias matching or search exposure for private deceased profiles.
Sources: https://www.geni.com/privacy and
https://help.geni.com/hc/en-us/articles/229704447-What-profiles-are-private

Use the isolated manual workflow, exact reviewed master SHA and config hash.
Verify protected reviewer, prevent self-review, master-only policy and no admin
bypass live. No environment changes are part of this code. Each live run requires
fresh applicable approval. Public outputs are fixed; all profile evidence stays
age-encrypted. No identifying package belongs in this repository. Tests use only
invented ZZ names or name-free data.
