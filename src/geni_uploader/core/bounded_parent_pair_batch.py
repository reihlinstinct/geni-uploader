"""Pure effect-injected parent-pair batch. No transport or credential construction."""
import copy
import re
import unicodedata

from geni_uploader.core.parent_contract import payload, profile_id
from geni_uploader.core.people import Blocked, digest, exact, require
from geni_uploader.runners import bounded_parent_addition as legacy
from geni_uploader.runners import bounded_relative_parent as relative

HARD_REQUEST_CEILING = 200


def first_plan(c, group):
    fields = {k: copy.deepcopy(v) for k, v in group.items() if k not in ('entries', 'sibling')}
    fields.update(schema=1, owner=c['owner'], expect_name=c['expect_name'],
                  expires_at=c['expires_at'], allow_unknown_merge=c['allow_unknown_merge'],
                  accept_hidden_duplicate_risk=c['accept_hidden_duplicate_risk'],
                  accept_private_create_risk=c['accept_private_create_risk'],
                  accept_union_selection_risk=c['accept_union_selection_risk'],
                  parent_union=None, existing_parent=None, entry=copy.deepcopy(group['entries'][0]))
    return relative.plan(fields)


def entry(value):
    exact(value, ('key', 'payload'))
    require(type(value['key']) is str and re.fullmatch(r'[a-z][a-z0-9-]{1,48}', value['key']))
    payload(value['payload'])


def inventory(c):
    # Each group revalidates its entire path, then each operation has fresh anchor
    # GET + POST + profile/anchor-family/created-family/direct-union proof GETs.
    return sum(2 * (len(g['profiles']) + len(g['path']) + len(g['path_unions']))
               + 6 * (2 + (g['sibling'] is not None)) for g in c['groups'])


def locale_name_pairs(names):
    """Exact first/last collision keys, not fuzzy identity or merge evidence."""
    def normalized(value):
        return unicodedata.normalize('NFC', value.strip().casefold())
    return {('en-US' if locale == 'en' else locale,
             normalized(fields['first_name']), normalized(fields.get('last_name', '')))
            for locale, fields in names.items()}


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'expires_at', 'allow_unknown_merge',
                  'allow_new_unknown_merge', 'accept_hidden_duplicate_risk',
                  'accept_private_create_risk', 'accept_union_selection_risk',
                  'max_requests', 'groups'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(type(value['allow_new_unknown_merge']) is bool)
    require(type(value['max_requests']) is int
            and 1 <= value['max_requests'] <= HARD_REQUEST_CEILING)
    require(type(value['groups']) is list and 1 <= len(value['groups']) <= 4)
    anchors, keys, names = set(), set(), set()
    profiles, baselines, unions = {}, {}, {}
    sibling_count = 0
    for g in value['groups']:
        exact(g, ('anchor', 'profiles', 'family', 'external_edges', 'path', 'path_unions',
                  'path_families', 'path_union_members', 'entries', 'sibling'))
        require(type(g['entries']) is list and len(g['entries']) == 2)
        require(g['anchor'] not in anchors)
        anchors.add(g['anchor'])
        first_plan(value, g)
        require({x['payload']['gender'] for x in g['entries']} == {'male', 'female'})
        all_entries = g['entries'] + ([] if g['sibling'] is None else [g['sibling']])
        sibling_count += g['sibling'] is not None
        for e in all_entries:
            entry(e)
            require(e['key'] not in keys and digest(e['payload']['names']) not in names)
            keys.add(e['key']); names.add(digest(e['payload']['names']))
        for dest, source in ((profiles, g['profiles']), (baselines, g['path_families']),
                             (unions, g['path_union_members'])):
            for key, body in source.items():
                require(key not in dest or dest[key] == body)
                dest[key] = copy.deepcopy(body)
    require(sibling_count <= 1)
    known_names = {pair for v in profiles.values() if 'names' in v
                   for pair in locale_name_pairs(v['names'])}
    new_names = {pair for g in value['groups']
                 for e in g['entries'] + ([] if g['sibling'] is None else [g['sibling']])
                 for pair in locale_name_pairs(e['payload']['names'])}
    require(not (new_names & known_names))
    # Unknown policy is scoped to all and only this package's explicitly pinned
    # existing profiles; new profiles have a separate, explicit policy flag.
    require(inventory(value) <= value['max_requests'])
    require(inventory(value) <= HARD_REQUEST_CEILING)
    return copy.deepcopy(value)


def marker(c, anchor, e, kind):
    if kind == 'parent':
        return legacy.marker({'owner': c['owner'], 'anchor': anchor, 'entry': e})
    # Stable before runtime parent/union IDs exist. An overlapping legacy sibling
    # operation needs external reconciliation before admission, not a new key.
    return 'parent-pair-sibling-consumed-v1-' + digest({
        'owner': c['owner'], 'anchor': anchor, 'entry': e})


