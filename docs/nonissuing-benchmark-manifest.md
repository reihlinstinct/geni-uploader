# Dormant non-issuing benchmark manifest boundary (#435)

`validateNonissuingBenchmarkManifest` checks only a closed JSON shape, returns a
snapshot, and always reports executable/approval/provider verification false.
It cannot install, call a provider, authenticate evidence, approve an action,
check current time, prove Free eligibility, or turn on the father release gate.
No caller should use its return as authorization. Hash fields are pins to future
private evidence, not evidence verified by this function.

The accepted preparation shape requires exact source/bundle/module/review/CI
hashes, account ID, fixed compatibility settings, short evidence interval,
Free assertion and SQLite backend, distinct synthetic `ZZ-benchmark-*` scripts,
synthetic class, zero cost and no public exposure. All real effects and output
IDs are forbidden. Unknown/missing keys reject with a value-free error.

The fixed one-request, zero-subrequest profile is ONLY a future no-network
microbenchmark, not the full issuer. No source collection, real signature,
reservation of an existing namespace, OAuth change, deletion, upgrade or live
Geni operation fits it. A whole-issuer/provider-CPU benchmark needs a separate
reviewed schema and exact package when composition exists. Local wall timing,
Miniflare timing and successful CI are not provider CPU evidence.

This is one boundary component of the preparation package, not a completed
installer, harness, approval manifest or deployable benchmark. The pending
provider outputs are null only at this shape-preparation stage. An installer
must generate and record actual versions/namespace; a separate installed-state
audit must verify them. Those outputs must never be filled into this preflight
shape and treated as release approval.

Still required before an approval request: exact reviewed closed bundle and
synthetic workload, authenticated account-plan/capacity evidence, no-exposure
invocation mechanism, complete create/update method counts and bootstrap
custody/removal, provider CPU observation route, private retention/readback,
rollback/revocation, expiry evaluation and an independent installation audit.
All remain blocked until separately implemented and reviewed. No real key,
resource or provider call is added by this slice.

Tests remove every leaf, add unknown fields at every object level and mutate
plan, expiry, source, target, measurement, public exposure, all effects and all
provider outputs. They also verify the checked snapshot does not alias input.
