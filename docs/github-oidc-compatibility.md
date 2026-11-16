# GitHub OIDC documented claim compatibility

Issue #321. The strict synthetic JWT shape rejected documented real GitHub
headers and informational claims. This patch accepts only the documented `x5t`
header addition and bounded scalar informational fields. It retains duplicate
key rejection, pinned RS256 key/issuer/audience, exact required repository,
owner ID, actor, workflow/ref/SHA, environment, event, run and attempt checks,
all existing time bounds, and workload-only output with no owner approval.

Reusable workflow identity is not informational. If a token includes
`job_workflow_ref` or `job_workflow_sha`, both must have explicit reviewed pins.
Missing, extra or mismatched reusable-workflow claims reject. Informational
claims cannot replace a required identity pin. Unknown non-documented claims
reject. Documented repository custom properties are accepted as bounded strings
but never used as authority.

The exact subject is still supplied by reviewed release configuration. The
repository's live read-only OIDC customization API reports default immutable
subject mode and an ID-bearing prefix. Do not build a release subject using the
older name-only convention. Environment jobs use the documented environment
suffix with percent encoding of colons. No settings, dispatch, permission or
OIDC token request is made by this patch. Actual emitted workload compatibility
still needs a separately approved run; tests use synthetic signed tokens with
the official documented shape and invented IDs.

The published example's historical time window or omitted required workflow
pins do not waive this service's stricter time and identity requirements. Those
remain fail-closed. Any actual-token mismatch needs explicit investigation,
not a blind removal of checks.

Sources inspected 2026-10-29:
- https://docs.github.com/en/actions/concepts/security/openid-connect
- https://docs.github.com/en/actions/reference/security/oidc
