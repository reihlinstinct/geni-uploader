# Parent evidence: offline first slice and human-run probe design

For #188, based on merged #144 and related to the #187 UI design. This is not a runnable live probe or a
production creation gate. `parent_evidence.py` inspects supplied snapshots only;
`collect()` always blocks. No credentials, network client, CLI/image/workflow
entry point or live Geni execution has been added. User-supplied snapshots are
untrusted evidence, not identity authorization or a vendor completeness proof.

## Proposed human-run collection sequence, not implemented

1. Human explicitly starts a read-only evidence session using their selected
   connection. Read current-user profile through the documented `/profile`
   behavior; verify canonical identity against the declared owner and anchor.
   Never use a name alone or application token as token-owner proof. A future
   implementation must validate actual response semantics, credentials and all
   redirect/merge variants, not merely accept an `id` key.
2. In that same bounded session request explicit owner identity/merge fields,
   immediate-family focus/nodes, and every relevant union's partners/children
   plus adopted/foster subsets. Capture requested versus returned fields and
   complete pagination/error status. Never follow arbitrary response URLs or
   allow a response to choose the host; use an exact endpoint/type allowlist.
   Endpoint fields/parameter details need separate implementation review.
3. Read explicitly returned public/is_alive values on known approved targets.
   Missing, null, zero or inaccessible is not boolean false. An existing private
   profile proves only observed current readback, not that a future create obeys
   public:false. No writes occur in this phase.
4. Stop on 401, 429, timeout, invalid identity, incomplete response or unexpected
   shape, preserving an encrypted private result if possible. Do not retry or
   refresh silently. Treat embedded captions/errors as untrusted data and output
   only fixed counts/statuses publicly. Tokens never appear in results or paths.

## Evidence matrix

| Question | Read-only observation | Still not proved |
| --- | --- | --- |
| Token belongs to intended owner | canonical self/owner/focus IDs agree | snapshot authorship, actual OAuth identity without reviewed collection |
| Parents and relationships | observed union partners where owner is child | hidden-parent absence or completeness of vendor graph |
| Union/slot behavior | current partners/children/adopted/foster edges | add-parent behavior for zero/one/two parents or second-call union selection |
| Privacy/life | explicitly returned boolean fields | create-time enforcement or omitted-field meaning |
| Bilingual names | observed names/default fields if requested | writable locale keys/default semantics and exact create/readback |

The offline reviewer deliberately always reports `create_enabled:false` and
`blocked_vendor_proof_required`. It counts observed parents and explicit private
life-status readbacks but cannot certify hidden-parent completeness or slots.
Do not feed these counts into an enablement boolean or treat zero as empty slots.
Its narrow normalized snapshot schema is not claimed to be the raw vendor shape.

## Mutation evidence is a separate decision

No synthetic test can settle actual POST semantics. Any creation trial needs a
separately reviewed exact proposal and explicit owner authority: two-parent cap,
verified anchor, exact bilingual names and life status, private-storage approval,
shown privacy/duplicate risks and acknowledgment that undo may be manual and
incomplete. Human initiates the run. Existing uncertain intent blocks any new
attempt. No agent/MCP dispatch, public:true experiment or disposable fake profile
in the live service. If read-only/vendor evidence cannot prove a required guard,
production stays disabled; the design does not force a write just to learn.

## Protected result contract for later implementation

Private encrypted envelope: schema version, collection time, owner/connection
handle, exact data/workflow/image pins and run/attempt, requested endpoint/field
allowlist version, result completeness and minimal normalized responses. Receipt
and journal do not hold tokens. Public counts/status report carries no names,
profile IDs, URLs, source captions or private filenames. Decryption and disclosure
are separately scoped; neither Worker nor MCP automatically receives raw logs.
Input size limits and unknown-field rejection must be applied before parsing;
current offline `review()` takes an already parsed bounded in-memory object.

## Tests and release gates

Synthetic fixtures only, zero network, identity mismatch/merges, missing parents,
malformed nodes/unions, duplicate IDs, missing/nonboolean privacy, bounds and
private sentinels. Fresh review must check that production remains disabled and
that no untrusted snapshot can lift it. Later human-run collection needs separate
transport, OAuth/session, redaction, encrypted persistence, path/rate/retry and
workflow pin tests plus independent review, green CI and chat approval.

## Official pages rechecked 28 October 2026

- https://www.geni.com/platform/developer/help/sdk_js?version=1 documents omitted
  profile ID applying to the current user's profile.
- https://www.geni.com/platform/developer/help/api?path=profile documents id,
  names, public, is_alive and merge fields; blank fields may be omitted.
- https://www.geni.com/platform/developer/help/api?path=profile/immediate-family
  documents focus/nodes, not hidden-parent completeness.
- https://www.geni.com/platform/developer/help/api?path=union documents partners,
  children and adopted/foster subsets, not create-slot semantics.
- https://www.geni.com/platform/developer/help/api?path=profile/add-parent
  documents POST and name/privacy fields, not union selection or default locale.
