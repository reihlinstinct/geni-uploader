import base64
import copy
from pathlib import Path

import pytest

import pilot_get_diagnostics as d
from people_core import Blocked
from tests.test_one_time_parent_pilot import BODY, Client, M
from tests.test_one_time_parent_pilot import C as CREATE

C = {k: v for k, v in CREATE.items() if k not in
     ('accept_hidden_parent_risk', 'accept_private_create_risk')}
C['mode'] = 'get_only_diagnostic'


def clients(change=None):
    prefix, source, vendor_routes = d.routes(C)
    calls = []
    class Transport:
        def __init__(self, host, token, **kw):
            self.host = host
            self.vendor = Client(change)
        def request(self, method, route):
            calls.append((self.host, method, route))
            if self.host == 'www.geni.com':
                return self.vendor.request(method, route)
            if change == 'denied':
                raise d.TransportStop('response_status')
            if route == prefix:
                return {'private': change != 'public', 'full_name': C['data_repo']}
            raw = d.canonical(M)
            if change == 'malformed':
                raw = b'ZZbad'
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}
    return (d.GetOnly('api.github.com', 'ZZ-token', [prefix, source], factory=Transport),
            d.GetOnly('www.geni.com', 'ZZ-token', vendor_routes, factory=Transport), calls)


def test_get_only_complete_exact_five_reads_and_encrypted_report_seam():
    gh, vendor, calls = clients()
    reports = []
    result = d.diagnose(copy.deepcopy(C), gh, vendor, reports.append, lambda: 200)
    assert result['phase'] == 'READ_ONLY_COMPLETE' and result['create_enabled'] is False
    assert len(calls) == 5 and all(x[1] == 'GET' for x in calls)
    assert reports == [result]
    assert result['payload_sha256'] == d.sha(d.canonical(BODY))


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
def test_mutation_method_rejected_before_transport_construction(method):
    constructed = []
    def factory(*a, **kw):
        constructed.append(True)
        pytest.fail('transport constructed')
    client = d.GetOnly('www.geni.com', 'ZZ-token', ['/api/profile'], factory=factory)
    with pytest.raises(Blocked):
        client.request(method, '/api/profile')
    assert constructed == []


@pytest.mark.parametrize('route,body', [('/api/profile-999001/add-parent', None),
    ('/api/profile', {}), ('https://zz.invalid/api/profile', None),
    ('/api/profile/refresh', None)])
def test_route_and_body_rejected_before_transport(route, body):
    client = d.GetOnly('www.geni.com', 'ZZ-token', ['/api/profile'],
                       factory=lambda *a, **k: pytest.fail('transport constructed'))
    with pytest.raises(Blocked):
        client.request('GET', route, body)


@pytest.mark.parametrize('change,stage', [('public', 'private_repository'),
    ('denied', 'private_repository'), ('malformed', 'manifest'),
    ('wrong_owner', 'vendor_reads'), ('duplicate', 'vendor_reads')])
def test_failure_saved_at_exact_fixed_stage_without_exception(change, stage):
    gh, vendor, calls = clients(change)
    saved = []
    r = d.diagnose(copy.deepcopy(C), gh, vendor, saved.append, lambda: 200)
    assert r['phase'] == 'STOPPED' and r['stage'] == stage
    assert saved == [r] and all(x[1] == 'GET' for x in calls)
    if stage != 'vendor_reads':
        assert not vendor.seen


def test_no_create_or_private_git_logic_can_be_called(monkeypatch):
    import one_time_parent_pilot as pilot
    def forbidden(*a, **kw):
        pytest.fail('write path called')
    for name in ['execute', 'run', 'verify']:
        monkeypatch.setattr(pilot, name, forbidden)
    monkeypatch.setattr(pilot.PrivateGit, 'consume', forbidden)
    monkeypatch.setattr(pilot.PrivateGit, 'receipt', forbidden)
    gh, vendor, _ = clients()
    assert d.diagnose(copy.deepcopy(C), gh, vendor, lambda _: None,
                      lambda: 200)['phase'] == 'READ_ONLY_COMPLETE'


