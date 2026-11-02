"""Invented fixtures, no network or identifying records."""
import copy
from unittest.mock import patch

import pytest

import bounded_tree_snapshot as s
from geni_uploader.core.people import Blocked


def cfg():
    return {'schema': 1, 'owner': 'profile-101', 'expect_name': 'ZZ Owner',
            'recipient': 'age1' + 'a' * 58, 'expires_at': 900,
            'limits': copy.deepcopy(s.LIMITS)}


def family(n):
    # A synthetic chain exercises BFS; service family edge labels are typed.
    a, b = 'profile-' + str(n), 'profile-' + str(n + 1)
    return {'focus': {'id': a}, 'nodes': {a: {'id': a, 'edges': {}},
            b: {'id': b, 'edges': {}}}}


class Client:
    def __init__(self):
        self.calls = []
        self.allowed = set()

    def allow(self, route):
        self.allowed.add(route)

    def request(self, method, route):
        assert method == 'GET' and route in self.allowed
        self.calls.append(route)
        if '/immediate-family' in route:
            return family(int(route.split('profile-')[1].split('/')[0]))
        return {'id': 'profile-101', 'first_name': 'ZZ', 'last_name': 'Owner',
                'names': {'en-US': {'first_name': 'ZZ'}},
                'unions': ['https://www.geni.com/api/union-201']}


