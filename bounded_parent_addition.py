"""One-parent effect-injected model only. No transport, credentials or entry point."""
import copy
import hashlib
import json
import re

from geni_uploader.core.parent_contract import payload, profile_id
from geni_uploader.core.people import Blocked, exact, require
from one_time_parent_pilot import merge_clear, vendor_payload


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def union_id(value):
    require(type(value) is str and re.fullmatch(r'union-[0-9]{1,30}', value))


def parent_payload(value):
    """Unknown life status stays explicit locally and is omitted from vendor fields."""
    require(type(value) is dict and 'is_alive' in value)
    checked = copy.deepcopy(value)
    unknown = checked['is_alive'] is None
    if unknown:
        checked['is_alive'] = True  # schema checking only, never emitted as an asserted fact
    payload(checked)
    return copy.deepcopy(value)


def vendor_parent_payload(value):
    checked = parent_payload(value)
    if checked['is_alive'] is None:
        checked['is_alive'] = True
        result = vendor_payload(checked)
        del result['is_alive']
        return result
    return vendor_payload(checked)


def graph_spec(value):
    require(type(value) is dict and 1 <= len(value) <= 2)
    for union, members in value.items():
        union_id(union)
        require(type(members) is dict and 2 <= len(members) <= 10)
        for node, role in members.items():
            profile_id(node)
            require(role in ('partner', 'child'))
        require(1 <= list(members.values()).count('partner') <= 2
                and list(members.values()).count('child') >= 1)
    return copy.deepcopy(value)


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'anchor', 'profiles', 'family',
                  'parent_union', 'existing_parent', 'entry', 'expires_at',
                  'allow_unknown_merge', 'accept_hidden_duplicate_risk',
                  'accept_private_create_risk', 'accept_union_selection_risk'))
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
    family = graph_spec(value['family'])
    profiles = value['profiles']
    require(type(profiles) is dict and 2 <= len(profiles) <= 12
            and set(profiles) == {node for members in family.values() for node in members})
    for node, body in profiles.items():
        profile_id(node)
        payload(body)  # explicit living OR deceased, always private
    require(value['anchor'] in profiles and value['owner'] in profiles)
    # Anchor must be an existing parent of the authenticated owner in one pinned union.
    owner_unions = [u for u, m in family.items()
                    if m.get(value['owner']) == 'child' and m.get(value['anchor']) == 'partner']
    require(len(owner_unions) == 1)
    parent_unions = [u for u, m in family.items() if m.get(value['anchor']) == 'child']
    existing, parent_union = value['existing_parent'], value['parent_union']
    if existing is None:
        require(parent_union is None and parent_unions == [] and len(family) == 1)
    else:
        profile_id(existing)
        union_id(parent_union)
        require(existing not in (value['owner'], value['anchor'])
                and parent_unions == [parent_union] and len(family) == 2)
        require(family[parent_union] == {existing: 'partner', value['anchor']: 'child'})
    entry = value['entry']
    exact(entry, ('key', 'payload'))
    require(type(entry['key']) is str and re.fullmatch(r'[a-z][a-z0-9-]{1,48}', entry['key']))
    body = parent_payload(entry['payload'])
    if existing is not None:
        require(body['gender'] != profiles[existing]['gender'])
    return copy.deepcopy(value)


def marker(value):
    """Stable across windows and package revisions; a consumed operation stays consumed."""
    return 'parent-add-consumed-v1-' + digest({key: value[key]
        for key in ('owner', 'anchor', 'entry')})


def profile_check(actual, expected, node, allow_unknown, *, new_parent=False):
    require(type(actual) is dict and actual.get('id') == node)
    merge_clear(actual, allow_unknown)
    fields = vendor_parent_payload(expected) if new_parent else vendor_payload(expected)
    for key, leaf in fields.items():
        require(actual.get(key) == leaf)


