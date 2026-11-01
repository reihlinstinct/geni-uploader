import copy

import pytest

import guarded_family_additions as g
from people_core import Blocked
from tests.test_one_time_parent_pilot import BODY


def fixture(mode='mother'):
    father = copy.deepcopy(BODY)
    mother = dict(copy.deepcopy(BODY), gender='female')
    mother['first_name'] = 'ZZ-Mother'
    for names in mother['names'].values():
        names['first_name'] = 'ZZ-Mother'
    entries = [{'key': 'zz-mother', 'payload': mother}]
    parents = [{'id': 'profile-999002', 'payload': father}]
    if mode == 'siblings':
        parents.append({'id': 'profile-999003', 'payload': mother})
        entries = []
        for i in range(4):
            b = copy.deepcopy(BODY)
            b['first_name'] = 'ZZ-Sibling' + str(i)
            for names in b['names'].values():
                names['first_name'] = b['first_name']
            entries.append({'key': 'zz-sibling-' + str(i), 'payload': b})
    return {'schema': 1, 'mode': mode, 'owner': 'profile-999001',
            'expect_name': 'ZZ-Root ZZ-Family', 'union_id': 'union-999001',
            'parents': parents, 'children': ['profile-999001'], 'entries': entries,
            'expires_at': 999, 'allow_unknown_merge': True,
            'accept_hidden_duplicate_risk': True, 'accept_private_create_risk': True,
            'accept_union_selection_risk': True}


def graph(focus, union, parents, children):
    roles = dict.fromkeys(parents, 'partner')
    roles.update(dict.fromkeys(children, 'child'))
    nodes = {node: {'id': node, 'url': 'https://www.geni.com/api/' + node,
                    'edges': {union: {'rel': role}}} for node, role in roles.items()}
    nodes[union] = {'url': 'https://www.geni.com/api/' + union, 'status': 'spouse',
                    'edges': {node: {'rel': role} for node, role in roles.items()}}
    return {'focus': {'id': focus}, 'nodes': nodes}


class IO:
    def __init__(self, cfg, anomaly=None):
        self.cfg = cfg
        self.profiles = {x['id']: dict(g.vendor_payload(x['payload']), id=x['id'],
            unions=['https://www.geni.com/api/' + cfg['union_id']]) for x in cfg['parents']}
        self.parents = [x['id'] for x in cfg['parents']]
        self.children = list(cfg['children'])
        self.posts = []
        self.anomaly = anomaly
        self.gets = 0

    def get_profile(self, target):
        self.gets += 1
        if target == 'profile':
            return {'id': self.cfg['owner'], 'first_name': 'ZZ-Root', 'last_name': 'ZZ-Family'}
        value = copy.deepcopy(self.profiles[target])
        if self.anomaly == 'privacy' and target.startswith('profile-99901'):
            value['public'] = True
        return value

    def get_union(self, target):
        self.gets += 1
        return {'id': target, 'partners': list(self.parents), 'children': list(self.children)}

    def get_family(self, target):
        self.gets += 1
        return graph(target, self.cfg['union_id'], self.parents, self.children)

    def add(self, owner, route, body):
        self.posts.append((owner, route, body))
        if self.anomaly == 'send':
            raise OSError('ZZ-lost-ack')
        target = 'profile-' + str(999010 + len(self.posts))
        self.profiles[target] = dict(copy.deepcopy(body), id=target,
                                    unions=[self.cfg['union_id']])
        if self.anomaly != 'wrong_union':
            (self.parents if route == 'add-parent' else self.children).append(target)
        return {'id': target}


class Store:
    def __init__(self, fail=None):
        self.consumed = set()
        self.fail = fail
        self.events = []

    def consume(self, marker):
        if marker in self.consumed:
            raise Blocked()
        self.consumed.add(marker)
        self.events.append('consume')

    def receipt(self, marker, stage, ciphertext):
        self.events.append(stage)
        if self.fail == stage:
            raise OSError('ZZ-storage')
        assert ciphertext == b'ZZ-cipher'


