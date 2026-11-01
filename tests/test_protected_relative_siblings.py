"""Synthetic exact-package admission and finite-route tests. No network."""
import base64
import copy
import json
from pathlib import Path

import pytest

import protected_relative_siblings as p
from tests.test_bounded_relative_siblings import ANCHOR, OWNER, PARENTS, plan
from tests.test_bounded_relative_siblings import IO as ModelIO
from tests.test_protected_parent_addition import TOKEN


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)


def config(c):
    return {'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a' * 40,
            'data_path': 'ZZ/ZZ-plan.json', 'owner': c['owner'], 'anchor': c['anchor'],
            'parent_union': c['parent_union'], 'expect_name': c['expect_name'],
            'recipient': 'age1' + 'a' * 58, 'allow_unknown_merge': True,
            'accept_hidden_parent_risk': True, 'accept_private_create_risk': True,
            'expires_at': c['expires_at'], 'plan_sha256': p.sha(p.canonical(c))}


def env(c, tmp_path):
    raw = p.canonical(config(c))
    return {'RELATIVE_DEBUG': 'true', 'RELATIVE_CONFIRM': 'CREATE_APPROVED_RELATIVE_SIBLINGS',
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
            'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
            'GITHUB_SHA': 'b' * 40, 'RELATIVE_EXECUTOR_SHA': 'b' * 40,
            'RELATIVE_CONFIG_JSON': raw.decode(), 'RELATIVE_CONFIG_SHA256': p.sha(raw),
            'RELATIVE_OUTPUT_DIR': str(tmp_path / 'ZZ-out'), 'GITHUB_RUN_ID': '991001',
            'RELATIVE_TREE_PAT': TOKEN, 'GENI_SECONDARY_ACCESS_TOKEN': TOKEN}


def wired(c, anomaly=None):
    vendor, model = p.ScopedVendor(TOKEN, c), ModelIO(c, anomaly)
    calls = []

    def request(method, route, body=None):
        vendor.admit_vendor(method, route)
        calls.append((method, route, copy.deepcopy(body)))
        if method == 'POST':
            return model.add_sibling(ANCHOR, body)
        node = route.split('/api/')[1].split('?')[0].split('/')[0]
        if '/immediate-family?' in route:
            return model.get_family(node)
        if '?fields=' in route:
            return model.get_profile(node)
        return model.get_union(node)
    vendor.request = request
    return vendor, model, calls


def test_two_posts_each_follow_verified_graphs_and_union():
    c = plan()
    v, model, calls = wired(c)
    from tests.test_guarded_family_additions import Store
    r = p.core.execute(c, p.IO(v), Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'VERIFIED' and len(model.posts) == 2 and v.post_count == 2
    assert not v.pending and v.calls == len(calls) < 40
    with pytest.raises(p.Blocked):
        p.IO(v).add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][0]['payload']))


@pytest.mark.parametrize('anomaly', ['lost_response', 'privacy', 'extra_edge'])
def test_uncertain_first_send_cannot_open_second(anomaly):
    from tests.test_guarded_family_additions import Store
    c = plan()
    v, model, _ = wired(c, anomaly)
    r = p.core.execute(c, p.IO(v), Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending
    with pytest.raises(p.Blocked):
        p.IO(v).add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][1]['payload']))


def test_routes_are_exact_and_created_reads_are_not_preopened():
    v = p.ScopedVendor(TOKEN, plan())
    for method, route in [('POST', '/api/' + OWNER + '/add-sibling'),
                          ('POST', '/api/' + ANCHOR + '/add-parent'),
                          ('DELETE', '/api/' + ANCHOR),
                          ('GET', '/api/profile-992001?fields=' + p.FIELDS + '&only_ids=true'),
                          ('GET', '/api/union-999999?only_ids=true'),
                          ('GET', '/api/' + PARENTS + '?only_ids=true&extra=true')]:
        with pytest.raises(p.Blocked):
            v.admit_vendor(method, route)


def test_payload_order_and_pending_union_proofs():
    c = plan()
    v, _, _ = wired(c)
    io = p.IO(v)
    with pytest.raises(p.Blocked):
        io.add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][1]['payload']))
    io.add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][0]['payload']))
    with pytest.raises(p.Blocked):
        io.get_union(PARENTS)
    io.get_family(ANCHOR)
    with pytest.raises(p.Blocked):
        io.get_union(PARENTS)
    io.get_family(v.created[-1])
    io.get_union(PARENTS)
    assert not v.pending


