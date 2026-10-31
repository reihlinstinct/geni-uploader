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
                      'profile_url': 'https://www.geni.com/zz-invented',
                      'url': 'https://www.geni.com/api/' + FATHER}
            if self.change == 'privacy':
                result['public'] = True
            if self.change == 'name':
                result['first_name'] = 'ZZ-wrong'
            return result
        if route.startswith('/api/' + UNION):
            return {'id': UNION, 'partners': [FATHER], 'children': [OWNER]}
        root = {'id': OWNER, 'first_name': 'ZZ-Root', 'last_name': 'ZZ-Family'}
        if self.change == 'self_only_wrong' and route.startswith('/api/profile?'):
            root['id'] = FATHER
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


@pytest.mark.parametrize('change', ['wrong_owner', 'merge', 'partial_merge', 'duplicate', 'root_union', 'self_only_wrong'])
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
    def fail(env, progress):
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
                if len([x for x in seen if x[0] == 'read']) >= 18:
                    return b''
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
        with pytest.raises(p.TransportStop):
            client.request('POST', '/api/' + OWNER + '/add-parent', BODY)
    assert len([x for x in seen if x[0] == 'request']) == 1 and closed == [True]
    with pytest.raises(Blocked):
        client.request('POST', '/api/' + OWNER + '/add-parent', BODY)
    if kind in ('redirect', 'link', 'status'):
        assert not any(x[0] == 'read' for x in seen)
    if kind == 'oversize':
        assert sum(x[1] for x in seen if x[0] == 'read') == p.LIMIT + 1
        assert len([x for x in seen if x[0] == 'read']) == 17


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

@pytest.mark.parametrize('stage', sorted(p.STAGES))
def test_fixed_stage_diagnostics_never_print_private_exception(monkeypatch, capsys, stage):
    def fail(env, progress):
        progress.enter(stage)
        raise AttributeError('ZZ-PRIVATE-SENTINEL')
    monkeypatch.setattr(p, 'run', fail)
    assert p.main() == 1
    out = capsys.readouterr().out
    assert 'stopped at ' + stage + ';' in out and 'ZZ-PRIVATE-SENTINEL' not in out


def test_malformed_post_object_retains_consumption_and_final_evidence():
    client = Client()
    original = client.request
    def request(method, route, body=None):
        if method == 'POST':
            client.calls.append((method, route, body))
            raise AttributeError('ZZ-PRIVATE-SENTINEL')
        return original(method, route, body)
    client.request = request
    store = Store(client)
    reports = []
    def save(report):
        reports.append(copy.deepcopy(report))
        return b'age-encryption.org/v1\nZZciphertext'
    assert p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store, save,
                     lambda: 200) == 'UNCERTAIN'
    assert store.consumed and store.receipts == ['before', 'final']
    assert reports[-1]['stopped_stage'] == 'send'
    assert reports[-1]['failure_code'] == 'validation_or_storage'
    assert 'ZZ-PRIVATE-SENTINEL' not in str(reports)
    assert sum(x[0] == 'POST' for x in client.calls) == 1


def test_oversize_response_retains_only_fixed_diagnostic_and_acknowledged_status():
    client = Client()
    original = client.request
    def request(method, route, body=None):
        if route.startswith('/api/' + FATHER):
            raise p.TransportStop('response_oversize')
        return original(method, route, body)
    client.request = request
    store = Store(client)
    reports = []
    def save(report):
        reports.append(copy.deepcopy(report))
        return b'age-encryption.org/v1\nZZciphertext'
    assert p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store, save,
                     lambda: 200) == 'ACKNOWLEDGED_NOT_VERIFIED'
    assert store.consumed and reports[-1]['object_id'] == FATHER
    assert reports[-1]['failure_code'] == 'response_oversize'
    assert reports[-1]['stopped_stage'] == 'readback'


def test_transport_malformed_response_object_closes_without_leaking(monkeypatch):
    closed = []
    class Connection:
        def __init__(self, *a, **kw):
            pass
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            return object()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(p.http.client, 'HTTPSConnection', Connection)
    client = p.HTTPS('www.geni.com', 'ZZ-token')
    with pytest.raises(p.TransportStop, match='transport_unavailable'):
        client.request('GET', '/api/profile')
    assert closed == [True]


def test_stage_transition_inventory_on_verified_run():
    class Progress(p.Progress):
        def __init__(self):
            super().__init__()
            self.seen = []
        def enter(self, stage):
            super().enter(stage)
            self.seen.append(stage)
    progress = Progress()
    client = Client()
    store = Store(client)
    assert p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store,
                     lambda _: b'age-encryption.org/v1\nZZciphertext', lambda: 200,
                     progress) == 'VERIFIED'
    assert progress.seen == ['config', 'manifest', 'preflight', 'preflight_evidence', 'consume',
                             'send', 'ack', 'readback', 'final']


