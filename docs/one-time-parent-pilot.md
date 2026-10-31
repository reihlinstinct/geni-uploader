# One-time protected parent pilot (#507)
The workflow hands the pilot its settings as environment variables:
`PILOT_CONFIRM` (must be `CREATE_ONE_PRIVATE_PARENT`), `PILOT_CONFIG_JSON` (injected from
the `ONE_TIME_PARENT_PILOT_JSON` secret), `PILOT_CONFIG_SHA256` and
`PILOT_EXECUTOR_SHA` (dispatch inputs pinning the config and the reviewed
executor commit), `PILOT_OUTPUT_DIR` (encrypted evidence output),
`FAMILY_TREE_PAT` and `GENI_SECONDARY_ACCESS_TOKEN` (scoped tokens). Before
any network call the pilot pins the GitHub run context (`GITHUB_SHA`,
`GITHUB_REF`, `GITHUB_REPOSITORY`, `GITHUB_EVENT_NAME`,
`GITHUB_RUN_ATTEMPT`, `GITHUB_ACTOR`, `GITHUB_TRIGGERING_ACTOR`);
`GITHUB_RUN_ID` and `GITHUB_SHA` are later recorded in the encrypted
evidence report.

This is a separate deliberately smaller path, not an opening of the dormant
production gate. It does not use the signed approval server, new OAuth callback,
new credential bundle/expiry/revocation path or their provider installation audit.
One independent exact-head code review, green CI and a separate protected human
run approval remain required. A code merge does not authorize a run.

## Scope and approval

The pilot accepts only one immutable private proposal with a private living male
parent, bilingual names and no other fields. The existing secondary-specific
repository secret supplies the credential; there is no primary fallback, refresh,
new login, source upload, merge, mother operation or automatic repair. Expired or
wrong-owner credentials stop. Reconnection, if needed, is performed by the human.

A private config (ONE_TIME_PARENT_PILOT_JSON) names data_repo, data_sha, data_path,
owner, expect_name, recipient, expires_at and explicit residual-risk decisions.
Its exact bytes have a SHA256 used in the manual dispatch. The dispatch also pins
the reviewed master executor commit; the protected father-create environment must
retain its human reviewer, self-review prevention, branch rules and no bypass.
Identifying values must never appear in public dispatch inputs, source or logs.
The human reviews the exact private file/commit/payload and config before approving
the waiting run. Config changes require a new reviewed hash and approval.

The config schema is 1. allow_unknown_merge is a boolean; true allows only wholly
missing merge fields, never known adverse or partly populated evidence.
accept_hidden_parent_risk and accept_private_create_risk must be true under the
specific pilot approval. Current API observations cannot prove absence of hidden
parents, and privacy readback cannot prevent an initial vendor privacy failure.
The existing repository credential can be replaced by its writer and has no new
TTL/revocation guarantee. GitHub administrators retain account/code control. This
is a weaker ceremony, not a claim of cryptographically human-only authentication.

## Sequence and no retry

1. Validate exact dispatch/ref/attempt/config pins and expiry. Preflight age
   encryption before network. Read immutable proposal from a confirmed private
   repository; validate its closed schema and payload.
2. GET token-self, exact owner and immediate family, with fixed host, bounded
   bodies, deadlines and rate spacing. Owner/name must match. Any observed other
   profile or union blocks this isolated-root pilot. Missing merge flags remain
   UNKNOWN and hidden-parent completeness UNPROVED, visibly in private evidence.
3. Persist encrypted preflight evidence as an annotated tag in the private repo.
   Atomically create an owner-scoped permanent consumed tag against the exact data
   commit, and read it back. Existing tags or persistence uncertainty STOP.
4. Make one fixed add-parent POST. Never retry, redirect, refresh or switch token.
   Record returned profile ID and bounded full response in encrypted evidence,
   and persist the acknowledgment before further vendor reads. A timeout is
   UNCERTAIN even if no ID was received. The consumed tag is never reset/deleted.
5. Read back that exact ID and its sole union: exact bilingual names, main names,
   male/living/private flags, exact owner as child and only new father as partner.
   Extra/blank profiles, missing fields or mismatch stop without repair. Save
   encrypted final evidence; VERIFIED means these exact checks passed, not that
   all Geni behavior is understood. A real profile may exist even on failure.

Private receipt tags contain only base64-encoded age ciphertext and point at the
approved immutable data commit. The consumed tag is a permanent one-time marker,
not authenticated global exclusion for all other tools/accounts. Local encrypted
artifacts are retained for one day as a fallback if remote persistence fails.
Receipt failure after POST does not undo the write or allow retry. Reconciliation
is GET-only and must be separately approved. Never delete markers to try again.

