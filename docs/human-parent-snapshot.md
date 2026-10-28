# Offline parser and packaged closed gate

Both production entry points read the packaged release-gate contract before
rejecting execution. A caller-supplied permit or JSON toggle cannot enable them.
Missing, malformed or changed contract fails closed. Even the expected contract
always raises Blocked. This is integration of a closed gate, not a live executor.

parent_snapshot.parse accepts only an already supplied four-part private
snapshot plus a canonical expected owner ID. It makes no requests, accepts no
credentials, follows no URL and authenticates neither source nor consent.
Do not use it as a live preflight or write permit. The existing strict collector
and existing strict evidence reviewer are unchanged.

Matching owner IDs and explicit merge flags are separate observations. Missing
merge flags stay unknown, invalid scalar flags are never coerced to false,
and merge targets/pending flags block. Custody bundles cannot be substituted
for snapshots. Names and GUIDs cannot replace canonical owner IDs.

Absent/null/wrapped, paginated, redacted, partial or inconsistent graphs produce
unknown graph status and no parent count. The parser recognizes only a bounded
reviewed field set. Unrecognized fields conservatively make graph consistency
unknown rather than silently discarding a possible partial-data signal.
An observed-consistent graph can provide a count of observed parents only.
Even zero is not evidence of absence. Every output preserves unknown hidden
parent completeness, unknown slots, unauthenticated evidence and creation false.
The snapshot hash identifies supplied content, not truth or authority.

Tests use invented identifiers only. No live vendor proof, account change,
production adapter, released artifact or human-write approval is supplied.
