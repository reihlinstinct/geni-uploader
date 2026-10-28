# Exact offline parent proposal view

For #190/#187, based on the merged human-run GET probe (#195). This first Plan
slice is strictly offline: a private JSON/HTML proposal, not a live checked plan
receipt, OAuth flow, apply command or creation authorization. No network calls or
image/workflow integration. `apply()` remains disabled. Current vendor/owner/
connection/transport blockers cannot be cleared with input flags.

The proposed one/two entries show all sent fields: English main-name proposal,
preserved Hebrew/English name maps, supplied gender and life status, fixed private
flag and exact existing-owner anchor. Unknown gender is blocked in this view;
no gender is inferred from a name. No dates, birthplaces, relatives, images or
profile edits. Full payload and complete proposal/pins are expandable for review.
Names and fields are escaped; there is no active script, form, network resource or
Upload button. The static HTML has a restrictive content security policy.

The canonical proposal hash binds manifest digest, exact payloads/anchors, stated
owner/operator/approval evidence, code/data/image pins and fixed blocker list.
It detects accidental changes; it is not a signature or proof of authorship.
Anybody able to replace both data and hash can forge an offline proposal, so a
later human-run apply must authenticate its real receipt independently, recheck
all remote preconditions, obtain exact user approval and use durable shared state.
This proposal cannot be passed to a production apply, which does not exist yet.
Supplied approval flags are displayed as unverified, never promoted into consent.

Local CLI reads bounded mode0600 JSON files and creates a new mode0700 directory
with mode0600 proposal.json and proposal.html. Use a private unsynced parent path;
these contain family data in plaintext for the authorized local reviewer. Public
stdout has only fixed status. Do not send output to an AI provider, public repo or
other audience without covered permission. Normal read permissions do not grant
sharing. Parent-only creation remains human-triggered, never a model/MCP tool.

Command shape (synthetic/private placeholders, not executed by agents):

```sh
python parent_plan.py --manifest-file /PRIVATE/parents.json \
  --pins-file /PRIVATE/pins.json --output-dir /PRIVATE/new-plan-draft
```

Pins JSON contains exact data_sha/workflow_sha (40hex) and image_digest
(sha256:64hex). Do not invent a runnable release pin: this view can record supplied
pins but cannot verify that a release exists or corresponds to these modules.
Missing proof keeps creation blocked. No secret belongs in pins or manifest.

Next stages, separately reviewed: bind protected human-run probe evidence to
canonical identity and exact plan; prove full parent set/slots/private/bilingual
readback; human approval of the live plan; single-POST durable journal path,
acknowledgment and GET-only recovery; final human-operated release. The current
view must not be labeled "ready" merely because it rendered successfully.
