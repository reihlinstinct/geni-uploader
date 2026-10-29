# Worker approval content port (#411)

Dormant, pure content checks only. No route, authenticated caller, key, issuer
composition or execution permit. The full v2 record shape, pins, source roles,
exclusions, strict types, time window and exact expectation checks are ported.
The check result retains every false provenance/permission flag and matches the
Python canonical record hash. Raw record/expected inputs are bounded at 64KiB.
Integer JSON tokens must be integer notation, not float/exponent notation, so
JavaScript parsing cannot silently accept Python-rejected numeric types. This
narrows wire inputs; it is not a general-purpose JSON parser or authenticator.
The caller supplies current time; this module does not prove that clock trusted.

Synthetic differential corpus is evaluated by the existing Python validator and
inside real workerd, bundled with only the pure Worker module and no Node
compatibility. The test harness uses Node/Python locally; the production bundle
does not. Corpus covers all record/pin/source fields, strict bool/int rules,
role separation, exact expected pins, unknown/missing fields and time/boundary
values. A content-consistent record does not authenticate its sender, prove
human approval/review/revocation, or permit a POST.

## CPU profiling plan, not a production performance claim

1. Complete the closed issuer bundle, v2 validator, JWT/JWKS verification,
   bounded capture transport, SQLite wrapper, WebCrypto signer and handoff.
2. Profile each cold and warm valid/invalid maximum-size path in workerd with
   fixed synthetic fixtures and explicit bundle/runtime digests. Profile whole
   phases and combined request path, not just individual crypto primitives.
3. Record CPU profile, memory/body limits, total subrequests including redirects,
   error paths and rejected large evidence. Local wall time and a fast unit test
   do not establish provider CPU or the account's actual Free eligibility.
4. Only after separate exact approval of a non-issuing benchmark deployment,
   measure provider CPU for the exact bundle on a verified Free account. Include
   cold starts and maximum accepted evidence; require margin below 10ms.
5. If it does not fit, stop activation. Optimize or revise with review. No paid
   fallback, budget change, upgrade or automatic weakening/splitting of checks.

No benchmark deployment or Cloudflare action is approved by this plan. The port
alone is not the issuer and cannot prove the full issuer fits Workers Free.

## Reviewer account assurance (#415)

The selected one-approval ceremony is GitHub account approval plus account2FA,
not proof of interactive human presence. Preserve all fixed reviewer/User/id,
exact-run, no-self-review and no-admin-bypass pins. No automation may hold or use
the reviewer's PAT/OAuth/session for this ceremony. No extra challenge is added.
See [github-reviewer-account-assurance.md](github-reviewer-account-assurance.md)
for token attribution, review-payload limits and the remaining assurance boundary.
