# Father service integration checkpoint

Unreleased, local-only route. No deployment or live profile creation.

## Joined path

`father-intent-service.mjs` joins the fixed GitHub issuer JWKS verifier to the
canonical owner Durable Object and the existing permanent consume transaction.
The Worker takes its owner, connection and fingerprint pins from deployment
configuration, never from the HTTP body. The body supplies only the workload
token and a plan hash to compare. The namespace name depends only on owner, not
run, connection or plan. The service exports no reset, transition or vendor POST.
Production stays closed. The explicit local-only rehearsal setting is required;
it is not a release switch and supplies no owner approval.

A local workerd test bundles the actual route, imports a signed synthetic JWT,
serves a synthetic JWKS at the fixed issuer URL, concurrently consumes against a
real SQLite Durable Object, restarts workerd with the same storage and proves
consume cannot repeat. The test permits only the fixed JWKS network request.
This is not evidence of deployed namespace provenance or real GitHub claim
compatibility.

The rehearsal exposed a real integration bug: workerd rejects `redirect:error`.
The JWKS fetch now uses `manual`, with the existing strict status-200 and
not-redirected checks. Redirects are still rejected, not followed.

## Protected environment created

The repository's `father-create` environment was created on 2026-10-29 and then
read back through the API. Creation is not permission for a run or live write:

- Required reviewer: `reihl`, numeric user ID 23318984.
- Self-review forbidden; administrator bypass forbidden; wait timer zero.
- Exactly one custom deployment branch policy: branch `master`, not tags.
- The environment API returned `can_admins_bypass:false`, but that field does not
  prove effective historical administrator-bypass protection; effective enforcement
  remains a release check.
- Environment ID 25657858358; branch policy ID 64756507.
- No secrets, workflow permissions, dispatch, deploy, or release were changed.

Environment activity:
https://github.com/reihlinstinct/geni-uploader/deployments/activity_log?environments_filter=father-create

The accepted limits remain: approval history lacks timestamp and job ID, so the
planned ceremony is attempt one and one gate; the shared human/application
identity establishes one human approval, not two; protection changes between
checks remain a TOCTOU risk. Environment existence does not prove approval of
any particular payload or grant permission for a run or live write.

## Remaining create blockers

- Integrate the one-human v2 record with the private admission/writer and the
  protected job. Current private admission still expects the old v1 shape.
- Confirm real GitHub OIDC claim compatibility without discarding required pins.
- Join age encryption, immutable private evidence persistence, permanent
  intent transitions and one fixed vendor POST/readback. A successful consume
  response here expressly says `post_permitted:false`.
- Review deployment configuration, credential and cumulative storage accounting;
  configure the real owner-global namespace only under separate approval.
- Independent review and exact-head CI, then separately authorized release,
  deployment, approval ceremony and first live create.

No actual workflow or wrangler configuration is installed by this checkpoint.
