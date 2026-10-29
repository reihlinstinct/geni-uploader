# Protected run workflow draft (#348)

The adjacent YAML is review-only outside `.github/workflows`. It is not installed
and adds no effective permission. It names the existing single protected job gate,
master only, attempt one, no cancel-in-progress, empty workflow permissions and
job-scoped contents read/OIDC token issuance. The first step always fails. There
are no secrets, usable service endpoints, dispatch, credential actions or deploy.
The OIDC permission is a code proposal, not an instruction to enable it now.

Before installation: separate exact release approval, immutable checked-out source
and artifact, verified service/namespace/config/credential binding, fixed audience
and actual emitted token compatibility, private persistent journal provisioning,
collector/runner CLI composition and approved exact payload/risk. Replace the
intentional failure only in a separately reviewed release change. A merge of this
draft is neither permission nor readiness to install or run it.

The existing service capture requires exactly one gated job total, whose name
binds plan, risk, run and attempt. Do not add a prep job without reviewing that
contract. GitHub environment approval happens before this job issues a token.
The reviewer and dispatcher remain distinct IDs under the accepted one-human
ceremony. Workflow YAML cannot prove historical protections or independent review.
Do not place private payload fields into workflow inputs, job names or logs.

This draft intentionally does not include a checkout action without an observed,
reviewed immutable pin, nor a pretend working command for an unfinished CLI.
No claim is made that the draft can execute the create. YAML parse and contract
checks cover the closed scaffold only. Operational release remains blocked.
