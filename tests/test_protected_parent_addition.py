"""Synthetic offline route, entry and immutable-source tests. No credentials or network."""
import base64
import json

import pytest

import protected_parent_addition as p
from tests.test_bounded_parent_addition import ANCHOR, IO, NEW, OWNER, PARENTS, family, plan

TOKEN = 'ZZ-not-a-real-token'


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)


def config(c):
    return {'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a'*40,
        'data_path': 'ZZ/ZZ-plan.json', 'owner': c['owner'], 'anchor': c['anchor'],
        'expect_name': c['expect_name'], 'recipient': 'age1'+'a'*58,
        'allow_unknown_merge': True, 'accept_hidden_parent_risk': True,
        'accept_private_create_risk': True, 'expires_at': c['expires_at'],
        'plan_sha256': p.sha(p.canonical(c))}


def env(c, tmp_path):
    cfg = config(c)
    raw = p.canonical(cfg)
    return {'PARENT_DEBUG': 'true', 'PARENT_CONFIRM': 'CREATE_APPROVED_ONE_PARENT',
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
        'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
        'GITHUB_SHA': 'b'*40, 'PARENT_EXECUTOR_SHA': 'b'*40,
        'PARENT_CONFIG_JSON': raw.decode(), 'PARENT_CONFIG_SHA256': p.sha(raw),
        'PARENT_OUTPUT_DIR': str(tmp_path/'ZZ-out'), 'GITHUB_RUN_ID': '991001',
        'PARENT_TREE_PAT': TOKEN, 'GENI_SECONDARY_ACCESS_TOKEN': TOKEN}


def test_allow_only_initial_plan_profile_and_anchor_reads():
    c = plan()
    v = p.ScopedVendor(TOKEN, c)
    for target in ['profile', *c['profiles']]:
        v.admit_vendor('GET', '/api/'+target+'?fields='+p.FIELDS+'&only_ids=true')
    v.admit_vendor('GET', '/api/'+ANCHOR+'/immediate-family?only_ids=true')
    for route in ['/api/'+NEW+'?fields='+p.FIELDS+'&only_ids=true',
        '/api/'+PARENTS+'?only_ids=true', '/api/'+OWNER+'/immediate-family?only_ids=true',
        '/api/'+ANCHOR+'/merge', '/api/'+ANCHOR+'/immediate-family?only_ids=true&ZZ=1']:
        with pytest.raises(p.Blocked):
            v.admit_vendor('GET', route)


def test_one_post_only_and_never_to_authenticated_owner():
    v = p.ScopedVendor(TOKEN, plan())
    for route in ['/api/'+OWNER+'/add-parent', '/api/'+ANCHOR+'/add-sibling']:
        with pytest.raises(p.Blocked):
            v.admit_vendor('POST', route)
    v.admit_vendor('POST', '/api/'+ANCHOR+'/add-parent')
    with pytest.raises(p.Blocked):
        v.admit_vendor('POST', '/api/'+ANCHOR+'/add-parent')
    assert v.post_count == 1 and v.unknown_send


def test_pacing_expiry_rechecked_after_wait(monkeypatch):
    v = p.ScopedVendor(TOKEN, plan())
    v.admit_vendor('GET', '/api/profile?fields='+p.FIELDS+'&only_ids=true')
    waits = []

    def wait(n):
        waits.append(n)
        monkeypatch.setattr(p.time, 'time', lambda: 999)
    monkeypatch.setattr(p.time, 'sleep', wait)
    with pytest.raises(p.Blocked):
        v.admit_vendor('POST', '/api/'+ANCHOR+'/add-parent')
    assert len(waits) == 1 and 0 < waits[0] <= 15 and v.calls == 1


def test_ack_then_exact_graph_controls_new_routes():
    c, v = plan(), p.ScopedVendor(TOKEN, plan())
    model = IO(c)

    def request(method, route, body=None):
        v.admit_vendor(method, route)
        if method == 'POST':
            return model.add_parent(ANCHOR, body)
        if '/immediate-family' in route:
            return model.get_family(ANCHOR)
        return model.get_union(PARENTS)
    v.request = request
    io = p.IO(v, debug=True)
    io.add_parent(ANCHOR, p.core.vendor_parent_payload(c['entry']['payload']))
    assert NEW in v.profiles and NEW in v.families and v.unions == set()
    with pytest.raises(p.Blocked):
        io.get_union(PARENTS)
    io.get_family(ANCHOR)
    assert io.get_union(PARENTS)['id'] == PARENTS and v.unions == {PARENTS}
    with pytest.raises(p.Blocked):
        io.add_parent(ANCHOR, p.core.vendor_parent_payload(c['entry']['payload']))