def test_each_route_consumed_before_failed_network_no_retry():
    attempts = []
    class Fail:
        def __init__(self, *a, **kw):
            pass
        def request(self, *a):
            attempts.append(True)
            raise OSError('ZZprivate')
    client = d.GetOnly('www.geni.com', 'ZZ-token', ['/api/profile'], factory=Fail)
    with pytest.raises(OSError):
        client.request('GET', '/api/profile')
    with pytest.raises(Blocked):
        client.request('GET', '/api/profile')
    assert attempts == [True]


def test_config_cannot_reuse_create_or_unknown_fields():
    with pytest.raises(Blocked):
        d.configuration(CREATE)
    with pytest.raises(Blocked):
        d.configuration(dict(C, allow_create=True))
    with pytest.raises(Blocked):
        d.configuration(dict(C, mode='create'))


def test_expiry_before_network_and_bad_run_before_encryption(monkeypatch):
    gh, vendor, calls = clients()
    r = d.diagnose(C, gh, vendor, lambda _: None, lambda: 999)
    assert r['phase'] == 'STOPPED' and calls == []
    monkeypatch.setattr(d, 'encrypt', lambda *a: pytest.fail('encrypt called'))
    with pytest.raises(Blocked):
        d.run({}, {})


def test_workflow_separate_protected_secondary_exact_pins():
    s = Path('.github/workflows/pilot-get-diagnostics.yml').read_text()
    assert 'workflow_dispatch:' in s and 'pull_request:' not in s
    assert 'environment: father-create' in s and 'github.run_attempt == 1' in s
    assert 'github.sha == inputs.executor_sha' in s
    assert 'secrets.PILOT_GET_DIAGNOSTIC_JSON' in s
    assert 'secrets.ONE_TIME_PARENT_PILOT_JSON' not in s
    assert 'READ_ONLY_NO_CREATE' in s and 'CREATE_ONE_PRIVATE_PARENT' not in s
    assert 'pilot_get_diagnostics.py' in s and 'one_time_parent_pilot.py' not in s
    assert 'contents: read' in s and 'contents: write' not in s


def environment(tmp_path):
    c = dict(C, expires_at=2**39)
    raw = d.canonical(c)
    return {'DIAGNOSTIC_CONFIRM': 'READ_ONLY_NO_CREATE', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
            'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
            'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_SHA': 'b'*40,
            'DIAGNOSTIC_EXECUTOR_SHA': 'b'*40, 'DIAGNOSTIC_CONFIG_SHA256': d.sha(raw),
            'DIAGNOSTIC_CONFIG_JSON': raw.decode(), 'DIAGNOSTIC_OUTPUT_DIR': str(tmp_path/'out'),
            'GITHUB_RUN_ID': '999004', 'FAMILY_TREE_PAT': 'ZZ-token',
            'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-secondary'}


