# Protected GET-only setup diagnostics (#518)

Separate manual workflow, never a create mode or fallback. Requires the reviewed
#510 diagnostics dependency. New workflow merge is held for explicit owner
approval in addition to independent review, exact-head CI and the normal signed
merge. No dispatch follows from merge. A fresh exact config/executor approval and
protected father-create human approval are required for every diagnostic run.

Closed config: schema=1, mode=get_only_diagnostic, data_repo, data_sha, data_path,
owner, expect_name, recipient, allow_unknown_merge and expires_at. Config bytes
are pinned by SHA256 and executor by exact master SHA. Private source identity,
path, names and recipient belong only in the environment secret
PILOT_GET_DIAGNOSTIC_JSON, never public inputs. The old create config is not used.
No risk acceptance flag here can grant creation.

Environment read by the executor: DIAGNOSTIC_CONFIRM is the run-confirmation
input and must equal READ_ONLY_NO_CREATE. DIAGNOSTIC_CONFIG_JSON carries the
closed config bytes and arrives only from the environment secret named above.
DIAGNOSTIC_CONFIG_SHA256 pins those config bytes, and DIAGNOSTIC_EXECUTOR_SHA
must equal the exact commit SHA being run. DIAGNOSTIC_OUTPUT_DIR is the local
protected artifact directory under the runner temp area, retained one day,
never a remote or public path.

Only five distinct GET routes can be used: exact private repo metadata, exact
immutable private proposal, vendor token-self, exact owner and immediate family.
Method/body/route checks happen before transport construction. POST, PUT, PATCH,
DELETE, refresh, receipt, consumed marker and create logic are unreachable from
this entry point. Each route has one attempt, with no rerun or retry. Existing
fixed-host transport supplies bounds, deadlines, no redirects and vendor spacing.
Unknown merge evidence stays UNKNOWN, hidden-parent completeness UNPROVED. An
observed relative or union stops the isolated-root preflight, without repair.

Age encryption is checked before network. After that, setup/source/vendor failure
writes a fixed stage/error report encrypted to the existing private recipient,
as a local protected artifact retained for one day. There are no remote Git writes.
Raw errors/responses/credentials and identifying values never enter public logs.
An encryption/setup failure before artifact creation may still have only a fixed
public stage. Diagnostic completion does not prove create readiness or authorize a
write. Inspect the encrypted result and report the actual failing stage privately.
No real provider/network request is made by implementation or tests.

## Bounded encrypted HTTP failures (#520)

Only this GET-only entry point enables failure-detail capture. A non-success
response retains its numeric HTTP status in encrypted evidence. GitHub errors
may also retain the error JSON message and X-Accepted-GitHub-Permissions hint,
each stripped of control characters and capped at 256 characters. Error JSON
is read once with a 4096-byte limit; malformed or oversized content is omitted.
The active credential is redacted from retained strings. No other response
headers/body are retained. Public output remains fixed stage/error wording.
No retry, redirect, refresh or new route is added. Existing create paths do not
enable this capture. HTTP status alone does not prove a credential's root cause.

Credential syntax is checked offline at github_credential and
secondary_credential before transport construction. Missing/malformed values
stop there with encrypted local evidence, after encryption/output setup succeeds.
Syntax validity is not authentication: a well-formed but denied credential still
fails at the actual private_repository or vendor_reads HTTP boundary.

## Scoped post-write reconciliation (#532)

A separate protected pilot-get-reconcile workflow uses PILOT_GET_RECONCILE_JSON
and pins DIAGNOSTIC_MODE=get_only_reconcile. It has the same exact executor/config, master,
owner-actor, first-attempt and human environment gates. It receives the read-only
repository credential and secondary vendor token, never the evidence writer.

After verifying the immutable proposal and exact owner identity, it reads the
owner's immediate family once and at most eight related profile IDs once each.
No union expansion, graph traversal, pagination or retries occur. IDs are syntax
checked before route construction. Name comparison uses normalized full name
fields and the proposal's localized names; a candidate match is not proof of
parenthood or of the uncertain write. Hidden-parent completeness stays unproved.
Encrypted local evidence alone contains observed IDs and name-match booleans.
Public output remains fixed-stage only. No raw names/response/header values are
retained. HTTP 500 after a send remains uncertain even if no match is observed.
No markers are changed and this workflow cannot authorize or retry creation.

Record observed name-locale keys in encrypted reconciliation evidence. Keys only,
no name values, and no extra requests. Root self/owner keys are recorded separately;
candidate keys are attached to each encrypted checked-ID observation.

## Pinned read-only verification

`get_only_verify` uses two additional exact config pins: `created_id` and
`union_id`. Its protected `pilot-get-verify.yml` workflow uses the separate
dedicated verification configuration secret and still requires READ_ONLY_NO_CREATE, exact
executor/config digests, expiry and environment approval. The vendor allowlist
contains only the pinned profile fields GET and pinned union GET. No traversal,
mutation or retry is possible. The private source is loaded read-only as before.

Each parsed response is encrypted and saved before validation or the next read.
A save failure stops further reads. Per-check booleans retain the original
strict privacy, living, gender, names, union and relationship checks. Exact
names-map and bare-ID expectations are not relaxed. Failed checks leave the
result STOPPED, never VERIFIED. Parsed responses are encrypted only, never
printed in workflow logs. This mode does not create remote receipt markers.

### Exact union reference representation

Create readback and pinned GET verification accept either a bare `union-<digits>`
ID or exactly `https://www.geni.com/api/union-<digits>`. Both map to the same ID
before checking the pinned relationship. Other hosts, schemes, queries, fragments,
ports, whitespace and trailing paths are rejected. Cardinality, privacy, names,
partner IDs and child IDs remain strict; this is representation normalization only.
