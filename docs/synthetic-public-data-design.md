# Synthetic placeholder data for public files (#725)

Owner rule (2026-11-03): every public doc, test and example uses placeholder
variables backed by a shared synthetic source - never ad-hoc invented values
and never real names, surnames, phones, national IDs or profile IDs. This doc
is the design; no file moves or CI changes land here.

## Target paths (stated up front, per the layout rule)

- `synthetic/personas.json` - machine-readable canonical persona set (new
  top-level directory; the `.repo-layout.yml` contract gains a `synthetic/`
  entry allowing `*.json` in the same PR that adds the directory; that PR
  lands after #723 merges the contract).
- `docs/synthetic-personas.md` - human doc: the rule, the generation
  pattern, the invalidity proofs, and the persona table rendered from the
  JSON.
- `tools/check_public_placeholders.py` - pattern-only scanner (stdlib only,
  same reuse model as `tools/check_repo_layout.py`).
- `tests/test_public_placeholders.py` - runs the scanner over the tracked
  tree in CI plus unit tests with synthetic mutant fixtures.
- `tests/test_cli_env_docs.py` + `docs/repo-layout.md` / CONTRIBUTING -
  register the new entry point and the writing rule.

## Canonical synthetic values and why they cannot be real

1. **Names** - generated as `<token>-<4 random digits>` where tokens come
   from a fixed non-dictionary syllable list (e.g. `Abqef`, `Torlin`,
   `Veshka`). The digits suffix and the documented generator make every name
   provably synthetic; docs reference `personas[i].first_name` /
   `personas[i].last_name` or copy the canonical rendered value.
2. **Phones** - two provably invalid shapes only:
   - `+999-...`: country code 999 is spare/unassigned in ITU-T
     Recommendation E.164 (assigned 99x codes are 990-995 for global
     services; 996-999 spare), so no subscriber can hold it;
   - `+1-555-0100`..`+1-555-0199`: the NANPA range reserved for fictional
     use.
   No other phone-shaped string is permitted in public files.
3. **Israeli-format national IDs** - 9-digit strings that FAIL the official
   check-digit algorithm by construction (weights 1,2 repeating over the
   first 8 digits, digit-sum of products, check digit = (10 - sum mod 10)
   mod 10; a synthetic value chooses a wrong check digit). A checksum-failing
   value is provably never a valid ID. The doc states the algorithm so the
   failure is verifiable.
4. **Geni profile IDs** - only the synthetic ZZ range (`profile-ZZ<digits>`,
   e.g. the existing `ZZ429` style). Real Geni IDs are numeric-only; any
   ZZ-prefixed ID is provably not a live profile.

`personas.json` carries, per persona: first_name, last_name, maiden_name,
phone, national_id, profile_id, plus the invalidity rationale for the
ID/phone fields so the proofs travel with the data.

## Scanner (pattern-only, embeds no real data)

`tools/check_public_placeholders.py` scans tracked public text files
(docs, README, workflows, examples; excludes `synthetic/`, itself and its
tests) and flags:

- **ID-shaped sequences**: 9 consecutive digits (with word boundaries) whose
  check digit is VALID per the stated algorithm, unless the exact value is
  listed in `personas.json` (synthetic values fail the checksum, so any
  match here is real-looking by definition).
- **Phone-shaped sequences**: international phone patterns
  (`\+\d[\d -]{6,16}\d`) not matching the two synthetic shapes above.
- **Profile-ID shapes**: `profile-<digits>` or bare `union-<digits>`/
  numeric Geni ID references outside the ZZ range.

The scanner contains only regexes, the check-digit function and the two
synthetic range definitions - no list of real names, numbers or IDs, and no
lookup against any external source. Human names are NOT machine-detectable
pattern-only; they are governed by the writing rule (CONTRIBUTING) and
review, and that limitation is stated in the doc.

## CI and rollout

- `tests/test_public_placeholders.py` runs the scanner on the tracked tree;
  unit tests prove it bites with synthetic mutant fixtures (valid-checksum
  ID, real-range phone, numeric profile ID) and stays quiet on the canonical
  personas.
- geni-uploader first; the same source + scanner pattern rolls out to every
  reihlinstinct public repo via its own issue + PR inside the
  `.repo-layout.yml` / community-standards rollout (#721), one repo at a
  time with green CI + independent review.

## Verification

Full suite green; mutant fixtures demonstrate detection; independent review
at the exact head. No live Geni effect. No real personal data appears in any
file, issue or PR text produced by this work.