@pytest.mark.parametrize('kind,code', [('status', 'response_status'),
    ('redirect', 'response_redirect'), ('link', 'response_redirect'),
    ('oversize', 'response_oversize'), ('malformed', 'response_malformed'),
    ('timeout', 'transport_unavailable'), ('before_deadline', 'response_deadline'),
    ('after_deadline', 'response_deadline')])
def test_exact_transport_failure_codes_and_deadline_branches(monkeypatch, kind, code):
    reads, closed = [], []
    appended = []
    import inspect
    import sys
    lines, first_line = inspect.getsourcelines(p.HTTPS.request)
    append_line = first_line + next(i for i, line in enumerate(lines) if 'chunks.append(chunk)' in line)
    def trace(frame, event, arg):
        if event == 'line' and frame.f_code is p.HTTPS.request.__code__ and frame.f_lineno == append_line:
            appended.append(True)
        return trace
    ticks = iter([0, 0, 30] if kind == 'before_deadline' else
                 [0, 0, 1, 30] if kind == 'after_deadline' else [0] * 100)
    monkeypatch.setattr(p.time, 'monotonic', lambda: next(ticks, 1))
    class Response:
        status = 403 if kind == 'status' else 200
        def getheader(self, name):
            return 'ZZ' if (kind == 'redirect' and name == 'Location' or
                            kind == 'link' and name == 'Link') else None
        def read(self, size):
            reads.append(size)
            if kind == 'timeout':
                raise TimeoutError('ZZprivate')
            if kind == 'oversize':
                return b' ' * size if len(reads) <= 17 else b''
            return b'ZZbad' if len(reads) == 1 else b''
    class Connection:
        def __init__(self, *a, **kw):
            pass
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(p.http.client, 'HTTPSConnection', Connection)
    old_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        with pytest.raises(p.TransportStop) as exc:
            p.HTTPS('www.geni.com', 'ZZ-token').request('GET', '/api/profile')
    finally:
        sys.settrace(old_trace)
    assert exc.value.code == code
    assert closed == [True]
    if kind == 'before_deadline':
        assert reads == []
    if kind == 'after_deadline':
        assert reads == [65536] and appended == []


@pytest.mark.parametrize('change,stage', [('lost', 'send'), ('malformed', 'send'),
    ('ack', 'ack'), ('privacy', 'readback'), ('final', 'final')])
def test_main_reports_original_stop_stage_unless_final_persistence_fails(monkeypatch, capsys,
                                                                       change, stage):
    def run(env, progress):
        client = Client(change)
        store = Store(client, change)
        return p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store,
                         lambda _: b'age-encryption.org/v1\nZZ', lambda: 200, progress)
    monkeypatch.setattr(p, 'run', run)
    assert p.main() == 1
    assert 'stopped at ' + stage + ';' in capsys.readouterr().out


def pilot_environment(tmp_path):
    c = dict(C, expires_at=2**39)
    raw = p.canonical(c)
    return {'PILOT_CONFIRM': 'CREATE_ONE_PRIVATE_PARENT', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
            'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
            'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_SHA': 'b'*40,
            'PILOT_EXECUTOR_SHA': 'b'*40, 'PILOT_CONFIG_SHA256': p.sha(raw),
            'PILOT_CONFIG_JSON': raw.decode(), 'PILOT_OUTPUT_DIR': str(tmp_path/'out'),
            'GITHUB_RUN_ID': '999004', 'FAMILY_TREE_PAT': 'ZZ-token',
            'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-secondary'}


@pytest.mark.parametrize('failure,stage', [('env', 'setup'), ('config', 'config'),
    ('encryption', 'encryption'), ('github_credential', 'github_credential'),
    ('private_source', 'private_source'), ('credential', 'credential'), ('output', 'output'),
    ('manifest', 'manifest')])
