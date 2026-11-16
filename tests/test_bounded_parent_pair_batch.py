"""Synthetic pure batch tests. No credentials or network."""
import copy

import pytest

from geni_uploader.core import bounded_parent_pair_batch as m
from geni_uploader.runners import bounded_parent_addition as legacy
from tests import test_bounded_relative_parent as f
from tests.test_guarded_family_additions import Store


def config(sibling=True):
    p = f.plan(spouse=True)
    group = {k: copy.deepcopy(p[k]) for k in ('anchor', 'profiles', 'family', 'external_edges',
              'path', 'path_unions', 'path_families', 'path_union_members')}
    group['entries'] = [{'key': 'zz-first', 'payload': f.fixture.body('ZZ-First', 'male')},
                        {'key': 'zz-second', 'payload': f.fixture.body('ZZ-Second', 'female')}]
    group['sibling'] = ({'key': 'zz-sibling', 'payload': f.fixture.body('ZZ-Sibling', 'female')}
                        if sibling else None)
    return {'schema': 1, 'owner': p['owner'], 'expect_name': p['expect_name'], 'expires_at': 999,
                'allow_unknown_merge': True, 'allow_new_unknown_merge': True,
                'accept_hidden_duplicate_risk': True, 'accept_private_create_risk': True,
                'accept_union_selection_risk': True, 'max_requests': 200, 'groups': [group]}


class IO:
    def __init__(self, c):
        self.c = copy.deepcopy(c); self.posts = []; self.reads = []
        self.profiles = {n: dict(v, id=n) for g in c['groups'] for n, v in g['profiles'].items()}
        self.graphs = {n: copy.deepcopy(b) for g in c['groups']
                       for n, b in g['path_families'].items()}
        self.created = {}; self.unions = {}; self.next = 990100
        for g in c['groups']:
            self.unions.update(copy.deepcopy(g['path_union_members']))

    def get_profile(self, n):
        self.reads.append(('profile', n))
        return copy.deepcopy(self.profiles[self.c['owner'] if n == 'profile' else n])

    def get_family(self, n):
        self.reads.append(('family', n))
        b = self.graphs[n]
        v = f.fixture.family(n, b['family'])
        for p, edges in b['external_edges'].items():
            v['nodes'][p]['edges'].update({u: {'rel': r} for u, r in edges.items()})
        return v

    def get_union(self, u):
        self.reads.append(('union', u)); d = self.unions[u]
        return {'id': u, 'partners': [p for p, r in d.items() if r == 'partner'],
                'children': [p for p, r in d.items() if r == 'child']}

    def add(self, anchor, body, role):
        self.posts.append((anchor, body, role)); n = 'profile-' + str(self.next); self.next += 1
        u = self.created.setdefault(anchor, 'union-' + str(self.next + 100))
        graph = self.graphs[anchor]['family']; graph.setdefault(u, {anchor: 'child'})[n] = role
        self.unions[u] = copy.deepcopy(graph[u]); self.profiles[n] = dict(body, id=n, claimed=False)
        # Every parent/child proof sees all members in the new union, and anchor
        # boundary edges preserve its existing household without expanding it.
        for p in graph[u]:
            if p == anchor: continue
            self.graphs[p] = {'family': {u: copy.deepcopy(graph[u])},
                              'external_edges': {anchor: {x: v[anchor]
                                  for x, v in graph.items() if x != u and anchor in v}}}
        for focus, b in self.graphs.items():
            if focus == anchor or u in b['family']: continue
            if anchor in {p for v in b['family'].values() for p in v}:
                b['external_edges'].setdefault(anchor, {})[u] = 'child'
        return {'id': n}

    def add_parent(self, a, b): return self.add(a, b, 'partner')
    def add_sibling(self, a, b): return self.add(a, b, 'child')


def run(c=None, io=None, st=None):
    c = c or config(); io = io or IO(c); st = st or Store(); saved = []
    r = m.execute(c, io, st, lambda x: saved.append(copy.deepcopy(x)) or b'ZZ-cipher', lambda: 200)
    return r, io, st, saved


