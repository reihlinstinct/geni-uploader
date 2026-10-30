"""Synthetic-only tests. No provider or GitHub calls."""
import copy
from pathlib import Path

import pytest

import one_time_parent_pilot as p
from people_core import Blocked

OWNER, FATHER, UNION = 'profile-999001', 'profile-999002', 'union-999003'
BODY = {'first_name': 'ZZ-Father', 'last_name': 'ZZ-Family', 'gender': 'male',
        'is_alive': True, 'public': False,
        'names': {'en': {'first_name': 'ZZ-Father', 'last_name': 'ZZ-Family'},
                  'he': {'first_name': 'ZZ-Hebrew', 'last_name': 'ZZ-Family'}}}
C = {'schema': 1, 'data_repo': 'zz-owner/zz-private', 'data_sha': 'a' * 40,
     'data_path': 'zz/proposal.json', 'owner': OWNER, 'expect_name': 'ZZ-Root ZZ-Family',
     'recipient': 'age1' + 'a' * 58, 'allow_unknown_merge': True,
     'accept_hidden_parent_risk': True, 'accept_private_create_risk': True, 'expires_at': 999}
M = {'kind': 'offline_father_only_data_proposal', 'target': OWNER,
     'creation_enabled': False, 'payload': BODY}


class Client:
    def __init__(self, change=None):
        self.calls = []
        self.change = change

    def request(self, method, route, body=None):
        self.calls.append((method, route, copy.deepcopy(body)))
        if method == 'POST':
            if self.change == 'lost':
                raise OSError('ZZ-SENTINEL')
            if self.change == 'malformed':
                return {'not_id': 'ZZ-SENTINEL'}
            return {'id': FATHER, **BODY, 'ZZ-extra-provider-field': 'ZZ-SENTINEL'}
        if route.startswith('/api/' + FATHER):
            result = {'id': FATHER, **copy.deepcopy(BODY), 'unions': [UNION],
                      'url': 'https://www.geni.com/zz-invented'}
            if self.change == 'privacy':
                result['public'] = True
            if self.change == 'name':
                result['first_name'] = 'ZZ-wrong'
            return result
        if route.startswith('/api/' + UNION):
            return {'id': UNION, 'partners': [FATHER], 'children': [OWNER]}
        root = {'id': OWNER, 'first_name': 'ZZ-Root', 'last_name': 'ZZ-Family'}
        if self.change == 'wrong_owner':
            root['id'] = FATHER
        if self.change == 'root_union':
            root['unions'] = [UNION]
        if self.change == 'merge':
            root['merge_pending'] = True
        if self.change == 'partial_merge':
            root['merged_into'] = None
        if 'immediate-family' in route:
            return {'focus': root, 'nodes': {} if self.change != 'duplicate' else {FATHER: {}}}
        return root


class Store:
    def __init__(self, client=None, change=None):
        self.consumed = False
        self.receipts = []
        self.change = change
        self.client = client

    def consume(self):
        if not self.consumed:
            assert not any(x[0] == 'POST' for x in self.client.calls)
        if self.consumed or self.change == 'consume':
            raise Blocked()
        self.consumed = True

    def receipt(self, stage, ciphertext):
        assert ciphertext.startswith(b'age-encryption.org/v1\n')
        if self.change == stage:
            raise Blocked()
        self.receipts.append(stage)


def run(change=None, config=None, manifest=None, clock=lambda: 200):
    client = Client(change)
    store = Store(client, change)
    reports = []
    def save(report):
        reports.append(copy.deepcopy(report))
        return b'age-encryption.org/v1\nZZciphertext'
    result = p.execute(config or copy.deepcopy(C), manifest or copy.deepcopy(M),
                       client, store, save, clock)
    return result, client, store, reports


def test_full_profile_response_persisted_before_readback_and_verified():
    result, client, store, reports = run()
    assert result == 'VERIFIED' and store.consumed
    assert store.receipts == ['before', 'ack', 'final']
    assert [x[0] for x in client.calls] == ['GET', 'GET', 'GET', 'POST', 'GET', 'GET']
    assert client.calls[3] == ('POST', '/api/' + OWNER + '/add-parent', BODY)
    assert reports[0]['preflight']['merge_evidence'] == ['UNKNOWN'] * 3
    assert reports[-1]['object_id'] == FATHER
    assert reports[-1]['create_response']['ZZ-extra-provider-field'] == 'ZZ-SENTINEL'


