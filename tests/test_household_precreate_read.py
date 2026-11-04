"""Synthetic exact household fixtures, no network."""
from unittest.mock import patch

import pytest

import geni_uploader.runners.household_precreate_read as h
from geni_uploader.core.people import Blocked


def cfg():
    return {'schema': 1, 'owner': 'profile-101', 'expect_name': 'ZZ Owner',
            'recipient': 'age1' + 'a' * 58, 'expires_at': 900,
            'profiles': ['profile-101', 'profile-201'], 'unions': ['union-301']}


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


def test_exact_six_gets_unknown_not_empty():
    c = Client(); saved = []; r = h.observe(cfg(), c, saved.append, lambda: 200)
    assert r['phase'] == 'HOUSEHOLD_BASELINE_COLLECTED' and len(c.calls) == 6
    assert len(r['unknown_union_fields']) == 1
    assert r['full_children_visibility'] == 'UNPROVED'
    assert all('children' not in x['value'] for x in r['responses'] if x['kind'] == 'union')
    assert saved[-1] == r


@pytest.mark.parametrize('which', ['profiles', 'unions'])
def test_config_duplicate_or_foreign_ids(which):
    c = cfg(); c[which].append(c[which][0])
    with pytest.raises(Blocked): h.config(c)
    c = cfg(); c[which][-1] = 'https://evil.invalid/profile-1'
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
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 6


