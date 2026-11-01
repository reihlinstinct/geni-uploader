# Bounded relative-sibling model (#588)

Pure effect-injected model only. No HTTP client, credentials, workflow, environment
secret or runnable entry point. It does not authorize a vendor effect.

The authenticated owner remains distinct from the existing child anchor. The
anchor must be a parent of the owner in one pinned union and a child of exactly
two existing parents in the other pinned union. Existing parents may be living
or deceased, but unknown status is rejected. The two pinned parents must have
explicit opposite genders (one male and one female). Up to four new siblings are explicit
living/private payloads. The complete profile set and both unions are pinned.

Execution checks the authenticated owner, all existing profiles, the complete
anchor graph and the direct target union. Before each possible send it persists
an encrypted before receipt and atomically consumes a stable operation marker.
It admits one injected add_sibling call for that item. It persists the acknowledged
ID before readback, verifies its exact payload/privacy, the complete anchor graph,
the new sibling's reciprocal graph and the direct union. Only boundary edges from
the approved graph may appear in the smaller reciprocal graph. Any uncertain
send, storage failure, graph difference or expiry stops subsequent effects.

The marker binds owner, anchor, target union, entry key and payload, not expiry.
Changing a window cannot replay a consumed operation. No retry, repair, update,
delete, rollback, or transport seam is provided. Receipt snapshot ordering follows
the existing parent model: the item is VERIFIED in its final receipt; overall
VERIFIED/complete is saved after final receipt storage succeeds.

Tests use invented ZZ names and IDs, covering deceased-parent admission, two
successful siblings, exact boundary edges, extra-edge rejection, privacy drift,
uncertain sends, receipt failures, expired plans and consumed-marker reuse.

Before any live use, a separate protected transport/workflow must be designed,
reviewed and tested against real package admission. The owner must approve that
exact immutable private package, scope, risks and bounded window. This model is
not a dispatch route and must not replace the existing owner-focused sibling core.
