"""Synthetic ZZ fixtures. No transport or credentials."""
import copy

import pytest

import bounded_relative_siblings as b
from tests.test_bounded_parent_addition import (
    ANCHOR,
    FAMILY,
    NEW,
    OLD,
    OWNER,
    PARENTS,
    body,
    family,
)
from tests.test_bounded_parent_addition import (
    plan as parent_plan,
)
from tests.test_guarded_family_additions import Store


def plan():
    c = parent_plan(existing=True)
    del c['existing_parent'], c['entry']
    c['profiles'][OLD]['is_alive'] = False
    c['profiles'][NEW] = body('ZZ-Other-Parent', 'female')
    c['family'][PARENTS][NEW] = 'partner'
    c['entries'] = [{'key': 'zz-first', 'payload': body('ZZ-First')},
                    {'key': 'zz-second', 'payload': body('ZZ-Second', 'female')}]
    return c


class IO:
    def __init__(self, c, anomaly=None):
        self.c, self.anomaly, self.posts, self.reads = c, anomaly, [], []
        self.spec = copy.deepcopy(c['family'])
        self.profiles = {p: dict(b.parent.existing_payload(v), id=p)
                         for p, v in c['profiles'].items()}

    def get_profile(self, node):
        self.reads.append(('profile', node))
        r = copy.deepcopy(self.profiles[OWNER if node == 'profile' else node])
        if self.anomaly == 'privacy' and node != 'profile' and node not in self.c['profiles']:
            r['public'] = True
        return r

    def get_family(self, node):
        self.reads.append(('family', node))
        r = family(node, self.spec if node == ANCHOR else {PARENTS: self.spec[PARENTS]})
        if node != ANCHOR:
            r['nodes'][ANCHOR]['edges'][FAMILY] = {'rel': 'partner'}
            if self.anomaly == 'extra_edge':
                r['nodes'][ANCHOR]['edges']['union-999999'] = {'rel': 'partner'}
        return r

    def get_union(self, node):
        self.reads.append(('union', node))
        r = {'id': node, 'partners': [p for p, role in self.spec[node].items() if role == 'partner'],
             'children': [p for p, role in self.spec[node].items() if role == 'child']}
        if self.anomaly == 'wrong_union':
            r['children'].append('profile-999998')
        return r

    def add_sibling(self, anchor, payload):
        assert anchor == ANCHOR
        self.posts.append(payload)
        if self.anomaly == 'lost_response':
            raise OSError('ZZ-uncertain')
        node = f'profile-{992000 + len(self.posts)}'
        self.profiles[node] = dict(payload, id=node)
        self.spec[PARENTS][node] = 'child'
        return {'id': node}


def run(c=None, anomaly=None, store=None, clock=lambda: 200):
    c = c or plan()
    io, st, snapshots = IO(c, anomaly), store or Store(), []

    def save(r):
        snapshots.append(copy.deepcopy(r))
        return b'ZZ-cipher'
    return b.execute(c, io, st, save, clock), io, st, snapshots


def test_two_living_siblings_beneath_deceased_and_living_parents():
    c = plan()
    original = copy.deepcopy(c)
    r, io, st, snapshots = run(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 2
    assert st.events == ['before', 'consume', 'ack', 'final'] * 2
    assert len(st.consumed) == 2 and snapshots[-1] == r and c == original
    assert all(item['phase'] == 'VERIFIED' for item in r['items'])
    assert all(p['public'] is False and p['is_alive'] is True for p in io.posts)
    assert r['production_enabled'] is False


@pytest.mark.parametrize('anomaly,count', [('privacy', 1), ('extra_edge', 1),
    ('lost_response', 1), ('wrong_union', 0)])
def test_uncertainty_stops_without_second_post(anomaly, count):
    r, io, _, _ = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


@pytest.mark.parametrize('stage,count', [('before', 0), ('ack', 1), ('final', 1)])
def test_receipt_failure_stops(stage, count):
    r, io, _, _ = run(store=Store(stage))
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


def test_consumed_operation_stays_consumed_after_expiry_change():
    c = plan()
    _, _, st, _ = run(c)
    c['expires_at'] += 1
    r, io, _, _ = run(c, store=st)
    assert r['phase'] == 'STOPPED' and io.posts == []


@pytest.mark.parametrize('change', ['owner_anchor', 'unknown_parent', 'bad_union', 'duplicate',
                                  'false_accept', 'deceased_entry', 'extra_field'])
def test_invalid_plan(change):
    c = plan()
    if change == 'owner_anchor':
        c['anchor'] = OWNER
    elif change == 'unknown_parent':
        c['profiles'][OLD]['is_alive'] = None
    elif change == 'bad_union':
        c['parent_union'] = FAMILY
    elif change == 'duplicate':
        c['entries'][1] = copy.deepcopy(c['entries'][0])
    elif change == 'false_accept':
        c['accept_private_create_risk'] = False
    elif change == 'deceased_entry':
        c['entries'][0]['payload']['is_alive'] = False
    else:
        c['unexpected'] = True
    with pytest.raises(b.Blocked):
        run(c)


def test_expired_plan_makes_no_read_or_write():
    r, io, st, _ = run(clock=lambda: 999)
    assert r['phase'] == 'STOPPED' and io.reads == [] and io.posts == [] and st.events == []


def test_same_gender_parents_are_rejected():
    c = plan()
    c['profiles'][NEW]['gender'] = 'male'
    with pytest.raises(b.Blocked):
        run(c)


def test_existing_profile_name_collision_is_rejected():
    c = plan()
    c['entries'][0]['payload'] = copy.deepcopy(c['profiles'][NEW])
    with pytest.raises(b.Blocked):
        run(c)


def test_created_id_must_not_reuse_known_profile():
    c = plan()
    io, st = IO(c), Store()
    original = io.add_sibling

    def reused(anchor, payload):
        original(anchor, payload)
        return {'id': OLD}

    io.add_sibling = reused
    r = b.execute(c, io, st, lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1
    assert st.events == ['before', 'consume']
