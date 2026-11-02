# Protected one-profile surname correction

Implements #661. This is a separate existing-profile update path, not a relative
creation or source-description route. No dispatch or live effect is part of the
implementation. Deployment protection must be checked live before use.

## Closed effect

Only `last_name`, `maiden_name` and those two fields in the existing `en-US` and
`he` name maps may change. The prior surname must be preserved as maiden name;
a conflicting existing maiden name blocks. First/middle names, gender, privacy,
life status, merge state and union membership remain pinned. Target must be a
private, living, explicitly unclaimed profile with explicit no-merge state.
Missing safety fields block rather than assume safe. Unknown locales or name
fields are not dropped to make a plan pass. Email/invitations, other profile
fields, creation, deletion, spouse/child edges and sources are excluded.

`expected` is the exact snapshot projection defined by `SNAPSHOT_KEYS` in the
model. `names` uses vendor locale keys (`en-US`, `he`). Union IDs use the explicit
`only_ids=true` representation. Do not synthesize missing safety fields from an
older receipt. A fresh read may block if the vendor omits a required field.

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
