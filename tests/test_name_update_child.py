"""Synthetic ZZ mixed update/create tests, no live effects."""
import copy

import pytest

import geni_uploader.core.geni_protected_household_model as old
import geni_uploader.core.name_update_child_model as m
import geni_uploader.runners.name_update_child_create as p
from tests.test_geni_protected_household import ANCHOR, OWNER, TOKEN, UNION, ModelIO
from tests.test_geni_union_child import n_plan
from tests.test_guarded_family_additions import Store

TARGET = 'profile-99801'


def plan():
    c = n_plan(1); c['family'][UNION][TARGET] = 'child'
    expected = {'id': TARGET, 'guid': '99901', 'first_name': 'שם', 'last_name': 'משפחה',
                'names': {'he': {'first_name': 'שם', 'last_name': 'משפחה'},
                          'en-US': {'first_name': 'שם', 'last_name': 'משפחה'}},
                'gender': 'male', 'is_alive': True, 'public': False, 'claimed': False,
                'about_me': 'ZZ existing report', 'unions': ['https://www.geni.com/api/' + UNION]}
    change = {'first_name': 'ZZ Existing', 'last_name': 'ZZ Family',
              'names': {'he': copy.deepcopy(expected['names']['he']),
                        'en-US': {'first_name': 'ZZ Existing', 'last_name': 'ZZ Family'}}}
    c['profiles'][TARGET] = {k: v for k, v in dict(expected, **change).items()
                            if k in ('first_name', 'last_name', 'gender', 'is_alive', 'public', 'claimed')}
    return {'schema': 1, 'owner': OWNER, 'expect_name': c['expect_name'], 'anchor': ANCHOR,
            'target': TARGET, 'union': UNION, 'expected': expected, 'set': change,
            'create': c, 'expires_at': c['expires_at']}


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)


def wired(c=None, anomaly=None):
    c = c or plan(); v = p.ScopedVendor(TOKEN, c); model = ModelIO(c['create'])
    model.profiles[TARGET] = copy.deepcopy(c['expected']); calls = []; saved = []
    def request(method, route, body=None):
        v.admit_vendor(method, route); calls.append((method, route, body))
        if method == 'POST':
            if route.endswith('/update'):
                if anomaly == 'update_loss': raise OSError()
                model.profiles[TARGET].update(copy.deepcopy(body))
                if anomaly == 'privacy': model.profiles[TARGET]['public'] = True
                return {'id': TARGET}
            return model.add(ANCHOR, 'child', body)
        node = route.split('/api/')[1].split('?')[0].split('/')[0]
        if '/immediate-family?' in route: return model.get_family(node)
        if '/union-' in route: return model.get_union(node)
        return model.get_profile(node)
    v.request = request
    io = p.IO(v, evidence=saved.append)
    return c, v, model, calls, saved, io


def run(anomaly=None, store=None):
    c, v, model, calls, saved, io = wired(anomaly=anomaly)
    r = m.execute(c, io, store or Store(), lambda _: b'ZZ-cipher', lambda: 200)
    return r, v, model, calls, saved


def test_update_verified_then_one_create():
    r, v, model, calls, saved = run()
    assert r['phase'] == 'VERIFIED' and r['update_phase'] == 'VERIFIED'
    assert v.update_verified and len(model.posts) == 1
    assert [route for method, route, _ in calls if method == 'POST'] == [
        '/api/' + TARGET + '/update', '/api/' + UNION + '/add-child']
    assert any(x['stage'] == 'update_ack_raw' for x in saved)


@pytest.mark.parametrize('anomaly', ['update_loss', 'privacy'])
def test_uncertain_update_stops_create(anomaly):
    r, v, model, calls, _ = run(anomaly)
    assert r['phase'] == 'STOPPED' and not model.posts and not v.update_verified
    assert sum(method == 'POST' for method, _, _ in calls) == 1


def test_create_route_never_opens_before_update_proof():
    c, v, model, calls, _, io = wired()
    with pytest.raises(m.child.shared.Blocked):
        io.add(ANCHOR, 'child', old.vendor_payload(c['create']['entries'][0]['payload']))
    with pytest.raises(m.child.shared.Blocked): v.admit_vendor('POST', '/api/' + UNION + '/add-child')
    assert not model.posts and not calls