def test_bad_anchor_graph_never_admits_union():
    c, v = plan(), p.ScopedVendor(TOKEN, plan())
    v.created = NEW
    io = p.IO(v)
    io.anchor_after = family(ANCHOR, c['family'])
    with pytest.raises(p.Blocked):
        io.get_union(PARENTS)
    assert v.unions == set()


@pytest.mark.parametrize('result', [{'id': OWNER}, {'id': 'ZZ-invalid'},
    {'error': {}}, None, {'id': 'https://ZZ.invalid/'}])
def test_bad_ack_no_profile_route(result):
    v = p.ScopedVendor(TOKEN, plan())
    v.request = lambda *a: result
    with pytest.raises(p.Blocked):
        p.IO(v).add_parent(ANCHOR, p.core.vendor_parent_payload(plan()['entry']['payload']))
    assert v.created is None and NEW not in v.profiles


@pytest.mark.parametrize('key,value', [('PARENT_DEBUG','false'),('GITHUB_RUN_ATTEMPT','2'),
    ('GITHUB_EVENT_NAME','push'),('GITHUB_REF','refs/heads/ZZ'),('GITHUB_ACTOR','ZZ'),
    ('GITHUB_TRIGGERING_ACTOR','ZZ'),('PARENT_EXECUTOR_SHA','c'*40),
    ('PARENT_CONFIG_SHA256','0'*64),('PARENT_CONFIRM','ZZ')])
def test_bad_entry_env_blocks_before_credentials(tmp_path, monkeypatch, key, value):
    e = env(plan(), tmp_path)
    e[key] = value
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    with pytest.raises(p.Blocked):
        p.run(e)


def test_config_anchor_closed_and_distinct():
    c = config(plan())
    assert p.config(c) == c
    for change in ({'anchor': OWNER}, {'anchor': 'ZZ-invalid'}, {'extra': True}):
        bad = dict(c, **change)
        with pytest.raises(p.Blocked):
            p.config(bad)


def replay(tmp_path, monkeypatch, *, mutate=None, stop_at_vendor=False, change_env=None):
    c = plan()
    c['entry']['payload']['names']['he']['first_name'] = 'ZZ-אב'
    if mutate:
        mutate(c)
    e = env(c, tmp_path)
    if change_env:
        change_env(e)
    calls = []
    snapshots = []
    model = IO(c)

    class Git:
        def __init__(self, *a, **k):
            pass

        def request(self, method, route, body=None):
            calls.append((method, route))
            assert method == 'GET'
            if route == '/repos/ZZ-owner/ZZ-source':
                return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            assert route == '/repos/ZZ-owner/ZZ-source/contents/ZZ/ZZ-plan.json?ref='+'a'*40
            raw = json.dumps(c).encode()  # ASCII serialization intentionally differs from canonical
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}

    class Vendor:
        def __init__(self, token, approved):
            assert approved == c
            if stop_at_vendor:
                raise OSError('ZZ-offline-boundary')
            self.plan = approved

    class Store:
        def __init__(self, private):
            self.private = private

        def receipt(self, marker, stage, ciphertext):
            assert ciphertext.startswith(b'age-encryption.org/v1\n')

        def consume(self, marker):
            pass

    def encrypt(recipient, raw):
        snapshots.append(raw)
        return b'age-encryption.org/v1\nZZ-cipher'
    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'ScopedVendor', Vendor)
    monkeypatch.setattr(p, 'IO', lambda vendor, **k: model)
    monkeypatch.setattr(p, 'Store', Store)
    monkeypatch.setattr(p, 'encrypt', encrypt)
    return p.run(e), calls, snapshots, model


