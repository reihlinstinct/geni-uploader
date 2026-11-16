# Protected GET-only source reconciliation

Design for #697. Generic, private hash-bound configuration supplies an expected
account profile ID, target GUID, expected served profile ID and exact name,
1-5 approved URL/title/description-SHA256 identities, age recipient and expiry.
No names, IDs or source URLs appear in public workflow inputs or logs.

A manual father-create workflow binds the exact master executor SHA and config
hash, fixed automation actor, first attempt and READ_ONLY_SOURCE_RECONCILE.
Validate run metadata and existing human reviewer/master/no-bypass protection.
Do not change protections or existing secrets. Source token is the environment
GENI_ACCESS_TOKEN; config is SOURCE_RECONCILE_JSON. No repository source clones.

Read account identity, target identity via GUID, then the target document list
and account uploaded-documents list. The account list is needed because a lost
create acknowledgement can leave an untagged document. Inspect at most 5 pages
of 50 rows per list, 10 unique candidate documents and 25 total vendor calls.
Requests are paced at least 10 seconds apart, with no retry. Exact same-host
sequential pagination only, no redirects or external response URLs as requests.
Only exact URL matches become candidate document GETs; validate numeric IDs and
fixed document routes before network. Preserve title-only collisions as warnings.

Classify exact matches only after document GET confirms URL/title/description
hash and tags. Multiple matches, stale/incomplete/malformed listings, missing
fields, wrong identities, errors, budget exhaustion or pagination ambiguity are
UNKNOWN. An absent target tag is not absent creation. Even complete scans with
no match are observations, never permission to recreate or reset an uncertain
journal. No write, tagging, repository push, journal edit or upload dispatch.

Before any vendor read, prove age encryption works. Preserve raw responses and
partial findings in an encrypted artifact even on stop, using a PATH-only age
child environment. Public output is fixed success/stop text only. Config and
account-upload listing are private; report only approved source matches.
Independent exact-head review, synthetic negative tests and green CI before
normal signed merge. A separate human deployment approval gates every read.

References: official user/uploaded-documents documentation supports page and
per_page with maximum 50, returning results/page/next_page. Official document
GET supports id/title/source_url/description/tags. Unexpected shapes stay
UNKNOWN rather than loosening the parser silently.

Environment reads: RECONCILE_EXECUTOR_SHA, RECONCILE_CONFIG_SHA256,
RECONCILE_CONFIRM, RECONCILE_CONFIG_JSON and RECONCILE_OUTPUT_DIR are scoped
to this workflow. GITHUB_TOKEN reads only run/protection metadata, while
GENI_ACCESS_TOKEN reads Geni. Runtime checks GITHUB_REPOSITORY,
GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_ACTOR, GITHUB_TRIGGERING_ACTOR,
GITHUB_RUN_ATTEMPT, GITHUB_SHA and GITHUB_RUN_ID. PATH is the sole child
environment key. A full 50-row terminal page with no continuation is ambiguous
and stops UNKNOWN. Duplicate query keys, duplicate row IDs and page cycles stop.

## Empty initial collection compatibility (#699)

Design: accept exactly {"results": []} on page 1 as a terminal empty collection.
No other keys, later page, nonempty rows, links, error or metadata are admitted
by this compatibility branch. The normal documented page checks stay unchanged.
This only advances read-only inspection; it grants no recreation or journal reset.
