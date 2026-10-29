# Secondary owner and current graph preflight join

Issue #332. The local service now runs three fixed Geni GETs after workload,
private approval/live capture and immutable evidence checks, before durable
owner consume: token-self profile, exact configured owner profile and that
owner's immediate family. Only the service-held secondary token is used. No
POST, refresh, redirect, retry or caller URL is supported.

The approved v2 record's graph hash must equal the reviewed preflight policy's
graph hash before any Geni GET. The canonical complete bounded self/owner/family
snapshot must then match that hash. Token-self, explicit owner and family focus
must have the exact same configured canonical ID. Missing merge fields stay
UNKNOWN, and require the explicit configured exception. Pending merge, known
merge target, partial/malformed merge state, pagination, redaction, wrong focus,
malformed edges, observed parent union or graph drift block before consume.
Zero observed parent unions is still not proof of parent absence. Unknown parent
risk acceptance stays explicit; this preflight does not manufacture completeness.

A request budget of three, one-MiB streamed response cap, nesting cap, duplicate
JSON rejection and ten-second total deadline apply. No remote URLs returned in
objects are followed. Family edges must reference bounded canonical IDs present
in the returned node set. The exact graph comparison is deliberately conservative:
any benign returned-field drift also requires a fresh reviewed plan. Current API
fields may be omitted for blank values, so absence is not converted into false.

Local workerd SQLite tests now join JWT, immutable private record, live protected
capture, pre-write evidence, actual fixed GET preflight and owner-global consume
across concurrent calls and restart. Synthetic sources and credentials only.
A valid approval/evidence chain with wrong token-self must leave durable intent
unconsumed. Separate negative tests cover merge/graph/adverse evidence and the
UNKNOWN policy. No live Geni request was sent by these tests.

Source contract inspected:
- https://www.geni.com/platform/developer/help/api?path=profile
- https://www.geni.com/platform/developer/help/api?path=profile/immediate-family

The route remains local-only and returns no POST permit. Authenticated policy
provisioning, approved live GET budget/rate, durable cumulative ledger, complete
one-POST acknowledgment/readback executor and separate immutable release,
deployment and exact-run approval remain open. A successful preflight is not a
production release or permission to create.
