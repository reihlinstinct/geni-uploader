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

### Sibling parent-union verification

The same GET-only mode can carry a complete approved `target_payload`, two exact
`expected_parents` and exact `expected_children`. This adds one pinned immediate-
family GET for the target. The profile's fields, canonical union reference, pinned
union membership and direct family back-reference must all pass. Every response
is encrypted before further work. The original father verification mode is
unchanged when these optional fields are absent. No mutation or retry is added.


## Bounded match discovery

`get_only_matches` requires a separately approved pinned `discovery_id`, expiry,
executor SHA and config hash. Its protected workflow uses `PILOT_GET_MATCHES_JSON`.
It makes two fixed vendor GETs: a profile summary with managers and merge fields,
then that profile's `tree_matches` listing. Each response is encrypted before
validation or the next read. Access errors, unexpected schemas, over 20 entries
or a response above 256 KiB stop the run. No paging, candidate or manager reads,
URL following, retries, edits or merges are supported. Private/redacted returned
values remain private; they do not authorize access elsewhere. No match proves
identity, and an empty or inaccessible listing never proves duplicate absence.
The SDK documents `tree_matches`, but its detailed return schema is not specified;
unrecognized shapes are retained encrypted and stop rather than guessed.

References: https://www.geni.com/platform/developer/help/sdk_js?version=1 and
https://www.geni.com/platform/developer/help/api?path=profile&version=1 .


Discovery uses an exact two-route read-only HTTPS admission class, not the legacy
create transport's profile/family route expression. Both the outer wrapper and
actual transport reject repeats, non-GET methods and any other route before a
socket is opened. The transport keeps the two-call cap and ten-second pacing.
Offline tests exercise the production transport with only the socket substituted.


## Single-profile diagnostic

`get_only_profile` pins `target_id` and boolean `debug` in its private config.
The protected pilot-get-profile workflow uses PILOT_GET_PROFILE_JSON, and its
optional boolean debug input maps to DIAGNOSTIC_DEBUG (0/1) and must agree with
config.debug before transport is constructed. Default debug is off. This mode
makes exactly one vendor GET using the existing fifteen-field FIELDS list,
with no owner identity read, union read, follow-up, retry or mutation. Two
private GitHub source checks remain unchanged. A successful parsed response is
saved encrypted before validation. Read errors retain exact status; debug adds
only the fixed structural evidence allowed by the family diagnostic helper,
never arbitrary error text or secrets. Run only after a separately coordinated
quiet period, at least thirty seconds with no other agent Geni calls. A quiet
period does not prove absence of concurrent external account activity. A result
never establishes that a prior unknown 4xx had the same cause.
