# Bounded multi-anchor baseline reads

Issue #763. Schema 1 remains exactly six GETs with two explicit profiles
(owner first) and one union. It does not accept a budget field.

Schema 2 adds an integer `max_gets` from 1 through 50. The code hard ceiling
is 50. Profiles are 2 through 24 exact profile IDs, owner first; unions are
1 through 47 exact union IDs. Both lists reject duplicates, foreign URLs
and invalid IDs. A shared union is listed once, never once per anchor.
The complete route plan must fit the configured budget and hard ceiling
before any vendor connection. No field is a traversal instruction.

The plan is deterministic: current-token owner, explicit owner profile,
owner immediate family, then each explicit anchor's profile and immediate
family, then each explicit union. The plan has no duplicate routes. For
four anchors and three distinct unions, this is 14 GETs. Candidate counts
are not request counts: people without existing IDs cannot be fetched by
profile ID. Family reads supply reconciliation evidence, not proof that
all hidden or omitted relatives are absent. `full_children_visibility`
remains `UNPROVED`, and omitted union fields remain unknown.

The transport admits GET only, in the exact precomputed order, consumes
budget before transport, waits at least 15 seconds between requests, and
never retries, follows pagination, discovers routes or mutates profiles.
The existing identity, expiry, encrypted response preservation, diagnostic
allowlist and protected exact executor/config approval checks remain.
Schema 2 is not a live-run authorization. Each run still requires its own
human GitHub environment approval and expires with its reviewed config.

The job timeout is 40 minutes, including setup and encrypted artifact upload.
Fifty requests paced at 15 seconds consume at least 735 seconds between
requests, plus connection/response time (20-second transport timeout per
request). Transport or schema failure stops the sequence immediately.
No successful evidence phase overrides write preflight, merge holds,
privacy checks or missing visibility.

Regressions cover unchanged six-route behavior, four-anchor 14-route plans,
50 accepted / 51 rejected, invalid and duplicate IDs, integer-only config
budgets, sequence/pacing/no-retry enforcement and rejection of mutations.
All fixtures use synthetic IDs and names. No live API calls are tests.
