# One-shot protected job CLI (#364)

`node oauth-bootstrap/protected-job-cli.mjs` invokes the existing protected job
entrypoint once. No arguments are accepted. URLs, files, identities and secrets
come only from its existing fixed deployment/environment contract. Success emits
one value-free JSON status saying receipt accounted and reconciliation required,
not VERIFIED. No created ID, descriptor, provider object or token appears there.
Failure emits a fixed inspection/no-replay message with exit1, never a raw stack
or exception. The CLI does not refresh credentials, dispatch or retry.

The module is import-safe: importing it does not execute the job. Synthetic bundled
subprocess tests replace only its entrypoint import to cover success, exception
privacy and argument rejection; an unmodified subprocess with no approved config
also proves fail-closed output. Existing real collector/runner tests cover that
entrypoint independently. This is executable packaging, not operational authority.
The unconditional service create gate remains closed and the workflow draft
remains uninstalled. Provisioning, actual OIDC compatibility, private persistent
storage, exact immutable config and user-approved run are still required.