@pytest.mark.parametrize('key,val', [('DIAGNOSTIC_CONFIRM', 'CREATE_ONE_PRIVATE_PARENT'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTOR', 'reihl'),
    ('GITHUB_REF', 'refs/heads/ZZ'), ('DIAGNOSTIC_CONFIG_SHA256', 'c'*64),
    ('DIAGNOSTIC_EXECUTOR_SHA', 'c'*40)])
def test_invalid_run_pins_stop_before_network_or_encryption(monkeypatch, tmp_path, key, val):
    env = environment(tmp_path)
    env[key] = val
    monkeypatch.setattr(d, 'encrypt', lambda *a: pytest.fail('encryption called'))
    with pytest.raises(Blocked):
        d.run(env, {})


def test_live_wiring_writes_ciphertext_only_even_on_source_failure(monkeypatch, tmp_path):
    reports = []
    def encrypt(recipient, raw):
        reports.append(raw)
        return b'age-encryption.org/v1\nZZciphertext'
    monkeypatch.setattr(d, 'encrypt', encrypt)
    def factory(*args, **kw):
        raise d.TransportStop('response_status')
    original = d.GetOnly
    def get_only(*args, **kw):
        return original(*args, factory=factory, **kw)
    monkeypatch.setattr(d, 'GetOnly', get_only)
    # Preserve exact type validation while wrapping constructor dependencies.
    monkeypatch.setattr(d, 'diagnose', lambda c, gh, vendor, save: _failure(save))
    def _failure(save):
        report = {'phase': 'STOPPED', 'stage': 'private_repository', 'create_enabled': False}
        save(report)
        return report
    progress = {}
    assert d.run(environment(tmp_path), progress) is False
    assert progress['stage'] == 'private_repository'
    out = tmp_path/'out'/'diagnostic.age'
    assert out.read_bytes() == b'age-encryption.org/v1\nZZciphertext'
    assert out.stat().st_mode & 0o777 == 0o600
    assert (tmp_path/'out').stat().st_mode & 0o777 == 0o700


def test_main_public_failure_has_no_exception(monkeypatch, capsys):
    def fail(env, progress):
        progress['stage'] = 'private_source'
        raise AttributeError('ZZ-PRIVATE-SECRET')
    monkeypatch.setattr(d, 'run', fail)
    assert d.main() == 1
    out = capsys.readouterr().out
    assert 'private_source' in out and 'ZZ-PRIVATE-SECRET' not in out


def test_real_wiring_fake_https_collects_all_five_gets(monkeypatch, tmp_path):
    prefix, source, _ = d.routes(C)
    calls = []
    class FakeHTTPS:
        def __init__(self, host, token, **kw):
            self.host = host
            self.vendor = Client()
        def request(self, method, route, body=None):
            calls.append((method, route, body))
            if self.host == 'www.geni.com':
                return self.vendor.request(method, route, body)
            if route == prefix:
                return {'private': True, 'full_name': C['data_repo']}
            assert route == source
            raw = d.canonical(M)
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}
    # Default factory is bound at declaration; replace that dependency for this test only.
    monkeypatch.setattr(d.GetOnly.__init__, '__kwdefaults__', {'factory': FakeHTTPS})
    monkeypatch.setattr(d, 'encrypt', lambda *a: b'age-encryption.org/v1\nZZciphertext')
    assert d.run(environment(tmp_path), {}) is True
    assert len(calls) == 5 and all(method == 'GET' and body is None for method, _, body in calls)


@pytest.mark.parametrize('body', [b'{"message":"ZZ-denied"}', b'ZZbad', b'x' * 4097])
def test_http_failure_details_bounded_and_encrypted_only(monkeypatch, body, capsys):
    import one_time_parent_pilot as p
    reads = []
    class Response:
        status = 403
        def getheader(self, name):
            return 'contents=read;ZZ-token\n' + 'x' * 400
        def read(self, size):
            reads.append(size)
            return body
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
                capture_failure=True).request('GET', '/repos/zz/zz')
    e = exc.value
    assert str(e) == 'response_status' and e.evidence['http_status'] == 403
    assert reads == [4097]
    assert len(e.evidence['github_permissions_hint']) == 256
    assert 'ZZ-token' not in str(e.evidence) and '\n' not in str(e.evidence)
    assert ('github_message' in e.evidence) == (body.startswith(b'{'))
    gh, vendor, _ = clients()
    monkeypatch.setattr(gh, 'request', lambda *a: (_ for _ in ()).throw(e))
    saved = []
    r = d.diagnose(C, gh, vendor, saved.append, lambda: 200)
    assert r['http_failure'] == e.evidence and saved == [r]
    assert not vendor.seen and capsys.readouterr().out == ''
    monkeypatch.setattr(d, 'run', lambda *a: (_ for _ in ()).throw(e))
    assert d.main() == 1
    assert '403' not in capsys.readouterr().out
    with pytest.raises(p.TransportStop) as default:
        p.HTTPS('api.github.com', 'ZZ-token', github=True).request('GET', '/repos/zz/zz')
    assert default.value.evidence == {}


@pytest.mark.parametrize('key,stage', [('FAMILY_TREE_PAT', 'github_credential'),
    ('GENI_SECONDARY_ACCESS_TOKEN', 'secondary_credential')])