def test_update_payload_exact_and_hebrew_preserved():
    c = plan(); c['set']['names']['he']['first_name'] = 'שגוי'
    with pytest.raises(m.child.shared.Blocked): m.plan(c)
    c, _, _, calls, _, io = wired()
    with pytest.raises(m.child.shared.Blocked): io.update(TARGET, {'gender': 'female'})
    assert not calls


@pytest.mark.parametrize('missing', ['profile', 'anchor', 'reciprocal', 'union'])
def test_independent_update_proofs_cannot_be_skipped(missing):
    _c, v, _, _, _, io = wired(); v.update_pending = True; v.update_index = len(v.update_sequence)
    model = ModelIO(_c['create'])
    model.profiles[TARGET] = m.after(_c)
    io.update_proofs = {'profile': model.get_profile(TARGET),
                        'anchor': model.get_family(ANCHOR),
                        'reciprocal': model.get_family(TARGET), 'union': model.get_union(UNION)}
    io.update_proofs.pop(missing)
    with pytest.raises((m.child.shared.Blocked, KeyError)): io.verified_update()
    assert not v.update_verified


def test_update_marker_survives_expiry_change():
    c = plan(); key = m.marker(c); c['expires_at'] += 10; c['create']['expires_at'] += 10
    assert m.marker(c) == key


def test_replay_update_blocks_all_posts():
    c, _, _, _, _, _ = wired(); st = Store(); st.consume(m.marker(c))
    r, _, model, calls, _ = run(store=st)
    assert r['phase'] == 'STOPPED' and not model.posts and not any(x[0] == 'POST' for x in calls)


@pytest.mark.parametrize('stage', ['before', 'ack', 'final'])
def test_update_receipt_failure_never_creates(stage):
    class Denied(Store):
        def receipt(self, marker, actual, cipher):
            if marker.startswith('mixed-name-') and actual == stage: raise OSError()
            return super().receipt(marker, actual, cipher)
    r, _, model, calls, _ = run(store=Denied())
    assert r['phase'] == 'STOPPED' and not model.posts
    assert sum(x[0] == 'POST' for x in calls) == (0 if stage == 'before' else 1)


@pytest.mark.parametrize('field,value', [('guid', '99999'), ('gender', 'female'),
                                       ('is_alive', False), ('about_me', 'ZZ-changed'),
                                       ('claimed', True), ('unions', [])])
def test_post_update_immutable_fields_checked(field, value):
    c, _, model, _, _, io = wired(); original = io.update
    def update(target, body):
        actual = original(target, body); model.profiles[TARGET][field] = value
        return actual
    io.update = update
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and not model.posts


def test_unknown_ack_saved_then_stops_without_create():
    c, v, model, _, saved, io = wired(); original = v.request
    def request(method, route, body=None):
        actual = original(method, route, body)
        return {'id': UNION} if method == 'POST' else actual
    v.request = request
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and not model.posts
    assert any(x.get('stage') == 'update_ack_raw' and x['value']['id'] == UNION for x in saved)


