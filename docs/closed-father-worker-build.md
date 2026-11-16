# Fixed offline closed Worker build (#390)

The build module has no caller-controlled options/entrypoint/plugins/defines. It
bundles only the father service with esbuild 0.28.2, workerd/browser resolution,
ES2022 and external node:crypto. Deployment metadata records compatibility date
2026-10-01/nodejs_compat; the recipe does not configure a deployed service. The
unconditional rejecting gate must match exact shipped bytes before the build and
its rejection text must remain in the output. No test gate replacement exists.

Verify clean tracked imported source, exact package/lockfile versions, regular
bounded input files, exact checked-in expected module list (with inventory digest) and network-import audit and one bounded output. Return bytes,
source/bundle/lockfile/input digests privately in memory. No file upload, wrangler
invocation, account access, active workflow, key creation or Geni call occurs.
The package builder can consume these bundle bytes and digest after review.

This is reproducible build consistency, not complete supply-chain attestation.
Installed dependency bytes are inventoried, not independently proven genuine by
a version string or lockfile. A separately reviewed installer must use npm ci
with the pinned lockfile, audit expected dependency digests, pin toolchain/runtime
and confirm source signature/exact-head review/CI. It must not use a mutable
working tree or accept arbitrary build plugins. Actual uploaded deployed bytes,
config, namespace and public key still require verification under approval.

Runtime fetch calls remain in the bundle by design; the audit rejects network
imports, not runtime network calls.

Tests compare two bundles byte-for-byte and reject gate, exact esbuild/jose
package/lock entries and module-list mutations in temporary committed copies.
The tests never mutate the actual tracked source in place; no live deployment or resource is touched. A
matching bundle digest is not user approval and cannot open the shipped gate.
