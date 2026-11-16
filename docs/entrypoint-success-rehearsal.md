# Protected entrypoint success rehearsal (#358)

Follow-up to the entrypoint review: the actual callable entrypoint now has a
synthetic success-path test. It invokes the fixed real Python collector as a
subprocess, reads its exclusive private v2 approval file, requests one synthetic
OIDC response and runs the actual journaled runner/private Git writers/age
ciphertext persistence. The test then inspects the completed private journal and
proves a repeated invocation stops without another token or create request.

A temporary test-only Python startup hook replaces urllib responses for the
collector, checking exact GET URLs; the production collector itself is not
replaced. Node HTTP responses are mocked. Both encrypted stages use real age.
No real credential, identity, token request, vendor call or deployment is used.
The shared synthetic runner fixture now accepts the fixture's expected workload
token instead of a hardcoded value, so the test exercises token handoff too.

This covers the previously missing entrypoint success branch, not hosted runner
configuration, real emitted token claims, collector transport deployment or any
live authority. Existing authenticated Worker/SQLite joined tests cover the
service separately. All release and persistent-private-storage requirements
remain. CI extends the existing pinned-age step, no permission changes.