@pytest.mark.parametrize('change', ['wrong_owner', 'merge', 'partial_merge', 'duplicate', 'root_union'])
def test_preflight_blocks_observed_adverse_evidence(change):
    with pytest.raises(Blocked):
        run(change)


@pytest.mark.parametrize('key,val', [('schema', True), ('data_sha', 'ZZbad'),
    ('data_repo', 'zz-owner/../zz-private'), ('data_path', '../zz.json'), ('owner', 'ZZbad'),
    ('recipient', 'ZZbad'), ('accept_hidden_parent_risk', False),
    ('accept_private_create_risk', False), ('allow_unknown_merge', 1), ('expires_at', True)])
def test_config_closed_and_risk_pins(key, val):
    c = copy.deepcopy(C)
    c[key] = val
    with pytest.raises(Blocked):
        run(config=c)


def test_unknown_merge_must_be_explicit():
    c = dict(C, allow_unknown_merge=False)
    with pytest.raises(Blocked):
        run(config=c)


@pytest.mark.parametrize('change', ['lost', 'malformed', 'privacy', 'name', 'ack'])
def test_post_failure_preserves_consumption_and_never_retries(change):
    result, client, store, reports = run(change)
    assert result in ('UNCERTAIN', 'ACKNOWLEDGED_NOT_VERIFIED')
    assert store.consumed and sum(x[0] == 'POST' for x in client.calls) == 1
    assert store.receipts[-1] == 'final'
    assert reports[-1]['retry_allowed'] is False
    if change == 'ack':
        assert len(client.calls) == 4


@pytest.mark.parametrize('change', ['before', 'consume'])
def test_persistence_failure_before_send_blocks(change):
    with pytest.raises(Blocked):
        run(change)


def test_expiry_before_network_or_after_consumption():
    with pytest.raises(Blocked):
        run(clock=lambda: 999)
    ticks = iter([200, 200, 999])
    result, client, store, _ = run(clock=lambda: next(ticks))
    assert result == 'UNCERTAIN' and store.consumed
    assert not any(x[0] == 'POST' for x in client.calls)


def test_private_false_and_payload_scope_are_mandatory():
    for key, value in [('public', True), ('is_alive', False), ('gender', 'female'),
                       ('ZZ-extra', 'ZZ')]:
        manifest = copy.deepcopy(M)
        manifest['payload'][key] = value
        with pytest.raises(Blocked):
            run(manifest=manifest)


def test_json_rejects_duplicate_and_over_limit():
    with pytest.raises(Blocked):
        p.decode(b'{"id":"ZZ","id":"ZZ"}')
    with pytest.raises(Blocked):
        p.decode(b' ' * (p.LIMIT + 1))


def test_live_entry_stops_before_network_on_invalid_run(monkeypatch):
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **k: pytest.fail('network constructed'))
    with pytest.raises(Blocked):
        p.run({})


def test_workflow_is_separate_manual_protected_pinned_and_silent():
    text = Path('.github/workflows/one-time-parent-pilot.yml').read_text()
    assert 'workflow_dispatch:' in text and 'pull_request:' not in text
    assert 'environment: father-create' in text and 'github.run_attempt == 1' in text
    assert 'github.sha == inputs.executor_sha' in text
    assert 'secrets.GENI_SECONDARY_ACCESS_TOKEN' in text
    assert 'secrets.GENI_ACCESS_TOKEN' not in text and 'REFRESH' not in text
    assert 'contents: write' not in text and 'retention-days: 1' in text
    assert 'if: always()' in text and 'persist-credentials: false' in text
    assert 'PYTHONPATH=src python3 one_time_parent_pilot.py' in text


class Git:
    def __init__(self):
        self.calls = []
    def request(self, method, route, body=None):
        self.calls.append((method, route, body))
        if method == 'POST' and route.endswith('/git/refs'):
            return {'ref': body['ref'], 'object': {'sha': body['sha']}}
        if '/git/ref/tags/' in route:
            return {'object': {'sha': C['data_sha']}}
        raise Blocked()


