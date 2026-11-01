import copy
import json
from pathlib import Path

import pytest

import protected_family_additions as p
from people_core import Blocked
from tests.test_guarded_family_additions import IO as FakeIO
from tests.test_guarded_family_additions import fixture


def env(tmp_path, mode='mother'):
    plan = fixture(mode)
    plan['expires_at'] = 2**39
    from tests.test_one_time_parent_pilot import C
    c = {k: v for k, v in C.items()}
    c.update(expires_at=plan['expires_at'], plan_sha256=p.sha(p.canonical(plan)))
    raw = p.canonical(c)
    return plan, c, {'FAMILY_DEBUG': 'true', 'FAMILY_CONFIG_JSON': raw.decode(), 'FAMILY_CONFIG_SHA256': p.sha(raw),
        'FAMILY_EXECUTOR_SHA': 'b'*40, 'GITHUB_SHA': 'b'*40,
        'FAMILY_CONFIRM': 'CREATE_APPROVED_FAMILY_ADDITIONS', 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
        'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
        'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_RUN_ID': '999009',
        'FAMILY_OUTPUT_DIR': str(tmp_path / 'out'), 'FAMILY_TREE_PAT': 'ZZ-private',
        'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-vendor'}


@pytest.mark.parametrize('mode,count', [('mother', 1), ('siblings', 4)])
@pytest.mark.parametrize('debug_value', ['1', 'true'])
def test_full_wiring_with_fake_provider_encrypted_only(monkeypatch, tmp_path, mode, count, debug_value):
    plan, cfg, e = env(tmp_path, mode)
    e['FAMILY_DEBUG'] = debug_value
    io = FakeIO(plan)
    calls, consumed, receipts, snapshots = [], set(), [], []

    class Git:
        def __init__(self, *a, **kw):
            pass

    class Private:
        def __init__(self, *a):
            self.marker = ''

        def load(self, path):
            assert path == cfg['data_path']
            return copy.deepcopy(plan)

        def consume(self):
            assert self.marker not in consumed
            consumed.add(self.marker)

        def receipt(self, stage, cipher):
            receipts.append(stage)
            assert cipher.startswith(b'ZZ-cipher')

    def request(self, method, route, body=None):
        self.admit_vendor(method, route)
        calls.append((method, route))
        if method == 'POST':
            return io.add(plan['owner'], route.rsplit('/', 1)[-1], body)
        target = route.split('/')[2].split('?')[0]
        if '/immediate-family?' in route:
            return io.get_family(target)
        return io.get_union(target) if target.startswith('union-') else io.get_profile(target)

    def encrypt(recipient, raw):
        snapshots.append(raw)
        return b'ZZ-cipher' + str(len(snapshots)).encode()
    original_io = p.IO
    debug_values = []

    def checked_io(client, *, debug=False):
        debug_values.append(debug)
        return original_io(client, debug=debug)
    monkeypatch.setattr(p, 'IO', checked_io)
    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p.ScopedVendor, 'request', request)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    assert p.run(e) is True
    assert debug_values == [True]
    assert len([x for x in calls if x[0] == 'POST']) == count
    assert len(consumed) == count and receipts == ['before', 'ack', 'final'] * count
    files = list((tmp_path / 'out').glob('*.age'))
    assert len(files) == len(snapshots) - 1
    assert all(x.read_bytes().startswith(b'ZZ-cipher') for x in files)
    assert all(x.stat().st_mode & 0o777 == 0o600 for x in files)
    assert json.loads(snapshots[-1])['phase'] == 'VERIFIED'


