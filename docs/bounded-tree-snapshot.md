# Bounded tree snapshot

Separate GET-only read route. No vendor write, create, invitation, deletion,
token refresh, automatic retry, merged-profile redirect or repository mutation.
Existing secondary-readonly-evidence environment remains protected. Exact
executor/config digest, owner ID/name, expiry, actor, attempt1 and manual
approval gates apply. New BOUNDED_TREE_SNAPSHOT_JSON secret; never reuse an
old snapshot approval. No package installation or dispatch is part of a PR.

## Scope

Two owner GETs (/profile and exact owner), then deterministic breadth-first
service immediate-family graph traversal. Read families at depth0,1,2;
profiles first discovered at depth3 are recorded as boundary, not expanded.
A hop is service-returned immediate-family adjacency, not a claim about a
civil/legal degree of kinship. Maximum50family requests,25union requests,
2owner requests =77GETs;15seconds minimum pacing (about19minutes pacing at
cap),45minute job timeout. Family response cap500nodes, discovered queue
cap5000profiles, per-response cap256KiB, cumulative accepted responses16MiB.
Union reads corroborate returned union nodes and never broaden traversal.
Nonrequested profile details, hidden nodes, pagination, and outside bounds
remain unobserved. Positive/unknown merge fields remain evidence, never a
permission to follow a new identity. Locale keys are retained as source data.
Exact Geni union/profile URLs are accepted only for typed references; routes
are constructed only from validated canonical node IDs. Never follow URLs.

Stop on any auth/rate/challenge/transport/schema/storage/expiry error. No
HTTP retry, including after429. Each attempted route is consumed before
transport. No current tree completeness claim, even at successful phase
BOUNDED_SNAPSHOT_COLLECTED. Boundary ledger states truncated coverage.

## Evidence and private refresh

Encrypt before exporting identifying data, persist sequential immutable local
ciphertext snapshots after each response, retain artifact even on failure.
Only fixed status text enters public console. A separate authorized follow-up
fetches artifact, validates executor/run/config, decrypts privately, then
archives exact ciphertext with digest/provenance in a NEW private snapshot
path. Do not overwrite old intake or treat missing profiles as absent.
Reconcile old drafts by exact IDs + relationship evidence, flag ambiguous
matches. Never turn matching names into creation proof or make vendor changes.
The read runner has no GitHub write credential.

## Run ceremony

Independent exact-head review and green CI, exact config audit, fresh user go,
then one dispatch: bounded-tree-snapshot.yml, master, executor_sha and
config_sha256 exact, confirm=READ_ONLY_BOUNDED_TREE. Human approves deployment.
No rerun. Inspect encrypted final phase and scope; successful Action alone is
not a whole-tree import. Partial STOP snapshots may be archived as partial,
never used as a complete replacement. New run needs new explicit approval.

## Environment contract

SNAPSHOT_CONFIG_JSON contains the private exact JSON config;
SNAPSHOT_CONFIG_SHA256 pins its UTF-8 bytes. SNAPSHOT_EXECUTOR_SHA must match
the execution commit. SNAPSHOT_CONFIRM must be READ_ONLY_BOUNDED_TREE.
SNAPSHOT_OUTPUT_DIR must be an absolute new directory for immutable ciphertext.
GENI_SECONDARY_ACCESS_TOKEN is the isolated read credential. No generic token
or GitHub writer is accepted. Standard GITHUB_ACTOR and
GITHUB_TRIGGERING_ACTOR gates both require the reviewed automation identity.

## Omitted union lists

For this GET-only observation route, an absent union partners or children
field is recorded in unknown_union_fields as UNKNOWN_OMITTED. Raw response
stays unchanged; no empty array is invented, no absence-of-family inference
is allowed. Present lists must still be actual lists of exact validated
profile references, bounded and duplicate-free after canonical normalization.
Null, scalar, malformed, foreign-host and duplicate present lists STOP. This
policy changes no write runner, limits, traversal discovery or retry rule.
