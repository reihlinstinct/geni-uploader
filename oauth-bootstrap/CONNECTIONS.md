# Fixed isolated human OAuth destinations

For #197/#189. Code only, not deployed by this PR. Uses the existing app and
/callback route: no new Geni app/callback, account, paid plan or service is
required by this design. Actual registration/selected provider route must still
be verified before the human starts. No agent executes OAuth or live API calls.

A fixed source registry defines primary, secondary and tertiary. Each destination
has its own fixed access-token and refresh-bundle GitHub secret names. The human
chooses a button before authorization. The destination is stored in one-time
server-side state bound to the authenticated GitHub subject/browser; callback
parameters cannot choose a secret name. Unknown destinations/query selectors and
replays stop. New destination registry entries require a code review/release,
not a runtime string supplied by a caller. Named slots are generic in public code;
the operator privately records which consenting owner occupies each slot.

Enabling any additional owner pin also requires PRIMARY_OWNER_NODE, and all
configured owner pins must be distinct canonical profile-N IDs. SECONDARY_OWNER_NODE
and TERTIARY_OWNER_NODE independently enable those slots. Missing secondary/tertiary
pin stops that selection. Before any secret write in a configured slot, the
human-initiated callback reads token-self from the fixed HTTPS /api/profile route
with bearer header and redirects refused. It requires exact expected ID,
merge_pending:false and no merged_into/results wrapper. Wrong or unprovable
identity stops all writes. Primary is checked too when pins are configured, so
pressing the wrong button while logged into another owner cannot overwrite it.
Legacy primary-only installations without any owner pins retain existing behavior;
that compatibility mode is not safe for multiple connections and is not permission
to deploy an additional route without the pins.

Do not guess owner pins from website GUIDs or name-only matches. Establish the
canonical nodes through authorized human-observed evidence first. Never publish
real owner IDs, access/refresh tokens, app secrets, callback codes or raw responses.
The owner GET validates identity only; it does not prove parent completeness,
private create behavior, consent or plan readiness. It must be understood as part
of the user's deliberately initiated connection, not an agent-initiated probe.

Each slot writes pending refresh bundle, matching access token and finalized
bundle only into that slot. Partial failure stops; pending recovery must be
reviewed for that exact slot. Current upload/refresh workflows still consume ONLY
primary secrets. New secondary/tertiary tokens are NOT automatically usable by
those workflows, and this PR does not wire any upload or parent creation route.
Separate reviewed human-run consumers must select the correct slot and validate
owner again before use. No sharing a primary refresh runner with an additional
slot by renaming arbitrary secrets at runtime.

Deployment needs separate chat approval after independent review/green CI, verified
expected-owner values and existing secret-writer permission scope. No secrets in
commands/URLs/logs/chat. After deployment the human opens the verified landing
page, signs into approved GitHub identity if asked, confirms correct Geni account
and selects the intended slot. Never give the old single-primary connect link to
a second owner before the new deployment/config is verified. Record the actual
callback/route and slot mapping privately and provide one step at a time.

## Discovery-only bootstrap (#199)

When the canonical owner nodes are not yet established, a separately approved
rollout may set `DISCOVERY_ONLY=true`. This deployment hides and rejects every
connection start, including primary. `/discover/start` is a same-origin POST
behind the same GitHub identity gate. Normal mode (variable absent) rejects this
route. Any other variable value fails setup. Writer credentials are not required
in discovery mode and should be removed from its binding for least privilege.
Preserve approved secrets securely for a later reviewed normal-mode rollout.
Do not rotate, copy or replace existing repository tokens during discovery.

One-time state contains `purpose=discover` without a destination, bound to the
human session and browser. The callback exchanges the human-approved code and
performs only the fixed HTTPS GET
`/api/profile?fields=id,first_name,last_name,merge_pending,merged_into`, bearer
header, no redirects. A canonical string ID, nonblank bounded first name,
bounded optional last name, explicit `merge_pending:false`, no merge target and
no results wrapper are required. The result shows escaped canonical ID, name
and merge status to the authenticated human, with no-store/no-referrer and the
binding cookie cleared. It does not show tokens or raw responses. Access and
refresh tokens remain transient memory only; no writer, tree mutation, durable
credential custody or automatic pin enrollment occurs. Geni may retain the app
authorization even though the Worker discards its tokens. No revocation or
revocation of other connections is attempted.