@pytest.mark.parametrize('key,val', [('FAMILY_CONFIRM', 'bad'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_REF', 'refs/heads/zz-other'), ('FAMILY_CONFIG_SHA256', 'a'*64),
    ('FAMILY_EXECUTOR_SHA', 'a'*40)])
def test_pins_before_any_effect(monkeypatch, tmp_path, key, val):
    _, _, e = env(tmp_path)
    e[key] = val
    monkeypatch.setattr(p, 'encrypt', lambda *a: pytest.fail('effect before pins'))
    with pytest.raises(Blocked):
        p.run(e)


@pytest.mark.parametrize('method,route', [('POST', '/api/profile-999001/add-sibling'),
    ('POST', '/api/profile-999001/delete'), ('GET', '/api/profile-999999?only_ids=true'),
    ('DELETE', '/api/profile-999001'), ('GET', '/api/union-999002?only_ids=true')])
def test_transport_exact_routes_reject_before_connection(method, route):
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    with pytest.raises(Blocked):
        v.admit_vendor(method, route)
    assert v.calls == 0


def test_transport_uncertain_send_is_permanently_blocked():
    c = fixture('siblings')
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    v.admit_vendor('POST', '/api/profile-999001/add-sibling')
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/profile-999001/add-sibling')


def test_unknown_seam_exception_normalized():
    class CustomError(Exception):
        pass

    class Client:
        def request(self, *a):
            raise CustomError('ZZ-private')
    with pytest.raises(Blocked):
        p.IO(Client()).get_profile('profile')


def test_workflow_protected_pins_and_shared_concurrency():
    s = Path('.github/workflows/guarded-family-additions.yml').read_text()
    assert 'environment: father-create' in s and 'group: one-time-parent-pilot' in s
    assert 'secrets.GUARDED_FAMILY_ADDITIONS_JSON' in s
    assert 'github.run_attempt == 1' in s and 'github.sha == inputs.executor_sha' in s
    assert 'contents: read' in s and 'CREATE_APPROVED_FAMILY_ADDITIONS' in s
    assert 'if: always()' in s and 'set +x' in s
    assert 'inputs.debug == true' in s
    assert 'required: true\n        default: true\n        type: boolean' in s
    assert "FAMILY_DEBUG: ${{ inputs.debug && '1' || '0' }}" in s


def test_scoped_add_body_cannot_drift_before_send():
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    with pytest.raises(Blocked):
        p.IO(v).add(c['owner'], 'add-parent', {'public': True})
    assert v.calls == 0 and v.post_count == 0


def test_scoped_add_duplicate_id_keeps_latch(monkeypatch):
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)

    def request(method, route, body):
        v.admit_vendor(method, route)
        return {'id': c['parents'][0]['id']}
    monkeypatch.setattr(v, 'request', request)
    with pytest.raises(Blocked):
        p.IO(v).add(c['owner'], 'add-parent', p.core.vendor_payload(c['entries'][0]['payload']))
    assert v.unknown_send and v.post_count == 1


def test_scoped_get_budget_enforced(monkeypatch):
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    v.calls = 40
    with pytest.raises(Blocked):
        v.admit_vendor('GET', '/api/' + c['union_id'] + '?only_ids=true')


def test_private_plan_hash_drift_stops_without_vendor(monkeypatch, tmp_path):
    plan, _, e = env(tmp_path)
    changed = copy.deepcopy(plan)
    changed['entries'][0]['payload']['gender'] = 'male'

    class Private:
        def __init__(self, *a):
            pass

        def load(self, *a):
            return changed
    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **kw: None)
    monkeypatch.setattr(p, 'encrypt', lambda *a: b'ZZ-cipher')
    monkeypatch.setattr(p, 'ScopedVendor', lambda *a: pytest.fail('vendor constructed'))
    assert p.run(e) is False


def test_transport_failure_encrypted_fields_are_structural_only():
    class Client:
        def request(self, *a):
            raise p.TransportStop('response_status', evidence={
                'http_status': 500, 'geni_error_message': 'ZZ-private',
                'arbitrary': 'ZZ-token', 'body_media': 'text/html'})
    with pytest.raises(p.TransportStop) as caught:
        p.IO(Client()).get_union('union-999001')
    assert caught.value.evidence == {'host': 'www.geni.com',
        'error_type': 'response_status', 'status_class': '5xx', 'http_status': 500}


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500])
@pytest.mark.parametrize('debug', [False, True])
def test_real_read_error_status_and_debug_shape(monkeypatch, status, debug):
    class Response:
        def __init__(self):
            self.status = status
            self.raw = b'{"error":{"type":"ZZ-private","message":"ZZ-secret"}}'
        def getheader(self, key):
            return {'Content-Type': 'application/json', 'X-API-Rate-Limit': '1',
                    'X-API-Rate-Remaining': '0', 'X-API-Rate-Window': '10'}.get(key)
        def read(self, size):
            result, self.raw = self.raw[:size], self.raw[size:]
            return result
    class Socket:
        def __init__(self, *a, **kw):
            pass
        def request(self, method, route, **kw):
            assert method == 'GET'
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(p.core.http.client, 'HTTPSConnection', Socket)
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    with pytest.raises(p.TransportStop) as caught:
        p.IO(v, debug=debug).get_profile(c['parents'][0]['id'])
    evidence = caught.value.evidence
    assert evidence['http_status'] == status
    assert ('debug' in evidence) is debug
    assert 'ZZ-private' not in str(evidence) and 'ZZ-secret' not in str(evidence)
    if debug:
        assert evidence['debug']['body_parse'] == 'json'
        assert evidence['debug']['error_shape'] == 'object'
        assert evidence['debug']['geni_rate_window'] == 10


