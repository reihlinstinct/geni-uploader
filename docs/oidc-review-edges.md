# OIDC review edge regressions

Issue #324. Invalid `x5t` values and a lone reusable-workflow identity pin now
have isolated negative tests. Both `job_workflow_ref` and `job_workflow_sha` must
be configured together; token-provided workflow claims do not fill missing pins.
The undocumented `ref_protected` informational entry is removed rather than
assuming its source/type. Tokens containing it reject until supported scope is
reviewed. This does not weaken any required pin or change deployment/settings.
