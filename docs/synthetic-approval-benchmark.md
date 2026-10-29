# Closed synthetic approval microbenchmark (#439)

Dormant, no-network and non-issuing. The `ZZApprovalBenchmark.run()` internal
Worker entrypoint takes no arguments and runs the real content validator on
one fixed synthetic JSON record at a fixed synthetic time. It returns only a
synthetic hash and false authority/CPU/release flags. Repeated calls are safe
because there is no signature, grant, storage, reservation or vendor call.
Public fetch denies every method/path. No real payload, environment input or
runtime binding is consumed. This is not an issuer or an authenticated route.
A service binding capable of invoking it is an admin-controlled capability;
no production binding, dispatcher or installation is supplied here.

The local builder uses pinned esbuild, checks tracked source against HEAD,
refuses symlinks, and verifies the exact three-module import inventory and only
`cloudflare:workers` as an external edge. It returns bytes and hashes in memory.
It never invokes wrangler, writes an account or deploys. Source, builder, package,
lockfile, module and bundle hashes plus compatibility settings are recorded;
none constitutes independent review, owner approval or installed readback.

Local workerd RPC tests exercise actual internal entrypoint dispatch, reject
argument-bearing calls, check deterministic output and deny public ingress.
Package mutation tests cover dirty source, extra imports, fixture and compiler
changes. Local timing is diagnostic only. No claim of provider CPU measurement,
Free eligibility, entire issuer capacity or complete action-manifest readiness.
The complete future issuer requires a separate exact-workload benchmark.

Before any provider action: approved installer manifest with actual scope and
counts, current account/product/quota evidence, reviewed no-public-ingress
invocation method, exact version correlation/CPU observation and independent
source/settings readback. Those remain missing. No resource/key/credential,
route/domain, namespace or deployment is created by this component.

Tests also pin literal reviewed module/bundle/content hashes, not only repeat-build
comparison. An intentional source or compiler change requires a reviewed pin
update. A valid altered fixture changes its known hash and fails comparison
against the fixed expected fixture. These are regression pins, not authority.