def test_debug_structure_rejects_arbitrary_values_and_post_diagnostics():
    result = p.read_error_structure({'body_parse': 'ZZ-private', 'http_status': 403,
        'geni_error_message': 'ZZ-secret', 'body_bytes_observed': True,
        'geni_rate_limit': -1, 'request_id_present': 'ZZ-header'})
    assert result == {}
    class Client:
        def request(self, *a):
            raise p.TransportStop('response_status', evidence={'http_status': 403,
                'body_parse': 'json', 'error_shape': 'object'})
    with pytest.raises(p.TransportStop) as caught:
        p.IO(Client(), debug=True).request('POST', '/api/profile-999001/add-sibling')
    assert 'http_status' not in caught.value.evidence and 'debug' not in caught.value.evidence


@pytest.mark.parametrize('value', [None, '0', 'false', 'False', '', 'ZZ-invalid', True, 1])
def test_disabled_missing_invalid_debug_stops_before_effects(monkeypatch, tmp_path, value):
    _, _, e = env(tmp_path)
    if value is None:
        del e['FAMILY_DEBUG']
    else:
        e['FAMILY_DEBUG'] = value
    for seam in ('encrypt', 'HTTPS', 'PrivateGit', 'ScopedVendor', 'IO'):
        monkeypatch.setattr(p, seam, lambda *a, **kw: pytest.fail('effect before debug guard'))
    with pytest.raises(Blocked):
        p.run(e)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('elapsed,delay', [(0, 15), (4, 11), (10, 5), (14.5, 0.5), (16, 0)])
def test_guarded_request_start_pacing_has_fifteen_second_margin(monkeypatch, elapsed, delay):
    c = fixture()
    c['expires_at'] = 2**39
    v = p.ScopedVendor('ZZ-token', c)
    v.last = 100
    sleeps = []
    monkeypatch.setattr(p.time, 'monotonic', lambda: 100 + elapsed)
    monkeypatch.setattr(p.time, 'sleep', sleeps.append)
    v.admit_vendor('GET', '/api/' + c['union_id'] + '?only_ids=true')
    assert sleeps == [delay] and v.calls == 1


def test_expiry_during_margin_blocks_before_socket(monkeypatch):
    c = fixture()
    c['expires_at'] = 999
    v = p.ScopedVendor('ZZ-token', c)
    v.last = 100
    clock = [990]
    monkeypatch.setattr(p.time, 'time', lambda: clock[0])
    monkeypatch.setattr(p.time, 'monotonic', lambda: 100)
    monkeypatch.setattr(p.time, 'sleep', lambda delay: clock.__setitem__(0, 1005))
    monkeypatch.setattr(p.core.http.client, 'HTTPSConnection',
                        lambda *a, **kw: pytest.fail('socket constructed after expiry'))
    with pytest.raises(Blocked):
        v.request('GET', '/api/' + c['union_id'] + '?only_ids=true')
    assert v.calls == 0


@pytest.mark.parametrize('stage', ['github_credential', 'private_source', 'plan_hash',
    'plan_schema', 'plan_config_consistency', 'vendor_credential', 'execute_or_storage'])
