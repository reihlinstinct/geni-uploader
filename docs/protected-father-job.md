# Protected father job capture and v2 private admission

Part of the integration work in #313. This is not an installed workflow or a
release. The existing proposal still stops unconditionally.

`protected_father_job.collect_from_environment` is an actual fixed-HTTPS GET
collector, not a supplied-response parser. It reads a canonical hash-pinned
configuration and read credential only from the job environment, checks the
runtime run/attempt/SHA/ref/repository/actor and v2 record pins, and fetches the
run, current environment rules, approval history and branch policy. Redirects,
pagination and oversized responses are rejected; there is no retry.

It also fetches attempt-one jobs and requires exactly one job, currently running,
whose name shows the exact static plan fingerprint, risk hash, run ID and attempt.
The collector recomputes that fingerprint from the v2 record static pins,
exclusions, expected human identity, fixed agent sources, risk and revocation.
Only dynamic run/time and the human action capture are excluded. The older
`parent_envelope.envelope_hash` belongs to the all-proofs path, so it is not
silently reused for this distinct risk-accepted one-father ceremony. It rechecks
current environment protections and branch policy after collection. The sole
human decision source is derived from the actual captured review response; the
record preserves its configured agent dispatch and independent review sources.
The collector does not authenticate those independent review source records or
prove the installed workflow content. These remain explicit release gaps.

The collector writes the resulting v2 record to one new mode-0600 local file
using exclusive creation and fsync. It does not upload a file, change a ref,
install permissions, dispatch, deploy or call Geni. Its returned capture metadata
is private too. No raw response or record is printed. Configuration hash equality
is consistency, not deployment provenance. Current repeated rule snapshots do
not eliminate historical protection TOCTOU, and the review API still lacks a
human approval timestamp and job ID. The shared application identity limit and
one-human assurance remain unchanged.

`admitSingleHumanApproval` now joins the existing module-owned immutable private
Git receipt to the v2 record contract. It checks the exact expected record,
expiry, all source roles, same sole human, distinct agent identities and review
source references, exclusions, risk/revocation pins and immutable byte equality.
It does not turn a private Git receipt or matching record into permission. Its
owner-approval, human-action and POST flags remain false. The old v1 function is
kept separate and cannot silently satisfy v2 admission.

The private admission and ciphertext writer now use manual redirect handling,
required by workerd, while rejecting every non-success status and redirected
response. No production caller or deployment is installed here. Encryption,
remote write, authenticated independent review, live claim compatibility and
end-to-end service composition still need their joined rehearsal and release.
