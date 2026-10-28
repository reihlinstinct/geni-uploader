# Authenticated intent service and encrypted evidence boundary

Design only. Closes #247, follows #233/#236 and #245/#246. No service route,
Worker export, binding, migration, signing key, credential, deployment or gate
change. Existing models remain non-executable. No real identity token or private
profile evidence was collected for this design.

## Four distinct decisions

1. Workload identity: a verified GitHub OIDC token identifies a particular job.
2. Owner authority: a separately authenticated exact private approval authorizes
   this owner's one-father payload and its named residual risks. OIDC is NOT that
   approval. A protected environment approval alone is NOT payload approval.
3. Release authority: reviewed service/executor/data/policy pins are approved for
   deployment independently of code merge. A merge is NOT a release.
4. Run gate: exact run and protected human environment review are mandatory.
   A correctly signed token or caller-provided approval boolean cannot replace
   any missing decision. No chat phrase parser establishes authority.

## Official identity contract

Inspected 28 October 2026:
https://docs.github.com/en/actions/reference/security/oidc
https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments

GitHub documents issuer https://token.actions.githubusercontent.com, custom aud,
sub, exp/nbf/iat/jti, repository_id/repository_owner_id, workflow_ref/workflow_sha,
run_id/run_attempt, environment, event_name and runner_environment. job_workflow_ref
and job_workflow_sha are for reusable workflow jobs, not universal claims.

IMPORTANT current subject change: GitHub documents immutable subjects including
owner/repository IDs for repositories created after July 15, 2026, and migration
on later rename/transfer. Older repositories may retain legacy format. Do not
assume legacy repo:ORG/REPO:environment:NAME or construct a production subject
from a remembered example. Before release, inspect authenticated tokens from the
exact approved environment job and independently match repository numeric IDs,
owner IDs and effective OIDC subject configuration. Store the reviewed exact
subject as a release pin. No wildcard or silent legacy fallback.

Environment context replaces branch context in the default sub. Therefore exact
sub alone does NOT prove the approved branch/ref or workflow SHA. Require those
claims independently. Required reviewers, prevent self-review, branch policies
and no administrator bypass must be audited in effective environment settings;
the environment claim proves its name, not the current reviewer configuration.
Do not configure or customize OIDC settings as part of this design.

## Proposed verifier, not implemented

The service must verify signature with an allowlisted algorithm and trusted keys
from the fixed issuer's reviewed discovery/JWKS endpoints. Reject unsigned/wrong
algorithm, unknown key after one bounded refresh, malformed/duplicate claims,
oversize tokens, arbitrary jku/x5u URLs and network/key errors. Never follow an
attacker-selected issuer, key URL or redirect. Do not decode-and-trust a JWT.

Require exact issuer, custom operation-specific audience, pinned exact subject,
numeric repository/owner IDs, expected repository and workflow_ref, released
workflow_sha and code sha, exact approved branch ref, event_name workflow_dispatch,
runner_environment github-hosted, approved environment, exact run_id, run_attempt
1 and authorized actor_id. Reject missing/malformed values, fork/PR/push/scheduled
jobs, reruns, alternate workflows and unexpected reusable-workflow contexts.
If reusable workflows are chosen later, also pin both job_workflow_ref and
job_workflow_sha; do not accept them as substitutes for caller workflow identity.

Bound exp/nbf/iat to verified server time and a reviewed short skew/window. Never
use caller clock. Remember issuer+jti and operation/owner/run consumption in
shared durable state so token replay and newly minted tokens for the same run
cannot make a second operation. A short token lifetime alone is not one-use.
A maximum 15-minute approved plan does not extend token validity.

OIDC pins are necessary but not sufficient. A compromised approved runner holding
vendor credentials can bypass an application client. This is an explicit residual
trust limit, not solved by hashing data or hiding the POST behind a Python class.
Service authentication does not repair unrelated repository-scoped token exposure.

## Exact owner grant and permanent namespace

A separately reviewed trusted approval authority must bind canonical owner,
secondary connection, exact payload/graph/data hashes, executor/artifact/service/
policy pins, encryption recipient, human approval evidence, run/attempt, nonce,
expiry and one father operation. It must authenticate the owner and authorized
reviewer from trusted records, not OIDC actor name or a copied approval message.

