# Bilingual names for new profiles

Requirement recorded 28 October 2026 for the parent-only creation backlog (#190),
with design context in #144 and local review-card design #187. This is a data and
review requirement, not an implemented feature or permission to create profiles.

When a supplied name is in Hebrew:

- Preserve the supplied Hebrew in the profile's Hebrew locale/name fields.
- Prepare an English transliteration or translation as appropriate for the
  profile's main/default name. Do not replace or discard the Hebrew original.
- Keep supplied spellings distinct from proposed spellings. A person's name must
  not be silently translated into a different identity. If several spellings are
  plausible, show the choices and their provenance for review before upload.
- The exact-diff card must show both names, their locales, and which is intended
  as the main/default. Approval binds those exact values and target identity.
- Verify the vendor's locale keys, writable name fields, default-name selection
  and readback behavior before enabling production. The existing offline core's
  support for locale dictionaries alone does not prove default-name behavior.
- Readback must confirm both locale values and the intended default without
  silently overwriting the original. Missing or unverifiable fields block success.

This requirement does not permit guessed surnames, dates, relatives or life
status. It does not widen the parent-only cap, authorize live API access by an AI
client, or change the human-triggered execution rule. Only approved data in the
approved private scope may appear in actual bundles or review cards.

Implementation tests must use synthetic ZZ-prefixed examples and cover original
Hebrew preservation, English/default selection, ambiguous transliteration review,
changed-payload approval invalidation and exact round-trip verification. Public
fixtures must contain no real family names, profile IDs or protected outputs.
