# Profile creation: documented routes and recovery limits

Checked 28 October 2026. Related: #237, #240. This is a capability inventory,
not a release, authority grant, executable request or live-test result. Default
and single-father production gates stay closed. Current offline models do not
supply shared durable storage, caller authentication or encryption.

## Official-source capability matrix

| Method | Documented operation and fields | Limits important to a plan |
|---|---|---|
| [profile/add-parent](https://www.geni.com/platform/developer/help/api?path=profile/add-parent) | POST creates a parent and returns the added profile; form/JSON; main names, names locale maps, gender, is_alive, public | No documented existing-profile input, parent-slot selector, idempotency key or promise of hidden-parent completeness |
| [profile/add-partner](https://www.geni.com/platform/developer/help/api?path=profile/add-partner) | POST creates a partner of a profile; form/JSON; names maps and marriage event accepted | Not an existing-ID connector; does not promise reuse of a particular child's parent union |
| [profile/add-child](https://www.geni.com/platform/developer/help/api?path=profile/add-child) | POST creates a child of a profile; names maps; relationship_modifier adopt/foster | No documented selector for choosing among that profile's unions |
| [profile/add-sibling](https://www.geni.com/platform/developer/help/api?path=profile/add-sibling) | POST creates a sibling; names maps; relationship_modifier adopt/foster | No documented sibling ordering control or explicit parent-union selector |
| [union/add-partner](https://www.geni.com/platform/developer/help/api?path=union/add-partner) | Says add a partner to a union and return the added profile; main names, gender, is_alive, public | Names locale maps not listed; usage shows bare union/add-partner, not an ID; HTTP verb not stated on this page; returned-fields table lists union fields despite profile-return prose |
| [union/add-child](https://www.geni.com/platform/developer/help/api?path=union/add-child) | Says add a child to a union and return the added profile; usage shows union-1/add-child; relationship_modifier adopt/foster | Names locale maps not listed; HTTP verb not stated on this page; returned-fields table lists union fields despite profile-return prose |
| [profile/update](https://www.geni.com/platform/developer/help/api?path=profile/update) | POST updates an existing profile; form/JSON; names locale maps, main names, is_alive, public | Existing-profile edit requires exact target/field approval; table alone does not prove rights, merge-clear state or readback |
| [union/update](https://www.geni.com/platform/developer/help/api?path=union/update) | POST updates a union; writable parameters listed are marriage and divorce events | partners and status are returned fields, not documented writable inputs; not a demonstrated connector for two existing profiles |
| [profile/merge](https://www.geni.com/platform/developer/help/api?path=profile/merge) | POST usage shows profile-1/merge/profile-2 | Sparse contract, not a marriage operation; never use identity merge to connect spouses |

Index inspected: https://www.geni.com/platform/developer/help . Its Union section
lists union, add-child, add-partner and update. No existing-profile connector or
create-union method was found in that inspected index or the listed parameter
tables. This is a bounded documentation finding, not proof that no other Geni
capability exists. Do not invent an endpoint or an existing-ID parameter.

The union create pages have real documentation inconsistencies. They supply
useful operation-level building blocks, not sufficient evidence to guess the
HTTP verb, union-ID encoding or response schema for an executable adapter.
Resolve those details through a trusted supported contract or separately
approved evidence before release. Do not turn a mutation into an unapproved
probe. Examples with query data are documentation examples, not recommended
credential transport; credentials belong only in reviewed headers.

## Identity, graph, privacy and language evidence

[Profile](https://www.geni.com/platform/developer/help/api?path=profile)
distinguishes id from guid and exposes merge_pending/merged_into. Missing merge
fields stay UNKNOWN, not false. A custody exception is not create permission.

[Immediate family](https://www.geni.com/platform/developer/help/api?path=profile/immediate-family)
returns focus and nodes. [Union](https://www.geni.com/platform/developer/help/api?path=union)
returns partners/children/adopted_children/foster_children and status. These pages
do not certify hidden-parent completeness or say that a blank partner is
created automatically by add-parent. An omitted field is not an empty list;
zero observed parents is not proof of absence. Graph links must be checked
against exact IDs, never names alone. Unknown or extra nodes are not empty slots.

[Multilingual names help](https://help.geni.com/hc/en-us/articles/229704207-How-do-I-add-multilingual-names-and-biographies-to-a-profile)
describes language-dependent display and English/default fallback behavior.
It does not replace exact payload approval or API readback. Main names plus
names.he/names.en are distinct reviewed values. Do not assume a parameter missing
from union/add-partner's table is supported because another method accepts it.

[Private profile help](https://help.geni.com/hc/en-us/articles/229704447-What-profiles-are-private)
describes general privacy rules. Request explicit public:false and explicit
living status; do not infer status. This help is not a transactional guarantee
that a create request honored privacy. Post-write readback can detect failure,
but cannot prevent an initial exposure. Exact risk acceptance must say so.

## Father-first decision tree

1. Offline plan and current read-only evidence first. No approved executor or
   shared durable intent backend means STOP before any POST. Require exact
   owner/account, immutable code/data pins, payload, named risk decision, release
   approval, exact run approval and protected human gate. Pin mismatch or scanner
   trip means STOP, not repair-the-control-and-continue.
2. If the separately approved path is eventually released, commit shared durable
   intent before its one father POST. No retry, redirect, refresh or second POST.
   A timeout after consumption remains consumed even if send is uncertain.
3. Read back the exact returned father ID, approved names, living/private flags
   and union edges under the exact approved GET budget. Child must match exact
   owner and father exact created ID. Record encrypted evidence. Exit/HTTP success
   alone is not VERIFIED.
4. Unexpected union, blank partner, extra profile, missing field, privacy/name
   mismatch or unknown result means STOP and report evidence, never auto-repair.
   A blank box in a UI is not proof of a canonical writable mother profile.
5. If a real extra canonical profile is present, separately verify its identity,
   relationship, custody and edit rights before even proposing an update. Never
   overwrite it because it lacks a name. A mother update is a new exact approval.
6. If verified parent union contains exact child and only exact new father as
   partner, union/add-partner is the documented building block for creating a new
   mother directly there. Do not separately create mother then try to connect
   existing profiles. Resolve union endpoint inconsistencies and locale behavior
   first; mother is a separately approved plan, not an automatic next step.
7. Record marriage on a verified union only under a separate exact event plan.
   An existing pair's missing union is a connector gap, not permission to create
   duplicate partners or merge their identities. No guessed marriage dates.

## Children are a separate design scope

union/add-child can name the union as the anchor at the operation level, whereas
profile/add-child and add-sibling need verified relationship/union semantics.
Check existing children and hidden/partial graph limits before considering a
create. Do not treat birth order as request order or invent an ordering field.
Specify adopt/foster only from approved facts, not inferred household roles.
Privacy, locale, durable intent and approvals apply to children too. No child
operation is included in the single-father path.

## Uncertainty and recovery

Preserve consumed intent across crashes, receipt expiry, new manifests/plan IDs,
connection labels and fresh runners. Shared owner-scoped exclusion must cover
all approved execution surfaces; local/mock CAS does not prove it. Encryption
failure after POST must not erase consumption or cause another create.

Uncertain result: separately approved GET-only reconciliation. Existing known
created ID cannot change. Ordinary verify is forbidden from uncertain state;
only the dedicated reviewed reconciliation transition can finish. No reset,
replay, retry, automatic rollback/delete/merge or implied safe undo. A created
father may remain even when readback fails. Report that partial outcome honestly.

Required code review, exact-head CI and named merge approval do not authorize
release/deployment or an actual run. Each remains a separate decision. Public
summaries contain no private data or approval references; raw results stay
protected and encrypted. No live Geni request was made to write this inventory.