def execute(value, io, store, save, clock):
    c = plan(value)
    groups = copy.deepcopy(c['groups'])
    known = {n for g in groups for b in g['path_families'].values()
             for m in b['family'].values() for n in m}
    r = {'schema': 1, 'mode': 'parent_pair_batch_model', 'production_enabled': False,
         'phase': 'STOPPED', 'stage': 'preflight', 'items': [], 'responses': [],
         'retry_allowed': False, 'request_budget': inventory(c), 'requests': 0}

    def now():
        require(clock() < c['expires_at'])

    def read(kind, node):
        now(); require(r['requests'] < c['max_requests'])
        r['stage'] = 'read_' + kind; r['requests'] += 1
        actual = getattr(io, 'get_' + kind)(node)
        r['responses'].append({'kind': kind, 'target': node, 'value': actual})
        save(copy.deepcopy(r))
        return actual

    def baseline(g):
        owner = read('profile', 'profile')
        relative.profile_check(owner, g['profiles'][c['owner']], c['owner'],
                               c['allow_unknown_merge'])
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        for n, fields in g['profiles'].items():
            if n != c['owner']:
                relative.profile_check(read('profile', n), fields, n, c['allow_unknown_merge'])
        for n in g['path']:
            b = g['path_families'][n]
            legacy.graph_check(read('family', n), n, b['family'], external_edges=b['external_edges'])
        for u in g['path_unions']:
            legacy.direct_union_check(read('union', u), u, g['path_union_members'][u])

    def propagate(anchor, union):
        # A completed operation adds exactly one child-role external edge to this
        # existing anchor in other pinned focus graphs. No new traversal permission.
        for g in groups:
            for focus, b in g['path_families'].items():
                visible = {n for m in b['family'].values() for n in m}
                if anchor in visible and focus != anchor and union not in b['family']:
                    b['external_edges'].setdefault(anchor, {})[union] = 'child'
            if g['anchor'] != anchor and anchor in {n for m in g['family'].values() for n in m}:
                g['external_edges'].setdefault(anchor, {})[union] = 'child'

    try:
        # Validate every initial path before the first possible effect.
        for g in groups:
            baseline(g)
        for index, g in enumerate(groups):
            r['group'] = index
            baseline(g)
            graph, boundary = copy.deepcopy(g['family']), copy.deepcopy(g['external_edges'])
            target = None
            sequence = [('parent', e) for e in g['entries']]
            if g['sibling'] is not None:
                sequence.append(('sibling', g['sibling']))
            for kind, e in sequence:
                now()
                legacy.graph_check(read('family', g['anchor']), g['anchor'], graph,
                                   external_edges=boundary)
                item = {'key': e['key'], 'kind': kind, 'phase': 'NOT_SENT',
                        'marker': marker(c, g['anchor'], e, kind)}
                r['items'].append(item)
                now(); r['stage'] = 'before'
                store.receipt(item['marker'], 'before', save(copy.deepcopy(r)))
                now(); r['stage'] = 'consume'; store.consume(item['marker'])
                now(); require(r['requests'] < c['max_requests'])
                r['requests'] += 1; r['stage'] = 'send'; item['phase'] = 'UNCERTAIN'
                actual = getattr(io, 'add_' + kind)(g['anchor'],
                                                    legacy.vendor_parent_payload(e['payload']))
                item['create_response'] = actual
                save(copy.deepcopy(r))
                require(type(actual) is dict and 'error' not in actual)
                created = actual.get('id'); profile_id(created); require(created not in known)
                known.add(created); item.update(id=created, phase='ACKNOWLEDGED_NOT_VERIFIED')
                now(); r['stage'] = 'ack'
                store.receipt(item['marker'], 'ack', save(copy.deepcopy(r)))
                relative.profile_check(read('profile', created), e['payload'], created,
                                       c['allow_new_unknown_merge'], created=True)
                after = read('family', g['anchor'])
                if target is None:
                    spec = dict(g, parent_union=None, existing_parent=None)
                    target, members = relative.parent_union_after(after, spec, created)
                    graph[target] = members
                else:
                    graph[target][created] = 'partner' if kind == 'parent' else 'child'
                    legacy.graph_check(after, g['anchor'], graph, external_edges=boundary)
                item['union_id'] = target
                b = legacy.boundary_edges({'family': graph, 'external_edges': boundary},
                                          target, graph[target])
                legacy.graph_check(read('family', created), created, {target: graph[target]},
                                   external_edges=b)
                legacy.direct_union_check(read('union', target), target, graph[target])
                now(); item['phase'] = 'VERIFIED'; r['stage'] = 'final'
                store.receipt(item['marker'], 'final', save(copy.deepcopy(r)))
                propagate(g['anchor'], target)
            r['stage'] = 'group_complete'; save(copy.deepcopy(r))
        require(r['requests'] == inventory(c))
        r['phase'], r['stage'] = 'VERIFIED', 'complete'; save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'; save(copy.deepcopy(r))
    return r
