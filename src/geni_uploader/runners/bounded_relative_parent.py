"""Pure bounded relative-parent model. No credentials, HTTP or dispatch path."""
import copy
import re

from geni_uploader.core.parent_contract import payload, profile_id
from geni_uploader.core.people import exact, require, text
from geni_uploader.runners import bounded_parent_addition as legacy
from geni_uploader.runners.one_time_parent_pilot import merge_clear

Blocked = legacy.Blocked
marker = legacy.marker


def graph(value, focus, *, anchor=False):
    require(type(value) is dict and 1 <= len(value) <= (2 if anchor else 4))
    seen = set()
    for union, members in value.items():
        legacy.union_id(union)
        require(type(members) is dict and 2 <= len(members) <= 20)
        for node, role in members.items():
            profile_id(node)
            require(role in ('partner', 'child'))
            seen.add(node)
        require(1 <= list(members.values()).count('partner') <= 2
                and list(members.values()).count('child') >= 1
                and focus in members)
    require(len(seen) <= 80)
    return copy.deepcopy(value)


def boundary(value, spec):
    require(type(value) is dict)
    members = {node for roles in spec.values() for node in roles}
    require(set(value) <= members)
    for edges in value.values():
        require(type(edges) is dict and 1 <= len(edges) <= 4)
        for union, role in edges.items():
            legacy.union_id(union)
            require(union not in spec and role in ('partner', 'child'))
    return copy.deepcopy(value)


def existing_payload(value):
    """Exact served fields, including explicit privacy/status/claimed, never edits."""
    required = {'first_name', 'gender', 'is_alive', 'public', 'claimed'}
    optional = {'middle_name', 'last_name', 'maiden_name', 'names'}
    require(type(value) is dict and required <= set(value) <= required | optional)
    for key in ('first_name', 'middle_name', 'last_name', 'maiden_name'):
        if key in value:
            text(value[key])
    require(value['gender'] in ('male', 'female'))
    for key in ('is_alive', 'public', 'claimed'):
        require(type(value[key]) is bool)
    if 'names' in value:
        names = value['names']
        require(type(names) is dict and set(names) <= {'en-US', 'he'} and names)
        for fields in names.values():
            require(type(fields) is dict and 'first_name' in fields
                    and set(fields) <= {'first_name', 'middle_name', 'last_name', 'maiden_name'})
            for leaf in fields.values():
                text(leaf)
    return copy.deepcopy(value)


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'anchor', 'profiles', 'family',
                  'external_edges', 'parent_union', 'existing_parent', 'entry', 'expires_at',
                  'allow_unknown_merge', 'accept_hidden_duplicate_risk',
                  'accept_private_create_risk', 'accept_union_selection_risk',
                  'path', 'path_unions', 'path_families', 'path_union_members'))
    require(type(value['schema']) is int and value['schema'] == 1)
    for key in ('owner', 'anchor'):
        profile_id(value[key])
    require(value['owner'] != value['anchor'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['allow_unknown_merge']) is bool)
    for key in ('accept_hidden_duplicate_risk', 'accept_private_create_risk',
                'accept_union_selection_risk'):
        require(value[key] is True)
    profiles = value['profiles']
    require(type(profiles) is dict and 2 <= len(profiles) <= 12)
    for node, fields in profiles.items():
        profile_id(node)
        existing_payload(fields)
    path, unions = value['path'], value['path_unions']
    require(type(path) is list and 2 <= len(path) <= 5 and len(set(path)) == len(path)
            and path[0] == value['owner'] and path[-1] == value['anchor']
            and set(path) <= set(profiles))
    require(type(unions) is list and len(unions) == len(path) - 1
            and len(set(unions)) == len(unions))
    for union in unions:
        legacy.union_id(union)
    family = graph(value['family'], value['anchor'], anchor=True)
    external = boundary(value['external_edges'], family)
    require(value['anchor'] not in external)
    families = value['path_families']
    require(type(families) is dict and set(families) == set(path))
    for node, baseline in families.items():
        exact(baseline, ('family', 'external_edges'))
        spec = graph(baseline['family'], node, anchor=node == value['anchor'])
        boundary(baseline['external_edges'], spec)
        require(node not in baseline['external_edges'])
    require(families[value['anchor']] == {'family': family, 'external_edges': external})
    memberships = value['path_union_members']
    require(type(memberships) is dict and set(memberships) == set(unions))
    for index, union in enumerate(unions):
        left, right = path[index:index + 2]
        members = memberships[union]
        # Both independent endpoint baselines must pin the entire same union.
        require(type(members) is dict and left in members and right in members)
        for node in (left, right):
            require(families[node]['family'].get(union) == members)
    parent_unions = [u for u, m in family.items() if m.get(value['anchor']) == 'child']
    existing, parent_union = value['existing_parent'], value['parent_union']
    if existing is None:
        require(parent_union is None and parent_unions == [])
    else:
        profile_id(existing)
        legacy.union_id(parent_union)
        require(existing in profiles and existing not in (value['owner'], value['anchor'])
                and parent_unions == [parent_union]
                and family[parent_union] == {existing: 'partner', value['anchor']: 'child'})
    # Separately read profiles must actually occur in the pinned connection context.
    visible = {p for b in families.values() for m in b['family'].values() for p in m}
    require(set(profiles) <= visible)
    entry = value['entry']
    exact(entry, ('key', 'payload'))
    require(type(entry['key']) is str and re.fullmatch(r'[a-z][a-z0-9-]{1,48}', entry['key']))
    payload(entry['payload'])  # Known boolean life status, public=false.
    if existing is not None:
        require(entry['payload']['gender'] != profiles[existing]['gender'])
    return copy.deepcopy(value)