def test_finite_budget_and_expiry_after_pacing(monkeypatch):
    v = p.ScopedVendor(TOKEN, plan())
    v.calls = 40
    with pytest.raises(p.Blocked):
        v.admit_vendor('GET', '/api/profile?fields=' + p.FIELDS + '&only_ids=true')
    v.calls = 1
    v.last = p.time.monotonic()
    monkeypatch.setattr(p.time, 'sleep', lambda _: monkeypatch.setattr(p.time, 'time', lambda: 999))
    with pytest.raises(p.Blocked):
        v.admit_vendor('POST', '/api/' + ANCHOR + '/add-sibling')
    assert v.calls == 1 and v.pending and v.post_count == 1


@pytest.mark.parametrize('key,value', [('RELATIVE_DEBUG', 'false'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/ZZ'), ('GITHUB_ACTOR', 'ZZ'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('RELATIVE_EXECUTOR_SHA', 'c' * 40),
    ('RELATIVE_CONFIG_SHA256', '0' * 64), ('RELATIVE_CONFIRM', 'ZZ')])
def test_bad_entry_blocks_before_credentials(tmp_path, monkeypatch, key, value):
    e = env(plan(), tmp_path)
    e[key] = value
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    with pytest.raises(p.Blocked):
        p.run(e)


def replay(tmp_path, monkeypatch, change=None):
    c = plan()
    e = env(c, tmp_path)
    if change:
        cfg = json.loads(e['RELATIVE_CONFIG_JSON'])
        cfg.update(change)
        raw = p.canonical(cfg)
        e.update(RELATIVE_CONFIG_JSON=raw.decode(), RELATIVE_CONFIG_SHA256=p.sha(raw))
    vendor, model, _ = wired(c)
    snapshots = []

    class Git:
        def __init__(self, *a, **k):
            pass

        def request(self, method, route, body=None):
            assert method == 'GET' and body is None
            if route == '/repos/ZZ-owner/ZZ-source':
                return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            assert route.endswith('/contents/ZZ/ZZ-plan.json?ref=' + 'a' * 40)
            raw = json.dumps(c).encode()
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}

    class Store:
        def __init__(self, private):
            self.private = private

        def receipt(self, marker, stage, ciphertext):
            assert ciphertext.startswith(b'age-encryption.org/v1\n')

        def consume(self, marker):
            pass

    monkeypatch.setattr(p, 'HTTPS', Git)
    monkeypatch.setattr(p, 'ScopedVendor', lambda token, approved: vendor)
    monkeypatch.setattr(p, 'Store', Store)
    monkeypatch.setattr(p, 'encrypt', lambda recipient, raw: snapshots.append(raw) or b'age-encryption.org/v1\nZZ')
    return p.run(e), snapshots, model


def test_actual_admission_decode_hash_then_complete_executor(tmp_path, monkeypatch):
    ok, snapshots, model = replay(tmp_path, monkeypatch)
    assert ok and len(model.posts) == 2
    r = json.loads(snapshots[-1])
    assert r['phase'] == 'VERIFIED' and r['mode'] == 'protected_relative_siblings'
    assert r['production_enabled'] is True and r['executor_sha'] == 'b' * 40


@pytest.mark.parametrize('change,stage', [({'plan_sha256': '0' * 64}, 'plan_hash'),
    ({'parent_union': 'union-999999'}, 'plan_config_consistency'),
    ({'expires_at': 998}, 'plan_config_consistency')])
def test_source_config_mismatch_stops_before_send(tmp_path, monkeypatch, change, stage):
    ok, snapshots, model = replay(tmp_path, monkeypatch, change)
    assert not ok and not model.posts
    assert json.loads(snapshots[-1])['failure']['setup_stage'] == stage


def test_workflow_preserves_protected_human_gate_and_exact_inputs():
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/protected-relative-siblings.yml').read_text()
    for token in ["github.sha == inputs.executor_sha", "github.run_attempt == 1", "environment: father-create",
                  "github.actor == 'reihlinstinct'", "github.triggering_actor == 'reihlinstinct'",
                  "github.ref == 'refs/heads/master'", 'cancel-in-progress: false', 'permissions:\n  contents: read',
                  'secrets.RELATIVE_SIBLINGS_JSON', 'CREATE_APPROVED_RELATIVE_SIBLINGS',
                  'protected_relative_siblings.py', 'if: always()', 'retention-days: 1']:
        assert token in s
    assert 'schedule:' not in s and 'pull_request:' not in s


