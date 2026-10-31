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
    return plan, c, {'FAMILY_CONFIG_JSON': raw.decode(), 'FAMILY_CONFIG_SHA256': p.sha(raw),
        'FAMILY_EXECUTOR_SHA': 'b'*40, 'GITHUB_SHA': 'b'*40,
        'FAMILY_CONFIRM': 'CREATE_APPROVED_FAMILY_ADDITIONS', 'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
        'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
        'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_RUN_ID': '999009',
        'FAMILY_OUTPUT_DIR': str(tmp_path / 'out'), 'FAMILY_TREE_PAT': 'ZZ-private',
        'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-vendor'}


@pytest.mark.parametrize('mode,count', [('mother', 1), ('siblings', 4)])
def test_full_wiring_with_fake_provider_encrypted_only(monkeypatch, tmp_path, mode, count):
    plan, cfg, e = env(tmp_path, mode)
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
    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p.ScopedVendor, 'request', request)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    assert p.run(e) is True
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
        'error_type': 'response_status', 'status_class': '5xx'}
