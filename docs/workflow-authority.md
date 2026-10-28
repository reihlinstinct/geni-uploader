# Workflow authority: current paths and unreleased target (#264)

28 October 2026. Documentation reconciliation only. No workflow, actor condition,
environment, permission, secret, schedule, deployment or account state changes.
No legal conclusion is implied. Geni and GitHub terms still apply. This document
is not consent, a run request, OAuth authorization or exact payload approval.

## Current checked-in paths

- `geni-upload.yml`: manual workflow_dispatch. Both actor and triggering actor
  must be the personal `reihl` account. That restriction remains in force for
  source upload and existing-source details modes; agents do not invoke or
  schedule this write workflow. The private data manifest is data, not authority.
- `token-probe.yml`: personal actor and triggering actor, master only, protected
  token-probe environment and explicit TEST input. It is not a creation path.
- `secondary-readonly-evidence.yml`: a narrow read-only path.
  Manual workflow_dispatch, master only, assistant actor and triggering actor,
  attempt one, explicit READ_ONLY input and secondary-readonly-evidence
  environment. Its implementation bounds GET-only requests and encrypted output,
  without create, upload, refresh, retry or fallback to a primary credential.
- `publish-image.yml`: image building is separate from contacting Geni. Its own
  actor conditions do not authorize an API operation, deployment or write run.

These are checked-in conditions, not proof that effective protected environment
settings or secrets are currently correct. Before an authorized run, verify the
exact workflow/code and effective settings, required human reviewer, no self-review,
no admin bypass, branch policy and exact run approval. A successful prior run is
not reusable consent. No live settings audit was performed by this docs change.
OAuth authorization remains a human browser step, outside the read-only exception.

## Target, not production readiness

The future profile-creation design may use a public runner and a separate
protected human approval job, with independently authenticated immutable private
owner/payload/run approval, exact reviewed code/artifact/data pins and permanent
single-use consumption. See [intent storage decisions](intent-storage-decisions.md)
and [service authentication design](intent-service-auth-design.md). A protected
human environment review alone is not exact private payload approval. Workload
identity is not owner consent; a run's actor is not automatically the owner.

The record-creation provenance, trusted approval evidence reader, immutable
workflow-content binding, job/attempt correlation, effective rules/freshness and
rule-change handling, production storage/executor and live adapter release remain
separate gates. Offline models and synthetic tests do not close those gates.
Production creation remains closed. Do not reinterpret the read-only exception,
engineering/merge approval or this design as permission to dispatch a write.
The human approves each exact live operation separately under the current policy;
this document does not decide who may trigger any future unreleased write path.
