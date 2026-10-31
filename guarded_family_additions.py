"""Effect-injected family addition core. No credential, transport or runnable entry point."""
import copy
import http.client
import re
import time

from geni_uploader.core.parent_contract import payload, profile_id
from geni_uploader.core.people import Blocked, exact, require
from one_time_parent_pilot import (
    TransportStop,
    canonical,
    canonical_union_reference,
    merge_clear,
    sha,
    vendor_payload,
)


def plan(value):
    exact(value, ('schema', 'mode', 'owner', 'expect_name', 'union_id', 'parents',
                  'children', 'entries', 'expires_at', 'allow_unknown_merge',
                  'accept_hidden_duplicate_risk', 'accept_private_create_risk',
                  'accept_union_selection_risk'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(value['mode'] in ('mother', 'siblings'))
    profile_id(value['owner'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(canonical_union_reference(value['union_id']) == value['union_id'])
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['allow_unknown_merge']) is bool)
    for key in ('accept_hidden_duplicate_risk', 'accept_private_create_risk',
                'accept_union_selection_risk'):
        require(value[key] is True)
    parents = value['parents']
    require(type(parents) is list and len(parents) == (1 if value['mode'] == 'mother' else 2))
    ids = set()
    for parent in parents:
        exact(parent, ('id', 'payload'))
        profile_id(parent['id'])
        require(parent['id'] != value['owner'] and parent['id'] not in ids)
        ids.add(parent['id'])
        reviewed = payload(parent['payload'])
        require(reviewed['is_alive'] is True)
    require(parents[0]['payload']['gender'] == 'male')
    if value['mode'] == 'siblings':
        require(parents[1]['payload']['gender'] == 'female')
    children = value['children']
    require(type(children) is list and 1 <= len(children) <= 20
            and len(set(children)) == len(children) and value['owner'] in children)
    for child in children:
        profile_id(child)
        require(child not in ids)
    entries = value['entries']
    require(type(entries) is list and len(entries) == (1 if value['mode'] == 'mother' else 4))
    keys, names = set(), set()
    for entry in entries:
        exact(entry, ('key', 'payload'))
        require(type(entry['key']) is str and re.fullmatch(r'[a-z][a-z0-9-]{1,48}',
                                                        entry['key']))
        require(entry['key'] not in keys)
        keys.add(entry['key'])
        reviewed = payload(entry['payload'])
        require(reviewed['is_alive'] is True)
        if value['mode'] == 'mother':
            require(reviewed['gender'] == 'female')
        # Names are an extra local duplicate guard, not proof of remote absence.
        name = canonical(reviewed['names'])
        require(name not in names)
        names.add(name)
    return copy.deepcopy(value)


def profile_fields(actual, expected, target, allow_unknown):
    require(type(actual) is dict and actual.get('id') == target)
    merge_clear(actual, allow_unknown)
    for key, value in vendor_payload(expected).items():
        require(actual.get(key) == value)


def union_state(actual, target, parents, children):
    require(type(actual) is dict and actual.get('id') == target and 'error' not in actual)
    for field, expected in (('partners', parents), ('children', children)):
        values = actual.get(field)
        require(type(values) is list and len(values) == len(expected))
        require(all(type(v) is str for v in values) and len(set(values)) == len(values))
        require(set(values) == set(expected))
    # Never infer adoption/foster semantics from a generic child edge.
    require(actual.get('adopted_children', []) == [] and actual.get('foster_children', []) == [])


def marker(plan_value, entry):
    """No attempt namespace: the same approved operation cannot be retried by changing expiry."""
    return 'family-add-consumed-v1-' + sha(canonical({
        'owner': plan_value['owner'], 'mode': plan_value['mode'],
        'key': entry['key'], 'payload': entry['payload']}))


def execute(value, io, store, save, clock=time.time):
    """Injected seams only. io supplies bounded get_profile/get_union/add methods.

    store.consume is atomic create-only; store.receipt persists encrypted save output.
    No recovery, retry, update, delete or rollback seam exists.
    """
    c = plan(value)
    report = {'schema': 1, 'mode': c['mode'], 'plan_sha256': sha(canonical(c)),
              'phase': 'STOPPED', 'stage': 'preflight', 'items': [], 'responses': [],
              'retry_allowed': False}
    parents = [x['id'] for x in c['parents']]
    children = list(c['children'])
    known = set(parents + children)

    def now():
        require(clock() < c['expires_at'])

    def observe(kind, target):
        now()
        report['stage'] = 'read_' + kind
        actual = (io.get_profile(target) if kind == 'profile' else
                  io.get_family(target) if kind == 'family' else io.get_union(target))
        report['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(report))  # durable local encryption before checks/next effect
        return actual

    try:
        now()
        owner = observe('profile', 'profile')
        require(owner.get('id') == c['owner'])
        merge_clear(owner, c['allow_unknown_merge'])
        actual_name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in actual_name.casefold().split()
                    for w in c['expect_name'].split()))
        for parent in c['parents']:
            actual = observe('profile', parent['id'])
            profile_fields(actual, parent['payload'], parent['id'], c['allow_unknown_merge'])
            unions = actual.get('unions')
            require(type(unions) is list and len(unions) == 1
                    and canonical_union_reference(unions[0]) == c['union_id'])
        for entry in c['entries']:
            union_state(observe('union', c['union_id']), c['union_id'], parents, children)
            item = {'key': entry['key'], 'marker': marker(c, entry), 'phase': 'NOT_SENT',
                    'payload_sha256': sha(canonical(entry['payload']))}
            report['items'].append(item)
            report['stage'] = 'before'
            now()
            store.receipt(item['marker'], 'before', save(copy.deepcopy(report)))
            now()
            report['stage'] = 'consume'
            store.consume(item['marker'])  # permanently consumes before possible send
            now()
            report['stage'] = 'send'
            item['phase'] = 'UNCERTAIN'
            route = 'add-parent' if c['mode'] == 'mother' else 'add-sibling'
            response = io.add(c['owner'], route, vendor_payload(entry['payload']))
            item['create_response'] = response
            require(type(response) is dict and 'error' not in response)
            created = response.get('id')
            profile_id(created)
            require(created not in known)
            item['id'], item['phase'] = created, 'ACKNOWLEDGED_NOT_VERIFIED'
            report['stage'] = 'ack'
            store.receipt(item['marker'], 'ack', save(copy.deepcopy(report)))
            report['stage'] = 'readback'
            actual = observe('profile', created)
            profile_fields(actual, entry['payload'], created, c['allow_unknown_merge'])
            if c['mode'] == 'mother':
                refs = actual.get('unions')
                require(type(refs) is list and len(refs) == 1
                        and canonical_union_reference(refs[0]) == c['union_id'])
                parents.append(created)
            else:
                children.append(created)
            union_state(observe('union', c['union_id']), c['union_id'], parents, children)
            if c['mode'] == 'siblings':
                family = observe('family', created)
                require(type(family) is dict and family.get('focus', {}).get('id') == created
                        and type(family.get('nodes')) is dict)
                union_state(family['nodes'].get(c['union_id']), c['union_id'], parents, children)
            known.add(created)
            item['phase'] = 'VERIFIED'
            report['stage'] = 'final'
            store.receipt(item['marker'], 'final', save(copy.deepcopy(report)))
        report['stage'], report['phase'] = 'complete', 'VERIFIED'
        save(copy.deepcopy(report))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError,
            RecursionError, http.client.HTTPException) as exc:
        if isinstance(exc, TransportStop):
            report['transport_failure'] = {'code': exc.code, **exc.evidence}
        # Deliberately no further remote effects after any anomaly or storage failure.
        report['phase'] = 'STOPPED'
        save(copy.deepcopy(report))
    return report
