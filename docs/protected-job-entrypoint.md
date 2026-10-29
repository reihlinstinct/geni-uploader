# Dormant collector/token/job entrypoint (#353)

`runProtectedJobEntrypoint` is a callable Node function, not an installed workflow
or auto-executing CLI. It validates the fixed run/context, reads a bounded 0600
prewrite file from a 0700 private directory, invokes the existing fixed Python
collector (exclusive private approval file), acquires one workload token and
passes captured approval/prewrite bytes to the journaled runner. The collector
script and cwd are fixed, with no shell. Failure does not retry any step. Original
private files remain for inspection, no plaintext gets printed or returned.

The token acquisition helper accepts only the platform-provided request URL at a
deployment-pinned HTTPS origin with a fixed audience and bearer request token.
It refuses an existing audience override, redirects, link pagination, oversized
body, malformed/duplicate-key response and non-JWT shape. Timeout is ten seconds,
no retry. The workload token stays in memory; signature and exact identity are
verified by the service, not this shape check. Matching an origin/hash cannot
prove correct deployment provisioning. Actual request origin and emitted claims
must be inspected under a separately approved workflow before release.

Ten synthetic tests cover valid fixed token request, tampered request context,
malformed/duplicate response and invalid entrypoint config. The real Python
collector has its existing independent tests; this PR does not claim a full
collector subprocess + hosted OIDC integration, or an operational deployment.
The protected workflow draft still stops at its intentional first-step failure.
Persistent private journal backing, exact config/namespace/credential proof,
pre-upload reservation, unknown-outcome reconciliation and separate release/run
approval remain required. No live token request, credential action, effective
workflow permission, dispatch, configuration change or deployment is performed.
