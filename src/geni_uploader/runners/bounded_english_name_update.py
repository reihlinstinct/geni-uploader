"""One private deceased profile, English names only, injected effects."""
import copy

from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners import bounded_alias_append as alias
from geni_uploader.runners import bounded_profile_name_update as base
from geni_uploader.runners.one_time_parent_pilot import canonical, sha

SNAPSHOT_KEYS = (*base.SNAPSHOT_KEYS, 'guid', 'nicknames', 'display_name', 'title', 'suffix')


def snapshot(actual):
    require(type(actual) is dict and 'error' not in actual)
    require(actual.get('public') is False and actual.get('is_alive') is False
            and actual.get('claimed') is False)
    base.merge_state(actual)
    require(type(actual.get('guid')) is str and actual['guid'].isdigit()
            and 1 <= len(actual['guid']) <= 30)
    require(actual.get('gender') in ('male', 'female', 'unknown'))
    base.names({k: v for k, v in actual.items() if k in base.NAME_KEYS})
    require('first_name' in actual and type(actual.get('names')) is dict
            and set(actual['names']) == {'en-US', 'he'})
    for fields in actual['names'].values():
        base.names(fields)
        require('first_name' in fields)
    for key in ('display_name', 'title', 'suffix'):
        if key in actual:
            require(type(actual[key]) is str and len(actual[key]) <= 200)
    if 'nicknames' in actual:
        alias.aliases(actual['nicknames'])
    require(type(actual.get('unions')) is list and len(actual['unions']) <= 8)
    unions = [base.union_reference(u) for u in actual['unions']]
    require(len(set(unions)) == len(unions))
    result = {k: copy.deepcopy(actual[k]) for k in SNAPSHOT_KEYS
              if k in actual and k not in ('merge_pending', 'merged_into', 'unions')}
    result['unions'] = sorted(unions)
    return result


def text(value):
    require(type(value) is str and 0 < len(value) <= 200 and value == value.strip()
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'target', 'target_guid', 'expected',
                  'set', 'expires_at', 'accept_unknown_merge_metadata',
                  'accept_english_default_projection'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(value['accept_unknown_merge_metadata'] is True
            and value['accept_english_default_projection'] is True)
    profile_id(value['owner'])
    profile_id(value['target'])
    require(value['owner'] != value['target'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['expected']) is dict and set(value['expected']) <= set(SNAPSHOT_KEYS))
    before = snapshot(value['expected'])
    require(value['target_guid'] == before['guid'])
    change = value['set']
    exact(change, ('names',))
    require(type(change['names']) is dict and set(change['names']) == {'en-US'})
    english = change['names']['en-US']
    require(type(english) is dict)
    for key in ('first_name', 'last_name'):
        require(key in english)
        text(english[key])
    want = copy.deepcopy(before['names']['en-US'])
    want.update(first_name=english['first_name'], last_name=english['last_name'])
    require(english == want and before['names']['en-US'] != want)
    result = copy.deepcopy(value)
    result['expected'] = before
    return result


def payload(c):
    return copy.deepcopy(c['set'])


def marker(c):
    # Baseline, expiry, GUID, source and executor cannot rearm the same English intent.
    return 'english-name-consumed-v1-' + sha(canonical({
        'owner': c['owner'], 'target': c['target'],
        'first_name': c['set']['names']['en-US']['first_name'],
        'last_name': c['set']['names']['en-US']['last_name']}))


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
            r.update(phase='READ_ONLY_ENGLISH_NAME_VERIFIED', stage='complete')
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
        want['names']['en-US'] = copy.deepcopy(c['set']['names']['en-US'])
        observed = snapshot(after)
        before_primary = {k: c['expected'][k] for k in ('first_name', 'last_name')
                          if k in c['expected']}
        observed_primary = {k: observed[k] for k in ('first_name', 'last_name')
                            if k in observed}
        english_primary = {k: c['set']['names']['en-US'][k]
                           for k in ('first_name', 'last_name')}
        # Never POST primary keys. Accept only unchanged or exact English-derived
        # readback, not a third value or a partially projected pair.
        projection = ('UNCHANGED' if observed_primary == before_primary else
                      'ENGLISH_DERIVED' if observed_primary == english_primary else
                      'UNEXPECTED')
        r['primary_projection'] = {'classification': projection,
                                   'before': before_primary, 'after': observed_primary,
                                   'written_keys': []}
        save(copy.deepcopy(r))
        require(projection != 'UNEXPECTED')
        for key in ('first_name', 'last_name'):
            if key in observed:
                want[key] = observed[key]
            else:
                want.pop(key, None)
        require(after.get('id') == c['target'] and observed == want)
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
