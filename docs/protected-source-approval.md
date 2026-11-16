# Protected source approval workflow

Issue #691. Separate from the unchanged user-only source workflow.

## Contract

Automation dispatches one plan or one upload, each as a new run requiring the
existing master-only protected environment and human reviewer. No bypass,
rerun, schedule, pull-request trigger, automatic upload or retry. Dispatch
inputs contain only mode, executor SHA, configuration SHA256, prior plan run
ID and fixed confirmation. All source identifiers remain in a separate
private environment secret. The existing pinned container is reused; no new
Geni client or token leaves GitHub.

## Immutable package

Private JSON fields: schema, private_repo_url, private_ref, private_expect_sha,
manifest_path and recipient. Canonical JSON SHA256 is the public package pin.
Reject unknown fields, unsafe repository/ref/path/recipient values and missing
pins. Before the container starts, validate automation actor, master, first
attempt, exact executor SHA and package digest. Check the protected environment
still has required human review, prevents self-review, forbids administrator
bypass and allows master only. No environment settings are changed by a run.

## Plan to upload

Plan confirmation is PLAN_SOURCES. Upload confirmation is UPLOAD_SOURCES and
requires a successful prior plan from this separate workflow, first attempt,
same exact executor and package digest, dispatched by the automation account,
within 24 hours. The prior run's fixed hash-only run name binds mode/package;
GitHub run metadata must match. Each plan admits only one upload dispatch, including failed, rejected or uncertain attempts. Serialized source concurrency checks the workflow history before starting a container; a truncated or over-limit history stops. A fresh plan is needed after any prior upload dispatch. A successful process is necessary, not enough:
the human reviews decrypted identity, listing, duplicate/blocked state and
safe-to-run result before separately approving the upload deployment. Plan
approval never approves upload. A moved source branch fails its exact SHA
check; stop and prepare/review a fresh package and plan. Source status commits
may move the branch after upload; no blind repin or rerun.

## Output and effects

Mount temporary token files read-only, use the existing container's source
loader and exact git SHA check, capture all stdout/stderr privately, and never
publish raw exceptions or identifying values. Encrypt captured output and
plan report to the package recipient, retain encrypted artifacts for one day,
and remove temporary plaintext in an always step. Do not commit log files
back to the source branch: a plan must not invalidate its own data pin.
Container failures still preserve encrypted evidence and fail the job.
Uncertain writes require evidence review, not retry. Source documents only;
no profile edit, details repair, fact changes or invitations in this route.

## Tests

Synthetic tests kill actor/ref/attempt/executor/config/mode/confirmation and
prior-plan identity/hash/age/result gates. Test private values never enter
public output, container image digest is fixed, secrets are not CLI values,
plan/run remain separate human approvals, failed container evidence is
preserved, original user-only workflow is byte-for-byte unchanged, and no
runtime network or dispatch happens in tests. Independent exact-head review
and green CI precede signed normal merge. Live execution still needs exact
owner authority and the human deployment approval.

## Environment

SOURCE_EXECUTOR_SHA and SOURCE_CONFIG_SHA256 bind exact code/package.
SOURCE_MODE is plan or run; SOURCE_CONFIRM is PLAN_SOURCES or UPLOAD_SOURCES.
SOURCE_PLAN_RUN_ID is empty for plan and the reviewed prior plan ID for run.
SOURCE_PACKAGE_JSON comes from PROTECTED_SOURCE_PACKAGE_JSON. SOURCE_TREE_PAT
and GENI_ACCESS_TOKEN fill temporary read-only token mounts. SOURCE_TEMP is a
new absolute runner directory. GITHUB_TOKEN reads only current/prior run and
environment protection metadata. Workflow-provided GITHUB_REPOSITORY,
GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_ACTOR, GITHUB_TRIGGERING_ACTOR,
GITHUB_RUN_ATTEMPT, GITHUB_SHA and GITHUB_RUN_ID are independently checked.

## Secret custody and runtime setup gate

Before any dispatch, the operator must verify PROTECTED_SOURCE_PACKAGE_JSON,
FAMILY_TREE_PAT and GENI_ACCESS_TOKEN exist in father-create environment
secrets, not rely on repository-level fallback. GitHub expressions do not
expose a secret's scope, so this is an explicit pre-dispatch setup check,
not a claim that the job can distinguish fallback values. None of these
three environment secrets has been installed by this implementation.
Missing setup is a hard live-use blocker; never dispatch to test it.
Source credentials must be copied from an authorized saved secret through
the approved secret-sync route, without printing or passing values in chat.

The shared geni-upload concurrency is deliberate: both source workflows
must not race on status or duplicate listing. The existing workflow remains
unchanged. Containers explicitly run as uid0 inside Docker; host token files
remain0600 and directories0700. A no-secret CI smoke uses the exact pinned
production container with network disabled to prove token readability and
plan-directory writes. It makes no Geni request.

## Test contract follow-up

Issue #693: expression normalization must preserve every character inside
single-quoted GitHub expression literals, including doubled-quote escapes.
Only whitespace outside literals may be removed. Artifact checks normalize
action-reference casing before classifying all upload-artifact steps.
Negative synthetic mutations cover changed literal whitespace and mixed-case
extra plaintext uploads. Runtime and workflow permissions are unchanged.
