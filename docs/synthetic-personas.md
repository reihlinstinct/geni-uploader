# Synthetic personas for public files (#725)

Rule: public docs, tests and examples use the canonical personas in
`synthetic/personas.json` - never ad-hoc invented values and never real
names, surnames, phones, national IDs or profile IDs. Reference personas by
key or copy their canonical values.

## Why the values cannot be real

- **Names**: generated `<non-dictionary token>-<4 digits>` (e.g.
  `Abqef-4821`); Hebrew forms carry the `זז-` sentinel prefix.
- **Phones**: `+999-...` (E.164 country code 999 is reserved for future
  global service - no subscriber can hold it) and `+1-<NPA>-555-0100..0199`
  (the NANPA fictional range).
- **National IDs**: every persona ID FAILS the Israeli-style check digit
  (weights 1,2 repeating over the first 8 digits, digit-sum of products,
  check digit `(10 - sum mod 10) mod 10`); `tests/test_public_placeholders.py`
  asserts this. A checksum-failing value can never validate as a real ID.
- **Profile/union IDs**: clearly synthetic high fixture numbers
  (`profile-99xxxx` / `union-98xxxx`), disjoint from any live Geni ID in use
  in this repo's private configs.

## Checker

```sh
python tools/check_public_placeholders.py [--root DIR] [--write-baseline]
```

Exit 0 when the tracked tree (docs, tests, workflows, sources - `tests/` is
in scope) holds no real-looking values; exit 1 with one
`placeholder violation:` line per finding otherwise. Pattern-only: valid
check-digit IDs, phone shapes outside the reserved fictional forms, and
structured numeric `profile_id:`/`union_id:`/`profile-N`/`union-N`
references outside the persona set. It embeds no real data and performs no
external lookups.

`synthetic/public-corpus-baseline.json` grandfathers the pre-existing
corpus: entries are anchored by exact file + line + value + class, so moving
or editing a grandfathered line re-flags it. `allowlist` entries (same
anchoring plus a mandatory `reason`) cover values that must stay. Migration
PRs shrink `findings` per area (tests, oauth-bootstrap, docs, src, tools);
`--write-baseline` is migration tooling, never a way to bless new data -
adding entries requires review like any other change.

## Known blind spots

Bare numeric IDs in prose are not reliably distinguishable from fixture
values; obfuscated/separator-split numbers may evade the phone patterns;
real names are caught by review, not by the scanner. These are governed by
the writing rule in CONTRIBUTING.md.