Selection/implementation of that approval authority and grant signing/verification
is OPEN and release-blocking. No self-selected key, unsigned JSON hash, Git file
boolean, supplied source reference or environment secret named approved is proof.
No signing service/key is created by this document. The service must verify grant
provenance against reviewed allowlists and preserve revocation/narrower limits.

Server derives ONE permanent namespace from the authenticated canonical owner,
not plan ID, connection label, payload, run, caller path or encryption recipient.
Owner namespace cannot be reset by expiry, new token, new plan or backend version.
Binding an owner to a new deployment/namespace requires preserving consumed history
or blocks release. No reset/delete/lease release endpoint. Admin namespace removal,
restore/rollback, backup loss and compromised service remain explicit trust limits.

The shared backend atomically verifies immutable binding/expected version and
records intent plus history BEFORE any possible POST. Ambiguous commit response
means STOP/read-only inspect, never infer empty or replay. Stored acknowledgment
must preserve exact created ID; uncertain can finish only through separately
approved GET-only reconciliation, not ordinary verify. No automatic retry,
refresh, second POST, merge, delete, unlink or rollback.

## Encrypted evidence contract

Encrypt private plan/preflight/request/response/readback evidence with the exact
approved recipient BEFORE storage/upload. No key/private token in service state,
logs, public summaries, URL query/fragment or public artifact metadata. Storage
contains ciphertext only; ledger contains bounded opaque descriptors, not raw
family values. Owner IDs and binding hashes are private service data too.

A descriptor binds ciphertext digest, byte length, recipient fingerprint, schema,
operation/stage, authenticated uploader/run, storage identity and retention expiry.
A hash or filename alone does not prove encryption, existence, correct recipient,
provenance or retention. Require verified ciphertext upload completion plus
readback/digest confirmation from an approved private store before marking an
evidence stage durable. No arbitrary caller URLs, cross-tenant objects, public
buckets or secret-bearing download links. Object-store selection is OPEN and
release-blocking. Retention/deletion policy requires separate approval; expiry
never deletes consumed intent or authorizes another POST.

If encryption/upload/ack fails AFTER intent or POST, consumed state survives and
blocks creation. Report uncertain, including uncertainty about evidence storage.
Do not claim missing evidence means no write. Before-send storage failures block
POST. No plaintext fallback to improve diagnostics. Test cleanup on both success
and failure; unavoidable transient runner plaintext is a named trust limit.

Reconciliation uses a new short-lived read-only grant bound to the same permanent
intent/run/result. No vendor token refresh or mutation is included. Read only
approved fixed IDs/routes and bounded response fields/counts. Never accept a new
created ID when one is already known. Verified creation does not imply source/tag/
fact completion; private profile ID+verified URL and provenance are #244 work.

## Release verification matrix

| Boundary | Required negative evidence before release |
|---|---|
| JWT verifier | forged/wrong issuer/aud/sub/key/alg; duplicate/missing claims; expired/future token; untrusted key URL; bounded key failure |
| job pins | wrong numeric owner/repo ID, workflow/ref/SHA/environment, reusable context, event, actor, run or attempt; no wildcard fallback |
| owner grant | missing/forged/revoked/stale/changed owner, payload, graph, artifact, recipient or run; workload identity alone cannot grant |
| environment | removed reviewers, self-review/admin bypass, branch change or unverified effective audit stops |
| replay/CAS | same jti, fresh token same run, concurrent requests, new connection/plan/backend version never clear owner consumption |
| ciphertext | wrong recipient/digest/length/tenant/retention, incomplete upload/readback, plaintext or public object blocks durability claim |
| failure/recovery | lost commit/ack, restart, POST timeout, encryption/upload failure preserve intent; ordinary verify from uncertain rejected |
| scope | no second POST/retry/refresh/delete/merge; GET-only reconciliation; no public private-data/error echo |

Synthetic design assertions check that these requirements remain written. They
cannot prove cryptographic validation, human authority, settings, encryption or
shared durability. Implement verifier, authenticated grant, permanent namespace,
approved private ciphertext store and runtime fault tests in focused reviewed
PRs. Only after those, named release/deployment approval, immutable pins, exact
private payload/risk/run approval and protected human gate may live creation be
considered. This document supplies none of those approvals.