@pytest.mark.parametrize('value', [None, '', 'ZZ bad', 'short', 'x' * 4097, 'ZZtoken123\n', 123])
def test_run_bad_credential_stops_at_named_stage_without_transport(monkeypatch, tmp_path,
                                                                  key, stage, value):
    from tests.test_one_time_parent_pilot import pilot_environment
    env = pilot_environment(tmp_path)
    c = dict(C, expires_at=2**39)
    raw = d.canonical(c)
    env.update(DIAGNOSTIC_CONFIRM='READ_ONLY_NO_CREATE', DIAGNOSTIC_CONFIG_JSON=raw.decode(),
               DIAGNOSTIC_CONFIG_SHA256=d.sha(raw), DIAGNOSTIC_EXECUTOR_SHA=env['GITHUB_SHA'],
               DIAGNOSTIC_OUTPUT_DIR=str(tmp_path / 'diagnostic'))
    if value is None:
        del env[key]
    else:
        env[key] = value
    reports = []
    def encrypt(recipient, body):
        if body != b'diagnostic preflight':
            reports.append(d.decode(body))
        return b'age-encryption.org/v1\nZZciphertext'
    def forbidden(*a, **kw):
        pytest.fail('transport constructed')
    monkeypatch.setattr(d, 'encrypt', encrypt)
    monkeypatch.setattr(d, 'HTTPS', forbidden)
    progress = {}
    with pytest.raises(Blocked):
        d.run(env, progress)
    assert progress['stage'] == stage and reports[0]['stage'] == stage
    assert reports[0]['phase'] == 'STOPPED' and reports[0]['create_enabled'] is False
    assert len(list((tmp_path / 'diagnostic').iterdir())) == 1


def reconcile_clients(change=None):
    c = dict(C, mode='get_only_reconcile')
    prefix, source, vr = d.routes(c)
    calls = []
    root = {'id': c['owner'], 'first_name': 'ZZ-Root', 'last_name': 'ZZ-Family',
            'names': {'en-US': {'first_name': 'ZZ-Root'}, 'he': {'first_name': 'ZZ-Hebrew'}}}
    class Transport:
        def __init__(self, host, token, **kw):
            self.host = host
        def request(self, method, route):
            calls.append((self.host, method, route))
            assert method == 'GET'
            if route == prefix:
                return {'private': True, 'full_name': c['data_repo']}
            if route == source:
                raw = d.canonical(M)
                return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                        'content': base64.b64encode(raw).decode()}
            if 'immediate-family' in route:
                nodes = {'profile-999002': {'id': 'profile-999002'},
                         'union-999003': {'id': 'union-999003'}}
                if change == 'isolated':
                    nodes = {}
                if change == 'badid':
                    nodes = {'https://zz.invalid': {'id': 'https://zz.invalid'}}
                if change == 'mismatch':
                    nodes['profile-999002']['id'] = 'profile-999004'
                if change == 'cap':
                    nodes = {'profile-'+str(i): {'id': 'profile-'+str(i)} for i in range(9)}
                r = {'focus': root, 'nodes': nodes}
                if change == 'pagination':
                    r['next_page'] = 'ZZ'
                return r
            if '/api/profile-999002?' in route:
                if change == 'http':
                    raise d.TransportStop('response_status', evidence={'http_status': 500})
                return {'id': 'profile-999002', 'first_name': 'ZZ-Father',
                        'last_name': 'ZZ-Other' if change == 'nonmatch' else 'ZZ-Family'}
            return dict(root, id='profile-999004') if change == 'wrongroot' else root
    return c, d.GetOnly('api.github.com', 'ZZ-token', [prefix, source], factory=Transport), d.GetOnly(
        'www.geni.com', 'ZZ-token', vr, factory=Transport), calls


@pytest.mark.parametrize('change,count,match', [(None, 6, True), ('isolated', 5, None),
                                               ('nonmatch', 6, False)])
def test_reconcile_only_bounded_gets_encrypted_ids_no_name_or_parent_claim(change, count, match):
    c, gh, vendor, calls = reconcile_clients(change)
    saved = []
    r = d.diagnose(c, gh, vendor, saved.append, lambda: 200)
    assert r['phase'] == 'READ_ONLY_COMPLETE' and r['mode'] == 'get_only_reconcile'
    result = r['reconciliation']
    assert result['completeness'] == result['parenthood'] == 'UNPROVED'
    assert len(calls) == count and all(x[1] == 'GET' for x in calls)
    assert 'ZZ-Father' not in str(r) and 'ZZ-Root' not in str(r)
    assert result['checked'] == ([] if match is None else [{'id':'profile-999002', 'name_match':match, 'name_locales':[]}])
    assert r['root_name_locales'] == [['en-US', 'he'], ['en-US', 'he']]
    assert len(vendor.seen) <= 11 and saved == [r]


