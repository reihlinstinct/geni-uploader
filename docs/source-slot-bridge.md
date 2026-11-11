# Fixed-slot source credential bridge

Design for #695. A separate protected workflow copies only repository
GENI_SECONDARY_ACCESS_TOKEN to father-create GENI_ACCESS_TOKEN, encrypted
with the destination environment public key inside the GitHub runner.
No Geni calls, OAuth, primary-slot writes, dynamic targets, artifacts or
credential output. Existing connection slots and site mode stay unchanged.

Master-only, exact executor SHA, automation actor/triggering actor and first
attempt required. A fixed confirmation and the existing human deployment
approval are mandatory. The dedicated SOURCE_BRIDGE_WRITER environment secret
must permit reading environment metadata/public key and writing this environment
secret. Its installation is separate authorized setup, never a repository-secret
read. GitHub credentials cannot themselves restrict writes to one named secret;
fixed code destinations and review constrain this operation, not the token scope.

Runtime independently checks run metadata, human reviewer/master/no-bypass
protection, and absence of an environment override for the secondary source
name. A hash-only source updated_at input must match current repository secret
metadata before transfer. The source value is only supplied through Actions'
secret environment injection. It is never printed, persisted or returned.
Destination metadata is verified after one PUT. On uncertain PUT or any error,
stop without retry. Only fixed success/failure text reaches public logs.

Follow bridge with a separately approved source PLAN explicitly naming the
selected account in private communication; then inspect target identity,
listing/duplicates and safe-to-run status. Bridge success does not prove Geni
identity, upload permission or authorize an upload. No upload before its own go.
Tests cover gates, exact paths/destination, sealed-value transport, no plaintext
output and all workflow steps, including no artifact uploads or scripts with
secret interpolation. Independent review and exact-head green CI before merge.

Environment: BRIDGE_EXECUTOR_SHA binds exact master code; BRIDGE_CONFIRM is
COPY_SECONDARY_TO_SOURCE_ENV. BRIDGE_SOURCE_UPDATED_AT pins only source-secret
metadata; BRIDGE_SOURCE_VALUE is repository secret injection only, never input.
BRIDGE_WRITER is the dedicated SOURCE_BRIDGE_WRITER environment secret.
GITHUB_REPOSITORY/GITHUB_EVENT_NAME/GITHUB_REF/GITHUB_ACTOR/
GITHUB_TRIGGERING_ACTOR/GITHUB_RUN_ATTEMPT/GITHUB_SHA/GITHUB_RUN_ID are verified.

## Residual source and writer scope

The current secondary source is a repository secret. Any workflow on a branch
with repository-secret access can receive it without this deployment gate.
This bridge protects the destination transfer, not historical source custody.
After successful copy, propose removing the repository copy and changing the
site writer to an environment-scoped secondary secret. This is a separate
owner decision and reviewed site change, because deleting it now would break
existing secondary consumers and the site's refresh destination. Do not delete
or move it automatically. No claim of environment-only source custody is made.

The writer can affect other secrets within its GitHub permission scope. Approve
only the exact independently reviewed executor SHA, never an unreviewed branch.
Master's live protection must be checked before enabling this writer; if PR
review is not enforced, report that gap and require the owner's decision.
The sealer child receives PATH only, never writer/source environment variables.
Destination metadata is read before PUT (404 is allowed) and must have a changed
updated_at after it. This proves metadata changed, not plaintext equality;
GitHub secrets are unreadable and the next identity plan remains required.

Master live check: strict test/coverage checks and enforce_admins=true, but
required_pull_request_reviews is null by the owner's standing policy. Do not
change it here. The gate is independent exact-head review plus the owner's
deployment approval of that exact reviewed SHA. SOURCE_BRIDGE_WRITER remains
uninstalled until separate owner go. Repository-secondary custody migration
is deferred to a separate reviewed change and must not delay or be silently
bundled into this fixed copy. Node22.23.0 and npm10.9.8 are checked exactly;
setup-node v7.1.0 is pinned to949feb2413d6458794dcd2491c4babbbce0c15c1;
the npm package lock is pinned. The action runtime is Node24; the selected
project runtime remains exactly Node22.23.0.
