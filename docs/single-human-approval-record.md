# Version2 single-human assurance content (#307)

Design chosen29October2026: designated agent dispatches a protected workflow;
ONE human owner personally approves the required-reviewer environment action
showing the exact payload fingerprint, run and risk pins;
independent agent reviews exact code head. It is weaker than two humans. No
additional person is invented and agent GitHub User-type accounts do not count.

`single_human_approval_record.validate/check` is pure CONTENT only, not that
ceremony's writer. Existing approval_record v1 is unchanged and not broadened.
V2 has explicit assurance and human_count1, exact existing pins/exclusions,
risk_hash and revocation_epoch, reviewed executor SHA and3distinct source refs.
Owner grant and protected review bind the SAME approval source/content hash.
Roles and source kinds are separate: owner_grant/protected_environment_exact_payload_approval,
protected_review/protected_environment_human_action share the sole HUMAN
principal; dispatch/designated_agent_workflow_dispatch must differ; code_review/
independent_agent_exact_head_review must differ from owner and dispatcher.
An iMessage fingerprint copy is convenience only, NEVER part of authentication.
Numeric principal IDs are supplied opaque content, not authenticated identities.
Independent agent identities need a verified registration before use, not a
fabricated GitHub account. All real identifiers/source refs remain private.

Exact source/payload/risk content hashes and revocation epoch must match future
module-owned config and authenticated source capture. Neither a hash, comment,
actor identity, app-authored action, private blob nor successful schema check
proves human approval. No automatic parsing of chat words, no two-human upgrade.
Residual chosen assurance limit: an app can act as the owner GitHub identity;
numeric identity alone cannot distinguish app from human click. The approved
ceremony relies on the owner personally operating the protected environment
approval UI. No claim of cryptographically human-only provenance is made. Protected job/run/attempt/reviewer provenance and revocation retrieval
remain unresolved release blockers. Current v2 check returns all owner/action/
dispatch/review/revocation/POST/production flags FALSE and two_humans_verifiedfalse.
It never writes a private record, dispatches, deploys or calls Geni.

46synthetic tests and16individual mutants run/killed cover assurance/human count,
production flag, same-owner reviewer, distinct dispatcher/independent agent,
distinct source refs, same exact owner/review action+content, kind, exact
expectation, time, reviewed head and revocation.
Every pin mismatch rejects. These content tests do not establish live provenance.

## Remaining bound isolation (#310)

Six further individual guard mutants executed/killed: revocation epoch upper
bound, leading-zero principal IDs while role relations still agree, unknown
fields inside each source, None-as-false production flag, uppercase SHA/hash
pins with matching expected/review head, and float now inside the valid window.
59focused tests pass. Test/docs only; v1/v2 semantics unchanged.