def run(cfg, anomaly=None, fail=None, store=None):
    io, st, saved = IO(cfg, anomaly), store or Store(fail), []

    def save(r):
        saved.append(copy.deepcopy(r))
        return b'ZZ-cipher'
    return g.execute(cfg, io, st, save, lambda: 200), io, st, saved


@pytest.mark.parametrize('mode,count', [('mother', 1), ('siblings', 4)])
def test_complete_ordered_names_only(mode, count):
    c = fixture(mode)
    r, io, st, saved = run(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == count
    assert [x['phase'] for x in r['items']] == ['VERIFIED'] * count
    assert len(st.consumed) == count and st.events == ['before', 'consume', 'ack', 'final'] * count
    assert all('birth' not in x[2] and x[2]['public'] is False for x in io.posts)
    assert len(saved) > count * 3 and c == fixture(mode)


@pytest.mark.parametrize('anomaly', ['privacy', 'send', 'wrong_union'])
def test_stop_on_first_anomaly_no_retry(anomaly):
    r, io, st, _ = run(fixture('siblings'), anomaly)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1
    assert len(r['items']) == 1


@pytest.mark.parametrize('stage,count', [('before', 0), ('ack', 1), ('final', 1)])
def test_receipt_failure_forbids_next_create(stage, count):
    r, io, _, _ = run(fixture('siblings'), fail=stage)
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


def test_repeat_blocked_even_with_new_expiry():
    c = fixture()
    _, _, st, _ = run(c)
    c['expires_at'] = 1000
    r, io, _, _ = run(c, store=st)
    assert r['phase'] == 'STOPPED' and io.posts == []


@pytest.mark.parametrize('key,value', [('accept_union_selection_risk', False),
    ('expires_at', True), ('owner', 'union-999001'), ('union_id', 'https://evil.invalid/union-1')])
def test_bad_plan_rejected_before_effects(key, value):
    c = fixture()
    c[key] = value
    with pytest.raises(Blocked):
        run(c)


def test_expiry_stops_before_any_effect():
    c = fixture()
    c['expires_at'] = 100
    r, io, st, _ = run(c)
    assert r['phase'] == 'STOPPED' and io.posts == [] and io.gets == 0
    assert not st.consumed


def test_second_item_failure_preserves_first_and_skips_rest():
    cfg = fixture('siblings')
    io = IO(cfg)
    original = io.add

    def add(owner, route, body):
        if len(io.posts) == 1:
            io.anomaly = 'send'
        return original(owner, route, body)
    io.add = add
    st = Store()
    r = g.execute(cfg, io, st, lambda r: b'ZZ-cipher', lambda: 200)
    assert len(io.posts) == 2 and len(st.consumed) == 2
    assert r['items'][0]['phase'] == 'VERIFIED' and r['items'][1]['phase'] == 'UNCERTAIN'
    assert r['phase'] == 'STOPPED'


def test_local_capture_failure_forbids_remote_effects():
    cfg, st = fixture(), Store()
    io = IO(cfg)
    attempts = []

    def save(report):
        attempts.append(1)
        raise OSError('ZZ-capture')
    with pytest.raises(OSError):
        g.execute(cfg, io, st, save, lambda: 200)
    assert io.gets == 1 and not io.posts and not st.events


def test_sibling_missing_direct_backreference_stops_after_one():
    cfg = fixture('siblings')
    io = IO(cfg)
    io.get_family = lambda target: {'focus': {'id': target}, 'nodes': {}}
    r = g.execute(cfg, io, Store(), lambda r: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1
    assert r['items'][0]['phase'] == 'ACKNOWLEDGED_NOT_VERIFIED'


def test_remaining_three_plan_verifies_prior_child_and_preserves_marker():
    cfg = fixture('siblings')
    prior = cfg['entries'].pop(0)
    cfg['children'].append('profile-999009')
    cfg['verified_children'] = [dict(prior, id='profile-999009')]
    io = IO(cfg)
    io.profiles['profile-999009'] = dict(g.vendor_payload(prior['payload']), id='profile-999009')
    st = Store()
    old_marker = g.marker(cfg, prior)
    st.consumed.add(old_marker)
    r = g.execute(cfg, io, st, lambda r: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 3
    assert old_marker in st.consumed and len(st.consumed) == 4


def test_unverified_existing_child_blocks_before_effects():
    cfg = fixture('siblings')
    cfg['children'].append('profile-999009')
    with pytest.raises(Blocked):
        run(cfg)


@pytest.mark.parametrize('count', [1, 2, 3, 4])
def test_explicit_remaining_batch_size(count):
    cfg = fixture('siblings')
    cfg['entries'] = cfg['entries'][:count]
    r, io, _, _ = run(cfg)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == count


def test_union_get_transport_failure_retains_read_stage():
    cfg = fixture('siblings')
    io = IO(cfg)
    original = io.get_union

    def get_union(target):
        if io.posts:
            raise g.TransportStop('response_status', evidence={
                'host': 'www.geni.com', 'error_type': 'response_status', 'status_class': '5xx'})
        return original(target)
    io.get_union = get_union
    r = g.execute(cfg, io, Store(), lambda r: b'ZZ-cipher', lambda: 200)
    assert r['stage'] == 'read_union' and r['phase'] == 'STOPPED'
    assert r['transport_failure']['status_class'] == '5xx' and len(io.posts) == 1


def remaining_fixture():
    cfg = fixture('siblings')
    prior = cfg['entries'].pop(0)
    cfg['children'].append('profile-999009')
    cfg['verified_children'] = [dict(prior, id='profile-999009')]
    return cfg, prior


@pytest.mark.parametrize('anomaly', ['key', 'id', 'name'])
def test_invalid_verified_child_plan_rejected_before_reads_or_sends(anomaly):
    cfg, prior = remaining_fixture()
    if anomaly == 'key':
        cfg['entries'][0]['key'] = prior['key']
    elif anomaly == 'id':
        cfg['verified_children'][0]['id'] = 'profile-999008'
    else:
        cfg['entries'][0]['payload'] = copy.deepcopy(prior['payload'])
    io = IO(cfg)
    with pytest.raises(Blocked):
        g.execute(cfg, io, Store(), lambda r: b'ZZ-cipher', lambda: 200)
    assert io.posts == [] and io.gets == 0


@pytest.mark.parametrize('anomaly', ['payload', 'family'])
def test_verified_child_readback_mismatch_stops_before_send(anomaly):
    cfg, prior = remaining_fixture()
    io = IO(cfg)
    io.profiles['profile-999009'] = dict(g.vendor_payload(prior['payload']), id='profile-999009')
    if anomaly == 'payload':
        io.profiles['profile-999009']['public'] = True
    else:
        io.get_family = lambda target: {'focus': {'id': target}, 'nodes': {}}
    st = Store()
    r = g.execute(cfg, io, st, lambda r: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and io.posts == [] and st.consumed == set()


def corrupt_graph(value, anomaly, focus, union, parents, children):
    u = value['nodes'][union]
    node = parents[0]
    if anomaly == 'missing_union':
        del value['nodes'][union]
    elif anomaly == 'wrong_focus':
        value['focus']['id'] = node
    elif anomaly == 'extra_node':
        value['nodes']['profile-999099'] = {}
    elif anomaly == 'missing_profile':
        del value['nodes'][node]
    elif anomaly == 'wrong_union_url':
        u['url'] += '?ZZ=1'
    elif anomaly == 'wrong_union_id':
        u['id'] = 'union-999099'
    elif anomaly == 'wrong_status':
        u['status'] = 'ex_spouse'
    elif anomaly == 'missing_edge':
        del u['edges'][node]
    elif anomaly == 'extra_edge':
        u['edges']['profile-999099'] = {'rel': 'child'}
    elif anomaly == 'wrong_role':
        u['edges'][node] = {'rel': 'child'}
    elif anomaly == 'adoption_role':
        u['edges'][children[0]] = {'rel': 'adopted_child'}
    elif anomaly == 'foster_role':
        value['nodes'][focus]['edges'][union] = {'rel': 'foster_child'}
    elif anomaly == 'edge_extra':
        u['edges'][node]['adopted'] = True
    elif anomaly == 'adopted_children':
        u['adopted_children'] = []
    elif anomaly == 'foster_children':
        u['foster_children'] = [focus]
    elif anomaly == 'reciprocal_missing':
        value['nodes'][node]['edges'] = {}
    elif anomaly == 'reciprocal_wrong':
        value['nodes'][node]['edges'][union]['rel'] = 'child'
    elif anomaly == 'reciprocal_extra':
        value['nodes'][node]['edges']['union-999099'] = {'rel': 'partner'}
    elif anomaly == 'profile_id':
        value['nodes'][node]['id'] = focus
    elif anomaly == 'profile_url':
        value['nodes'][node]['url'] = 'https://evil.invalid/' + node
    elif anomaly == 'focus_url':
        value['focus']['url'] = 'https://evil.invalid/' + focus
    elif anomaly == 'focus_edges':
        value['focus']['edges'] = {union: {'rel': 'partner'}}
    elif anomaly == 'profile_adopted':
        value['nodes'][node]['adopted_children'] = []
    elif anomaly == 'focus_foster':
        value['focus']['foster_children'] = []
    elif anomaly == 'top_extra':
        value['extra'] = True
    else:
        raise AssertionError(anomaly)
    return value


GRAPH_ANOMALIES = ['missing_union', 'wrong_focus', 'extra_node', 'missing_profile',
    'wrong_union_url', 'wrong_union_id', 'wrong_status', 'missing_edge', 'extra_edge',
    'wrong_role', 'adoption_role', 'foster_role', 'edge_extra', 'adopted_children',
    'foster_children', 'reciprocal_missing', 'reciprocal_wrong', 'reciprocal_extra',
    'profile_id', 'profile_url', 'focus_url', 'focus_edges', 'profile_adopted',
    'focus_foster', 'top_extra']


@pytest.mark.parametrize('anomaly', GRAPH_ANOMALIES)
@pytest.mark.parametrize('existing', [False, True])
def test_graph_anomaly_stops_at_correct_execution_boundary(anomaly, existing):
    cfg = fixture('siblings')
    io, st = IO(cfg), Store()
    if existing:
        prior = cfg['entries'].pop(0)
        cfg['children'].append('profile-999009')
        cfg['verified_children'] = [dict(prior, id='profile-999009')]
        io.children.append('profile-999009')
        io.profiles['profile-999009'] = dict(g.vendor_payload(prior['payload']),
                                            id='profile-999009')
    original = io.get_family

    def bad(target):
        return corrupt_graph(original(target), anomaly, target, cfg['union_id'],
                             io.parents, io.children)
    io.get_family = bad
    r = g.execute(cfg, io, st, lambda r: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and r['stage'] == 'read_family'
    assert len(io.posts) == (0 if existing else 1)
    assert len(st.consumed) == (0 if existing else 1)
    if existing:
        assert st.events == [] and r['items'] == []
    else:
        assert r['items'][0]['phase'] == 'ACKNOWLEDGED_NOT_VERIFIED'


def test_observed_graph_shape_is_pure_and_direct_union_remains_strict():
    parents, children = ['profile-999002', 'profile-999003'], ['profile-999001']
    value = graph(children[0], 'union-999001', parents, children)
    before = copy.deepcopy(value)
    g.family_graph(value, children[0], 'union-999001', parents, children)
    assert value == before
    with pytest.raises(Blocked):
        g.union_state(value['nodes']['union-999001'], 'union-999001', parents, children)
    value['nodes']['union-999001']['id'] = 'union-999001'
    value['focus']['url'] = 'https://www.geni.com/api/' + children[0]
    value['focus']['edges'] = {'union-999001': {'rel': 'child'}}
    g.family_graph(value, children[0], 'union-999001', parents, children)
