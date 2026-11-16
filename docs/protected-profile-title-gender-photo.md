# Protected profile title, gender and photo adapter (design)

Implements the design step of #715. Three disjoint capabilities on existing,
private, living, explicitly unclaimed profiles:

1. **Profile title** via `profile/update` `title` (e.g. ד"ר).
2. **Gender update** via `profile/update` `gender`.
3. **Photo upload** via `profile/add-photo`.

This document is design only. It ships no dispatch path, no live effect and no
vendor credential wiring. No live run is authorized by this document or by the
code that implements it; each run needs the owner's explicit approval, exactly
as the reviewed name adapter does.

## Relationship to the reviewed name adapter

The reviewed name adapter (`protected-profile-name-update.md`) covers
`last_name` / `maiden_name` and the two locale maps only. It excludes gender
and title by design, and that exclusion is unchanged. This adapter is a
separate entry point with its own private package, environment secret, confirm
tokens and intents. No scope crosses between them; a plan that mixes name
fields with title/gender/photo is rejected by both.

## Capability 1: profile title

`title` is a distinct vendor field. It is never concatenated into first, middle
or last name, never written into `display_name` or `occupation`, and never used
to infer a profession (a title of ד"ר does not imply physician).

**Readback gap (blocking).** The documented `ReturnedFields` for both
`profile/update` and `profile` omit `title`. A write that cannot be read back
cannot be verified, and this adapter's contract requires readback verification
before `VERIFIED`. Therefore:

- `mode=plan` for a title operation is implementable now: it validates the
  target safety predicates and records that title readback is UNRESOLVED.
- `mode=update` for a title operation REFUSES to dispatch until an exact,
  supported readback contract is established and encoded as an allowlisted
  readback check (endpoint, field path, expected value form). Establishing
  that contract - for example a documented `ReturnedFields` addition, or a
  verified observation on a scratch profile approved by the owner - is a
  separate reviewed change. Until then the title capability is plan-only.

If a readback contract is later established, the update shape matches the name
adapter: three preflight GETs, encrypted before receipt, one-use intent
consumption, a single form-encoded POST, then readback and unchanged-family
verification. A title readback that returns anything other than the exact
requested value is STOPPED, never retried.

## Capability 2: gender update

`gender` is a core profile field with documented readback, so verification is
standard. The adapter must READ the current gender in preflight before any
write is proposed:

- Current gender absent/empty (for example after a create that omitted it): a
  plan to set an explicit value is admissible.
- Current gender present and equal to the requested value: the plan is a no-op
  and blocks; idempotent rewrites are never sent.
- Current gender present and different: blocks. Changing an existing gender
  value requires a separate owner-approved plan that names the existing value;
  the adapter never assumes which side is wrong.

Plan and update shapes mirror the name adapter: three preflight GETs (account
owner, target profile, target family), before receipt, one-use intent, one
POST, profile readback on `gender` plus unchanged-family verification. All
other safety predicates (private, living, explicitly unclaimed, merge state,
union membership, names pinned) are identical to the name adapter's.

## Capability 3: photo upload

`profile/add-photo` takes a POST with `file` (base64-encoded) and a required `title`
(photo caption) and auto-tags the target profile. `GET photo` supports tags,
sizes, title and description.

Contract:

- **One upload per durable intent.** The intent binds owner, target profile,
  exact image SHA256, caption and consent reference. One POST per intent; no
  retry after an uncertain outcome; a stopped upload is inspected from retained
  evidence before any separately authorized next step.
- **No other tags.** The adapter requests no additional tags and verifies the
  readback tag list contains exactly the target profile.
- **Privacy acknowledgment.** The vendor documents no privacy parameter and no
  returned privacy field for photos. The plan must carry an explicit owner
  acknowledgment that the photo's privacy is whatever the vendor applies. A
  plan without that acknowledgment blocks.
- **Main portrait.** The endpoint may not set the main portrait, and the
  vendor's behavior for a profile's first photo is not assumed. Because the
  upload is irreversible and there is no repair path, the plan must establish
  BEFORE any send that the target already has a main portrait when the choice
  is `keep-current`. A target with no existing main portrait blocks a
  `keep-current` plan outright; uploading a first photo that could become the
  main portrait requires an explicit owner-approved set-as-main operation,
  reviewed separately. With an existing main portrait, the adapter verifies
  after upload that it is unchanged.
- **Caption.** The required `title` is supplied by the owner in the plan; the
  adapter never composes one from names, dates or file metadata.
- **Readback.** After the acknowledged POST, `GET photo` on the returned photo
  ID must confirm the caption and that the tag list contains exactly the
  target profile, and must return at least one rendered size entry. Rendered
  sizes are vendor-generated variants, so no byte count of the original is
  asserted. Any mismatch is STOPPED.

Consent for each depicted living person is a plan prerequisite recorded in the
private package (as with the photo-hold practice); the adapter does not track,
request or infer consent itself.

## Shared shape

```
plan mode (READ ONLY)                     update mode (ONE SEND)
----------------------                    ----------------------
GET account owner                         repeat the three preflight GETs
GET target profile                        write encrypted before receipt
GET target family                         consume one-use private intent
validate safety predicates      ---->     POST exactly one vendor request
validate capability preconditions         readback per capability contract
emit fixed public summary                 verify family edges unchanged
(no marker, no receipt tag,               retain ack + final receipts
 no vendor write)                         VERIFIED only after retention
```

- 15-second minimum spacing between vendor requests. Title and gender runs
  keep the name adapter's cap of at most six vendor requests (three preflight
  GETs, one POST, two verification GETs). A photo run is capped at seven:
  three preflight GETs, one POST, and three verification GETs (photo, target
  profile, family).
- Redirects, throttling, stale values and any ambiguity stop the run.
- Evidence is age-encrypted; receipts use the existing create-only store in the
  private source repository. No private identifiers in public prose or logs.
- The private package pins source repository, signed reviewed commit, JSON
  path, canonical plan SHA256, owner, target, expiry and age recipient, as the
  name adapter does, plus the per-capability fields above (readback-contract
  ID for title, existing-value rule for gender, image hash / caption / privacy
  and main-portrait acknowledgments for photo).
- Environment wiring uses its own variable names for this entry point, never
  the name adapter's `RELATIVE_*` names: `TGP_MODE` (plan/update),
  `TGP_CONFIG_JSON`, `TGP_CONFIG_SHA256`, `TGP_EXECUTOR_SHA`, `TGP_CONFIRM`,
  `TGP_OUTPUT_DIR`, `TGP_DEBUG` and `TGP_TREE_PAT`, plus the
  `PROFILE_TGP_JSON` environment secret. The vendor credential remains
  `GENI_SECONDARY_ACCESS_TOKEN`. Sibling configurations are not reused.

## Testing

Duplicate-hash blocking, defined: the receipt store records the image
SHA256 of every VERIFIED photo upload per target. A plan whose image hash
already has a VERIFIED receipt for the same target blocks as a re-upload of
the same bytes, independent of one-use intent consumption (which blocks
re-sending the same intent).

Unit and regression tests cover: plan validation for each capability; the
title readback gate (update refuses while UNRESOLVED); gender present/absent/
equal/conflict cases; photo duplicate-hash blocking, missing privacy or
main-portrait acknowledgment blocking, keep-current blocked when no main
portrait exists, tag-list and caption verification; intent one-use
consumption; and the no-retry STOPPED paths. Mutant checks prove
each regression test bites. Tests use the mock vendor client; no network.
Existing name-adapter tests must pass unchanged, proving no scope bleed.

## Explicit exclusions

No creation, deletion, merge, spouse/child edges, sources, email/invitations,
display_name or occupation changes. No profession inference from title. No
photo privacy guarantees beyond the recorded acknowledgment. No automatic
retry, resume, rollback or repair. No live run without the owner's explicit
approval for that run.

API contracts:
https://www.geni.com/platform/developer/help/api?path=profile/update ,
https://www.geni.com/platform/developer/help/api?path=profile ,
https://www.geni.com/platform/developer/help/api?path=profile/add-photo ,
https://www.geni.com/platform/developer/help/api?path=photo
