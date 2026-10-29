"""No real network: closed gate or a synthetic HTTPS connection spy only."""
import json
from copy import deepcopy

import pytest

import parent_http_candidate as mod
from people_core import Blocked


def proposed():
    return {'names': {'he': {'first_name': 'ZZאב', 'last_name': 'ZZבדיקה'},
                      'en': {'first_name': 'ZZFather', 'last_name': 'ZZExample'}},
            'first_name': 'ZZFather', 'last_name': 'ZZExample',
            'gender': 'male', 'is_alive': True, 'public': False}


def spy(monkeypatch, stage=None, status=200, body=b'{"id":"profile-999002"}'):
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            calls.append(('construct', args, kwargs))
            if stage == 'construct':
                raise OSError('ZZSECRET')

        def request(self, *args, **kwargs):
            calls.append(('request', args, kwargs))
            if stage == 'request':
                raise TimeoutError('ZZSECRET')

        def getresponse(self):
            calls.append(('response',))
            if stage == 'response':
                raise OSError('ZZSECRET')
            return self

        def read(self, size):
            calls.append(('read', size))
            if stage == 'read':
                raise OSError('ZZSECRET')
            return body

        def close(self):
            calls.append(('close',))
            if stage == 'close':
                raise OSError('ZZSECRET')

    Client.status = status
    monkeypatch.setattr(mod.http.client, 'HTTPSConnection', Client)
    return calls


def test_shipped_gate_blocks_before_validation_or_connection(monkeypatch):
    calls = spy(monkeypatch)
    with pytest.raises(Blocked):
        mod.ClosedParentHTTP().send(None, None, None)
    assert calls == []


def enabled_fixture(monkeypatch):
    # TEST ONLY. Product gate is never modified, toggled or configured.
    monkeypatch.setattr(mod, 'require_production_release', lambda: None)
    return mod.ClosedParentHTTP()


def test_exact_wire_bytes_fixed_host_and_one_local_attempt(monkeypatch):
    calls = spy(monkeypatch)
    client = enabled_fixture(monkeypatch)
    data = proposed()
    before = deepcopy(data)
    result = client.send('profile-999001', data, 'ZZTOKEN')
    assert result['phase'] == 'acknowledged_not_verified'
    assert result['production_enabled'] is False
    assert result['retry_allowed'] is False
    assert data == before
    assert calls[0] == ('construct', ('www.geni.com',), {'port': 443, 'timeout': 10})
    _, args, kwargs = calls[1]
    assert args == ('POST', '/api/profile-999001/add-parent')
    assert kwargs['headers'] == {'Authorization': 'Bearer ZZTOKEN',
                                 'Content-Type': 'application/json',
                                 'Accept': 'application/json'}
    assert json.loads(kwargs['body']) == data
    assert calls[-2:] == [('read', 1024*1024+1), ('close',)]
    before_count = len(calls)
    with pytest.raises(Blocked):
        client.send('profile-999001', data, 'ZZTOKEN')
    assert len(calls) == before_count


@pytest.mark.parametrize('stage', ['construct', 'request', 'response', 'read'])
def test_failure_stays_uncertain_and_local_attempt_consumed(monkeypatch, stage):
    calls = spy(monkeypatch, stage=stage)
    client = enabled_fixture(monkeypatch)
    result = client.send('profile-999001', proposed(), 'ZZTOKEN')
    assert result['phase'] == 'UNCERTAIN'
    assert 'ZZSECRET' not in repr(result)
    assert result['retry_allowed'] is False
    count = len(calls)
    with pytest.raises(Blocked):
        client.send('profile-999001', proposed(), 'ZZTOKEN')
    assert len(calls) == count
    assert sum(c[0] == 'construct' for c in calls) == 1
    assert sum(c[0] == 'request' for c in calls) <= 1


@pytest.mark.parametrize('status,body', [(302, b'ZZLocation'), (429, b'ZZThrottle'),
                                       (500, b'ZZError'), (200, b'x'*(1024*1024+1)),
                                       (200, b'{"id":"profile-999002","id":"profile-999003"}')])
def test_no_retry_redirect_or_oversize_success(monkeypatch, status, body):
    calls = spy(monkeypatch, status=status, body=body)
    result = enabled_fixture(monkeypatch).send('profile-999001', proposed(), 'ZZTOKEN')
    assert result['phase'] == 'UNCERTAIN'
    assert sum(c[0] == 'request' for c in calls) == 1
    assert calls[-1] == ('close',)


@pytest.mark.parametrize('token', ['', 'ZZ\nInjected', 'ZZ\rInjected', 'ZZ token', None,
                                  'a'*8193, 'ZZ\u05d0'])
def test_bad_header_values_never_open_connection(monkeypatch, token):
    calls = spy(monkeypatch)
    with pytest.raises(Blocked):
        enabled_fixture(monkeypatch).send('profile-999001', proposed(), token)
    assert calls == []


@pytest.mark.parametrize('owner', ['profile-self', 'profile-0', 'profile-1/evil',
                                  'https://zz.invalid', None])
def test_owner_path_injection_blocked(monkeypatch, owner):
    calls = spy(monkeypatch)
    with pytest.raises(Blocked):
        enabled_fixture(monkeypatch).send(owner, proposed(), 'ZZTOKEN')
    assert calls == []


def test_close_failure_does_not_release_local_latch(monkeypatch):
    spy(monkeypatch, stage='close')
    client = enabled_fixture(monkeypatch)
    assert client.send('profile-999001', proposed(), 'ZZTOKEN')['production_enabled'] is False
    with pytest.raises(Blocked):
        client.send('profile-999001', proposed(), 'ZZTOKEN')


def test_mother_payload_refused_before_network(monkeypatch):
    calls = spy(monkeypatch)
    value = proposed()
    value['gender'] = 'female'
    with pytest.raises(Blocked):
        enabled_fixture(monkeypatch).send('profile-999001', value, 'ZZTOKEN')
    assert calls == []


def test_real_gate_blocks_fully_valid_inputs_before_network(monkeypatch):
    calls = spy(monkeypatch)
    with pytest.raises(Blocked, match='production parent creation disabled'):
        mod.ClosedParentHTTP().send('profile-999001', proposed(), 'ZZTOKEN')
    assert calls == []


@pytest.mark.parametrize('status', [302, 500])
def test_non200_valid_ack_body_cannot_be_success(monkeypatch, status):
    calls = spy(monkeypatch, status=status, body=b'{"id":"profile-999002"}')
    result = enabled_fixture(monkeypatch).send('profile-999001', proposed(), 'ZZTOKEN')
    assert result['phase'] == 'UNCERTAIN'
    assert sum(c[0] == 'request' for c in calls) == 1