def graph_check(actual, focus, expected):
    """Strict observed graph shape, with exact reciprocal edges and no extra relatives."""
    exact(actual, ('focus', 'nodes'))
    require(type(actual['focus']) is dict and actual['focus'].get('id') == focus
            and 'error' not in actual['focus'])
    profiles = {node for members in expected.values() for node in members}
    require(focus in profiles and type(actual['nodes']) is dict
            and set(actual['nodes']) == profiles | set(expected))
    for union, members in expected.items():
        node = actual['nodes'][union]
        exact(node, ('url', 'status', 'edges', *(('id',) if 'id' in node else ())))
        require(node.get('id', union) == union and node['status'] == 'spouse'
                and node['url'] == 'https://www.geni.com/api/' + union
                and node['edges'] == {p: {'rel': role} for p, role in members.items()})
    for profile in profiles:
        node = actual['nodes'][profile]
        edges = {u: {'rel': m[profile]} for u, m in expected.items() if profile in m}
        require(type(node) is dict and node.get('id') == profile
                and node.get('url') == 'https://www.geni.com/api/' + profile
                and node.get('edges') == edges and 'error' not in node
                and 'adopted_children' not in node and 'foster_children' not in node)
    focus_value = actual['focus']
    require('adopted_children' not in focus_value and 'foster_children' not in focus_value)
    if 'url' in focus_value:
        require(focus_value['url'] == 'https://www.geni.com/api/' + focus)
    if 'edges' in focus_value:
        require(focus_value['edges'] == actual['nodes'][focus]['edges'])


def parent_union_after(actual, value, created):
    """Extract at most one new syntactically valid union, then validate full graph."""
    require(type(actual) is dict and type(actual.get('nodes')) is dict
            and len(actual['nodes']) <= 15)
    unions = {node for node in actual['nodes'] if type(node) is str
              and re.fullmatch(r'union-[0-9]{1,30}', node)}
    if value['parent_union'] is None:
        added = unions - set(value['family'])
        require(len(added) == 1)
        target = next(iter(added))
    else:
        target = value['parent_union']
    expected = copy.deepcopy(value['family'])
    expected[target] = {value['anchor']: 'child', created: 'partner'}
    if value['existing_parent'] is not None:
        expected[target][value['existing_parent']] = 'partner'
    graph_check(actual, value['anchor'], expected)
    return target, expected[target]


def direct_union_check(actual, target, members):
    require(type(actual) is dict and actual.get('id') == target and 'error' not in actual)
    for field, role in (('partners', 'partner'), ('children', 'child')):
        values = actual.get(field)
        require(type(values) is list and all(type(p) is str for p in values)
                and len(values) == len(set(values))
                and set(values) == {p for p, r in members.items() if r == role})
    require(actual.get('adopted_children', []) == [] and actual.get('foster_children', []) == [])


def execute(value, io, store, save, clock):
    """Non-runnable model: injected I/O owns enforcement and protected deployment later."""
    c = plan(value)
    r = {'schema': 1, 'mode': 'one_parent_model', 'phase': 'STOPPED', 'stage': 'preflight',
         'retry_allowed': False, 'responses': [], 'item': None, 'production_enabled': False}

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
        now()
        owner = observe('profile', 'profile')
        require(owner.get('id') == c['owner'])
        merge_clear(owner, c['allow_unknown_merge'])
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        for node, body in c['profiles'].items():
            actual = owner if node == c['owner'] else observe('profile', node)
            profile_check(actual, body, node, c['allow_unknown_merge'])
        graph_check(observe('family', c['anchor']), c['anchor'], c['family'])
        r['item'] = {'marker': marker(c), 'key': c['entry']['key'], 'phase': 'NOT_SENT'}
        r['stage'] = 'before'
        now()
        store.receipt(r['item']['marker'], 'before', save(copy.deepcopy(r)))
        now()
        r['stage'] = 'consume'
        store.consume(r['item']['marker'])
        now()
        r['stage'], r['item']['phase'] = 'send', 'UNCERTAIN'
        actual = io.add_parent(c['anchor'], vendor_parent_payload(c['entry']['payload']))
        r['item']['create_response'] = actual
        require(type(actual) is dict and 'error' not in actual)
        created = actual.get('id')
        profile_id(created)
        require(created not in c['profiles'])
        r['item'].update(id=created, phase='ACKNOWLEDGED_NOT_VERIFIED')
        r['stage'] = 'ack'
        now()
        store.receipt(r['item']['marker'], 'ack', save(copy.deepcopy(r)))
        profile_check(observe('profile', created), c['entry']['payload'], created,
                      c['allow_unknown_merge'], new_parent=True)
        r['item']['source_life_status'] = c['entry']['payload']['is_alive']
        anchor_family = observe('family', c['anchor'])
        target, members = parent_union_after(anchor_family, c, created)
        r['item']['union_id'] = target
        graph_check(observe('family', created), created, {target: members})
        direct_union_check(observe('union', target), target, members)
        r['stage'], r['item']['phase'] = 'final', 'VERIFIED'
        now()
        store.receipt(r['item']['marker'], 'final', save(copy.deepcopy(r)))
        r['phase'], r['stage'] = 'VERIFIED', 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