@pytest.mark.parametrize('sibling', [True, False])
def test_complete_pair_and_optional_sibling(sibling):
    c = config(sibling); before = copy.deepcopy(c); r, io, st, saved = run(c)
    assert r['phase'] == 'VERIFIED'
    assert len(io.posts) == (3 if sibling else 2)
    assert r['requests'] == m.inventory(c) == len(io.reads) + len(io.posts)
    assert len(st.consumed) == len(io.posts)
    assert c == before and saved[-1] == r and not r['production_enabled']
    assert len({x['union_id'] for x in r['items']}) == 1


@pytest.mark.parametrize('field,bad', [('max_requests', True), ('max_requests', 201),
    ('max_requests', 1), ('allow_new_unknown_merge', None), ('allow_unknown_merge', 'yes'),
    ('accept_hidden_duplicate_risk', False), ('expires_at', True)])
def test_bad_top_level_before_io(field, bad):
    c = config(); c[field] = bad; io = IO(config())
    with pytest.raises(m.Blocked): run(c, io)
    assert not io.reads and not io.posts


@pytest.mark.parametrize('change', ['same_gender', 'duplicate_key', 'duplicate_name',
                                   'unknown_life', 'extra_group', 'wrong_path'])
def test_invalid_groups(change):
    c = config(); g = c['groups'][0]
    if change == 'same_gender': g['entries'][1]['payload']['gender'] = 'male'
    if change == 'duplicate_key': g['sibling']['key'] = g['entries'][0]['key']
    if change == 'duplicate_name': g['sibling']['payload'] = copy.deepcopy(g['entries'][0]['payload'])
    if change == 'unknown_life': g['entries'][0]['payload']['is_alive'] = None
    if change == 'extra_group': c['groups'].append(copy.deepcopy(g))
    if change == 'wrong_path': g['path'].reverse()
    with pytest.raises(m.Blocked): m.plan(c)


@pytest.mark.parametrize('stage,count', [('before', 0), ('ack', 1), ('final', 1)])
def test_storage_failure_leaves_no_next_send(stage, count):
    r, io, _, _ = run(st=Store(stage))
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


@pytest.mark.parametrize('field,bad', [('merge_pending', True), ('merge_pending', 0),
    ('public', True), ('claimed', True), ('is_alive', False)])