@pytest.mark.parametrize('change', ['badid', 'mismatch', 'cap', 'pagination', 'wrongroot', 'http'])
def test_reconcile_malformed_or_failure_stops_no_retry(change):
    c, gh, vendor, calls = reconcile_clients(change)
    r = d.diagnose(c, gh, vendor, lambda _: None, lambda: 200)
    assert r['phase'] == 'STOPPED' and r['stage'] == 'vendor_reads'
    assert all(x[1] == 'GET' for x in calls) and len(calls) <= 6
    assert len(calls) == len(set(calls))
    if change == 'http':
        assert r['http_failure'] == {'http_status': 500}


def test_reconcile_workflow_has_no_writer_and_fixed_mode():
    s = Path('.github/workflows/pilot-get-reconcile.yml').read_text()
    assert 'DIAGNOSTIC_MODE: get_only_reconcile' in s
    assert 'secrets.PILOT_GET_RECONCILE_JSON' in s
    assert 'PILOT_PRIVATE_EVIDENCE_WRITER' not in s
    assert 'environment: father-create' in s and 'github.run_attempt == 1' in s
    assert 'contents: read' in s and 'contents: write' not in s
    assert 'github.sha == inputs.executor_sha' in s


def test_mode_cannot_cross_workflows(monkeypatch, tmp_path):
    env = environment(tmp_path)
    c = d.decode(env['DIAGNOSTIC_CONFIG_JSON'].encode())
    c['mode'] = 'get_only_reconcile'
    raw = d.canonical(c)
    env.update(DIAGNOSTIC_CONFIG_JSON=raw.decode(), DIAGNOSTIC_CONFIG_SHA256=d.sha(raw))
    monkeypatch.setattr(d, 'encrypt', lambda *a: pytest.fail('encryption called'))
    with pytest.raises(Blocked):
        d.run(env, {})


def verify_clients(change=None):
    from tests.test_one_time_parent_pilot import FATHER, UNION
    cfg = dict(C, mode='get_only_verify', created_id=FATHER, union_id=UNION)
    prefix, source, vr = d.routes(cfg)
    calls = []

    class Transport:
        def __init__(self, host, token, **kw):
            self.host = host

        def request(self, method, route):
            calls.append((self.host, method, route))
            if self.host == 'api.github.com':
                if route == prefix:
                    return {'private': True, 'full_name': cfg['data_repo']}
                raw = d.canonical(M)
                return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                        'content': base64.b64encode(raw).decode()}
            value = Client(change).request(method, route)
            if change == 'extra_locale' and route.startswith('/api/' + FATHER):
                value['names']['zz'] = {'first_name': 'ZZ-extra'}
            if change == 'url_union' and 'unions' in value:
                value['unions'] = ['https://www.geni.com/api/' + UNION]
            if change == 'relationship' and route.startswith('/api/' + UNION):
                value['children'] = []
            return value

    return (cfg, d.GetOnly('api.github.com', 'ZZ-token', [prefix, source], factory=Transport),
            d.GetOnly('www.geni.com', 'ZZ-token', vr, factory=Transport), calls)


@pytest.mark.parametrize('change,failed', [(None, None), ('privacy', 'private'),
    ('name', 'field_first_name'), ('extra_locale', 'field_names'),
    ('url_union', None), ('relationship', 'union_children')])
def test_verify_capture_before_checks_and_no_relaxation(change, failed):
    cfg, gh, vendor, calls = verify_clients(change)
    reports = []
    result = d.diagnose(cfg, gh, vendor, lambda r: reports.append(copy.deepcopy(r)), lambda: 200)
    assert len(calls) == 4 and all(x[1] == 'GET' for x in calls)
    assert set(reports[0]['verification']['responses']) == {'profile'}
    assert reports[0]['verification']['checks'] == {}
    assert set(reports[1]['verification']['responses']) == {'profile', 'union'}
    checks = result['verification']['checks']
    if failed:
        assert checks[failed] is False
        assert result['phase'] == 'STOPPED' and not result['verification']['verified']
    else:
        assert all(checks.values()) and result['verification']['verified']
        assert result['phase'] == 'READ_ONLY_COMPLETE'


