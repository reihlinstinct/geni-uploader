# Worker exact source and CI correlation (#423)

Dormant read-only evidence check. No issuer authority or independent review.
Deployment-owned hash-pinned canonical config names source SHA and exact expected
check names plus numeric App identity per check. Two exact official GitHub GETs
use one bounded transport: commit and check-runs(filter=all,per_page=100).

Require exact returned commit SHA and GitHub verification verified:true/reason:
valid. This is GitHub's attestation, not independent verification against our
pinned GPG fingerprint. Require exact count/set of checks, no duplicate names,
each exact head SHA, completed/success and pinned numeric App ID. Pagination,
extra runs and unknown config reject rather than selecting a convenient green
subset. Reruns/other checks can therefore block this narrow capture until the
reviewed expected evidence is resolved; never silently discard them.

Check names alone are insufficient: Apps can create check runs. Pinning the App
adds attribution, not proof of workflow bytes or executed code. GitHub Actions
may report check head SHA on a PR test-merge rather than reviewed source head;
that mismatch blocks here. No source/merge equivalence is inferred. Future
orchestration must explicitly resolve signed merge, exact-head CI relation,
workflow/source bundle digest and freshness before activation. The two calls
are not a whole-issuer subrequest/CPU proof and do not prevent later TOCTOU.

Independent review remains unresolved: shared GitHub identity, a PR comment,
APPROVED label or matching hash cannot establish distinct reviewing agent.
Return independent_review_verified:false, pinned_signing_key_verified:false,
merge_path_verified:false, installed_bundle_verified:false and post_permitted:
false. A distinct attributable exact-head reviewer receipt needs a separate
design; this module does not manufacture one from available account evidence.

Real-workerd synthetic tests cover each check pin, signature flags, source/head,
missing/duplicate/paginated checks, unknown config and fixed errors. Test-only
mutations remove signature/head/App/success comparisons individually; each then
accepts a hostile fixture that the original rejects. No Node compatibility in
the bundled module, no external network or production keys used.

## Official sources checked2026-10-29

- https://docs.github.com/en/rest/commits/commits
- https://docs.github.com/en/rest/checks/runs
- https://docs.github.com/en/rest/pulls/reviews