def test_wrong_candidate_id_stops():
    c = Client(); old = c.request
    c.request = lambda method, route: {'id': 'profile-999'} if '/profile-201?' in route else old(method, route)
    r = h.observe(cfg(), c, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 4


def test_route_order_no_post_repeat_or_jump():
    with patch.object(h.time, 'time', lambda: 200), patch.object(h.time, 'sleep'):
        c = cfg(); v = h.Vendor('ZZ-token-123', c); routes = h.routes(c)
        with pytest.raises(Blocked): v.admit_vendor('POST', routes[0][0])
        with pytest.raises(Blocked): v.admit_vendor('GET', routes[1][0])
        for route, _, _ in routes: v.admit_vendor('GET', route)
        assert v.calls == 6
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
    env = {'HOUSEHOLD_CONFIRM': 'READ_ONLY_HOUSEHOLD_BASELINE', 'GITHUB_RUN_ATTEMPT': '1',
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
    assert len(list((tmp_path / 'evidence').glob('*.age'))) == 7
    assert h.decode(captures[-1])['config_sha256'] == h.sha(raw)
    env['GITHUB_RUN_ATTEMPT'] = '2'
    with pytest.raises(Blocked): h.run(env)


@pytest.mark.parametrize('mutate', [
    lambda c: c.update(extra=True),
    lambda c: c.update(profiles=['profile-201', 'profile-101']),
    lambda c: c.update(profiles=['profile-101']),
    lambda c: c.update(unions=[]),
    lambda c: c.update(unions=['union-301', 'union-302']),
])
def test_exact_config_rejects_invalid_shape(mutate):
    c = cfg(); mutate(c)
    with pytest.raises(Blocked): h.config(c)


@pytest.mark.parametrize('bad', [
    {'error': {'message': 'ZZ-secret-like-value'}},
    {'paging': 'ZZ'},
    {'focus': {'id': 'profile-999'}, 'nodes': {}},
    {'focus': {'id': 'profile-101'}, 'nodes': {'profile-101': {'edges': {'union-301': {'rel': 'sibling'}}}}},
    {'focus': {'id': 'profile-101'}, 'nodes': {'profile-101': {'edges': []}}},
    {'focus': {'id': 'profile-101'}, 'nodes': {'evil': {'edges': {}}}},
])
def test_failed_body_or_family_schema_saved_before_validation(bad):
    c = Client(); old = c.request; saved = []
    c.request = lambda method, route: bad if '/immediate-family' in route else old(method, route)
    r = h.observe(cfg(), c, saved.append, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 3
    assert saved[-1]['responses'][-1]['value'] == bad
    assert saved[2]['responses'][-1]['value'] == bad


@pytest.mark.parametrize('status,headers', [(302, {'Location': 'https://evil.invalid/'}),
    (200, {'Location': 'https://evil.invalid/'}), (200, {'Link': 'ZZ'}),
    (429, {'Retry-After': '1'}), (503, {})])
def test_real_transport_no_redirect_or_retry(status, headers, monkeypatch, capsys):
    import geni_uploader.runners.one_time_parent_pilot as transport
    opened = []; requests = []
    monkeypatch.setattr(h.time, 'time', lambda: 200)
    class Response:
        def __init__(self): self.status = status
        def getheader(self, name): return headers.get(name)
        def read(self, _): return b'{"error":{"message":"ZZ-private-name"}}' if status != 200 else b'{}'
    class Connection:
        def __init__(self, host, port, timeout):
            assert host == 'www.geni.com' and port == 443 and timeout == 20
            opened.append(host)
        def request(self, method, route, **kwargs): requests.append((method, route))
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', Connection)
    v = h.Vendor('ZZ-token-123', cfg())
    assert v.calls == 0 and v.last is None
    with pytest.raises(transport.TransportStop): v.request('GET', h.routes(cfg())[0][0])
    assert len(opened) == len(requests) == v.calls == 1
    assert requests[0][0] == 'GET' and requests[0][1].endswith('&api_version=1')
    r = h.observe(cfg(), h.Vendor('ZZ-token-123', cfg()), lambda _: None, lambda: 200)
    assert r['exception_type'] == 'TransportStop'
    assert r['http_failure']['http_status'] == status
    assert len(r['requests']) == 1 and r['responses'] == []
    assert 'ZZ-private-name' not in h.canonical(r).decode()
    assert capsys.readouterr().out == ''


def test_real_transport_rejects_post_before_connect(monkeypatch):
    import geni_uploader.runners.one_time_parent_pilot as transport
    def forbidden(*args, **kwargs): raise AssertionError('ZZ must not open connection')
    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', forbidden)
    v = h.Vendor('ZZ-token-123', cfg())
    with pytest.raises(Blocked): v.request('POST', h.routes(cfg())[0][0], {})
    assert v.calls == 0


def test_success_evidence_encrypted_and_token_not_recorded(tmp_path, monkeypatch, capsys):
    raw = h.canonical(cfg()); captures = []
    env = {'HOUSEHOLD_CONFIRM': 'READ_ONLY_HOUSEHOLD_BASELINE', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
           'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
           'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'HOUSEHOLD_CONFIG_JSON': raw.decode(),
           'HOUSEHOLD_CONFIG_SHA256': h.sha(raw), 'HOUSEHOLD_EXECUTOR_SHA': 'a' * 40,
           'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '990001',
           'HOUSEHOLD_OUTPUT_DIR': str(tmp_path / 'evidence'), 'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-token-123'}
    monkeypatch.setattr(h.time, 'time', lambda: 200)
    monkeypatch.setattr(h, 'encrypt', lambda _, value: captures.append(value) or b'ZZ-ciphertext')
    monkeypatch.setattr(h, 'Vendor', lambda *_: Client())
    assert h.run(env)
    assert all(b'ZZ-token-123' not in value for value in captures)
    assert all(x.read_bytes() == b'ZZ-ciphertext' for x in (tmp_path / 'evidence').glob('*.age'))
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('mode,stage', [
    ('malformed', 'response_malformed'),
    ('oversize', 'response_oversize'),
    ('deadline', 'response_deadline'),
])
def test_real_transport_body_edges_close_without_retry(mode, stage, monkeypatch, capsys):
    import geni_uploader.runners.one_time_parent_pilot as transport
    now = [0.0]
    calls = []; closed = []
    monkeypatch.setattr(h.time, 'time', lambda: 200)
    monkeypatch.setattr(h.time, 'monotonic', lambda: now[0])

    class Response:
        status = 200

        def __init__(self):
            self.sent = False

        def getheader(self, _):
            return None

        def read(self, size):
            if self.sent:
                return b''
            self.sent = True
            if mode == 'deadline':
                now[0] += 31
            return b'x' * size if mode == 'oversize' else (
                b'{ZZ' if mode == 'malformed' else b'{}')

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('www.geni.com', 443, 20)
            self.response = Response()

        def request(self, method, route, **kwargs):
            calls.append((method, route))

        def getresponse(self):
            return self.response

        def close(self):
            closed.append(True)

    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(transport, 'LIMIT', 8)
    v = h.Vendor('ZZ-token-123', cfg())
    with pytest.raises(transport.TransportStop) as error:
        v.request('GET', h.routes(cfg())[0][0])
    assert str(error.value) == stage
    assert v.calls == len(calls) == len(closed) == 1
    assert calls[0][0] == 'GET'
    assert capsys.readouterr().out == ''


def test_real_transport_paces_every_get_and_stops_if_wait_expires(monkeypatch):
    now = [100.0]; wall = [200.0]; waits = []
    monkeypatch.setattr(h.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(h.time, 'time', lambda: wall[0])

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds
        wall[0] += seconds

    monkeypatch.setattr(h.time, 'sleep', sleep)
    v = h.Vendor('ZZ-token-123', cfg())
    sequence = h.routes(cfg())
    v.admit_vendor('GET', sequence[0][0])
    now[0] += 4
    v.admit_vendor('GET', sequence[1][0])
    assert waits == [11]
    now[0] += 20
    v.admit_vendor('GET', sequence[2][0])
    assert waits == [11, 0]
    wall[0] = v.c['expires_at'] - 1
    with pytest.raises(Blocked):
        v.admit_vendor('GET', sequence[3][0])
    assert waits[-1] == 15
    assert v.calls == 4  # consumed before wait; expiry cannot authorize a retry


@pytest.mark.parametrize('code', ['transport_unavailable', 'response_oversize',
    'response_deadline', 'response_status', 'response_redirect', 'response_malformed'])
def test_transport_reason_and_safe_evidence_preserved(code, capsys):
    c = Client(); saved = []
    def request(*_):
        raise h.TransportStop(code, evidence={'http_status': 401,
            'geni_rate_remaining': 0, 'retry_after_seconds': 15,
            'location_present': True, 'geni_error_message': 'ZZ-secret',
            'Authorization': 'ZZ-secret', 'body': 'ZZ-private'})
    c.request = request
    r = h.observe(cfg(), c, saved.append, lambda: 200)
    assert r['phase'] == 'STOPPED' and len(r['requests']) == 1
    assert r['responses'] == [] and r['retry_allowed'] is False
    assert r['exception_type'] == 'TransportStop' and r['failure_code'] == code
    assert r['http_failure'] == {'http_status': 401, 'geni_rate_remaining': 0,
        'retry_after_seconds': 15, 'location_present': True}
    assert saved[-1] == r and 'ZZ-secret' not in h.canonical(r).decode()
    assert 'ZZ-private' not in h.canonical(r).decode() and capsys.readouterr().out == ''


@pytest.mark.parametrize('value', [None, [], 'ZZ-secret', True, 1])
def test_transport_evidence_non_dict_ignored(value):
    assert h.safe_transport_evidence(value) == {}


@pytest.mark.parametrize('key', ['http_status', 'geni_rate_limit',
    'geni_rate_remaining', 'geni_rate_window', 'retry_after_seconds'])
@pytest.mark.parametrize('value', [True, False, None, '401', -1, 10000000000, {}])
def test_transport_numeric_fields_strict_and_bounded(key, value):
    assert h.safe_transport_evidence({key: value}) == {}


@pytest.mark.parametrize('value', [99, 600])
def test_transport_status_range(value):
    assert h.safe_transport_evidence({'http_status': value}) == {}


@pytest.mark.parametrize('key', ['location_present', 'link_present', 'request_id_present'])
@pytest.mark.parametrize('value', [0, 1, None, 'true', {}])
def test_transport_boolean_fields_strict(key, value):
    assert h.safe_transport_evidence({key: value}) == {}