The human independently confirms the intended logged-in account and returns only
the nonsecret canonical ID and displayed identity. Record the account-to-slot
mapping privately. A website GUID, a name alone or the discovery result without
the human's account confirmation is not enough. Repeat separately for each owner
whose pin lacks evidence. Then separately approve normal-mode deployment with
both distinct primary and secondary pins. This requires another human OAuth
connection; discovery does not save a reusable token. Existing secondary
consumer/refresh and parent-write restrictions remain unchanged.

Every Geni state now carries explicit `purpose=connect` or `purpose=discover`.
In-flight states from older releases, wrong-purpose callbacks, mode changes and
replays fail closed. Roll out only when there is no concurrent OAuth/refresh/
upload; do not retry an old callback. The callback URL can contain a code even
on discovery results: never share/copy the address. Share only the minimal result
text or a cropped result with address bar excluded. Existing provider URL-retention
limitations still apply and need rollout approval. Tests use synthetic identities
only; no live OAuth is performed by agents.

## Fixed discovery failure diagnostics

Discovery has separate allowlisted stages for transport, HTTP, format, provider
error, canonical ID, missing merge flag, non-false merge flag, merge target,
results wrapper and name shape. Only a static stage label is shown; no status
body, response data, token, identity or URL is included in errors or logs.
A stage identifies the failed check, not its root cause. No rejection rule is
relaxed. In particular, an absent `merge_pending` is still a stop: the vendor's
statement that blank fields may be omitted does not define absent Boolean as
false. Report only the stage, not the callback address. A consumed state cannot
be replayed; any retest requires a fresh human-started flow after review/release.

## Identity-only unknown merge status (#205)

The discovery-only display now permits an absent `merge_pending` ONLY when
`merged_into` is also completely absent. Both fields are checked by own-property
presence, so explicit null is not absence. The result prominently says
"Warning: merge status not supplied by Geni (unknown)" and says it is identity
evidence only, not connection or upload readiness. Missing is never normalized
to false. A present merge flag must still be literal false. Any merge-target
property in the unknown branch stops, including null or empty values. All other
identity/name/wrapper/transport checks remain unchanged. The earlier strict
missing-flag statement above describes the previous discovery release.

This exception applies only to displaying identity to the human. Credential
storage in pinned connections still requires explicit `merge_pending:false`;
production parent/probe checks are unchanged. No pin is enrolled automatically.
Official source: https://www.geni.com/platform/developer/help/api?path=profile
says blank fields are omitted, but does NOT define missing Boolean as false.
An unknown result therefore makes no claim about the absence of a merge.

## Explicit secondary credential-custody opt-in (#207)

`SECONDARY_ALLOW_UNKNOWN_MERGE=true` is an optional server-side setting, valid
only in normal connection mode with distinct pinned primary and secondary owners.
Other values fail setup; absence retains strict behavior. This opt-in applies
ONLY to secondary, and only if both merge properties are completely absent and
token-self ID exactly equals SECONDARY_OWNER_NODE. It never converts missing to
false. Present null/nonboolean/true flags, a merge target, wrapper or wrong ID
stop before storage. Primary and tertiary remain strict. Discovery mode rejects
this setting rather than silently mixing custody with discovery.

Secondary pending and finalized refresh bundles contain the same permanent
`owner_attestation`: expected owner_node, merge_status (`unknown` or
`explicit_false`), observed_at UTC time, policy_version
`pinned-secondary-custody-v1`, credential_storage_only:true and upload_ready:false.
This evidence is encrypted with the bundle. Partial writes stop without retry;
retain/review pending recovery for this exact slot. No attestation is added to
primary or tertiary bundles. Nothing in this change authorizes refresh consumers,
uploads, a live Plan or profile creation. Those must independently validate owner
and their own policy; no secondary consumer is wired by this feature. Never drop
or upgrade unknown status in future refresh/recovery. A future consumer/refresh
implementation must preserve the attestation and re-check identity before use.

A rollout for connecting secondary must disable the primary start route in its
separately reviewed deployment if primary reconnection is not authorized. The
existing primary credential is neither copied, renamed nor reconnected during
secondary setup. Do not publish real owner pins or private slot mappings.

Set `SECONDARY_ONLY=true` for that restricted rollout: the authenticated landing
shows only secondary, primary/tertiary start requests reject, and callback rejects
in-flight primary/tertiary states before code exchange. Other values fail setup;
it cannot be combined with discovery mode. Pins still protect both configured
identities. This is the intended deployment for a secondary-only approval.