def test_real_run_transitions_report_distinct_fixed_stages(monkeypatch, tmp_path, capsys,
                                                           failure, stage):
    env = pilot_environment(tmp_path)
    if failure == 'env':
        env['GITHUB_RUN_ATTEMPT'] = '2'
    if failure == 'config':
        env['PILOT_CONFIG_SHA256'] = 'c'*64
    if failure == 'output':
        (tmp_path/'out').mkdir()
    class FakeHTTPS:
        def __init__(self, host, token, **kw):
            if failure == 'github_credential' and host == 'api.github.com':
                raise Blocked()
            if failure == 'credential' and host == 'www.geni.com':
                raise Blocked()
        def request(self, *a, **kw):
            pytest.fail('unexpected vendor call')
    class FakeStore:
        def __init__(self, *a):
            pass
        def load(self, path):
            if failure == 'private_source':
                raise Blocked()
            return {} if failure == 'manifest' else copy.deepcopy(M)
    def encrypt(*a):
        if failure == 'encryption':
            raise Blocked()
        return b'age-encryption.org/v1\nZZ'
    monkeypatch.setattr(p, 'HTTPS', FakeHTTPS)
    monkeypatch.setattr(p, 'PrivateGit', FakeStore)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    monkeypatch.setattr(p.os, 'environ', env)
    assert p.main() == 1
    out = capsys.readouterr().out
    assert 'stopped at ' + stage + ';' in out


def test_real_run_expiry_at_execute_is_config_not_env_setup(monkeypatch, tmp_path, capsys):
    env = pilot_environment(tmp_path)
    monkeypatch.setattr(p.os, 'environ', env)
    ticks = iter([200, 2**39])
    monkeypatch.setattr(p.time, 'time', lambda: next(ticks, 2**39))
    monkeypatch.setattr(p, 'encrypt', lambda *a: b'age-encryption.org/v1\nZZ')
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **kw: object())
    class Store:
        def __init__(self, *a):
            pass
        def load(self, path):
            return copy.deepcopy(M)
    monkeypatch.setattr(p, 'PrivateGit', Store)
    # execute's default clock binds the original function; inject the fake explicitly.
    execute = p.execute
    monkeypatch.setattr(p, 'execute', lambda *a, **kw: execute(*a, clock=p.time.time, **kw))
    assert p.main() == 1
    assert 'stopped at config;' in capsys.readouterr().out


@pytest.mark.parametrize('failure', ['lost', 'privacy'])
def test_post_send_stop_plus_final_receipt_failure_reports_final(monkeypatch, capsys, failure):
    def run(env, progress):
        client = Client(failure)
        store = Store(client, 'final')
        return p.execute(copy.deepcopy(C), copy.deepcopy(M), client, store,
                         lambda _: b'age-encryption.org/v1\nZZ', lambda: 200, progress)
    monkeypatch.setattr(p, 'run', run)
    assert p.main() == 1
    assert 'stopped at final;' in capsys.readouterr().out



def test_create_and_diagnostic_credentials_are_separate_without_fallback():
    create = Path('.github/workflows/one-time-parent-pilot.yml').read_text()
    diagnostic = Path('.github/workflows/pilot-get-diagnostics.yml').read_text()
    assert 'FAMILY_TREE_PAT: ${{ secrets.PILOT_PRIVATE_EVIDENCE_WRITER }}' in create
    assert 'secrets.FAMILY_TREE_PAT' not in create
    assert 'FAMILY_TREE_PAT: ${{ secrets.FAMILY_TREE_PAT }}' in diagnostic
    assert 'PILOT_PRIVATE_EVIDENCE_WRITER' not in diagnostic
    assert "environment: father-create" in create


@pytest.mark.parametrize('stage', ['preflight_evidence', 'consume', 'send', 'ack', 'readback', 'final'])
def test_escaping_execution_failure_saved_locally_with_details(monkeypatch, tmp_path, capsys, stage):
    env = pilot_environment(tmp_path)
    saved = []
    remote_calls = []
    class FakeStore:
        def __init__(self, *a):
            pass
        def load(self, path):
            return copy.deepcopy(M)
    def fake_execute(config, manifest, client, store, save, **kw):
        kw['progress'].enter(stage)
        remote_calls.append(stage)
        raise p.TransportStop('response_redirect', evidence={
            'http_status': 201, 'location_present': True, 'link_present': False})
    def encrypt(recipient, raw):
        if raw != b'pilot preflight':
            saved.append(p.decode(raw))
        return b'age-encryption.org/v1\nZZ'
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **kw: object())
    monkeypatch.setattr(p, 'PrivateGit', FakeStore)
    monkeypatch.setattr(p, 'execute', fake_execute)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    monkeypatch.setattr(p.os, 'environ', env)
    assert p.main() == 1
    assert saved[0]['stage'] == stage and saved[0]['phase'] == 'STOPPED'
    assert saved[0]['http_failure']['http_status'] == 201
    assert saved[0]['failure_code'] == 'response_redirect'
    assert saved[0]['retry_allowed'] is False and remote_calls == [stage]
    assert '201' not in capsys.readouterr().out
    assert len(list((tmp_path / 'out').iterdir())) == 1


