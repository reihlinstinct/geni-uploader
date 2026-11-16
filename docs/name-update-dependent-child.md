# Protected existing-name update then dependent child create

Design for #689. A new entrypoint/workflow/secret, not an extension to existing
surname corrections or a retry of an earlier creation. No live dispatch authorized
by this design or its merge. Names must be explicitly approved, not inferred.

## Immutable plan

One existing child ID, exact pre-update profile snapshot and exact update body;
one child-only creation plan targeting the same two-parent union. Existing child
must already appear as a child in the expected graph. Update body admits only
top-level first/last names plus exact bilingual name maps, preserving Hebrew.
No dates, gender, privacy, about text or relationship changes. New child and
existing child must be distinct. Expiry and owner identity agree across plan.
The existing child's post-update pinned profile in the child plan matches the
approved name change. Config/source/executor SHA admission remains mandatory.

## Sequence and proof boundaries

1. Read owner identity; existing child profile; exact anchor and reciprocal
   existing child graphs; explicit target union parents and children. Missing
   children is not accepted. All pins and exact pre-update name values must match.
2. Durable before receipt, consume a distinct update marker, one update POST.
   Preserve decoded ACK encrypted before interpreting it. Unknown/transport-loss
   response is terminal. Never derive IDs or reset the old child-create marker.
3. Read existing child profile, exact anchor/reciprocal graphs and direct union
   again. Require exact new names and unchanged identity/GUID/privacy/living/
   gender/about/union membership. Model and independent IO latch each require
   these proofs before creation is admitted. Final update receipt must succeed.
4. Existing union-child creation model then rechecks its complete baseline and
   performs one separately approved child creation. Its original per-child
   consumed marker, ACK and exact post-create proofs remain unchanged.

Stop all later effects on any uncertainty, mismatch, expiry or storage failure.
No retry, automatic repair or partial-package resume. Update marker deliberately
excludes expiry/source/executor so repinning cannot reopen the named operation.
A verified update followed by failed creation is partial completion, not success;
report each operation separately and preserve all encrypted receipts.

## Transport and delivery

Fixed HTTPS host, exact method/route admission, no redirects/retries/429 loop.
Update phase is fixed GET/POST/GET sequence. Creation phase cannot begin until
independent update proofs pass. Existing bounded creation routes and pacing stay.
Decoded successful ACKs retained before validation, not malformed raw-wire bytes.
Evidence encrypted locally and retained on failure; archive promptly. Separate
protected secret and father-create human review, no bypass. No token scope claim.

## Required regression gates

Wrong identity/expected name/union/parents/child list; altered Hebrew; unrelated
update keys; partial ACK; privacy/living/gender/about drift; missing each proof;
update/creation latch and body-binding bypass; receipt/encryption failure; consumed
update/create replay; update success then create failure; expiry; real source
Base64 decode/canonical cross-hash and consistency; workflow protection. Synthetic
names only. Live compatibility is not proved by offline fixtures.

## Entrypoint environment

MIXED_CHILD_CONFIG_JSON and MIXED_CHILD_CONFIG_SHA256 bind exact package bytes.
MIXED_CHILD_EXECUTOR_SHA must match GITHUB_SHA. MIXED_CHILD_CONFIRM is
UPDATE_NAME_THEN_CREATE_CHILD; MIXED_CHILD_DEBUG must be true or 1.
MIXED_CHILD_OUTPUT_DIR is a new absolute encrypted-evidence directory.
MIXED_CHILD_TREE_PAT is the private evidence writer credential. Existing token
GENI_SECONDARY_ACCESS_TOKEN is never logged. Workflow name-update-child-create.yml
uses separate MIXED_CHILD_PACKAGE_JSON secret in protected father-create.