def test_three_hops_no_writes_unknown_merge_kept():
    c = Client(); saved = []
    r = s.observe(cfg(), c, saved.append, lambda: 200)
    assert r['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED'
    assert r['family_reads'] == 3 and len(c.calls) == 5
    assert r['boundary'] == [{'target': 'profile-104', 'depth': 3, 'reason': 'hop_limit'}]
    assert r['complete_tree'] is False and r['read_only'] is True
    assert saved[-1] == r


@pytest.mark.parametrize('value', ['union-01', 'union-0', 'https://geni.com/api/union-1',
    'http://www.geni.com/api/union-1', 'https://www.geni.com/api/union-1?q=1',
    'https://evil.invalid/api/profile-1'])
def test_reference_is_exact(value):
    with pytest.raises(Blocked): s.node(value)


def test_exact_reference():
    assert s.node('https://www.geni.com/api/union-202') == 'union-202'


@pytest.mark.parametrize('field,value', [('schema', True), ('expires_at', True),
                                        ('owner', 'https://www.geni.com/api/profile-101'),
                                        ('limits', {})])
def test_closed_config(field, value):
    c = cfg(); c[field] = value
    with pytest.raises(Blocked): s.config(c)


def test_transport_failure_stops_without_retry():
    c = Client()
    def fail(*_): raise OSError()
    c.request = fail
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 1


def test_wrong_owner_stops():
    c = Client(); c.request = lambda *_: {'id': 'profile-999', 'first_name': 'ZZ', 'last_name': 'Owner'}
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 1


def test_route_budget_get_only_and_no_repeat():
    with patch.object(s.time, 'time', lambda: 200), patch.object(s.time, 'sleep'):
        v = s.Vendor('ZZ-token-123', cfg()); route = '/api/profile-101/immediate-family?only_ids=true'
        v.allow(route)
        with pytest.raises(Blocked): v.admit_vendor('POST', route)
        v.admit_vendor('GET', route)
        with pytest.raises(Blocked): v.admit_vendor('GET', route)
        with pytest.raises(Blocked): v.admit_vendor('GET', '/api/profile-999/immediate-family?only_ids=true')
        v.calls = 77; v.allow('/api/union-202?only_ids=true')
        with pytest.raises(Blocked): v.admit_vendor('GET', '/api/union-202?only_ids=true')


def test_expiry():
    c = Client(); r = s.observe(cfg(), c, lambda _: None, lambda: 901)
    assert r['phase'] == 'STOPPED' and not c.calls


def test_entrypoint_rejects_attempt_before_encryption():
    with pytest.raises(Blocked): s.run({'SNAPSHOT_CONFIRM': 'READ_ONLY_BOUNDED_TREE'})


def test_family_cap_deterministic():
    c = Client(); old = c.request
    def request(method, route):
        if '/profile-101/immediate-family' in route:
            return {'focus': {'id': 'profile-101'}, 'nodes': {
                'profile-' + str(n): {'edges': {}} for n in range(101, 170)}}
        return old(method, route)
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED' and r['family_reads'] == 50
    assert any(x['reason'] == 'family_cap' for x in r['boundary'])
    assert len(r['requests']) == 52


def test_union_cap_and_strict_returned_reference():
    c = Client(); old = c.request
    def request(method, route):
        if route.startswith('/api/union-'):
            return {'id': route.split('/api/')[1].split('?')[0],
                    'partners': ['https://www.geni.com/api/profile-101'], 'children': []}
        if '/immediate-family' in route:
            return {'focus': {'id': 'profile-101'}, 'nodes': {
                'profile-101': {'edges': {}}, **{'union-' + str(n): {'edges': {}}
                                               for n in range(201, 231)}}}
        return old(method, route)
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED' and r['union_reads'] == 25
    assert len([x for x in r['boundary'] if x['reason'] == 'union_cap']) == 5
    assert len(r['requests']) == 28


@pytest.mark.parametrize('change', ['error', 'next_page', 'foreign_edge', 'wrong_focus'])
def test_malformed_family_terminal(change):
    c = Client(); old = c.request
    def request(method, route):
        if '/immediate-family' not in route: return old(method, route)
        f = family(101)
        if change in ('error', 'next_page'): f[change] = 'ZZ'
        if change == 'foreign_edge': f['nodes']['profile-101']['edges']['https://evil.invalid'] = {'rel': 'child'}
        if change == 'wrong_focus': f['focus']['id'] = 'profile-999'
        return f
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 3


def test_real_entrypoint(tmp_path, monkeypatch):
    raw = s.canonical(cfg()); saved = []
    env = {'SNAPSHOT_CONFIRM': 'READ_ONLY_BOUNDED_TREE', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
           'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
           'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'SNAPSHOT_CONFIG_JSON': raw.decode(),
           'SNAPSHOT_CONFIG_SHA256': s.sha(raw), 'SNAPSHOT_EXECUTOR_SHA': 'a' * 40,
           'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '990001',
           'SNAPSHOT_OUTPUT_DIR': str(tmp_path / 'evidence'), 'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-token-123'}
    monkeypatch.setattr(s.time, 'time', lambda: 200)
    monkeypatch.setattr(s, 'encrypt', lambda _, raw: saved.append(raw) or b'ZZ-cipher')
    monkeypatch.setattr(s, 'Vendor', lambda *_: Client())
    assert s.run(env)
    assert len(list((tmp_path / 'evidence').glob('*.age'))) == 6
    assert s.decode(saved[-1])['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED'


@pytest.mark.parametrize('missing', [('children',), ('partners',), ('children', 'partners')])
def test_omitted_union_lists_remain_unknown(missing):
    c = Client(); old = c.request
    def request(method, route):
        if route.startswith('/api/union-'):
            value = {'id': 'union-201', 'partners': ['profile-101'], 'children': []}
            for key in missing: del value[key]
            return value
        if '/immediate-family' in route:
            return {'focus': {'id': 'profile-101'}, 'nodes': {
                'profile-101': {'edges': {}}, 'union-201': {'edges': {}}}}
        return old(method, route)
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED'
    assert {x['field'] for x in r['unknown_union_fields']} == set(missing)
    assert all(x['state'] == 'UNKNOWN_OMITTED' for x in r['unknown_union_fields'])
    union = next(x['value'] for x in r['responses'] if x['kind'] == 'union')
    assert all(key not in union for key in missing)


@pytest.mark.parametrize('value', [None, '', {}, ['https://evil.invalid/api/profile-101'],
                                  ['profile-101', 'https://www.geni.com/api/profile-101'],
                                  ['profile-0101'], ['union-201']])
@pytest.mark.parametrize('field', ['children', 'partners'])
def test_present_union_lists_still_strict(field, value):
    c = Client(); old = c.request
    def request(method, route):
        if route.startswith('/api/union-'):
            return {'id': 'union-201', field: value}
        if '/immediate-family' in route:
            return {'focus': {'id': 'profile-101'}, 'nodes': {
                'profile-101': {'edges': {}}, 'union-201': {'edges': {}}}}
        return old(method, route)
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 4


def test_explicit_empty_union_list_is_not_unknown():
    c = Client(); old = c.request
    def request(method, route):
        if route.startswith('/api/union-'): return {'id': 'union-201', 'partners': [], 'children': []}
        if '/immediate-family' in route:
            return {'focus': {'id': 'profile-101'}, 'nodes': {
                'profile-101': {'edges': {}}, 'union-201': {'edges': {}}}}
        return old(method, route)
    c.request = request
    r = s.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED' and r['unknown_union_fields'] == []
