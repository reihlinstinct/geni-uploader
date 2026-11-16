# Strict immediate-family graph validation (#572)

The direct union GET returns an id and partner/child lists. The immediate-family
GET instead returns a focus profile plus a nodes map. An observed union node in
that map has a canonical API URL, spouse status and relationship edges; it is
not a direct union record. Passing it to the direct record validator stops even
when the graph links are consistent.

Use a separate pure validator, with no network or mutation capability. Keep
`union_state` unchanged. For the bounded sibling workflow, require the exact
focus ID, exactly the pinned union and expected family profile nodes, exactly
the expected union edge set, and reciprocal profile-to-union edges. Only partner
and child roles are accepted, with no extra edge fields. A profile node must
identify itself and its canonical API URL. The union node must have canonical
URL and spouse status; optional id must agree with the map key. No extra union
fields or adoption/foster declarations are supported. Focus URL/edges, when
present, must agree too. Non-relationship profile metadata is not interpreted.

This deliberately rejects additional relatives/unions, missing reciprocal
edges, partial graphs, other relationship roles, adoption/foster representations,
wrong URLs and conflicting IDs. It does not infer identity from names or prove
biological parentage from generic child edges. Existing payload/privacy checks
and the separate direct union read remain required. Unknown merge-state handling
is unchanged.

Apply this same validator before any send for a previously created child and
following creation for a new child. If preflight fails there must be no consume,
receipt or POST. If post-create linkage fails, preserve the consumed marker and
stop without creating the next child. No retry, normalization of arbitrary graph
shapes, endpoint expansion or new execution authority is added.

Tests use only invented ZZ names and synthetic IDs. They cover the observed
edge representation and corruptions at both execution boundaries, while keeping
direct union validation strict.

The public API documents focus and nodes, but not the detailed edge schema:
https://www.geni.com/platform/developer/help/api?path=profile%2Fimmediate-family&version=1
