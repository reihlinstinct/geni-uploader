# Protected one-profile surname correction

Implements #661. This is a separate existing-profile update path, not a relative
creation or source-description route. No dispatch or live effect is part of the
implementation. Deployment protection must be checked live before use.

## Closed effect

Only `last_name`, `maiden_name` and those two fields in the existing `en-US` and
`he` name maps may change. The prior surname must be preserved as maiden name;
a conflicting existing maiden name blocks. First/middle names, gender, privacy,
life status, merge state and union membership remain pinned. Target must be a
private, living, explicitly unclaimed profile with explicit claimed=false.
Missing core safety fields block rather than assume safe. Unknown locales or name
fields are not dropped to make a plan pass. Email/invitations, other profile
fields, creation, deletion, spouse/child edges and sources are excluded.

`expected` is the exact snapshot projection defined by `SNAPSHOT_KEYS` in the
model. `names` uses vendor locale keys (`en-US`, `he`). Union IDs use the explicit
`only_ids=true` representation. Do not synthesize missing safety fields from an
older receipt. A fresh read blocks if the vendor omits a required core field.

### Narrow merge-metadata omission policy (#663)

Geni can omit `merge_pending` and `merged_into` even when requested. Omission is
UNKNOWN, not proof of no merge. The owner-approved policy admits omission only
when all other safety predicates are explicit and match: private, living,
unclaimed, gender, exact names and valid union references. If present,
`merge_pending` must be exactly false; `merged_into` must be null or empty.
Positive or malformed merge state always blocks, before and after a write.
Residual risk: a merge not reported by Geni may exist. This policy does not
establish its absence. Re-review that risk with the exact effect before any run.

Only exact `union-N` IDs or `https://www.geni.com/api/union-N` references normalize
to an ID. No other host, scheme, query, suffix or path is accepted. Duplicate
references after normalization block. Normalized union membership must remain
identical after the update. No additional endpoint or effect is admitted.

## Private package and review

The private config pins source repository, signed reviewed commit, JSON path,
canonical decoded plan SHA256, owner, target, owner-name guard, expiry and age
recipient. It does not contain creation-risk consent fields. Plan/config owner,
target, name and expiry must match. The existing private-source admission checks
remain active. No private identifiers belong in public issue/PR prose or logs.

Use `protected-profile-name-update.yml`, exact reviewed master executor SHA and
exact raw config SHA256, `debug=true`. `mode=plan` with `confirm=READ_ONLY_NAME`
performs exactly three GETs: account owner, target profile, target family. It
validates the expected values but creates no marker, receipt tag or vendor write.
Evidence is encrypted. Source/config admission itself reads private Git.

Only after reviewing that result and exact effect approval use `mode=update`,
`confirm=UPDATE_APPROVED_NAME`, with the same reviewed package (or re-audit any
revision). Do not dispatch either mode without its owner's applicable approval.
The user reviews the protected environment deployment for each run. Verify
master-only branch policy, sole intended reviewer, prevent-self-review and no
admin bypass before installation or dispatch. No environment settings are
changed by this PR.

## One send, no retry

Update repeats the three preflight reads. It writes an encrypted before receipt,
atomically consumes a stable one-use private intent, sends one form-encoded
`POST /api/<target>/update`, then retains acknowledgement and verifies target
profile and unchanged family edges with two GETs. At most six vendor requests,
15-second minimum spacing. Redirects, throttling, stale values and any ambiguity
stop. The marker binds owner, target, expected values and requested change;
changing expiry, executor or source commit cannot rearm it. A stopped operation
has no automatic retry, resume, rollback or repair. Inspect retained evidence
before deciding a separately authorized next step. `VERIFIED` requires final
remote receipt retention, not merely an acknowledged POST.

The public workflow emits fixed output only. Age-encrypted snapshots are kept
as short-lived artifacts and encrypted before/ack/final receipts are stored in
the private source repository using the existing create-only store.

API contract: https://www.geni.com/platform/developer/help/api?path=profile/update

## Environment wiring

`RELATIVE_MODE` selects plan/update. Shared envelope variables are
`RELATIVE_CONFIG_JSON`, `RELATIVE_CONFIG_SHA256`, `RELATIVE_EXECUTOR_SHA`,
`RELATIVE_CONFIRM`, `RELATIVE_OUTPUT_DIR`, `RELATIVE_DEBUG` and
`RELATIVE_TREE_PAT`. They remain isolated to this entry point and its
`PROFILE_NAME_UPDATE_JSON` environment secret; sibling configurations are not
reused. The vendor credential is `GENI_SECONDARY_ACCESS_TOKEN`.

## Separate birth-surname-only shape (#711)

A plan whose `set` contains exactly `maiden_name` and `names` selects a separate
birth-surname-only operation. Main birth surname must equal the English locale
birth surname. The existing English and Hebrew maps contain exactly one requested
field each: `maiden_name`. No current surname is sent, inferred, cleared or filled.
Unlike the old correction shape, the expected snapshot may omit current surname
in main or either locale. Presence is significant: readback must preserve each
omission or exact existing current-surname value. All existing first/middle names,
locale maps, privacy, life status, explicit unclaimed status and family edges
remain pinned. Both existing locales and their first names are still required.

An already-present birth surname in main or either locale blocks this addition,
even if equal to the requested value. Conflicts and idempotent reapplications are
not silently overwritten. Unknown fields/locales, mixed correction/addition
bodies and main/English mismatches block. The old correction shape and its
old-surname preservation rules are unchanged. The same private exact package,
three-read plan, protected approval, stable consumption, one POST and two-read
verification apply. No live update is authorized by this code change. Vendor
partial locale-map update behavior is checked after the write; an acknowledged
update that drops existing names, adds current surname or changes family edges
is STOPPED, not verified, and is never automatically retried or repaired.

## Separate current-surname-fill shape (#718)

A plan whose `set` contains exactly `last_name` and `names` AND whose target
has no current surname anywhere selects a third, separate operation: adding an
approved spouse surname where none exists. Owner rule: when a man marries a
woman whose profile has no current last name (distinct from birth name), add
the husband's surname.

Admission requires the current `last_name` to be ABSENT in main AND in every
returned locale map. A surname present in main or any locale blocks this shape
entirely, even when the present value equals a birth name; this shape never
overwrites, and the correction shape's old-surname preservation rules are
unchanged. A target with any current surname is only ever handled by the
correction shape; a target with any maiden-name-only request is only ever
handled by the #711 shape. Mixed or ambiguous bodies block.

The payload is exactly `last_name` and the locale maps' `last_name` entries.
Locale mapping is enforced: each returned locale map is filled with the same
approved surname, main and English must match, and unknown locales or fields
block rather than being dropped. Every pre-existing `maiden_name` (main,
`en-US`, `he`) is preserved exactly: never moved, copied, cleared or derived
from the new surname. First/middle/nicknames, gender, privacy, life status,
explicit unclaimed status and family edges remain pinned as in the other
shapes, and the readback must show every birth-name field unchanged.

The spouse relationship must be verified, not inferred: the plan's family read
must show the husband whose surname is being added as a current union partner
of the target, and the private config names that spouse reference. A surname
requested for a spouse absent from the current union read blocks, as does any
stale or ambiguous union graph. No spouse is inferred from names, gender or
the requested value.

The same private exact package, three-read plan, protected approval, stable
one-use consumption, single POST and two-read verification apply. Invariant
readback covers the new surname (exact, main and every locale) and every
preserved field. A failed or uncertain POST is STOPPED and terminal: no
retry, resume, rollback or repair. No live update is authorized by this
shape's code; each run needs the owner's explicit approval.