def test_other_success_status_location_remains_rejected_with_safe_metadata(monkeypatch):
    class Response:
        status = 200
        def getheader(self, name):
            return 'ZZ-private-url' if name == 'Location' else None
    class Connection:
        def __init__(self, *a, **kw):
            pass
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(p.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(p.TransportStop) as exc:
        p.HTTPS('api.github.com', 'ZZ-token', github=True,
                capture_failure=True).request('POST', '/repos/zz/zz/git/tags', {})
    assert exc.value.code == 'response_redirect'
    assert exc.value.evidence == {'http_status': 200, 'location_present': True,
                                  'link_present': False}
    assert 'ZZ-private-url' not in str(exc.value.evidence)


def test_debug_trace_default_off_bounded_and_fixed(monkeypatch):
    progress = p.Progress()
    progress.enter('config')
    assert progress.trace is None
    ticks = iter([10, 9, 11] + [1000000] * 100)
    monkeypatch.setattr(p.time, 'monotonic', lambda: next(ticks))
    progress.enable_debug()
    for _ in range(100):
        progress.enter('manifest')
    assert len(progress.trace) == 64
    assert progress.trace[0] == {'stage': 'config', 'elapsed_ms': 0}
    assert all(set(e) == {'stage', 'elapsed_ms'} and e['stage'] in p.STAGES
               and 0 <= e['elapsed_ms'] <= 86400000 for e in progress.trace)
    with pytest.raises(Blocked):
        progress.enter('ZZ-private')


@pytest.mark.parametrize('debug', [None, '0', '1', 'ZZ-private'])
def test_debug_retained_only_inside_encryption(monkeypatch, tmp_path, capsys, debug):
    env = pilot_environment(tmp_path)
    if debug is not None:
        env['PILOT_DEBUG'] = debug
    saved = []
    class FakeStore:
        def __init__(self, *a):
            pass
        def load(self, path):
            return copy.deepcopy(M)
    def execute(config, manifest, client, store, save, **kw):
        kw['progress'].enter('preflight')
        save({'phase': 'ZZ-test'})
        return 'VERIFIED'
    def encrypt(recipient, raw):
        if raw != b'pilot preflight':
            saved.append(p.decode(raw))
        return b'age-encryption.org/v1\nZZ'
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **kw: object())
    monkeypatch.setattr(p, 'PrivateGit', FakeStore)
    monkeypatch.setattr(p, 'execute', execute)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    monkeypatch.setattr(p.os, 'environ', env)
    assert p.main() == 0
    assert ('debug_trace' in saved[0]) == (debug == '1')
    if debug == '1':
        assert saved[0]['debug_trace'][-1]['stage'] == 'preflight'
    out = capsys.readouterr().out
    assert 'debug_trace' not in out and 'elapsed_ms' not in out


@pytest.mark.parametrize('github,method,route,status,link,accepted', [
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 201, False, True),
    (True, 'POST', '/repos/zz-owner/zz-private/git/refs', 201, False, True),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 201, True, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/refs', 201, True, False),
    (True, 'GET', '/repos/zz-owner/zz-private/git/tags', 201, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 200, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 202, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 301, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 302, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 307, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags', 308, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags/ZZ', 201, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/git/tags?ZZ', 201, False, False),
    (True, 'POST', '/repos/zz-owner/zz-private/issues', 201, False, False),
    (False, 'POST', '/api/profile-999001/add-parent', 201, False, False),
    (False, 'GET', '/api/profile', 201, False, False),
])
def test_creation_location_narrow_exception_never_follows(monkeypatch, github, method,
                                                         route, status, link, accepted):
    calls, reads, closed = [], [], []
    class Response:
        def getheader(self, name):
            return 'https://zz.invalid/ZZ-do-not-follow' if name == 'Location' or (
                link and name == 'Link') else None
        def read(self, size):
            reads.append(size)
            return b'{"ZZ":true}' if len(reads) == 1 else b''
    Response.status = status
    class Connection:
        def __init__(self, host, **kw):
            assert host == ('api.github.com' if github else 'www.geni.com')
        def request(self, *a, **kw):
            calls.append(a)
        def getresponse(self):
            return Response()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(p.http.client, 'HTTPSConnection', Connection)
    client = p.HTTPS('api.github.com' if github else 'www.geni.com', 'ZZ-token',
                     github=github, capture_failure=True)
    if accepted:
        assert client.request(method, route, {}) == {'ZZ': True}
        assert len(reads) == 2
    else:
        with pytest.raises(p.TransportStop) as exc:
            client.request(method, route, {})
        assert exc.value.code == ('response_status' if status >= 300 else 'response_redirect')
        assert 'zz.invalid' not in str(exc.value.evidence)
        assert reads == ([4097] if status >= 300 else [])
    assert len(calls) == 1 and calls[0][:2] == (method, route) and closed == [True]