def test_verify_capture_storage_failure_stops_before_second_get():
    cfg, gh, vendor, calls = verify_clients()
    saved = []

    def save(r):
        saved.append(copy.deepcopy(r))
        if len(saved) == 1:
            raise OSError('ZZ-storage')
    result = d.diagnose(cfg, gh, vendor, save, lambda: 200)
    assert len(calls) == 3 and result['phase'] == 'STOPPED'
    assert set(saved[0]['verification']['responses']) == {'profile'}


@pytest.mark.parametrize('key,value', [('created_id', 'profile'), ('union_id', 'profile-999'),
                                     ('created_id', C['owner'])])
def test_verify_rejects_bad_target_pins(key, value):
    cfg, _, _, _ = verify_clients()
    cfg[key] = value
    with pytest.raises(Blocked):
        d.configuration(cfg)


def test_verify_workflow_fixed_mode_separate_secret_and_no_writer():
    s = Path('.github/workflows/pilot-get-verify.yml').read_text()
    assert 'DIAGNOSTIC_MODE: get_only_verify' in s
    assert 'secrets.PILOT_GET_VERIFY_JSON' in s
    assert 'READ_ONLY_NO_CREATE' in s and 'environment: father-create' in s
    assert 'PILOT_PRIVATE_EVIDENCE_WRITER' not in s
    assert 'contents: read' in s and 'github.run_attempt == 1' in s


def test_verify_run_preserves_each_encrypted_capture(monkeypatch, tmp_path):
    from tests.test_one_time_parent_pilot import FATHER, UNION
    env = environment(tmp_path)
    cfg = d.decode(env['DIAGNOSTIC_CONFIG_JSON'].encode())
    cfg.update(mode='get_only_verify', created_id=FATHER, union_id=UNION)
    env.update(DIAGNOSTIC_MODE='get_only_verify', DIAGNOSTIC_CONFIG_JSON=d.canonical(cfg).decode(),
               DIAGNOSTIC_CONFIG_SHA256=d.sha(d.canonical(cfg)))
    prefix, source, _ = d.routes(cfg)
    snapshots = []

    def request(self, method, route, body=None):
        assert method == 'GET' and body is None and route in self.routes
        if self.host == 'api.github.com':
            if route == prefix:
                return {'private': True, 'full_name': cfg['data_repo']}
            assert route == source
            raw = d.canonical(M)
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}
        return Client().request(method, route)

    def encrypt(recipient, raw):
        snapshots.append(raw)
        return b'ZZ-ciphertext-' + str(len(snapshots)).encode()
    monkeypatch.setattr(d.GetOnly, 'request', request)
    monkeypatch.setattr(d, 'encrypt', encrypt)
    assert d.run(env, {}) is True
    files = sorted((tmp_path / 'out').glob('*.age'))
    assert len(files) == 4 and len({f.read_bytes() for f in files}) == 4
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in files)
    assert d.decode(snapshots[-1])['verification']['verified'] is True


def test_sibling_verification_three_captures_with_direct_family():
    from tests.test_one_time_parent_pilot import FATHER, OWNER, UNION
    cfg, _, _, _ = verify_clients()
    cfg.update(target_payload=copy.deepcopy(BODY), expected_parents=['profile-999009', 'profile-999008'],
               expected_children=[OWNER, FATHER])
    d.configuration(cfg)
    _, _, allowed = d.routes(cfg)
    assert len(allowed) == 3
    actual = Client().request('GET', '/api/' + FATHER)
    union = {'id': UNION, 'partners': cfg['expected_parents'], 'children': cfg['expected_children']}
    calls, saved = [], []

    class ClientRead:
        def request(self, method, route):
            calls.append((method, route))
            assert method == 'GET' and route in allowed
            if '/immediate-family' in route:
                return {'focus': {'id': FATHER}, 'nodes': {UNION: copy.deepcopy(union)}}
            return copy.deepcopy(union if '/union-' in route else actual)
    report = {}
    d.verify_read_only(ClientRead(), cfg, BODY, report,
                       lambda r: saved.append(copy.deepcopy(r)), lambda: 200)
    assert len(calls) == 3 and len(saved) == 4
    assert report['verification']['verified']
    assert report['verification']['checks']['family_parent_union']
    union['children'] = [OWNER]
    with pytest.raises(Blocked):
        d.verify_read_only(ClientRead(), cfg, BODY, {}, lambda r: None, lambda: 200)