def test_real_private_source_decode_and_canonical_hash_replay(tmp_path, monkeypatch):
    ok, calls, snapshots, model = replay(tmp_path, monkeypatch)
    assert ok and len(calls) == 2 and len(model.posts) == 1
    reports = [json.loads(x) for x in snapshots[1:]]
    assert reports[-1]['phase'] == 'VERIFIED'
    assert reports[-1]['executor_sha'] == 'b'*40
    assert reports[-1]['production_enabled'] is True
    assert reports[-1]['mode'] == 'protected_one_parent'
    assert reports[-1]['run_id'] == '991001'
    assert len(list((tmp_path/'ZZ-out').glob('*.age'))) == len(reports)


def test_dry_replay_stops_at_vendor_boundary_without_post(tmp_path, monkeypatch):
    ok, calls, snapshots, model = replay(tmp_path, monkeypatch, stop_at_vendor=True)
    assert not ok and len(calls) == 2 and not model.posts
    assert json.loads(snapshots[-1])['failure']['setup_stage'] == 'vendor_credential'


def test_unknown_life_status_blocked_before_vendor(tmp_path, monkeypatch):
    ok, _, snapshots, model = replay(tmp_path, monkeypatch,
        mutate=lambda c: c['entry']['payload'].update(is_alive=None))
    assert not ok and not model.posts
    assert json.loads(snapshots[-1])['failure']['setup_stage'] == 'plan_config_consistency'


def test_plan_canonical_hash_mismatch_stops_before_vendor(tmp_path, monkeypatch):
    def alter(e):
        cfg = json.loads(e['PARENT_CONFIG_JSON'])
        cfg['plan_sha256'] = '0'*64
        raw = p.canonical(cfg)
        e.update(PARENT_CONFIG_JSON=raw.decode(), PARENT_CONFIG_SHA256=p.sha(raw))
    ok, _, snapshots, model = replay(tmp_path, monkeypatch, change_env=alter)
    assert not ok and not model.posts
    assert json.loads(snapshots[-1])['failure']['setup_stage'] == 'plan_hash'


def test_config_plan_anchor_mismatch_stops_before_vendor(tmp_path, monkeypatch):
    def alter(e):
        cfg = json.loads(e['PARENT_CONFIG_JSON'])
        cfg['anchor'] = 'profile-991099'
        raw = p.canonical(cfg)
        e.update(PARENT_CONFIG_JSON=raw.decode(), PARENT_CONFIG_SHA256=p.sha(raw))
    ok, _, snapshots, model = replay(tmp_path, monkeypatch, change_env=alter)
    assert not ok and not model.posts
    assert json.loads(snapshots[-1])['failure']['setup_stage'] == 'plan_config_consistency'


def test_finite_read_budget():
    v = p.ScopedVendor(TOKEN, plan())
    route = '/api/profile?fields='+p.FIELDS+'&only_ids=true'
    for _ in range(24):
        v.admit_vendor('GET', route)
    with pytest.raises(p.Blocked):
        v.admit_vendor('GET', route)


def test_fixed_failure_diagnostics_no_external_text():
    v = p.ScopedVendor(TOKEN, plan())

    def fail(*a):
        raise p.TransportStop('response_status', evidence={'http_status': 429,
            'geni_error_message': 'ZZ-external-text', 'body_media': 'text/plain',
            'body_parse': 'empty', 'geni_rate_remaining': 0})
    v.request = fail
    with pytest.raises(p.TransportStop) as exc:
        p.IO(v, debug=True).get_profile('profile')
    assert exc.value.evidence['http_status'] == 429
    assert 'ZZ-external-text' not in json.dumps(exc.value.evidence)


def test_workflow_gate_and_secret_are_separate():
    from pathlib import Path
    s = Path('.github/workflows/protected-parent-addition.yml').read_text()
    for required in ['environment: father-create', 'group: one-time-parent-pilot',
        'inputs.debug == true', 'github.run_attempt == 1', 'github.sha == inputs.executor_sha',
        'secrets.ONE_PARENT_ADDITION_JSON', 'PYTHONPATH=src python3 protected_parent_addition.py',
        'if: always()', 'retention-days: 1', 'persist-credentials: false']:
        assert required in s
    assert 'GUARDED_FAMILY_ADDITIONS_JSON' not in s
