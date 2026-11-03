# Exact household precreation baseline read

Read-only preparation, not absence proof or creation authority. Config lists
exactly two profiles with the owner first, and one explicit existing union.
Exactly 6 ordered GETs: two owner identity checks, two immediate-family reads,
one nonowner profile read and one union read. No discovery, mutation or retry.
Decoded responses are encrypted before body/schema validation. Missing fields
remain UNKNOWN. The transport cannot retain malformed raw bytes or full HTTP
error bodies; it raises on non-2xx and keeps structural diagnostics only.

15-second pacing is not a request timeout. Base transport uses a 20-second
socket timeout and 30-second response deadline. The job limit is 12 minutes.
The token's OAuth scope has NOT been independently verified as read-only.
The exact GET-only admission guard is the mutation protection, not token scope.
Every real vendor request calls that guard before opening the pinned
www.geni.com connection. Redirects, Link headers and non-2xx (including 429)
stop; no internal retry or redirect-following exists. Calls/last initialize to
0/None. No changes to the shared transport are included here.

Only the new HOUSEHOLD_PRECREATE_READ_JSON config secret is installed in the
existing secondary-readonly-evidence environment. Human approval and branch
restrictions remain unchanged. Exact reviewed executor/config pins and fresh
owner read-go are required before a single dispatch. No creation workflow or
source-upload pins change.

The union read checks its exact ID and returned list structure, not a claimed
relationship to the owner or other profile. Reconciliation must compare family
edges and union membership afterward. Immediate-family edge roles are union
roles partner/child, not kinship words such as sibling. Saved real household
responses from earlier approved reads use these roles; no vendor mutation is
needed to check this convention. Unsupported roles stop after response capture.
Visible matches can identify duplicates but cannot exclude hidden profiles.

All personal response values stay inside age-encrypted evidence. Tokens are
never included in reports or stdout. Console output is fixed text. Synthetic
ZZ tests cover invalid schema preservation and real transport guards with a
fake HTTPSConnection, without network calls. Closes #678.

## Supporting implementation provenance

Unchanged dependency base: 71d23cb1f10ac3d18a4dffdc95a4cca55a68791f.
These dependencies are reviewed in place, not copied or modified.
Layout note (#704, updated #721): the root runner files below moved to src/geni_uploader/runners/ (one_time_parent_pilot, src/geni_uploader/runners/bounded_tree_snapshot.py). Import-identity shims left at the root by #704 were removed in #721 once nothing imported them by bare name; the hashes below pin the reviewed pre-move contents (the removed root facades are pinned as historical provenance):
- root one_time_parent_pilot (removed in #721) SHA256 59bd1d4862575dcdd5b29558083ff9937f295995f967075438b6b034d31aefc5, lines 76-82 initialization/host, 152-239 admission/request/redirect/status/deadline.
- src/geni_uploader/runners/bounded_tree_snapshot.py SHA256 645edd485c3f1fe68e0105b4afb60a45e3fd7c7a2d47c2529387d2a90c08cbf2, lines 26-54 config/body/identity.
- root parent_probe facade (removed in #721) SHA256 11f452824157ce489ae42d95bbeb3aa20d9e16f9754c905890f41d8c9ec3ff04, lines 1-9 import facade (root facade removed in #721; the packaged module it wrapped is pinned next).
- src/geni_uploader/client/probe.py SHA256 fac8f9e42d24c9cbac3d3d9927cacf4ca73638151b2bad4a523efbd6d86ccd16, lines 187-193 age encryption.
- src/geni_uploader/core/people.py SHA256 fb5878fe39ca2f245ed9e520c17c7fafd86fa6c8fb2393fd6fe4ca4b28ebf651, lines 10-20 value-free require/exact.
