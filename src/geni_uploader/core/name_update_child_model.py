"""Exact existing-name update followed by one dependent child create. Injected IO only."""
import copy

import geni_uploader.core.geni_union_child_model as child
from geni_uploader.core.people import exact, require, text
from geni_uploader.runners.one_time_parent_pilot import canonical, merge_clear, sha

SNAPSHOT = ('id', 'guid', 'first_name', 'middle_name', 'last_name', 'maiden_name',
            'names', 'gender', 'public', 'is_alive', 'claimed', 'about_me', 'unions')


def snapshot(actual):
    require(type(actual) is dict and 'error' not in actual)
    merge_clear(actual, True)
    require(actual.get('public') is False and actual.get('is_alive') is True
            and actual.get('claimed') is False)
    return {key: copy.deepcopy(actual[key]) for key in SNAPSHOT if key in actual}


def after(c):
    result = copy.deepcopy(c['expected'])
    result.update(copy.deepcopy(c['set']))
    return result


def plan(value):
    exact(value, ('schema', 'owner', 'expect_name', 'anchor', 'target', 'union',
                  'expected', 'set', 'create', 'expires_at'))
    require(type(value['schema']) is int and value['schema'] == 1)
    c = child.plan(value['create'])
    require(len(c['entries']) == 1 and not c.get('accept_first_child_omission', False))
    require(all(value[key] == c[key] for key in ('owner', 'anchor', 'expect_name', 'expires_at'))
            and value['union'] == c['target_union'])
    target = value['target']; child.shared.profile_id(target)
    require(target != c['owner'] and c['family'][value['union']].get(target) == 'child')
    before = value['expected']
    require(snapshot(before) == before and before.get('id') == target
            and {'guid', 'names', 'gender', 'about_me', 'unions', 'first_name', 'last_name'} <= set(before))
    require(before['gender'] in ('male', 'female'))
    require(type(before['unions']) is list and len(before['unions']) == 1
            and before['unions'] == ['https://www.geni.com/api/' + value['union']])
    change = value['set']; exact(change, ('first_name', 'last_name', 'names'))
    for leaf in (change['first_name'], change['last_name']): text(leaf)
    require(type(change['names']) is dict and set(change['names']) == {'he', 'en-US'}
            and set(before['names']) == {'he', 'en-US'}
            and change['names']['he'] == before['names']['he'])
    for locale in ('he', 'en-US'):
        exact(change['names'][locale], ('first_name', 'last_name'))
        for leaf in change['names'][locale].values(): text(leaf)
    require(change['first_name'] == change['names']['en-US']['first_name']
            and change['last_name'] == change['names']['en-US']['last_name']
            and change != {key: before[key] for key in change})
    expected_pin = {key: leaf for key, leaf in after(value).items()
                    if key in ('first_name', 'middle_name', 'last_name', 'maiden_name',
                               'gender', 'is_alive', 'public', 'claimed')}
    require(c['profiles'][target] == expected_pin)
    return copy.deepcopy(value)


def marker(c):
    return 'mixed-name-update-consumed-v1-' + sha(canonical({
        key: c[key] for key in ('owner', 'target', 'expected', 'set')}))


def proofs(c, profile, anchor, reciprocal, union, *, updated):
    require(snapshot(profile) == (after(c) if updated else c['expected']))
    graph = c['create']['family']; target = c['union']
    child.shared.graph_check(anchor, c['anchor'], graph,
                             external_edges=c['create']['external_edges'])
    child.shared.graph_check(reciprocal, c['target'], {target: graph[target]},
                             external_edges=child.shared.boundary_edges(c['create'], target, graph[target]))
    require(child.union_check(union, target, graph[target], False) == [])


def execute(value, io, store, save, clock):
    c = plan(value)
    r = {'phase': 'STOPPED', 'stage': 'preflight', 'retry_allowed': False,
         'update_marker': marker(c), 'update_phase': 'NOT_SENT', 'responses': []}
    def now(): require(clock() < c['expires_at'])
    def read(kind, target):
        now(); r['stage'] = 'read_' + kind
        actual = getattr(io, 'get_' + kind)(target)
        r['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(r))
        return actual
    def verify(updated):
        proofs(c, read('profile', c['target']), read('family', c['anchor']),
               read('family', c['target']), read('union', c['union']), updated=updated)
    try:
        owner = read('profile', 'profile')
        require(owner.get('id') == c['owner'])
        full = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in full.casefold().split() for w in c['expect_name'].split()))
        verify(False)
        now(); r['stage'] = 'before'
        store.receipt(marker(c), 'before', save(copy.deepcopy(r)))
        now(); store.consume(marker(c))
        now(); r.update(stage='update', update_phase='UNCERTAIN')
        ack = io.update(c['target'], c['set'])
        r['update_response'] = ack
        require(type(ack) is dict and 'error' not in ack and ack.get('id') == c['target'])
        r.update(stage='ack', update_phase='ACKNOWLEDGED_NOT_VERIFIED')
        now(); store.receipt(marker(c), 'ack', save(copy.deepcopy(r)))
        verify(True)
        now(); r.update(stage='final_update', update_phase='VERIFIED')
        store.receipt(marker(c), 'final', save(copy.deepcopy(r)))
        io.verified_update()  # independent IO proofs required after durable receipt
        now(); r['stage'] = 'create'
        r['create_result'] = child.execute(c['create'], io, store, save, clock)
        require(r['create_result']['phase'] == 'VERIFIED')
        now(); r.update(phase='VERIFIED', stage='complete')
    except Exception:  # noqa: BLE001 - stop all later effects, no automatic repair
        r['phase'] = 'STOPPED'
    save(copy.deepcopy(r))
    return r