def match_config():
    return dict(copy.deepcopy(C), mode='get_only_matches', discovery_id='profile-999002')


def match_vendor(c, values, calls):
    class Transport:
        def __init__(self, *a, **kw):
            pass
        def request(self, method, route):
            calls.append((method, route))
            v = values[len(calls) - 1]
            if isinstance(v, Exception):
                raise v
            return v
    return d.GetOnly('www.geni.com', 'ZZ-token', d.routes(c)[2], factory=Transport)


@pytest.mark.parametrize('listing', [[], {'results': []}, [{'id': 'profile-999003'}]])
def test_match_discovery_exact_routes_capture_before_next_read(listing):
    c = match_config()
    assert d.configuration(c) == c
    calls, saved = [], []
    v = match_vendor(c, [{'id': c['discovery_id']}, listing], calls)
    report = {}
    def save(value):
        assert len(calls) == len(saved) + 1
        saved.append(value)
    d.discover_matches(v, c, report, save, lambda: 200)
    assert len(calls) == 2 and len(saved) == 2
    assert all(method == 'GET' for method, route in calls)
    assert report['discovery']['identity'] == 'UNPROVED'
    assert report['discovery']['duplicate_absence'] == 'UNPROVED'
    with pytest.raises(Blocked):
        v.request('GET', d.routes(c)[2][1])
    with pytest.raises(Blocked):
        v.request('GET', '/api/profile-999003')
    assert len(calls) == 2


@pytest.mark.parametrize('bad', [{'error': 'ZZ-private'}, {'id': 'profile-999003'},
                                  {'id': 'profile-999002', 'name': 'Z' * 262144}])
def test_match_profile_bad_or_oversize_capture_stops_before_listing(bad):
    c = match_config()
    calls, saved = [], []
    with pytest.raises(Blocked):
        d.discover_matches(match_vendor(c, [bad], calls), c, {}, saved.append, lambda: 200)
    assert len(calls) == len(saved) == 1


@pytest.mark.parametrize('bad', [{'error': 'ZZ-denied'}, {'results': [], 'next_page': 'ZZ'},
                                  {'unexpected': []}, [None], [{}] * 21])
def test_match_listing_unrecognized_captured_no_traversal(bad):
    c = match_config()
    calls, saved = [], []
    with pytest.raises(Blocked):
        d.discover_matches(match_vendor(c, [{'id': c['discovery_id']}, bad], calls),
                           c, {}, saved.append, lambda: 200)
    assert len(calls) == len(saved) == 2


def test_match_capture_failure_expiry_and_denial_stop_without_retry():
    c = match_config()
    for fault in ('save', 'expiry', 'denied'):
        calls = []
        values = [d.TransportStop('response_status')] if fault == 'denied' else [
            {'id': c['discovery_id']}, []]
        def save(value, fault=fault):
            if fault == 'save':
                raise OSError('ZZ-save')
        with pytest.raises((Blocked, OSError, d.TransportStop)):
            d.discover_matches(match_vendor(c, values, calls), c, {}, save,
                               lambda fault=fault: c['expires_at'] if fault == 'expiry' else 200)
        assert len(calls) == (0 if fault == 'expiry' else 1)


def test_production_match_transport_admission_and_wire_routes(monkeypatch):
    c = match_config()
    requests, sleeps = [], []
    values = [{'id': c['discovery_id']}, []]
    class Response:
        status = 200
        def __init__(self):
            self.raw = d.canonical(values[len(requests) - 1])
        def getheader(self, key):
            return None
        def read(self, size):
            result, self.raw = self.raw[:size], self.raw[size:]
            return result
    class Socket:
        def __init__(self, *a, **kw):
            pass
        def request(self, method, route, **kw):
            requests.append((method, route))
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', Socket)
    monkeypatch.setattr(d.time, 'sleep', sleeps.append)
    v = d.GetOnly('www.geni.com', 'ZZ-token', d.routes(c)[2])
    report = {}
    d.discover_matches(v, c, report, lambda r: None, lambda: 200)
    assert type(v.transport) is d.MatchHTTPS
    assert requests == [('GET', r + '&api_version=1') for r in d.routes(c)[2]]
    assert v.transport.calls == 2 and len(sleeps) == 1
    for method, route in [('POST', d.routes(c)[2][0]), ('GET', '/api/profile-999003'),
                           ('GET', d.routes(c)[2][1])]:
        with pytest.raises(Blocked):
            v.transport.request(method, route)
    assert len(requests) == 2


