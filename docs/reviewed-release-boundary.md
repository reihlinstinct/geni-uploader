# Deployment-owned config boundary candidate (#304)

No deployment binding, secret, production route or authority is created. The
future reviewed Worker entrypoint calls bindReviewedRelease with its platform
env, never request JSON. It captures canonical exact config bytes plus SHA256 and
a fixed credential binding once; exposes frozen fetchApproval/persistEvidence
methods with NO caller source/storagePins/config parameters. Request exact pins
must match captured owner/payload/service/policy/artifact/run. Approval and writer
must use same configured private numeric repository/name; paths distinct.

This closes caller override at the wrapper API, not authenticity of the binding
itself. A caller executing arbitrary JS can fabricate env and a matching hash.
Only a reviewed deployed entrypoint and audited config binding can supply that
provenance. The hash is consistency, not a signature. Existing exported low-level
modules remain candidates and MUST NOT be called directly by a future request
handler. Missing binding blocks. No real private config appears in this repo.
No new production toggle or release authority; production_enabled stays false.
Actual service config/credential scope and versioned approval adapter remain open.

23mockedHTTP tests;9individual guard mutants executed/killed cover fingerprint,
canonical JSON, same destination ID/owner/repo, path distinction, expected pins,
run and false production state. Future entrypoint isolation/authentication and
reviewed code/binding audit are not established by those tests.