def test_consumed_marker_is_atomic_create_with_readback_no_delete_or_update():
    client = Git()
    store = p.PrivateGit(client, C['data_repo'], C['data_sha'], OWNER)
    store.consume()
    assert [x[0] for x in client.calls] == ['POST', 'GET']
    assert client.calls[0][2]['ref'] == 'refs/tags/' + store.marker
    assert client.calls[0][2]['sha'] == C['data_sha']


def test_main_never_prints_exception_or_raw_result(monkeypatch, capsys):
    def fail(env):
        raise Blocked('ZZ-SENTINEL')
    monkeypatch.setattr(p, 'run', fail)
    assert p.main() == 1
    assert 'ZZ-SENTINEL' not in capsys.readouterr().out

@pytest.mark.parametrize('kind', ['normal', 'redirect', 'link', 'oversize', 'timeout', 'status'])
def test_transport_fixed_host_bound_body_no_redirect_or_retry(monkeypatch, kind):
    seen, closed = [], []
    class Response:
        status = 403 if kind == 'status' else 200
        def getheader(self, name):
            return 'ZZvalue' if ((kind == 'redirect' and name == 'Location')
                                or (kind == 'link' and name == 'Link')) else None
        def read(self, size):
            seen.append(('read', size))
            if kind == 'timeout':
                raise TimeoutError('ZZ-SENTINEL')
            if kind == 'oversize':
                return b' ' * size
            if len([x for x in seen if x[0] == 'read']) == 1:
                return b'{"id":"profile-999002"}'
            return b''
    class Connection:
        def __init__(self, host, **kw):
            assert host == 'www.geni.com' and kw == {'port': 443, 'timeout': 20}
        def request(self, method, route, **kw):
            seen.append(('request', method, route, kw))
        def getresponse(self):
            return Response()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(p.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)
    client = p.HTTPS('www.geni.com', 'ZZ-token')
    if kind == 'normal':
        assert client.request('POST', '/api/' + OWNER + '/add-parent', BODY)['id'] == FATHER
    else:
        with pytest.raises(Blocked, match='pilot transport unavailable'):
            client.request('POST', '/api/' + OWNER + '/add-parent', BODY)
    assert len([x for x in seen if x[0] == 'request']) == 1 and closed == [True]
    with pytest.raises(Blocked):
        client.request('POST', '/api/' + OWNER + '/add-parent', BODY)
    if kind in ('redirect', 'link', 'status'):
        assert not any(x[0] == 'read' for x in seen)
    if kind == 'oversize':
        assert sum(x[1] for x in seen if x[0] == 'read') == p.LIMIT + 1


def test_receipts_are_ciphertext_only_and_exact_readback():
    class ReceiptGit:
        def __init__(self):
            self.tag, self.ref, self.calls = None, None, []
        def request(self, method, route, body=None):
            self.calls.append((method, route, body))
            if method == 'POST' and route.endswith('/git/tags'):
                self.tag = body
                assert 'ZZ-secret-name' not in body['message']
                assert body['message'].startswith('Encrypted pilot evidence (age, base64)\n')
                return {'sha': 'b' * 40}
            if method == 'POST' and route.endswith('/git/refs'):
                self.ref = body
                return {'object': {'sha': 'b' * 40}}
            if '/git/ref/' in route:
                return {'object': {'sha': 'b' * 40}}
            return {'message': self.tag['message'], 'object': {'sha': C['data_sha']}}
    git = ReceiptGit()
    store = p.PrivateGit(git, C['data_repo'], C['data_sha'], OWNER)
    store.receipt('ack', b'age-encryption.org/v1\n\xff\xfeZZ-secret-name')
    assert [x[0] for x in git.calls] == ['POST', 'POST', 'GET', 'GET']


def test_consumed_marker_blocks_second_execute_and_does_not_retry():
    client = Client()
    store = Store(client)
    save = lambda _: b'age-encryption.org/v1\nZZciphertext'
    assert p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store, save,
                     lambda: 200) == 'VERIFIED'
    with pytest.raises(Blocked):
        p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store, save, lambda: 200)
    assert sum(x[0] == 'POST' for x in client.calls) == 1
