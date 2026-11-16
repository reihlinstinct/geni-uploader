"""Synthetic exact household fixtures, no network."""
from unittest.mock import patch

import pytest

import geni_uploader.runners.household_relationship_read as h
from geni_uploader.core.people import Blocked


def cfg():
    return {'schema': 1, 'owner': 'profile-101', 'expect_name': 'ZZ Owner',
            'recipient': 'age1' + 'a' * 58, 'expires_at': 900,
            'profiles': ['profile-201', 'profile-202'], 'unions': ['union-301', 'union-302']}


class Client:
    def __init__(self): self.calls = []
    def request(self, method, route):
        assert method == 'GET'; self.calls.append(route)
        if '/immediate-family' in route:
            target = route.split('/api/')[1].split('/')[0]
            return {'focus': {'id': target}, 'nodes': {target: {'edges': {}}}}
        target = route.split('/api/')[1].split('?')[0]
        if target.startswith('union-'): return {'id': target, 'partners': ['profile-201']}
        return {'id': 'profile-101' if target == 'profile' else target,
                'first_name': 'ZZ', 'last_name': 'Owner',
                'names': {'en-US': {'first_name': 'ZZ'}, 'he': {'first_name': 'ZZ'}}}


def test_exact_eight_gets_unknown_not_empty():
    c = Client(); saved = []; r = h.observe(cfg(), c, saved.append, lambda: 200)
    assert r['phase'] == 'HOUSEHOLD_RECONCILE_COLLECTED' and len(c.calls) == 8
    assert len(r['unknown_union_fields']) == 2
    assert r['full_children_visibility'] == 'UNPROVED'
    assert all('children' not in x['value'] for x in r['responses'] if x['kind'] == 'union')
    assert saved[-1] == r


@pytest.mark.parametrize('which', ['profiles', 'unions'])
def test_config_duplicate_or_foreign_ids(which):
    c = cfg(); c[which][1] = c[which][0]
    with pytest.raises(Blocked): h.config(c)
    c[which][1] = 'https://evil.invalid/profile-1'
    with pytest.raises(Blocked): h.config(c)


@pytest.mark.parametrize('value', [None, {}, 'ZZ', ['union-201'],
     ['profile-201', 'https://www.geni.com/api/profile-201']])
def test_union_present_malformed_stops(value):
    c = Client(); old = c.request
    def request(method, route):
        if '/union-' in route: return {'id': 'union-301', 'children': value}
        return old(method, route)
    c.request = request
    r = h.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 7


def test_wrong_candidate_id_stops():
    c = Client(); old = c.request
    c.request = lambda method, route: {'id': 'profile-999'} if '/profile-202?' in route else old(method, route)
    r = h.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 5


def test_route_order_no_post_repeat_or_jump():
    with patch.object(h.time, 'time', lambda: 200), patch.object(h.time, 'sleep'):
        c = cfg(); v = h.Vendor('ZZ-token-123', c); routes = h.routes(c)
        with pytest.raises(Blocked): v.admit_vendor('POST', routes[0][0])
        with pytest.raises(Blocked): v.admit_vendor('GET', routes[1][0])
        for route, _, _ in routes: v.admit_vendor('GET', route)
        assert v.calls == 8
        with pytest.raises(Blocked): v.admit_vendor('GET', routes[0][0])


def test_transport_no_retry():
    c = Client(); c.request = lambda *_: (_ for _ in ()).throw(OSError())
    r = h.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 1


def test_expired_no_calls():
    c = Client(); r = h.observe(cfg(), c, lambda _: None, lambda: 901)
    assert r['phase'] == 'STOPPED' and not c.calls


def test_entrypoint_real_config(tmp_path, monkeypatch):
    raw = h.canonical(cfg()); captures = []
    env = {'HOUSEHOLD_CONFIRM': 'READ_ONLY_HOUSEHOLD_RECONCILE', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
           'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
           'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'HOUSEHOLD_CONFIG_JSON': raw.decode(),
           'HOUSEHOLD_CONFIG_SHA256': h.sha(raw), 'HOUSEHOLD_EXECUTOR_SHA': 'a' * 40,
           'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '990001',
           'HOUSEHOLD_OUTPUT_DIR': str(tmp_path / 'evidence'), 'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-token-123'}
    monkeypatch.setattr(h.time, 'time', lambda: 200)
    monkeypatch.setattr(h, 'encrypt', lambda _, raw: captures.append(raw) or b'ZZ-cipher')
    monkeypatch.setattr(h, 'Vendor', lambda *_: Client())
    assert h.run(env)
    assert len(list((tmp_path / 'evidence').glob('*.age'))) == 9
    assert h.decode(captures[-1])['config_sha256'] == h.sha(raw)
    env['GITHUB_RUN_ATTEMPT'] = '2'
    with pytest.raises(Blocked): h.run(env)