@pytest.mark.parametrize('result', [{'id': OWNER}, {'id': 'ZZ-invalid'}, {'error': {}}, None])
def test_bad_ack_keeps_pending_and_never_adds_read_routes(result):
    c = plan()
    v = p.ScopedVendor(TOKEN, c)

    def request(method, route, body=None):
        v.admit_vendor(method, route)
        return result
    v.request = request
    with pytest.raises(p.Blocked):
        p.IO(v).add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][0]['payload']))
    assert v.pending and v.post_count == 1 and not v.created
    assert v.profiles == {'profile', *c['profiles']}


def test_config_closed_union_and_anchor_validation():
    c = config(plan())
    assert p.config(c) == c
    for change in ({'anchor': OWNER}, {'parent_union': 'ZZ-invalid'}, {'extra': True}):
        with pytest.raises(p.Blocked):
            p.config(dict(c, **change))


def test_get_error_structure_is_private_and_post_body_not_forwarded():
    c = plan()
    v = p.ScopedVendor(TOKEN, c)

    def fail(*a):
        raise p.parent.TransportStop('response_status', evidence={'http_status': 403,
            'body_media': 'application/json', 'body_json_kind': 'object', 'private': 'ZZ-secret'})
    v.request = fail
    io = p.IO(v, debug=True)
    with pytest.raises(p.parent.TransportStop) as caught:
        io.get_profile(OWNER)
    evidence = caught.value.evidence
    assert evidence['http_status'] == 403 and 'debug' in evidence
    assert 'ZZ-secret' not in str(evidence) and 'private' not in evidence
    with pytest.raises(p.parent.TransportStop) as caught:
        io.add_sibling(ANCHOR, p.core.parent.vendor_parent_payload(c['entries'][0]['payload']))
    assert 'debug' not in caught.value.evidence and 'http_status' not in caught.value.evidence



@pytest.mark.parametrize('key,value', [('RELATIVE_DEBUG', 'false'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ-owner/ZZ-other'),
    ('GITHUB_REF', 'refs/heads/ZZ'), ('GITHUB_ACTOR', 'ZZ'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('RELATIVE_EXECUTOR_SHA', 'c' * 40),
    ('RELATIVE_CONFIG_SHA256', '0' * 64), ('RELATIVE_CONFIRM', 'ZZ')])
def test_each_env_guard_is_the_only_rejection(tmp_path, monkeypatch, key, value):
    """Positive control (#620): every other input is perfect and unexpired, so
    only the named guard can stop admission. The encryption preflight is armed
    as a sentinel: if the guard is deleted the run reaches it and fails here."""
    e = env(plan(), tmp_path)
    e[key] = value
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached; guard deleted: ' + key)
    monkeypatch.setattr(p, 'encrypt', preflight_sentinel)
    with pytest.raises(p.Blocked):
        p.run(e)


def test_expiry_guard_is_the_only_rejection(tmp_path, monkeypatch):
    """Positive control (#620): expired config with every other input perfect;
    only the expiry require can stop admission before the encryption preflight."""
    e = env(plan(), tmp_path)
    monkeypatch.setattr(p.time, 'time', lambda: 999)
    monkeypatch.setattr(p, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached; expiry guard deleted')
    monkeypatch.setattr(p, 'encrypt', preflight_sentinel)
    with pytest.raises(p.Blocked):
        p.run(e)


def test_workflow_gate_is_a_single_conjunction_of_every_admission_term():
    """Sentinel (tightened in #624): the protected job gate must be a single
    && conjunction of exactly these terms. Substring presence is not enough:
    an 'A || B' rewrite or a silently dropped term must fail here."""
    import re as _re
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/protected-relative-siblings.yml').read_text()
    m = _re.search(r'^  pilot:\n    if: \$\{\{ (.+) \}\}$', s, _re.MULTILINE)
    assert m, 'protected job gate not found'
    expr = m.group(1)
    assert '||' not in expr, 'gate must be a pure conjunction'
    assert {t.strip() for t in expr.split('&&')} == {
        "github.repository == 'reihlinstinct/geni-uploader'",
        "github.event_name == 'workflow_dispatch'",
        "github.ref == 'refs/heads/master'",
        'github.sha == inputs.executor_sha',
        "github.actor == 'reihlinstinct'",
        "github.triggering_actor == 'reihlinstinct'",
        'github.run_attempt == 1',
        'inputs.debug == true',
        "inputs.confirm == 'CREATE_APPROVED_RELATIVE_SIBLINGS'",
    }
