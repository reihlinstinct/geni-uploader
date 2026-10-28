# GitHub review evidence contract candidate (#258)

This offline reader accepts supplied synthetic response envelopes only. It has
no HTTP client, credential, workflow integration, deployment, settings change,
execution path or Geni call. A consistent snapshot grants nothing. No production
entry imports it. Fixed GET descriptors use api.github.com and exact pinned
repository, run and environment paths. Caller URLs, slashes, query injection,
redirects, retries, non-200 results, duplicate JSON keys, over-1MiB responses,
pagination and ambiguous/multiple decisions are rejected. Metadata URLs and
approval comments are never followed or interpreted as instructions.

Repository IDs/names, run ID, exact head SHA/workflow path/branch, dispatch event,
initiating and triggering actor IDs, environment ID/name, reviewer ID and branch
policy are checked. Only one explicitly named User reviewer is supported, not
Team membership. Self-review and admin bypass must be disabled. Exactly one
custom branch-only policy must match the exact branch; protected-branches-only,
wildcards and tags are unsupported. Missing bypass fields block, not false.

Review history has no explicit run_attempt, review timestamp, job ID or private
payload digest in the documented schema. Attempt one only is accepted to avoid
silently reusing a prior attempt's decision, but this is NOT proof that review
approved a particular job, immutable workflow content or payload. A workflow path
and head SHA are snapshot binding, not a verified content digest. Current rules
are not proof of rules at approval time. Before production, a trusted bounded
HTTPS reader must establish provenance and freshness, an immutable private exact
owner/payload approval must be independently verified, and job/attempt review
correlation and rule-change TOCTOU must be resolved. Those are release blockers.
A caller can forge all supplied snapshots, so provenance_verified remains false.
The output cannot enable execution, retries, reset, storage or account changes.

No network tests or real review decisions are made. Synthetic ZZ fixtures test
every binding leaf with invalid types/values and missing fields, duplicate
records, raw size/JSON bounds and transport metadata. The whole normalized doc
is pinned; a changed claim requires explicit fixture review.

Sources read 2026-10-28:
- https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run
- https://docs.github.com/en/rest/deployments/environments#get-an-environment
- https://docs.github.com/en/rest/deployments/branch-policies#list-deployment-branch-policies
