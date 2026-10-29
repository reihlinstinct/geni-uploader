# Version2 single-human assurance content (#307)

Design chosen29October2026: ONE human owner approves exact payload fingerprint
in their trusted conversation; designated agent dispatches a protected workflow;
the same owner personally approves the required-reviewer environment action;
independent agent reviews exact code head. It is weaker than two humans. No
additional person is invented and agent GitHub User-type accounts do not count.

`single_human_approval_record.validate/check` is pure CONTENT only, not that
ceremony's writer. Existing approval_record v1 is unchanged and not broadened.
V2 has explicit assurance and human_count1, exact existing pins/exclusions,
risk_hash and revocation_epoch, reviewed executor SHA and4distinct source refs.
Roles and source kinds are separate: owner_grant/trusted_owner_conversation,
protected_review/protected_environment_human_action share the sole HUMAN
principal; dispatch/designated_agent_workflow_dispatch must differ; code_review/
independent_agent_exact_head_review must differ from owner and dispatcher.
Numeric principal IDs are supplied opaque content, not authenticated identities.
Independent agent identities need a verified registration before use, not a
fabricated GitHub account. All real identifiers/source refs remain private.

Exact source/payload/risk content hashes and revocation epoch must match future
module-owned config and authenticated source capture. Neither a hash, comment,
actor identity, app-authored action, private blob nor successful schema check
proves human approval. No automatic parsing of chat words, no two-human upgrade.
An app can act as the owner GitHub identity; identity alone cannot prove a human
click. Protected job/run/attempt/reviewer provenance and revocation retrieval
remain unresolved release blockers. Current v2 check returns all owner/action/
dispatch/review/revocation/POST/production flags FALSE and two_humans_verifiedfalse.
It never writes a private record, dispatches, deploys or calls Geni.

44synthetic tests and14individual mutants run/killed cover assurance/human count,
production flag, same-owner reviewer, distinct dispatcher/independent agent,
distinct source refs, kind, exact expectation, time, reviewed head and revocation.
Every pin mismatch rejects. These content tests do not establish live provenance.