def request_budget(value):
    c = plan(value)
    # Owner + remaining profiles + path families/unions + fresh anchor + POST + four proofs.
    return len(c['profiles']) + len(c['path']) + len(c['path_unions']) + 6


def profile_check(actual, expected, node, allow_unknown, *, created=False):
    require(type(actual) is dict and actual.get('id') == node and 'error' not in actual)
    merge_clear(actual, allow_unknown)
    for key in ('public', 'claimed', 'is_alive'):
        require(type(actual.get(key)) is bool)
    fields = legacy.vendor_parent_payload(expected) if created else existing_payload(expected)
    for key, leaf in fields.items():
        require(actual.get(key) == leaf)
    if created:
        require(actual.get('claimed') is False and actual.get('public') is False)


def parent_union_after(actual, value, created):
    require(type(actual) is dict and type(actual.get('nodes')) is dict
            and len(actual['nodes']) <= 84)
    unions = {u for u in actual['nodes'] if type(u) is str
              and re.fullmatch(r'union-[0-9]{1,30}', u)}
    target = value['parent_union']
    if target is None:
        added = unions - set(value['family'])
        require(len(added) == 1)
        target = next(iter(added))
    expected = copy.deepcopy(value['family'])
    expected[target] = {value['anchor']: 'child', created: 'partner'}
    if value['existing_parent'] is not None:
        expected[target][value['existing_parent']] = 'partner'
    legacy.graph_check(actual, value['anchor'], expected,
                       external_edges=value['external_edges'])
    return target, expected[target]


def execute(value, io, store, save, clock):
    """Injected seams only. No live adapter is shipped by this model slice."""
    c = plan(value)
    r = {'schema': 1, 'mode': 'relative_parent_model', 'phase': 'STOPPED',
         'stage': 'preflight', 'retry_allowed': False, 'responses': [],
         'item': None, 'production_enabled': False, 'request_budget': request_budget(c)}

    def now():
        require(clock() < c['expires_at'])

    def observe(kind, target):
        now()
        r['stage'] = 'read_' + kind
        method = {'profile': io.get_profile, 'family': io.get_family, 'union': io.get_union}[kind]
        actual = method(target)
        r['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(r))
        return actual

    try:
        owner = observe('profile', 'profile')
        profile_check(owner, c['profiles'][c['owner']], c['owner'], c['allow_unknown_merge'])
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        for node, fields in c['profiles'].items():
            if node != c['owner']:
                profile_check(observe('profile', node), fields, node, c['allow_unknown_merge'])
        for node in c['path']:
            b = c['path_families'][node]
            legacy.graph_check(observe('family', node), node, b['family'],
                               external_edges=b['external_edges'])
        for union in c['path_unions']:
            legacy.direct_union_check(observe('union', union), union,
                                      c['path_union_members'][union])
        # This independent fresh check is immediately before the durable write ceremony.
        legacy.graph_check(observe('family', c['anchor']), c['anchor'], c['family'],
                           external_edges=c['external_edges'])
        r['item'] = {'marker': marker(c), 'key': c['entry']['key'], 'phase': 'NOT_SENT'}
        r['stage'] = 'before'
        now()
        store.receipt(r['item']['marker'], 'before', save(copy.deepcopy(r)))
        now()
        r['stage'] = 'consume'
        store.consume(r['item']['marker'])
        now()
        r['stage'], r['item']['phase'] = 'send', 'UNCERTAIN'
        actual = io.add_parent(c['anchor'], legacy.vendor_parent_payload(c['entry']['payload']))
        r['item']['create_response'] = actual
        # Preserve ACK before interpreting its identifier or allowing another effect.
        save(copy.deepcopy(r))
        require(type(actual) is dict and 'error' not in actual)
        created = actual.get('id')
        profile_id(created)
        require(created not in {p for b in c['path_families'].values()
                                for m in b['family'].values() for p in m})
        r['item'].update(id=created, phase='ACKNOWLEDGED_NOT_VERIFIED')
        r['stage'] = 'ack'
        now()
        store.receipt(r['item']['marker'], 'ack', save(copy.deepcopy(r)))
        profile_check(observe('profile', created), c['entry']['payload'], created,
                      c['allow_unknown_merge'], created=True)
        after = observe('family', c['anchor'])
        target, members = parent_union_after(after, c, created)
        r['item']['union_id'] = target
        legacy.graph_check(observe('family', created), created, {target: members},
                           external_edges=legacy.boundary_edges(c, target, members))
        legacy.direct_union_check(observe('union', target), target, members)
        r['stage'], r['item']['phase'] = 'final', 'VERIFIED'
        now()
        store.receipt(r['item']['marker'], 'final', save(copy.deepcopy(r)))
        r['phase'], r['stage'] = 'VERIFIED', 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
