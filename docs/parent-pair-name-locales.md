# Parent-pair known-name collision keys (#788)

The previous digest guard compared different locale-map schemas: creation entries
use `en`, while served pinned profiles use `en-US`. Equal human names therefore
could not produce equal digests. This fix compares per-locale first/last pairs,
mapping `en` to `en-US`, trimming boundary whitespace, casefolding and applying
Unicode NFC. A collision in either Hebrew or English stops admission. Middle
and maiden names do not hide a matching first/last pair.

This is a conservative duplicate-risk stop, not proof that two people are the
same person. There is no override, fuzzy matching, transliteration, merge, name
edit or change to privacy/life-status requirements. A missing served name map
is not filled from a top-level display name. Existing payload validation still
runs before comparison; malformed or untrimmed creation fields remain blocked.

The initial 12-test synthetic suite was run before the source fix: seven failed
and five passed. Five later tests bring the final regression file to 17 tests.
They cover both locale mappings, case, Unicode decomposition, whitespace already
rejected by payload validation, different first/last pairs, extra middle names
and absent pinned name maps. No credentials, network, workflow dispatch or Geni
effects are involved. Seven isolated mutations (guard removal, locale mapping,
either locale dropped, casefold, trim and NFC removal) are killed by the new
regression file alone. The change restores a guard; it is not live-run approval.