def test_encrypted_setup_failure_stage_and_type_only(monkeypatch, tmp_path, stage):
    plan, cfg, e = env(tmp_path)
    snapshots = []

    class Git:
        def __init__(self, *a, **kw):
            if stage == 'github_credential':
                raise ValueError('ZZ-secret-must-not-survive')

    class Private:
        def __init__(self, *a):
            pass

        def load(self, *a):
            if stage == 'private_source':
                raise p.TransportStop('response_status', evidence={
                    'http_status': 403, 'message': 'ZZ-token', 'location_present': False})
            return copy.deepcopy(plan)

    if stage == 'plan_hash':
        cfg['plan_sha256'] = '0' * 64
    if stage == 'plan_schema':
        plan['entries'] = []
    if stage == 'plan_config_consistency':
        plan['expect_name'] = 'ZZ-Other ZZ-Family'
    if stage in ('plan_schema', 'plan_config_consistency'):
        cfg['plan_sha256'] = p.sha(p.canonical(plan))
    raw = p.canonical(cfg)
    e.update(FAMILY_CONFIG_JSON=raw.decode(), FAMILY_CONFIG_SHA256=p.sha(raw))

    def vendor(*a):
        assert stage in ('vendor_credential', 'execute_or_storage')
        if stage == 'vendor_credential':
            raise TypeError('ZZ-vendor-token')
        return object()

    def execute(*a):
        assert stage == 'execute_or_storage'
        raise OSError('ZZ-private-storage-message')

    def encrypt(recipient, raw):
        snapshots.append(raw)
        return b'ZZ-cipher'
    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p, 'ScopedVendor', vendor)
    monkeypatch.setattr(p.core, 'execute', execute)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    assert p.run(e) is False
    r = json.loads(snapshots[-1])
    assert r['failure']['setup_stage'] == stage
    assert r['stage'] == 'setup_or_storage' and r['retry_allowed'] is False
    expected = {'github_credential': 'ValueError', 'private_source': 'TransportStop',
        'plan_hash': 'Blocked', 'plan_schema': 'Blocked',
        'plan_config_consistency': 'Blocked', 'vendor_credential': 'TypeError',
        'execute_or_storage': 'OSError'}
    assert r['failure']['exception_type'] == expected[stage]
    assert b'ZZ-' not in snapshots[-1]
    if stage == 'private_source':
        assert r['failure']['http_status'] == 403
        assert r['failure']['transport_code'] == 'response_status'
        assert r['failure']['location_present'] is False


def test_setup_failure_filter_drops_unknown_type_and_arbitrary_evidence():
    class ZZSecretError(Exception):
        pass
    assert p.setup_failure('private_source', ZZSecretError('ZZ-token')) == {
        'setup_stage': 'private_source', 'exception_type': 'other'}
    exc = p.TransportStop('response_status', evidence={
        'http_status': True, 'location_present': 'ZZ-url', 'link_present': 1,
        'token': 'ZZ-secret', 'message': 'ZZ-private'})
    assert p.setup_failure('private_source', exc) == {'setup_stage': 'private_source',
        'exception_type': 'TransportStop', 'transport_code': 'response_status'}


def test_unicode_raw_hash_mismatch_and_canonical_source_replay(monkeypatch, tmp_path):
    import base64

    plan, cfg, e = env(tmp_path)
    plan['entries'][0]['payload']['names']['he'] = {
        'first_name': 'בדיקה', 'last_name': 'בדיקה'}
    # Same decoded plan, different wire bytes. Runtime intentionally pins canonical hash.
    source = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()
    assert source != p.canonical(plan)
    reached, snapshots = [], []

    class Git:
        def __init__(self, *a, **kw):
            pass

        def request(self, method, route):
            assert method == 'GET'
            if '/contents/' in route:
                return {'type': 'file', 'encoding': 'base64', 'size': len(source),
                        'content': base64.b64encode(source).decode()}
            return {'private': True, 'full_name': cfg['data_repo']}

    def vendor(*a):
        reached.append('vendor_boundary')
        raise ValueError('ZZ-intentional-boundary-stop')
    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'ScopedVendor', vendor)
    monkeypatch.setattr(p, 'encrypt', lambda recipient, raw: snapshots.append(raw) or b'ZZ-cipher')
    for canonical_pin in (False, True):
        cfg['plan_sha256'] = p.sha(p.canonical(plan) if canonical_pin else source)
        raw = p.canonical(cfg)
        e.update(FAMILY_CONFIG_JSON=raw.decode(), FAMILY_CONFIG_SHA256=p.sha(raw),
                 FAMILY_OUTPUT_DIR=str(tmp_path / str(canonical_pin)))
        assert p.run(e) is False
        failure = json.loads(snapshots[-1])['failure']
        assert failure['setup_stage'] == ('vendor_credential' if canonical_pin else 'plan_hash')
        assert reached == (['vendor_boundary'] if canonical_pin else [])
