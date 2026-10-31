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
        return {'focus': {'id': target}, 'nodes': {self.cfg['union_id']:
                self.get_union(self.cfg['union_id'])}}

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
