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
corpus. Scope note: grandfathered entries are not only synthetic-persona
fixtures - they include legacy documentation examples (README, docs,
workflows), source/test constants, and a few pattern false positives (digit
alphabet strings, hash fragments). Every entry was verified non-real when
anchored, but "in the baseline" means "reviewed and anchored", not "born
synthetic". Entries are anchored by exact file + line + value + class, so
moving or editing a grandfathered line re-flags it. `allowlist` entries
(same anchoring plus a mandatory `reason`) cover values that must stay.
Migration PRs shrink `findings` per area (tests, oauth-bootstrap, docs,
src, tools); `--write-baseline` is migration tooling, never a way to bless
new data.

CI guards (active automatically under `GITHUB_ACTIONS=true` / `CI=true`,
on pull requests (`GITHUB_BASE_REF` set),
reading the pull-request payload at `GITHUB_EVENT_PATH`):

- `--write-baseline` refuses to run in CI; regenerate locally and commit.
- A baseline entry that no longer matches any finding is stale and fails
  the check; removing flagged content requires a regenerated (smaller)
  baseline in the same PR.
- On pull requests the baseline may only shrink: added `findings` or
  `allowlist` entries versus the PR base fail the check unless the PR
  carries the `synthetic-baseline-grow` label, which marks explicit owner
  review of the added entries. Moving an entry between `findings` and
  `allowlist` is not growth. The guard fails closed: a missing/unreadable
  pull-request payload or base commit is a violation (the checker fetches
  the base commit explicitly, so a shallow checkout is fine). A verified
  absent baseline at the base counts as empty - the initial introduction
  of the baseline is growth and needs the label.

The `synthetic/` directory itself is not scanned: it is the source of truth
for the synthetic values (personas and the corpus baseline), so every value
there is expected. Its correctness is instead pinned by complete validation
tests over `synthetic/personas.json`: the approved persona values are pinned
literally in the test, and every field is validated (invented-token name
shapes, Hebrew variants, profile/union id ranges, field-specific reserved
phone forms, checksum-failing national ids, uniqueness of keys and ids).

## Persona-rendered documents (#733)

Documents listed in `synthetic/persona-template-manifest.json` are rendered
from `docs/templates/*.md.in` templates with values from
`synthetic/personas.json` (design: `docs/persona-template-design.md`; first
example: `docs/persona-template-example.md`). Edit the template, never the
generated output.

```sh
python tools/render_persona_docs.py [--root DIR] [--write]
```

Template tokens are `{persona.KEY.FIELD}` (KEY a persona key, FIELD one of
its string fields); `{{` and `}}` write literal braces. Tokens render the
same in prose and in code fences. Unknown keys or fields, malformed tokens
and lone braces fail; a manifest entry's `forbidden_fields` rejects those
fields (as tokens or as literal values) in its output.

The default run only checks: it renders every listed document in memory
(UTF-8, LF, one final newline, a generated-from notice) and compares the
exact committed bytes. Exit 0 when all match, 1 on drift (a stale persona
value, a template change not re-rendered, or a directly edited output), 2
on a manifest, persona-data, template or path error (unknown keys, duplicate
JSON keys, traversal, symlinks, duplicate or overlapping paths). `--write`
updates drifted outputs locally and is refused when `GITHUB_ACTIONS=true` or
`CI=true`. The renderer does not prove prose free of real names; review is
still required.

## Keyed private-term scanner core (#733)

`tools/check_private_terms.py` is the public core of the keyed check in
`docs/keyed-public-terms-design.md`. It holds no terms, key or real digests;
no workflow runs it yet.

```sh
PRIVATE_TERMS_KEY=... python tools/check_private_terms.py --policy FILE [--root DIR] [--expect-tree OID] [--findings]
```

The HMAC key comes only from the `PRIVATE_TERMS_KEY` environment variable
(at least 32 bytes), never from an argument. `--policy` names the JSON
digest file (schema, algorithm, normalization and policy versions, keyed
HMAC-SHA256 entries, optional exact-position exceptions with reason and
expiry). `--expect-tree` binds the result to an exact git tree id;
`--findings` adds `PATH:LINE:TOKEN: private-term` lines. Output never
contains a term, normalized token, digest or key. Exit 0 clean, 1 blocked,
2 not evaluated (missing key or policy, unsupported version, cap exceeded,
unreadable file, symlink, tree mismatch). Public tests use synthetic
persona fields and a public test key only.

## Known blind spots

Bare numeric IDs in prose are not reliably distinguishable from fixture
values; heavily obfuscated numbers (letters substituted, split across lines)
may evade the phone patterns; real names are caught by review, not by the
scanner. These are governed by
the writing rule in CONTRIBUTING.md.
