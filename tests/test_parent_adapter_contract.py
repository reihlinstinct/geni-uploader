import copy
import socket
import subprocess
import urllib.request

import pytest

import parent_adapter_contract as p
from people_core import Blocked
from tests.test_parent_envelope import fixture


def test_pure_contract_never_network_or_process(monkeypatch):
    def deny(*a, **k): pytest.fail('side effect forbidden')
    for module, key in [(socket, 'socket'), (subprocess, 'Popen'), (subprocess, 'run'),
                        (urllib.request, 'urlopen')]: monkeypatch.setattr(module, key, deny)
    proposal, _ = fixture()
    body = proposal['entries'][0]['proposed_payload']
    value = p.describe('POST', 'profile-99123/add-parent', body)
    body['public'] = True
    assert value['body']['public'] is False and not value['production_enabled']
    assert p.classify_create(sent=True, status=200, raw=b'{"id":"profile-99555"}')['phase'] == (
        'acknowledged_not_verified')


@pytest.mark.parametrize('route', ['profile', 'profile-99123', 'profile-99123/immediate-family',
                                  'union-99111'])
def test_exact_get_descriptor(route):
    assert p.describe('GET', route)['body'] is None


@pytest.mark.parametrize('route', ['https://www.geni.com/api/profile', '../profile',
                                  'profile?access_token=ZZsecret', 'profile-1/delete',
                                  'profile-1/add-parent', '//ZZ.invalid'])
def test_unreviewed_get_route_blocked(route):
    with pytest.raises(Blocked): p.describe('GET', route)


@pytest.mark.parametrize('change', ['public', 'extra', 'locale', 'main-name', 'alive', 'gender'])
def test_private_bilingual_exact_payload_contract(change):
    proposal, _ = fixture()
    body = copy.deepcopy(proposal['entries'][0]['proposed_payload'])
    if change == 'public': body['public'] = True
    if change == 'extra': body['birthplace'] = 'ZZplace'
    if change == 'locale': body['names'].pop('he')
    if change == 'main-name': body['first_name'] = 'ZZdifferent'
    if change == 'alive': body['is_alive'] = 1
    if change == 'gender': body['gender'] = 'unknown'
    with pytest.raises(Blocked): p.describe('POST', 'profile-99123/add-parent', body)


@pytest.mark.parametrize('status', [None, 201, 301, 302, 401, 429, 500, True, 200.0])
def test_after_send_errors_redirects_throttle_never_retry(status):
    result = p.classify_create(sent=True, status=status, raw=b'{"id":"profile-99555"}')
    assert result['phase'] == 'UNCERTAIN' and result['retry_allowed'] is False


@pytest.mark.parametrize('raw', [None, b'ZZprivate', b'[]', b'{"results":{"id":"profile-99555"}}',
                                b'{"id":"profile-99555","id":"profile-99556"}',
                                b'{"id":"profile-99555","error":"ZZprivate"}',
                                b'{"id":"https://ZZ.invalid"}', b'x'*(p.LIMIT+1),
                                b'['*1500+b'0'+b']'*1500])
def test_bad_response_is_uncertain_not_leaked(raw):
    result = p.classify_create(sent=True, status=200, raw=raw)
    assert result['phase'] == 'UNCERTAIN' and 'ZZ' not in str(result)


def test_before_send_vs_acknowledgement_and_mismatched_id():
    assert p.classify_create(sent=False)['phase'] == 'blocked_before_send'
    raw = b'{"id":"profile-99555"}'
    assert p.classify_create(sent=True, status=200, raw=raw,
                             expected_id='profile-99556')['phase'] == 'UNCERTAIN'
    with pytest.raises(Blocked): p.classify_create(sent=False, status=200)
