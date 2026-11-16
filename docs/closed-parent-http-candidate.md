# Closed one-father HTTP transport candidate

Related: #232. Dormant, not released. `ClosedParentHTTP.send` calls the shipped
always-blocking production gate before validating input or opening a connection.
There is no CLI, credential retrieval, deploy or setting that enables this class.
Tests replace that gate and the connection with fixtures only. No live Geni
request is part of this work. Do not remove the gate to run it.

The fixed HTTPS host is www.geni.com:443; the only request is POST to the
canonical approved owner's /api/profile-N/add-parent path, JSON body and bearer
header. No caller URL, query credentials, proxy environment, redirect following,
retry, refresh or alternate host is used. Python HTTPSConnection uses its normal
TLS certificate verification. Timeout is ten seconds per blocking socket action,
not an overall wall-clock deadline. Response reading is capped at 1 MiB plus one
sentinel byte; oversized or non-200 responses remain uncertain. The inherited
classifier accepts only the strict synthetic single-id acknowledgment shape.
Real vendor response schema/readback integration is not established by this PR.

The payload is the existing exact English-main plus he/en locale private parent
contract, restricted here to male. The header token must be bounded printable
ASCII without spaces/control bytes. It is never stored on the instance, returned
or printed. Request/transport exceptions yield value-free uncertainty. No logs
or public artifacts contain headers, bodies or error strings.

A per-instance attempt latch burns before connection construction. It is NOT
shared durable intent, cross-process exclusion, authenticated owner approval or
crash recovery. New instances can bypass a local latch; the release gate still
blocks them. A future authenticated executor must permanently consume canonical
owner-global shared intent before calling this transport and preserve consumed
state through all failures. This class deliberately does not accept a boolean
"durable intent approved" substitute. Connection failure before known send is
conservatively uncertain, not a reason to replay. Close errors never free the
latch. Acknowledgment is never verified profile success.

Release remains blocked by shared authenticated intent, exact approval and
release provenance, fresh bounded graph/owner preflight, encrypted durable
request/response/readback storage, vendor id/URL and parent/privacy/name
verification, protected human environment audit and separately approved release.
No source upload, mother, child, marriage, edit, merge or cleanup follows this
candidate. No live OAuth, dispatch or write is authorized by merge.
