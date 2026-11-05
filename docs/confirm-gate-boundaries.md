# Confirmation entry boundaries (#786)

Test-only follow-up to the confirmation-gate sweep on master. No production,
workflow or permission change. No live credentials, network, dispatch or effect.

`tests/test_confirm_gate_boundaries.py` covers the twelve reported entry points,
with create/update paths first:

| Module | Effect class |
|---|---|
| runners/one_time_parent_pilot | create |
| runners/protected_parent_addition | create |
| runners/geni_union_child_create | create |
| runners/geni_protected_household_create | create |
| runners/name_update_child_create | update + create |
| runners/protected_profile_tgp | update (plan and update confirms tested) |
| runners/parent_pair_batch_create | create; also covered by #780 |
| runners/household_relationship_read | read-only |
| runners/household_precreate_read | read-only |
| runners/bounded_tree_snapshot | read-only |
| runners/parent_household_read | read-only |
| workflow/secondary_probe | read-only |

Each valid synthetic environment must reach an encryption preflight patched to
raise `ReachedEncryption`, a distinct exception, not Blocked. Missing, empty and
incorrect confirmation values must raise Blocked before that boundary. Downstream
network/credential constructors are fail sentinels. No invalid synthetic age
recipient can make a missing admission check look like success: real encryption
is never called, and the positive control proves the preceding schema/hash/time
checks pass. Reuse synthetic config builders, not production secrets or settings.

All twelve isolated mutations replacing the confirmation require() with a bare
expression were killed by these tests. The TGP mutation fails both mode groups.
This proves these particular gates are pinned; it does not prove every adjacent
actor/hash/expiry check is covered or that workflow protection is configured.
Previously covered entry points and newer separate runners retain their own tests.
No claim about live vendor behavior, account authority or runtime readiness follows.