def test_created_profile_failure_blocks_next_send(field, bad):
    io = IO(config()); old = io.get_profile
    def get(n):
        v = old(n)
        if n not in io.c['groups'][0]['profiles'] and n != 'profile': v[field] = bad
        return v
    io.get_profile = get
    r, io, _, _ = run(io=io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1


def test_new_merge_policy_separate_and_explicit():
    c = config(); c['allow_new_unknown_merge'] = False
    r, io, _, _ = run(c)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1


@pytest.mark.parametrize('fault', ['wrong_union', 'extra_child', 'ack_existing', 'send_error'])
def test_uncertain_or_wrong_relationship_no_more_send(fault):
    io = IO(config()); old = io.add_parent
    def add(a, b):
        ack = old(a, b)
        if fault == 'ack_existing': return {'id': a}
        if fault == 'send_error': raise OSError('ZZ')
        u = io.created[a]
        if fault == 'wrong_union': io.unions[u]['profile-990004'] = 'partner'
        if fault == 'extra_child': io.graphs[a]['family'][u]['profile-990004'] = 'child'
        return ack
    io.add_parent = add
    r, io, st, _ = run(io=io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == len(st.consumed) == 1


def test_marker_parent_compatibility_and_replay_stays_consumed():
    c = config(); g = c['groups'][0]; e = g['entries'][0]
    assert m.marker(c, g['anchor'], e, 'parent') == legacy.marker(
        {'owner': c['owner'], 'anchor': g['anchor'], 'entry': e})
    r, _, st, _ = run(c)
    assert r['phase'] == 'VERIFIED'
    c['expires_at'] += 100
    r, io, _, _ = run(c, st=st)
    assert r['phase'] == 'STOPPED' and not io.posts


def four_groups():
    c = config(); groups = []
    for i in range(4):
        g = copy.deepcopy(c['groups'][0]); original = g['anchor']
        new = 'profile-' + str(990200 + i)
        def replace(v, original=original, new=new):
            if isinstance(v, dict): return {replace(k): replace(x) for k, x in v.items()}
            if isinstance(v, list): return [replace(x) for x in v]
            return new if v == original else v
        g = replace(g)
        # Distinct anchor household union, shared owner whose own graph must
        # include each household in which the owner is a child.
        old_union = g['path_unions'][0]; union = 'union-' + str(980200 + i)
        def swap(v, old_union=old_union, union=union):
            if isinstance(v, dict): return {swap(k): swap(x) for k, x in v.items()}
            if isinstance(v, list): return [swap(x) for x in v]
            return union if v == old_union else v
        g = swap(g)
        for j, e in enumerate(g['entries']):
            e.update(key=f'zz-group-{i}-parent-{j}',
                     payload=f.fixture.body(f'ZZ-Parent-{i}-{j}', 'male' if j == 0 else 'female'))
        if i == 3:
            g['sibling'] = {'key': 'zz-group-sibling', 'payload': f.fixture.body('ZZ-Sibling', 'female')}
        else: g['sibling'] = None
        groups.append(g)
    # Use a distinct path owner per group is forbidden. Build one shared owner
    # graph with all four explicit spouse connections, preserving complete edges.
    shared = {}
    for g in groups: shared.update(g['family'])
    for g in groups:
        g['path_families'][c['owner']] = {'family': copy.deepcopy(shared), 'external_edges': {}}
        spouse = f.SPOUSE
        for u, members in shared.items():
            if u not in g['family']:
                for p in (c['owner'], spouse):
                    g['external_edges'].setdefault(p, {})[u] = members[p]
        g['path_families'][g['anchor']]['external_edges'] = copy.deepcopy(g['external_edges'])
    c['groups'] = groups
    return c


def test_four_parent_pairs_one_sibling_nine_verified():
    c = four_groups(); r, io, st, _ = run(c)
    assert r['phase'] == 'VERIFIED', (r['stage'], r['group'], len(io.posts))
    assert len(io.posts) == len(st.consumed) == 9
    assert r['requests'] == m.inventory(c) <= m.HARD_REQUEST_CEILING
    assert len({x['union_id'] for x in r['items']}) == 4


@pytest.mark.parametrize('bad', [True, 0, 'false'])
def test_positive_or_malformed_existing_merge_stops_before_any_create(bad):
    c = config(); io = IO(c); io.profiles[c['groups'][0]['anchor']]['merge_pending'] = bad
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_all_groups_preflight_before_first_send():
    c = four_groups(); io = IO(c)
    io.profiles[c['groups'][-1]['anchor']]['public'] = True
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_later_group_stop_preserves_earlier_verified_results():
    c = four_groups(); io = IO(c); old = io.get_profile; seen = 0
    last = c['groups'][-1]['anchor']
    def get(n):
        nonlocal seen
        v = old(n)
        if n == last:
            seen += 1
            if seen == 2: v['merge_pending'] = True
        return v
    io.get_profile = get
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 6
    assert all(x['phase'] == 'VERIFIED' for x in r['items'])


def test_cross_group_conflicting_owner_baseline_rejected():
    c = four_groups(); c['groups'][-1]['profiles'][c['owner']]['public'] = True
    with pytest.raises(m.Blocked): m.plan(c)


def test_expired_model_has_no_calls():
    c = config(); io = IO(c); st = Store()
    r = m.execute(c, io, st, lambda _: b'ZZ', lambda: 1000)
    assert r['phase'] == 'STOPPED' and not io.reads and not io.posts


def test_sibling_marker_stable_across_runtime_and_window():
    c = config(); g = c['groups'][0]
    a = m.marker(c, g['anchor'], g['sibling'], 'sibling')
    c['expires_at'] += 100; c['allow_new_unknown_merge'] = False
    assert a == m.marker(c, g['anchor'], g['sibling'], 'sibling')
