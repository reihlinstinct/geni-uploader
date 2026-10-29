# Intent approval and ciphertext storage decisions

28 October 2026. Design direction only, follows #247/#251/#233/#236. No service,
job, secret, key, repository setting, deployment or live operation is created.
Code merge does not select a released executor or authorize a real run.

## Decision 1: protected job, immutable private approval record

Use the public tool repository's standard GitHub-hosted runner for the eventual
executor. Require a separate protected human approval job and an immutable exact
private approval record. Do not create a new approval signing key/service for
this first release. A verified OIDC workload identifies the job, not owner
consent. The service must independently verify exact owner/payload/risk/run
approval provenance and effective required reviewer/no-self-review/no-bypass
settings. No token, environment name, approval flag or Git hash is sufficient.

Bind the approval record to owner/connection, exact payload/graph/data hashes,
reviewed code/workflow/artifact/service/policy pins, run ID/attempt, nonce,
expiry, encryption recipient and excluded actions. Original owner approval
remains a trusted private source; a job's actor is not automatically that owner.
The authenticated record-creation/review mechanism is NOT implemented here and
remains a release blocker. No automatic interpretation of chat approval phrases.
No exact-run approval, protected environment review or release decision is waived.

## Decision 2: bounded ciphertext in existing private data storage

Store encrypted evidence blobs in the existing PRIVATE data repository, no
private-repository Actions job. No public artifacts, even for encrypted output.
No new object-store account, R2 bucket, paid plan or spending. Never link/name the
private storage repository in public issue/PR text. This document uses no private
paths, repository identifiers, approval references, personal values or keys.

Candidate hard cap: 1 MiB ciphertext per object and 8 MiB cumulative ciphertext
per exact operation, checked before any upload. These conservative design caps
need release validation with actual schema/encryption overhead; never truncate
evidence to fit or quietly raise the cap. Oversize pre-write evidence blocks
POST. Oversize post-write evidence means consumed/uncertain with no replay.
Upload failure cannot erase permanent consumption. No plaintext fallback.

Each approved ciphertext object must have exact digest/byte length/recipient,
schema/stage, immutable Git blob ID and commit hash plus authenticated
owner/operation/run provenance. Read back the remote blob and verify digest,
bytes and exact private commit before claiming durable evidence. Never infer
content from upload success, filename, status pointer or response metadata alone.
No raw family data, credentials or private key in public logs/artifacts/URLs.
Private status holds created IDs, verified vendor URLs and stage/evidence refs
under #244, not a public result summary. Raw values are not authority.

Git history makes retention/deletion harder and grows storage; cap the evidence
and document the private retention/backup policy before release. Repository
administrator rewrite/deletion, compromised writer credentials and loss of keys
remain trust limits. Writer access must be narrowly scoped and separately
audited; this design does not expose a new token or pick an authentication route.
No force-push, rewritten consumed history or control reset for recovery.

## Permanent intent is independent

Permanent owner-global consumption belongs in the separately approved shared
Durable Object state, not in artifacts or Git evidence retention alone. The
existing DO class remains a candidate without routing/authentication deployment.
Expiry, deleted evidence, changed connection/plan, new run, backend version or
fresh token never clears intent. Storage ambiguity requires read-only inspection,
not a second POST. No retry, refresh, delete, merge, unlink or automatic rollback.
Verified workload identity and stored ciphertext still do not authorize creation.

## Free-only execution boundary and tradeoffs

Official sources inspected 28 October 2026:

- https://docs.github.com/en/actions/administering-github-actions/usage-limits-billing-and-administration
  says standard GitHub-hosted public repository runners are free; private
  repositories have included compute/storage quotas and excess may be billed.
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
  says artifacts require repository read access and expire (default 90 days).
  Public ciphertext artifacts are therefore not a private durable store.
- https://developers.cloudflare.com/r2/pricing/ lists a Standard free allowance,
  with billable overages. Free allowance is not a hard no-spending guarantee.

Private quota constraints apply to private Actions, so do not schedule this
executor there. Git evidence upload needs no private Actions run. Audit actual
account permissions/storage/plan limits before deployment; do not claim every
Git operation has unlimited free capacity. A limit or unavailable free path means
STOP and ask, never enroll billing or silently switch to public artifacts.
R2 is deferred unless a separately reviewed free-only hard cutoff is established.

## Remaining release work

Authenticated exact approval-record creation/review, live issuer/subject and
claim shape verification, reviewed private writer access, approved permanent DO
namespace/authentication, ciphertext serialization/retention/remote verification,
actual one-shot secondary HTTP adapter, readback/reconciliation, #244 provenance,
protected environment audit, immutable release pins and named release approval.
Then exact private father payload/risk/run approval and protected human gate.
This record supplies none of these permissions or deployed capabilities.
