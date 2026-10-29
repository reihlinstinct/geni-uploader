# Dormant credential custody content policy (#473)

Candidate implementation of the expiry/revocation checks required by #453.
Not connected to worker.mjs, a secret writer, a runner or a Geni transport. It
checks content consistency and freshness, never authenticates a source or grants
permission. Current deployed/raw-token consumers are NOT changed or protected
by this module. Do not describe token expiry/revocation as installed yet.

Bundle: schema, fixed secondary slot/owner/numeric repository/environment/secret,
connection ID, generation, external revocation epoch, issue/provider/local expiry,
access and refresh token. All schemas are exact. Transport accepts compact JSON
whose JSON.stringify round-trip is byte-equal, rejecting duplicate keys and
noncanonical/unsafe-number encodings. Public failures are fixed and value-free.
Returned descriptors contain no credential and say authenticated:false and
write_permitted:false. They must never become bearer permits or signed grants.

Policy binds fixed destination, immutable executor/workflow SHA, run/attempt1,
maximum lifetime and approval expiry. Candidate maximum is at most900seconds,
not a rollout choice or native GitHub Secret TTL. Earliest credential/provider/
approval expiry wins with no grace. Provider expiry is mandatory; a future
integration must define safe provider missing-expiry behavior, not invent it.
Policy also requires matching externally supplied generation/revocation epoch,
connection event and revoked:false. Historical/monotonic truth of that state
requires separately authenticated durable custody; this pure module cannot
prove it. No client-supplied state or callback truth flag may fill that gap.

recheckCustodyAfterWait snapshots input strings, checks before waiting, then
checks fresh state/time after the await and rejects any changed state. It never
refreshes a credential, retries, dispatches or returns a token. The dependency
reader is a fake-only seam here. Before an actual consumer uses a credential,
trusted custody/authority and atomic use/revocation semantics still need review;
no async content check alone prevents a race after its return.

53synthetic tests cover exact schemas, destination/owner/source/run mismatches,
clock/expiry edges, wrong generation/revocation, duplicates/unsafe numbers,
revocation/rotation/expiry during wait, immutable input, no retry and sentinel
non-disclosure. No real credentials, settings, callback or deployment involved.

Environment-secret adapter research is #475, deliberately separate. Official
contract verified2026-10-29:
https://docs.github.com/en/rest/actions/secrets#get-an-environment-public-key
GET /repos/{owner}/{repo}/environments/{environment_name}/secrets/public-key;
PUT/DELETE sibling /secrets/{secret_name}. Fine-grained permissions use repository
Environments read/write, not assumed repo Secrets permission. Existing worker's
repository-secret route is not silently migrated. Rollout still needs exact
scope/custody/expiry/revocation/audience/rollback and account-capacity approval.
