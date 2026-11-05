"""One private deceased profile, exact append-only aliases, injected effects."""
import copy
import unicodedata

from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners import bounded_profile_name_update as base
from geni_uploader.runners.one_time_parent_pilot import canonical, sha

SNAPSHOT_KEYS = (*base.SNAPSHOT_KEYS, 'nicknames', 'display_name', 'title', 'suffix')


def aliases(value):
    require(type(value) is list and len(value) <= 32)
    for text in value:
        require(type(text) is str and 0 < len(text) <= 200 and text == text.strip()
                and ',' not in text and not any(ord(c) < 32 or ord(c) == 127 for c in text))
    require(len(set(value)) == len(value))
    return value


def snapshot(actual):
    require(type(actual) is dict and 'error' not in actual)
    require(actual.get('public') is False and actual.get('is_alive') is False
            and actual.get('claimed') is False)
    base.merge_state(actual)
    require(all(k in actual for k in ('first_name', 'last_name', 'gender', 'names', 'unions')))
    require(actual['gender'] in ('male', 'female', 'unknown'))
    base.names({k: v for k, v in actual.items() if k in base.NAME_KEYS})
    require(type(actual['names']) is dict and set(actual['names']) == {'en-US', 'he'})
    for fields in actual['names'].values():
        base.names(fields)
        require('first_name' in fields and 'last_name' in fields)
    for key in ('display_name', 'title', 'suffix'):
        if key in actual:
            require(type(actual[key]) is str and len(actual[key]) <= 200)
    aliases(actual.get('nicknames', []))
    require(type(actual['unions']) is list and len(actual['unions']) <= 8)
    unions = [base.union_reference(u) for u in actual['unions']]
    require(len(set(unions)) == len(unions))
    result = {k: copy.deepcopy(actual[k]) for k in SNAPSHOT_KEYS
              if k in actual and k not in ('merge_pending', 'merged_into', 'unions')}
    result['unions'] = sorted(unions)
    return result


def comparison_key(text):
    """Collision key only; never rewrite stored or approved alias text."""
    return unicodedata.normalize('NFC', ' '.join(
        unicodedata.normalize('NFC', text).split()).casefold())


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'target', 'expected', 'append',
                  'expires_at', 'accept_unknown_merge_metadata'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(value['accept_unknown_merge_metadata'] is True)
    profile_id(value['owner'])
    profile_id(value['target'])
    require(value['owner'] != value['target'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['expected']) is dict and set(value['expected']) <= set(SNAPSHOT_KEYS))
    before = snapshot(value['expected'])
    added = aliases(value['append'])
    require(1 <= len(added) <= 4)
    old = before.get('nicknames', [])
    require(not set(old).intersection(added))
    aliases(old + added)
    # Reject ambiguity, never normalize approved text or infer vendor behavior.
    for text in added:
        require(unicodedata.is_normalized('NFC', text)
                and '  ' not in text
                and not any(unicodedata.category(c) in ('Cf', 'Zl', 'Zp', 'Cc')
                            or (c.isspace() and c != ' ') for c in text))
    folded = [comparison_key(text) for text in old + added]
    require(len(set(folded)) == len(folded))
    result = copy.deepcopy(value)
    result['expected'] = before
    return result


def payload(c):
    return {'nicknames': ','.join(c['expected'].get('nicknames', []) + c['append'])}


def marker(c):
    return 'alias-append-consumed-v1-' + sha(canonical({
        'owner': c['owner'], 'target': c['target'], 'append': sorted(c['append'])}))


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
        full = ' '.join(owner.get(k, '') for k in base.NAME_KEYS[:3])
        require(all(w.casefold() in full.casefold().split() for w in c['expect_name'].split()))
        before = read('profile', c['target'])
        require(before.get('id') == c['target'] and snapshot(before) == c['expected'])
        edges = base.graph(read('family', c['target']), c['target'])
        if read_only:
            r.update(phase='READ_ONLY_ALIAS_VERIFIED', stage='complete')
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
        response = io.update(c['target'], payload(c))
        require(type(response) is dict and 'error' not in response
                and response.get('id') == c['target'])
        r['update_response'] = response
        r.update(stage='ack', phase='ACKNOWLEDGED_NOT_VERIFIED')
        now()
        store.receipt(intent, 'ack', save(copy.deepcopy(r)))
        after = read('profile', c['target'])
        want = copy.deepcopy(c['expected'])
        want['nicknames'] = want.get('nicknames', []) + c['append']
        require(after.get('id') == c['target'] and snapshot(after) == want)
        require(base.graph(read('family', c['target']), c['target']) == edges)
        now()
        r.update(phase='VERIFIED', stage='final')
        store.receipt(intent, 'final', save(copy.deepcopy(r)))
        r['stage'] = 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