## Learning from the pilot

After the approved run, inspect decrypted evidence privately and report observed
API response shape, multilingual-name/privacy behavior, graph/union shape,
missing merge fields and any failure point. Distinguish observed behavior from
assumptions and list needed fixes before broader release. No raw response,
credential, private names or private repository path belongs in public issues.
There is no live probe during implementation or tests. The fake suite covers
validation, consumed-marker persistence, transport limits, failure/uncertainty,
exact request/readback and no retry. It does not prove vendor behavior.

## Verified API contracts

Official references rechecked during implementation:
- https://www.geni.com/platform/developer/help/api?path=profile/add-parent
- https://www.geni.com/platform/developer/help/api?path=profile
- https://www.geni.com/platform/developer/help/api?path=profile/immediate-family
- https://www.geni.com/platform/developer/help/api?path=union

The create operation returns a full profile, not an exact id-only object. Only a
returned/read-back profile_url is a browser link; url is an API link. A missing
browser link stays missing, never synthesized. The documented fields may be
omitted when blank; missing privacy/name/relationship readback never verifies.

## Failure evidence follow-up (#509)

Malformed provider object/transport AttributeError paths produce fixed value-free
failures. Response overflow, status, redirect, deadline and malformed JSON have
fixed diagnostic codes; no raw exception, partial plaintext body or credentials
are logged. Available private encrypted acknowledgment/final evidence is retained
through post-send failures. Oversized bodies stop at the bound, not buffered whole.
Public early-stop lines name only a fixed stage: setup, encryption, private_source,
credential, preflight, preflight_evidence, consume, send, ack, readback or final.
An early stop can precede private evidence creation; its stage is diagnostic, not
proof of an absent vendor write. Permanent-marker and receipt evidence determine
whether a send was possible. No marker is reset and no attempt is rerun.
This adds no request, retry, refresh, workflow permission or live-run authority.

Review follow-up: preserve the original stopped stage after final evidence
succeeds, distinguish config/manifest/output setup stages, and pin transport
diagnostic codes plus both deadline branches and run transitions with fake-only
regressions. A final evidence failure reports final. No added calls, permissions,
retry or live action.

The combined earlier-stop/final-receipt-failure regression asserts final, and
exactly 30 seconds trips each deadline branch. Both previously surviving test-only
mutations are now killed. These are offline coverage additions, not a new run.

## Separate private evidence writer (#522)

The create workflow maps the father-create environment secret
PILOT_PRIVATE_EVIDENCE_WRITER into the executor's FAMILY_TREE_PAT variable.
The GET-only diagnostic continues to use the separate read-only repository
credential and never receives this writer. Missing writer stops before a vendor
request; there is no fallback to another credential.

Minimum GitHub token scope is one exact private repository, Contents read/write
and required Metadata read. GitHub does not offer a tag-only token permission:
the credential can technically write other repository contents, while reviewed
code limits its use to immutable source reads and atomic consumed/evidence tags.
Do not describe this as a technically tag-only credential. Store it only in the
protected environment, keep its human reviewer and branch policy, and disclose
this residual scope before any run. Never reset or delete consumed markers.

## Local encrypted failure details

After the output directory exists, escaping execution/receipt errors write one
local encrypted STOPPED report with the stage and fixed failure code. HTTP
failures retain numeric status and bounded GitHub message/permission hints using
the same redaction and bounds as the GET-only diagnostic. Redirect-rejection
evidence records only status and Location/Link presence, never their values.
Handled send/readback errors preserve the same details in encrypted reports.
No additional remote receipt attempt, vendor call, retry or repair is performed
by the outer failure handler. Failures before output creation remain fixed-stage
public messages only. This does not change redirect rejection or create gates.

## Opt-in encrypted debug trace (#526)

PILOT_DEBUG=1 enables fixed stage transitions and relative elapsed milliseconds
in encrypted reports only. It is off by default; other values leave it off.
The trace contains at most 64 events, each with an allowlisted stage and an elapsed
time clamped to zero through one day. It contains no URLs, payloads, names,
credentials, headers or raw responses. Public output and transport behavior do
not change. No workflow input or secret enables this setting in the current
workflow; any exposure of that control needs its own review and approval.

## GitHub creation Location metadata (#530)

Only GitHub POST responses with status 201 on the exact repository git/tags or
git/refs route may include Location. Its value is never followed or retained;
the bounded JSON response is read normally. Link remains rejected, as do 3xx
statuses and Location on other routes, methods, statuses or vendor responses.
This narrow metadata exception does not change authorization, retry or create
gates and does not authorize any new run.
