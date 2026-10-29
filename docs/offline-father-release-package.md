# Deterministic offline package (#388)

The offline Python builder accepts a checked-out signed source head, exact private
manifest, supplied reviewed Worker bundle and a new local output path. It checks
source HEAD consistency and rejects dirty included source, symlinks/oversize
inputs, active workflow installation, dispatch, Geni calls, nonzero cost, unknown
fields and missing phase-required pins. Bundle bytes must match their manifest
SHA256. The deterministic uncompressed tar uses sorted entries, fixed metadata
and SHA256 inventory. Inspection hashes members without extracting them.

Included files are tracked root Python modules, production Node modules, Node
package/lockfile, Python project dependency metadata, review-only workflow draft,
reviewed bundle and private manifest/inventory. No node_modules, credentials,
private receipt, .git or active .github/workflows path is included. The archive is
PRIVATE because its manifest contains operational metadata. Never upload it to a
public issue, PR, release or artifact. The builder is a library, not a deploy or
installer CLI. It performs no network, key generation or account mutation.

## Separate exact actions

A closed_provisioning manifest requires fixed chosen Worker/namespace-class and
private issuer repository/workflow names, reviewed source/workflow/bundle hashes,
free_only:true/max_cost_usd:0, and exactly the listed closed provisioning actions.
New namespace/repository IDs and public key are explicitly null because creation
has not occurred, NOT guessed placeholders. The exact key generation method is
named; creation itself remains unapproved. This is a proposal phase, not proof
that chosen names are available, free capacity exists or actions were authorized.

A verified_release_candidate manifest rejects absent namespace/repository IDs,
requires a canonical Ed25519 SPKI/public-key digest, and permits only inspection.
It does not provision, install a workflow, issue a grant, dispatch a probe or
create a profile. Actual account/scope/config/version/protection verification,
current compatibility observations, owner approval and independent review remain
outside this offline consistency check. No schema field substitutes for them.

No exact operational manifest is supplied by this PR. Exact private values and
cost/scopes must be grounded before an approval proposal. A package inventory or
matching digest proves consistency, not code safety, signature/review provenance,
completeness of dependencies or installed-code authenticity. The supplied bundle
must be produced by the separately reviewed build recipe; this packager cannot
prove that an arbitrary matching bundle actually implements the source. A later
installable workflow/issuer package still needs pinned tooling, credentials,
private inputs, durable handoff and exact installation actions. Nothing here
opens the shipped rejecting gate or turns a merge into a deployment.

## Review guard regressions (#392-#395)

Runtime fixture code is explicitly excluded from archive selection. The Geni-call
count must be the integer `0`, never boolean `False`. Missing required manifest,
inventory or bundle members produce the fixed ValueError before indexing.
Tests reject top-level unknown fields and symlink archive members without
extracting anything. These checks remain offline consistency checks, not install
or dispatch authority.

Manifest schema version also requires exact integer `1`, never boolean `True` (#401).