def test_no_evidence_sink_prevents_update_send():
    c, v, model, calls, _, _ = wired()
    r = m.execute(c, p.IO(v), Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and not model.posts and not any(x[0] == 'POST' for x in calls)


def test_update_success_then_child_failure_partial_not_full_success():
    c, v, model, _, _, io = wired(); original = model.add
    def add(*args): original(*args); raise OSError()
    model.add = add
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and r['update_phase'] == 'VERIFIED'
    assert r['create_result']['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending


def test_real_private_source_decode_hash_to_mixed_boundary(tmp_path, monkeypatch):
    import base64
    import json
    c = plan(); cfg = {'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a' * 40,
                      'data_path': 'ZZ/ZZ-plan.json', 'owner': OWNER, 'anchor': ANCHOR,
                      'target_union': UNION, 'expect_name': c['expect_name'],
                      'recipient': 'age1' + 'a' * 58, 'allow_unknown_merge': True,
                      'accept_hidden_parent_risk': True, 'accept_private_create_risk': True,
                      'expires_at': 900, 'plan_sha256': p.sha(p.canonical(c))}
    raw = p.canonical(cfg)
    env = {'MIXED_CHILD_DEBUG': '1', 'MIXED_CHILD_CONFIRM': 'UPDATE_NAME_THEN_CREATE_CHILD',
           'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
           'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
           'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
           'GITHUB_SHA': 'b' * 40, 'MIXED_CHILD_EXECUTOR_SHA': 'b' * 40,
           'MIXED_CHILD_CONFIG_JSON': raw.decode(), 'MIXED_CHILD_CONFIG_SHA256': p.sha(raw),
           'MIXED_CHILD_OUTPUT_DIR': str(tmp_path / 'ZZ-out'), 'GITHUB_RUN_ID': '99101'}
    class Git:
        def request(self, method, route, body=None):
            assert method == 'GET'
            if '/contents/' not in route: return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            data = json.dumps(c).encode()
            return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(data).decode(), 'size': len(data)}
    monkeypatch.setattr(p, 'HTTPS', lambda *_a, **_k: Git())
    monkeypatch.setattr(p, 'encrypt', lambda *_: b'ZZ-cipher')
    seen = []
    def boundary(token, actual): seen.append(actual); raise OSError()
    monkeypatch.setattr(p, 'ScopedVendor', boundary)
    assert not p.run(env) and seen == [c]


def test_workflow_new_secret_and_exact_protected_gate():
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/name-update-child-create.yml').read_text()
    for text in ['environment: father-create', 'MIXED_CHILD_PACKAGE_JSON', 'UPDATE_NAME_THEN_CREATE_CHILD',
                 'github.sha == inputs.executor_sha', 'github.run_attempt == 1',
                 'group: one-time-parent-pilot', 'cancel-in-progress: false',
                 'persist-credentials: false', 'if: always()', 'retention-days: 1']:
        assert text in s


@pytest.mark.parametrize('index', range(10))
def test_exact_update_transport_order_rejects_each_wrong_next_request(index):
    c = plan(); v = p.ScopedVendor(TOKEN, c)
    for method, route in v.update_sequence[:index]:
        v.admit_vendor(method, route)
    # Every candidate is a legitimate request in this workflow, but not the next
    # one. Keeping the route and budget valid isolates the exact ORDER gate.
    expected = v.update_sequence[index]
    wrong = next(item for item in v.update_sequence if item != expected)
    before = (v.update_index, v.calls, v.update_pending)
    with pytest.raises(m.child.shared.Blocked):
        v.admit_vendor(*wrong)
    assert (v.update_index, v.calls, v.update_pending) == before
    assert not v.update_verified


@pytest.mark.parametrize('expired_read', [0, 1, 5, 6, 7, 8, 9, 10, 11, 12, 13])
def test_model_expiry_independent_of_transport_clock(expired_read):
    c, v, model, calls, _, io = wired(); ticks = []
    def clock():
        ticks.append(None)
        return c['expires_at'] if len(ticks) > expired_read else 200
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', clock)
    assert r['phase'] == 'STOPPED' and not model.posts and not v.update_verified
    # Transport still sees a non-expired clock, so it cannot mask this gate.
    assert p.time.time() < c['expires_at']
    assert sum(method == 'POST' for method, _, _ in calls) == (expired_read >= 8)


@pytest.mark.parametrize('field,value', [('id', 'profile-99899'), ('first_name', 'IncorrectIdentity')])
def test_mixed_owner_identity_rejected_before_any_update(field, value):
    c, v, model, calls, _, io = wired(); original = io.get_profile
    def get_profile(target):
        actual = original(target)
        if target == 'profile':
            actual = copy.deepcopy(actual); actual[field] = value
        return actual
    io.get_profile = get_profile
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and r['update_phase'] == 'NOT_SENT'
    assert len(calls) == 1 and calls[0][0] == 'GET'
    assert not model.posts and not v.update_pending and not v.update_verified