def test_real_legacy_admission_still_rejects_match_route():
    c = match_config()
    with pytest.raises(Blocked):
        d.HTTPS('www.geni.com', 'ZZ-token').admit_vendor('GET', d.routes(c)[2][1])


def test_real_match_admission_rejects_mismatched_route_pair():
    c = match_config()
    routes = d.routes(c)[2]
    with pytest.raises(Blocked):
        d.MatchHTTPS('www.geni.com', 'ZZ-token', [routes[0], routes[1].replace('999002', '999003')])


def test_production_match_network_failure_consumes_route_no_retry(monkeypatch):
    c = match_config()
    sockets = []
    class Socket:
        def __init__(self, *a, **kw):
            sockets.append(True)
            raise OSError('ZZ-network-denial')
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', Socket)
    v = d.GetOnly('www.geni.com', 'ZZ-token', d.routes(c)[2])
    route = d.routes(c)[2][0]
    with pytest.raises(d.TransportStop):
        v.request('GET', route)
    with pytest.raises(Blocked):
        v.request('GET', route)
    with pytest.raises(Blocked):
        v.transport.request('GET', route)
    assert len(sockets) == 1


@pytest.mark.parametrize('debug', [False, True])
@pytest.mark.parametrize('status', [200, 400, 403, 429])
def test_single_profile_real_transport_one_vendor_route(monkeypatch, debug, status):
    c = dict(copy.deepcopy(C), mode='get_only_profile', target_id='profile-999002', debug=debug)
    assert d.configuration(c) == c
    _, _, vendor_routes = d.routes(c)
    gh, _, _ = clients()
    wires = []
    class Response:
        def __init__(self):
            self.status = status
            self.raw = d.canonical({'id': c['target_id']} if status == 200 else {
                'error': {'type': 'ZZ-sensitive', 'message': 'ZZ-token'}})
        def getheader(self, key):
            return 'application/json' if key == 'Content-Type' else None
        def read(self, size):
            result, self.raw = self.raw[:size], self.raw[size:]
            return result
    class Socket:
        def __init__(self, host, **kw):
            assert host == 'www.geni.com'
        def request(self, method, route, **kw):
            wires.append((method, route))
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', Socket)
    vendor = d.GetOnly('www.geni.com', 'ZZ-token', vendor_routes)
    saved = []
    r = d.diagnose(c, gh, vendor, saved.append, lambda: 200)
    assert len(wires) == 1 and wires[0] == ('GET', vendor_routes[0] + '&api_version=1')
    assert r['phase'] == ('READ_ONLY_COMPLETE' if status == 200 else 'STOPPED')
    if status == 200:
        assert saved[0]['profile_diagnostic']['response']['id'] == c['target_id']
    else:
        assert r['http_failure']['http_status'] == status
        assert ('debug' in r['http_failure']) is debug
        assert 'ZZ-sensitive' not in str(r) and 'ZZ-token' not in str(r)
    with pytest.raises(Blocked):
        vendor.request('GET', vendor_routes[0])
    with pytest.raises(Blocked):
        vendor.request('GET', '/api/profile')
    assert len(wires) == 1


def test_single_profile_capture_failure_and_expiry_no_followup():
    c = dict(copy.deepcopy(C), mode='get_only_profile', target_id='profile-999002', debug=True)
    for expired in (True, False):
        calls = []
        v = match_vendor(c, [{'id': c['target_id']}], calls)
        def save(report):
            raise OSError('ZZ-save')
        with pytest.raises((Blocked, OSError)):
            d.single_profile(v, c, {}, save, lambda expired=expired: c['expires_at'] if expired else 200)
        assert len(calls) == (0 if expired else 1)


def test_single_profile_config_rejects_extra_route_and_debug_drift(tmp_path):
    c = dict(copy.deepcopy(C), mode='get_only_profile', target_id='profile-999002', debug=True)
    for bad in (dict(c, target_id='profile'), dict(c, debug='true'), dict(c, union_id='union-999001')):
        with pytest.raises(Blocked):
            d.configuration(bad)
