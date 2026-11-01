"""Effect-injected relative-sibling model. No transport, credentials or entry point."""
import copy
import re

import bounded_parent_addition as parent
from geni_uploader.core.parent_contract import payload, profile_id
from geni_uploader.core.people import Blocked, exact, require


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'anchor', 'profiles', 'family',
                  'parent_union', 'entries', 'expires_at', 'allow_unknown_merge',
                  'accept_hidden_duplicate_risk', 'accept_private_create_risk',
                  'accept_union_selection_risk'))
    require(type(value['schema']) is int and value['schema'] == 1)
    profile_id(value['owner'])
    profile_id(value['anchor'])
    require(value['owner'] != value['anchor'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['allow_unknown_merge']) is bool)
    for key in ('accept_hidden_duplicate_risk', 'accept_private_create_risk',
                'accept_union_selection_risk'):
        require(value[key] is True)
    family = parent.graph_spec(value['family'])
    require(len(family) == 2)
    profiles = value['profiles']
    require(type(profiles) is dict and 4 <= len(profiles) <= 12
            and set(profiles) == {p for m in family.values() for p in m})
    for node, body in profiles.items():
        profile_id(node)
        parent.existing_payload(body)  # Explicit living OR deceased; never coerce unknown.
    require(value['anchor'] in profiles and value['owner'] in profiles)
    owner_unions = [u for u, m in family.items()
                    if m.get(value['owner']) == 'child' and m.get(value['anchor']) == 'partner']
    target = value['parent_union']
    parent.union_id(target)
    require(len(owner_unions) == 1 and owner_unions[0] != target and target in family)
    members = family[target]
    require(members.get(value['anchor']) == 'child'
            and list(members.values()).count('partner') == 2)
    parents = [p for p, role in members.items() if role == 'partner']
    require(value['owner'] not in members
            and {profiles[p]['gender'] for p in parents} == {'male', 'female'})
    entries = value['entries']
    require(type(entries) is list and 1 <= len(entries) <= 4
            and len(members) + len(entries) <= 10 and len(profiles) + len(entries) <= 12)
    keys, names = set(), set()
    known_names = {parent.canonical(body['names']) for body in profiles.values()
                   if 'names' in body}
    for entry in entries:
        exact(entry, ('key', 'payload'))
        require(type(entry['key']) is str and re.fullmatch(r'[a-z][a-z0-9-]{1,48}', entry['key'])
                and entry['key'] not in keys)
        keys.add(entry['key'])
        body = payload(entry['payload'])
        require(body['is_alive'] is True and body['public'] is False)
        name = parent.canonical(body['names'])
        require(name not in names)
        names.add(name)
        require(name not in known_names)
    return copy.deepcopy(value)


def marker(c, entry):
    """Expiry changes do not create another permission to send the same operation."""
    return 'relative-sibling-consumed-v1-' + parent.digest({
        'owner': c['owner'], 'anchor': c['anchor'], 'parent_union': c['parent_union'],
        'key': entry['key'], 'payload': entry['payload']})


def execute(value, io, store, save, clock):
    """Injected reads/add_sibling and create-only consume/encrypted receipt seams only."""
    c = plan(value)
    graph = copy.deepcopy(c['family'])
    target = c['parent_union']
    known = set(c['profiles'])
    r = {'schema': 1, 'mode': 'relative_siblings_model', 'phase': 'STOPPED',
         'stage': 'preflight', 'items': [], 'responses': [], 'retry_allowed': False,
         'production_enabled': False}

    def now():
        require(clock() < c['expires_at'])

    def read(kind, node):
        now()
        r['stage'] = 'read_' + kind
        actual = getattr(io, 'get_' + kind)(node)
        r['responses'].append({'kind': kind, 'target': node, 'value': actual})
        save(copy.deepcopy(r))
        return actual

    try:
        owner = read('profile', 'profile')
        require(owner.get('id') == c['owner'])
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        for node, body in c['profiles'].items():
            actual = owner if node == c['owner'] else read('profile', node)
            parent.profile_check(actual, body, node, c['allow_unknown_merge'])
        parent.graph_check(read('family', c['anchor']), c['anchor'], graph)
        for entry in c['entries']:
            parent.direct_union_check(read('union', target), target, graph[target])
            item = {'key': entry['key'], 'marker': marker(c, entry), 'phase': 'NOT_SENT'}
            r['items'].append(item)
            now()
            r['stage'] = 'before'
            store.receipt(item['marker'], 'before', save(copy.deepcopy(r)))
            now()
            r['stage'] = 'consume'
            store.consume(item['marker'])
            now()
            r['stage'], item['phase'] = 'send', 'UNCERTAIN'
            actual = io.add_sibling(c['anchor'], parent.vendor_parent_payload(entry['payload']))
            item['create_response'] = actual
            require(type(actual) is dict and 'error' not in actual)
            created = actual.get('id')
            profile_id(created)
            require(created not in known)
            item.update(id=created, phase='ACKNOWLEDGED_NOT_VERIFIED')
            now()
            r['stage'] = 'ack'
            store.receipt(item['marker'], 'ack', save(copy.deepcopy(r)))
            parent.profile_check(read('profile', created), entry['payload'], created,
                                 c['allow_unknown_merge'], new_parent=True)
            graph[target][created] = 'child'
            parent.graph_check(read('family', c['anchor']), c['anchor'], graph)
            parent.graph_check(read('family', created), created, {target: graph[target]},
                               external_edges=parent.boundary_edges(c, target, graph[target]))
            parent.direct_union_check(read('union', target), target, graph[target])
            known.add(created)
            now()
            r['stage'], item['phase'] = 'final', 'VERIFIED'
            store.receipt(item['marker'], 'final', save(copy.deepcopy(r)))
        now()
        r['phase'], r['stage'] = 'VERIFIED', 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
