# Synthetic placeholder data for public files (#725)

Rule (from the repo owner's 2026-11-03 13:19 IST message, relayed via the
Instinct parent agent): every public doc, test and example uses placeholder
variables backed by a shared synthetic source - not ad-hoc invented values
and not real names, surnames, phones, national IDs or profile IDs. This doc
is the design; no file moves or CI changes land here.

## Target paths (stated up front, per the layout rule)

- `synthetic/personas.json` - machine-readable canonical persona set (new
  top-level directory; the `.repo-layout.yml` contract gains a `synthetic/`
  entry allowing `*.json` in the same PR that adds the directory; that PR
  lands after #723 merges the contract).
- `docs/synthetic-personas.md` - human doc: the rule, the generation
  pattern, the invalidity arguments, and the persona table rendered from the
  JSON.
- `synthetic/public-corpus-baseline.json` - grandfathered-occurrence
  baseline so the scanner is green on day one (see Migration).
- `tools/check_public_placeholders.py` - pattern-only scanner (stdlib only,
  same reuse model as `tools/check_repo_layout.py`).
- `tests/test_public_placeholders.py` - runs the scanner over the tracked
  tree in CI plus unit tests with synthetic mutant fixtures, including a
  test that every ID value in `personas.json` FAILS the check digit.
- `tests/test_cli_env_docs.py` + CONTRIBUTING - register the new entry
  point and the writing rule.

## Canonical synthetic values and why they cannot be real

1. **Names** - generated as `<token>-<4 random digits>` where tokens come
   from a fixed non-dictionary syllable list. The digits suffix and the
   documented generator mark every name as synthetic; docs and tests
   reference `personas[i].first_name` / `personas[i].last_name` or copy the
   canonical rendered value. (Today the repo's synthetic-name convention is
   the `ZZ ...` sentinel style; personas keep a clearly synthetic shape.)
2. **Phones** - two reserved forms only:
   - `+999-...`: ITU-T E.164 lists country code 999 as reserved for future
     global service, so no subscriber can hold it;
   - `+1-<NPA>-555-0100`..`+1-<NPA>-555-0199`: the NANPA range reserved for
     fictional use (the 555-0100..0199 block in any Numbering Plan Area).
   The scanner accepts exactly these canonical fictional forms.
3. **Israeli-format national IDs** - 9-digit strings that FAIL the official
   check-digit algorithm by construction (weights 1,2 repeating over the
   first 8 digits, digit-sum of products, check digit = (10 - sum mod 10)
   mod 10; a synthetic value chooses a wrong check digit). A checksum-failing
   value can never validate as a real ID. The algorithm is stated here so
   the failure is verifiable, and a scanner unit test asserts every persona
   ID fails it.
4. **Geni profile/union IDs** - personas use clearly synthetic numeric IDs
   from the test-fixture convention already dominant in this repo (e.g.
   `profile-101`-style round numbers). There is no `profile-ZZ<digits>`
   convention today: `ZZ` is the repo's convention for synthetic names and
   sentinels, not an established ID range. Numeric IDs are not distinguishable
   from real ones by pattern alone; they are handled by the migration and
   baseline below, not by a scanner claim.

## Scanner (pattern-only, embeds no real data)

`tools/check_public_placeholders.py` scans tracked public text files -
docs, README, workflows, examples AND `tests/` (tests are in scope) -
excluding `synthetic/`, itself and its tests, and flags:

- **ID-shaped sequences**: 9 consecutive digits whose check digit is VALID
  per the stated algorithm, and the unpadded 8-digit form checked the same
  way, unless the exact value is in `personas.json` (persona IDs fail the
  checksum, so they can never match).
- **Phone-shaped sequences**: international (`+...` and `00`-prefix) and
  domestic (`05x-` / `0xx-`) phone patterns that do not match the two
  reserved fictional forms above.
- **Numeric ID references in structured forms**: `profile_id:` /
  `union_id:` JSON/YAML values and `profile-<digits>` / `union-<digits>`
  tokens - checked against the persona set and the baseline (see Migration).

The scanner contains only regexes, the check-digit function, the reserved
range definitions and the baseline file - no list of real names, numbers or
IDs and no lookup against any external source. Human names are NOT
machine-detectable by pattern; they are governed by the writing rule
(CONTRIBUTING) and review.

### Known blind spots (acknowledged, not claimed away)

- Bare numeric Geni IDs in prose are not reliably distinguishable from
  fixture values; coverage for them is the baseline+incremental rule, not
  detection.
- Obfuscated or separator-split numbers (spaces, dots) and free-form prose
  numbers may evade the phone patterns.
- Name-like real data is only caught by review, not by the scanner.

## Migration and baseline (CI green on day one)

The existing corpus holds hundreds of numeric profile-/union-ID occurrences
(order: ~620 in tests, ~165 in oauth-bootstrap, a few in docs, src, tools)
plus numeric `profile_id:`/`union_id:` forms. Plan:

1. Scanner PR ships with `synthetic/public-corpus-baseline.json` listing
   every grandfathered occurrence (file, line-anchored count, value class);
   occurrences in the baseline pass, new ones fail. CI is green immediately.
2. A documented false-positive allowlist (same file, separate section with
   per-entry reasons) covers values that must stay, e.g. protocol examples.
3. Fixture-sweep PRs migrate each area to personas - tests, oauth-bootstrap,
   docs, src, tools - one area per PR, tests green at every step, shrinking
   the baseline to the allowlisted residue.

## CI and rollout

- `tests/test_public_placeholders.py` runs the scanner on the tracked tree;
  unit tests prove it bites with synthetic mutant fixtures (valid-checksum
  ID, reserved-range-violating phone, non-persona structured ID reference)
  and stays quiet on the canonical personas and the baseline.
- geni-uploader first; the same source + scanner pattern rolls out to every
  reihlinstinct public repo via its own issue + PR inside the
  `.repo-layout.yml` / community-standards rollout (#721), one repo at a
  time with green CI + independent review.

## Verification

Full suite green; mutant fixtures demonstrate detection; the personas
checksum-failure test proves the ID values cannot validate; independent
review at the exact head. No live Geni effect. No real personal data appears
in any file, issue or PR text produced by this work.
