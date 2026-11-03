"""One existing private profile's surname correction. Injected effects only."""
import copy
import re

from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.one_time_parent_pilot import canonical, sha

NAME_KEYS = ('first_name', 'middle_name', 'last_name', 'maiden_name')
SNAPSHOT_KEYS = (*NAME_KEYS, 'names', 'gender', 'is_alive', 'public', 'claimed',
                 'merge_pending', 'merged_into', 'unions')


def names(value):
    require(type(value) is dict and set(value) <= set(NAME_KEYS))
    for text in value.values():
        require(type(text) is str and 0 < len(text) <= 200
                and not any(ord(c) < 32 for c in text))


def merge_state(value):
    # Omission remains UNKNOWN. A narrow owner-approved policy accepts that risk.
    require('merge_pending' not in value or value['merge_pending'] is False)
    require('merged_into' not in value or value['merged_into'] in (None, ''))


def union_reference(value):
    require(type(value) is str)
    match = re.fullmatch(r'(?:https://www\.geni\.com/api/)?(union-[0-9]{1,30})', value)
    require(match is not None)
    return match.group(1)


def expected(value, *, birth_surname_only=False):
    require(type(value) is dict and set(value) <= set(SNAPSHOT_KEYS))
    require(value.get('public') is False and value.get('is_alive') is True
            and value.get('claimed') is False)
    merge_state(value)
    require(all(k in value for k in ('first_name', 'gender', 'unions', *(() if birth_surname_only else ('last_name',))))
            and value['gender'] in ('male', 'female', 'unknown'))
    names({k: v for k, v in value.items() if k in NAME_KEYS})
    require(type(value.get('names')) is dict and set(value['names']) == {'en-US', 'he'})
    for fields in value['names'].values():
        names(fields)
        require('first_name' in fields and (birth_surname_only or 'last_name' in fields))
    require(type(value.get('unions')) is list and len(value['unions']) <= 8)
    require(len(set(value['unions'])) == len(value['unions']))
    for union in value['unions']:
        union_reference(union)
    require(len({union_reference(u) for u in value['unions']}) == len(value['unions']))


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'target', 'expected', 'set', 'expires_at'))
    require(type(value['schema']) is int and value['schema'] == 1)
    profile_id(value['owner'])
    profile_id(value['target'])
    require(value['owner'] != value['target'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    change = value['set']
    require(type(change) is dict)
    birth_only = set(change) == {'maiden_name', 'names'}
    expected(value['expected'], birth_surname_only=birth_only)
    if birth_only:
        exact(change, ('maiden_name', 'names'))
        names({'maiden_name': change['maiden_name']})
        require(type(change['names']) is dict and set(change['names']) == {'en-US', 'he'})
        for locale, fields in change['names'].items():
            exact(fields, ('maiden_name',))
            names(fields)
            require('maiden_name' not in value['expected']['names'][locale])
        require('maiden_name' not in value['expected'])
        require(change['maiden_name'] == change['names']['en-US']['maiden_name'])
        result = copy.deepcopy(value)
        result['expected'] = snapshot(dict(value['expected']))
        return result
    exact(change, ('last_name', 'maiden_name', 'names'))
    names({k: change[k] for k in ('last_name', 'maiden_name')})
    require(type(change['names']) is dict and set(change['names']) == {'en-US', 'he'})
    for locale, fields in change['names'].items():
        exact(fields, ('last_name', 'maiden_name'))
        names(fields)
        require(fields['maiden_name'] == value['expected']['names'][locale]['last_name'])
    require(value['expected'].get('maiden_name', change['maiden_name']) == change['maiden_name'])
    for locale, fields in change['names'].items():
        require(value['expected']['names'][locale].get('maiden_name', fields['maiden_name'])
                == fields['maiden_name'])
    require(change['maiden_name'] == value['expected']['last_name'])
    require(change['last_name'] != value['expected']['last_name'])
    result = copy.deepcopy(value)
    result['expected'] = snapshot(dict(value['expected']))
    return result


def snapshot(actual):
    require(type(actual) is dict and 'error' not in actual)
    require(actual.get('public') is False and actual.get('is_alive') is True
            and actual.get('claimed') is False)
    merge_state(actual)
    require(type(actual.get('unions')) is list and len(actual['unions']) <= 8)
    unions = [union_reference(u) for u in actual['unions']]
    require(len(set(unions)) == len(unions))
    result = {k: actual[k] for k in SNAPSHOT_KEYS
              if k in actual and k not in ('merge_pending', 'merged_into', 'unions')}
    result['unions'] = sorted(unions)
    return result


def graph(actual, target):
    require(type(actual) is dict and actual.get('focus', {}).get('id') == target)
    nodes = actual.get('nodes')
    require(type(nodes) is dict and target in nodes and 1 <= len(nodes) <= 64)
    result = {}
    for node, body in nodes.items():
        require(type(body) is dict and type(body.get('edges')) is dict)
        result[node] = body['edges']
    return copy.deepcopy(result)


def marker(c):
    # Neither expiry nor executor/source commit can mint another send.
    return 'profile-name-consumed-v1-' + sha(canonical({
        k: c[k] for k in ('owner', 'target', 'expected', 'set')}))


def execute(value, io, store, save, clock, *, read_only):
    c = plan(value)
    require(type(read_only) is bool)
    r = {'phase': 'STOPPED', 'stage': 'preflight', 'retry_allowed': False,
         'responses': [], 'read_only': read_only, 'target': c['target']}

    def now():
        require(clock() < c['expires_at'])

    def read(kind, target):
        now()
        r['stage'] = 'read_' + kind
        actual = getattr(io, 'get_' + kind)(target)
        r['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(r))
        return actual

    try:
        owner = read('profile', 'profile')
        require(owner.get('id') == c['owner'])
        full = ' '.join(owner.get(k, '') for k in NAME_KEYS[:3])
        require(all(w.casefold() in full.casefold().split() for w in c['expect_name'].split()))
        before = read('profile', c['target'])
        require(before.get('id') == c['target'] and snapshot(before) == c['expected'])
        edges = graph(read('family', c['target']), c['target'])
        if read_only:
            r.update(phase='READ_ONLY_NAME_VERIFIED', stage='complete')
            save(copy.deepcopy(r))
            return r
        intent = marker(c)
        now()
        r['stage'] = 'before'
        store.receipt(intent, 'before', save(copy.deepcopy(r)))
        now()
        r['stage'] = 'consume'
        store.consume(intent)
        now()
        r.update(stage='send', phase='UNCERTAIN')
        response = io.update(c['target'], c['set'])
        require(type(response) is dict and 'error' not in response and response.get('id') == c['target'])
        r['update_response'] = response
        r.update(stage='ack', phase='ACKNOWLEDGED_NOT_VERIFIED')
        now()
        store.receipt(intent, 'ack', save(copy.deepcopy(r)))
        after = read('profile', c['target'])
        want = copy.deepcopy(c['expected'])
        for key in ('last_name', 'maiden_name'):
            if key in c['set']:
                want[key] = c['set'][key]
        for locale, fields in c['set']['names'].items():
            want['names'][locale].update(fields)
        require(after.get('id') == c['target'] and snapshot(after) == want)
        require(graph(read('family', c['target']), c['target']) == edges)
        now()
        r.update(phase='VERIFIED', stage='final')
        store.receipt(intent, 'final', save(copy.deepcopy(r)))
        r['stage'] = 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
