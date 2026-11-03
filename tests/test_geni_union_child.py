"""Synthetic ZZ single-child experiment. No live credentials or endpoints."""
import base64
import json

import pytest

import geni_uploader.core.geni_union_child_model as m
import geni_uploader.runners.geni_union_child_create as p
from tests.test_geni_protected_household import (
    ANCHOR,
    OWNER,
    TOKEN,
    UNION,
    ModelIO,
    env,
)
from tests.test_geni_protected_household import (
    plan as old_plan,
)
from tests.test_guarded_family_additions import Store


def plan():
    c = old_plan(); c['entries'] = c['entries'][:1]
    c['accept_omitted_union_fields'] = False
    return c


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)


def wired(c, anomaly=None, ack=None, evidence=None):
    v = p.ScopedVendor(TOKEN, c); model = ModelIO(c, anomaly); calls = []
    def request(method, route, body=None):
        v.admit_vendor(method, route); calls.append((method, route, body))
        if method == 'POST':
            actual = model.add(c['anchor'], c['mode'], body)
            return ack if ack is not None else actual
        node = route.split('/api/')[1].split('?')[0].split('/')[0]
        if '/immediate-family?' in route: return model.get_family(node)
        if '/union-' in route: return model.get_union(node)
        return model.get_profile(node)
    v.request = request
    return v, model, calls, p.IO(v, evidence=evidence)


def run(c=None, anomaly=None, ack=None, evidence=None, store=None):
    c = c or plan(); saved = []
    v, model, calls, io = wired(c, anomaly, ack, evidence or saved.append)
    result = m.execute(c, io, store or Store(), lambda x: b'ZZ-cipher', lambda: 200)
    return result, v, model, calls, saved


def test_one_union_target_post_then_all_proofs():
    r, v, model, calls, saved = run()
    assert r['phase'] == 'VERIFIED' and len(model.posts) == 1
    assert [route for method, route, _ in calls if method == 'POST'] == ['/api/' + UNION + '/add-child']
    assert len([x for x in calls if x[0] == 'GET']) == 12
    assert next(x for x in saved if x['stage'] == 'ack_raw')['value']['id'] == 'profile-99201'
    with pytest.raises(m.shared.Blocked): v.admit_vendor('POST', '/api/' + UNION + '/add-child')


@pytest.mark.parametrize('bad', ['partner', 'multiple', 'omitted'])
def test_policy_rejects_other_modes_multiple_and_omitted_proofs(bad):
    c = plan()
    if bad == 'partner': c['mode'] = 'partner'; c['target_union'] = None
    if bad == 'multiple': c['entries'] = old_plan()['entries']
    if bad == 'omitted': c['accept_omitted_union_fields'] = True
    with pytest.raises(m.shared.Blocked): p.ScopedVendor(TOKEN, c)


@pytest.mark.parametrize('ack', [{'id': UNION, 'children': ['profile-99201']}, {},
                               {'id': OWNER}, {'error': 'ZZ'}, {'id': 'ZZ-invalid'}])
def test_unknown_or_union_ack_saved_then_stop_no_discovery(ack):
    r, v, model, calls, saved = run(ack=ack)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending
    assert saved[-1]['stage'] == 'ack_raw' and saved[-1]['value'] == ack
    post = next(i for i, x in enumerate(calls) if x[0] == 'POST')
    assert len(calls) == post + 1


@pytest.mark.parametrize('anomaly', ['privacy', 'description', 'claimed', 'extra_edge',
                                   'wrong_union', 'lost_response', 'omitted'])
def test_anomalies_stop_never_second_post(anomaly):
    r, _v, model, calls, _ = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED'
    assert len(model.posts) == (0 if anomaly == 'omitted' else 1)
    assert sum(method == 'POST' for method, _, _ in calls) <= 1


def test_ack_storage_failure_closes_pending_before_profile_read():
    def save(r):
        if r['stage'] == 'ack_raw': raise OSError()
    r, v, model, calls, _ = run(evidence=save)
    assert r['phase'] == 'STOPPED' and v.pending and len(model.posts) == 1
    assert calls[-1][0] == 'POST'


def test_routes_never_profile_or_other_union_or_update():
    v = p.ScopedVendor(TOKEN, plan())
    for method, route in [('POST', '/api/' + ANCHOR + '/add-child'),
                          ('POST', '/api/union-99999/add-child'),
                          ('POST', '/api/' + UNION + '/update'),
                          ('DELETE', '/api/' + UNION),
                          ('GET', '/api/profile-99999?fields=' + p.FIELDS + '&only_ids=true')]:
        with pytest.raises(m.shared.Blocked): v.admit_vendor(method, route)


def test_marker_reuse_shared_with_old_workflow():
    c = plan(); st = Store(); run(c, store=st)
    c['expires_at'] += 50
    r, _, model, _, _ = run(c, store=st)
    assert r['phase'] == 'STOPPED' and not model.posts


def test_real_source_decode_hash_and_consistency_to_boundary(tmp_path, monkeypatch):
    c = plan(); e = {k.replace('HOUSEHOLD_CREATE_', 'UNION_CHILD_'): v
                     for k, v in env(c, tmp_path).items()}
    e['UNION_CHILD_CONFIRM'] = 'CREATE_ONE_UNION_CHILD'
    requests = []
    class Git:
        def request(self, method, route, body=None):
            requests.append((method, route))
            if '/contents/' not in route: return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            raw = json.dumps(c).encode()
            return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(raw).decode(), 'size': len(raw)}
    monkeypatch.setattr(p, 'HTTPS', lambda *_a, **_k: Git())
    monkeypatch.setattr(p, 'encrypt', lambda *_: b'ZZ-cipher')
    seen = []
    def boundary(token, actual): seen.append(actual); raise OSError()
    monkeypatch.setattr(p, 'ScopedVendor', boundary)
    assert not p.run(e) and seen == [c]
    assert all(method == 'GET' for method, _ in requests)


def test_workflow_separate_secret_same_human_protection():
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/geni-union-child-create.yml').read_text()
    for text in ['environment: father-create', 'UNION_CHILD_PACKAGE_JSON',
                 'CREATE_ONE_UNION_CHILD', 'github.run_attempt == 1',
                 'github.sha == inputs.executor_sha', 'group: one-time-parent-pilot',
                 'cancel-in-progress: false', 'persist-credentials: false', 'if: always()']:
        assert text in s
    assert 'HOUSEHOLD_CREATE_PACKAGE_JSON' not in s


@pytest.mark.parametrize('status', [301, 302, 429, 500])
def test_real_https_post_no_redirect_or_retry(status, monkeypatch):
    import geni_uploader.runners.one_time_parent_pilot as transport
    sent = []
    class Response:
        def __init__(self): self.status = status
        def getheader(self, name): return 'https://evil.invalid/ZZ' if name == 'Location' else 'application/json'
        def read(self, _): return b'{"error":"ZZ-private"}'
    class Connection:
        def __init__(self, host, port, timeout):
            assert host == 'www.geni.com' and port == 443 and timeout == 20
        def request(self, method, route, **kwargs): sent.append((method, route))
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', Connection)
    v = p.ScopedVendor(TOKEN, plan()); io = p.IO(v, evidence=lambda _: None)
    with pytest.raises(transport.TransportStop): io.add(ANCHOR, 'child', m.vendor_payload(plan()['entries'][0]['payload']))
    assert sent == [('POST', '/api/' + UNION + '/add-child')]
    assert v.pending and v.post_count == 1
    with pytest.raises(m.shared.Blocked): io.add(ANCHOR, 'child', m.vendor_payload(plan()['entries'][0]['payload']))
    assert len(sent) == 1


def test_omitted_union_children_after_create_is_not_success():
    c = plan(); v, model, calls, io = wired(c, evidence=lambda _: None)
    original = model.get_union
    def union(node):
        actual = original(node)
        if model.posts: actual.pop('children')
        return actual
    model.get_union = union
    result = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert result['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending
    assert calls[-1][0] == 'GET'


def test_no_evidence_sink_means_no_send():
    c = plan(); _v, model, calls, io = wired(c)
    result = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert result['phase'] == 'STOPPED' and not model.posts
    assert not any(x[0] == 'POST' for x in calls)


def hebrew_plan():
    c = plan(); b = c['entries'][0]['payload']
    b['names'] = {'he': {'first_name': 'שם בדוי', 'last_name': 'משפחה בדויה'}}
    b['first_name'] = 'שם בדוי'; b['last_name'] = 'משפחה בדויה'; b['gender'] = 'female'
    return c


def test_hebrew_only_no_invented_english_and_exact_readback():
    c = hebrew_plan(); r, _, model, _, _ = run(c)
    assert r['phase'] == 'VERIFIED'
    body = model.posts[0]
    assert body['names'] == c['entries'][0]['payload']['names']
    assert body['first_name'] == 'שם בדוי' and body['gender'] == 'female'
    assert 'en' not in body['names'] and 'en-US' not in body['names']


def test_old_household_workflow_still_rejects_hebrew_only():
    import geni_uploader.core.geni_protected_household_model as old
    c = hebrew_plan()
    with pytest.raises(m.shared.Blocked): old.plan(c)
    with pytest.raises(m.shared.Blocked): old.vendor_payload(c['entries'][0]['payload'])
    assert m.plan(c) == c


@pytest.mark.parametrize('field', ['first_name', 'last_name'])
def test_hebrew_top_level_must_match_name_map(field):
    c = hebrew_plan(); c['entries'][0]['payload'][field] = 'ZZ-wrong'
    with pytest.raises(m.shared.Blocked): m.plan(c)


@pytest.mark.parametrize('names', [{'en': {'first_name': 'ZZ'}},
                                  {'en-US': {'first_name': 'ZZ'}},
                                  {'he': {'first_name': 'שם'}, 'fr': {'first_name': 'ZZ'}}, {}])
def test_other_locale_shapes_not_admitted(names):
    c = hebrew_plan(); c['entries'][0]['payload']['names'] = names
    with pytest.raises(m.shared.Blocked): m.plan(c)


def test_generated_extra_locale_not_accepted_as_exact_payload():
    c = hebrew_plan(); expected = c['entries'][0]['payload']
    actual = dict(m.vendor_payload(expected), id='profile-99201', claimed=False)
    actual['names'] = dict(actual['names'], **{'en-US': {'first_name': 'ZZ-generated'}})
    with pytest.raises(m.shared.Blocked):
        m.profile_check(actual, expected, 'profile-99201', True, created=True)


def test_hebrew_and_bilingual_markers_remain_original_policy():
    import geni_uploader.core.geni_protected_household_model as old
    for c in [plan(), hebrew_plan()]:
        entry = c['entries'][0]
        assert old.marker(c, entry) == old.marker(m.plan(c), entry)


def first_child_plan():
    c = plan(); c['family'][UNION].pop(OWNER)
    c['accept_first_child_omission'] = True
    return c


def first_child_run(c=None, after_omitted=False, partners_omitted=False):
    c = c or first_child_plan(); saved = []
    _v, model, _, io = wired(c, evidence=saved.append)
    original = model.get_union
    def union(node):
        actual = original(node)
        if not model.posts or after_omitted: actual.pop('children')
        if partners_omitted: actual.pop('partners')
        return actual
    model.get_union = union
    result = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    return result, model


def test_first_child_omission_before_only_explicit_after():
    r, io = first_child_run()
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert r['unknown_union_fields'] and all(x['fields'] == ['children'] for x in r['unknown_union_fields'])
    assert r['responses'][-1]['value']['children'] == ['profile-99201']


def test_first_child_after_omitted_stops_with_consumed_create():
    r, io = first_child_run(after_omitted=True)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1


def test_first_child_partners_must_be_explicit_before():
    r, io = first_child_run(partners_omitted=True)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('flag', [False, None, 1, 'true'])
def test_first_child_risk_not_implicit_or_truthy(flag):
    c = first_child_plan(); c['accept_first_child_omission'] = flag
    if flag is False:
        r, io = first_child_run(c)
        assert r['phase'] == 'STOPPED' and not io.posts
    else:
        with pytest.raises(m.shared.Blocked): m.plan(c)


def test_first_child_default_off():
    c = first_child_plan(); del c['accept_first_child_omission']
    r, io = first_child_run(c)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_first_child_flag_rejected_when_existing_child_visible():
    c = plan(); c['accept_first_child_omission'] = True
    with pytest.raises(m.shared.Blocked): m.plan(c)


def test_old_workflow_rejects_new_flag():
    import geni_uploader.core.geni_protected_household_model as old
    with pytest.raises(m.shared.Blocked): old.plan(first_child_plan())


def test_first_child_exception_never_applies_to_another_union():
    c = first_child_plan()
    c['family']['union-99888'] = {OWNER: 'partner'}
    v, model, _, io = wired(c, evidence=lambda _: None)
    original = model.get_union
    def union(node):
        actual = original(node)
        if not model.posts: actual.pop('children')
        return actual
    model.get_union = union
    r = m.execute(c, io, Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and not model.posts and v.post_count == 0


def test_shared_model_no_exception_when_child_already_in_graph():
    import geni_uploader.core.geni_protected_household_model as old
    c = plan(); model = ModelIO(c, 'omitted')
    r = old.execute(c, model, Store(), lambda _: b'ZZ-cipher', lambda: 200,
                    accept_first_child_omission=True)
    assert r['phase'] == 'STOPPED' and not model.posts


def test_model_level_post_creation_omission_stops_without_transport_layer():
    import geni_uploader.core.geni_protected_household_model as old
    c = first_child_plan(); c.pop('accept_first_child_omission')
    model = ModelIO(c); original = model.get_union
    def union(node):
        actual = original(node)
        actual.pop('children')  # both before and after the one create
        return actual
    model.get_union = union
    r = old.execute(c, model, Store(), lambda _: b'ZZ-cipher', lambda: 200,
                    accept_first_child_omission=True)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1
    assert r['items'][0]['phase'] == 'ACKNOWLEDGED_NOT_VERIFIED'
    assert r['stage'] == 'read_union'


def two_plan():
    c = old_plan(); c['accept_omitted_union_fields'] = False
    c['declared_children'] = 2
    return c


def test_explicit_two_children_each_verified_before_second():
    c = two_plan(); r, v, model, calls, _ = run(c)
    assert r['phase'] == 'VERIFIED' and len(model.posts) == 2 and not v.pending
    posts = [i for i, x in enumerate(calls) if x[0] == 'POST']
    between = calls[posts[0] + 1:posts[1]]
    assert any('/profile-99201/immediate-family?' in route for _, route, _ in between)
    assert sum('/union-' in route for _, route, _ in between) == 2
    assert len(r['items']) == 2 and all(x['phase'] == 'VERIFIED' for x in r['items'])


@pytest.mark.parametrize('anomaly', ['privacy', 'description', 'claimed', 'extra_edge',
                                   'wrong_union', 'lost_response'])
def test_two_children_uncertainty_never_sends_second(anomaly):
    r, v, model, _, _ = run(two_plan(), anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending


def test_two_flag_exact_scope_not_general_unbounded_mode():
    for count in [1, 3]:
        c = two_plan(); c['entries'] = n_plan(count)['entries']
        with pytest.raises(m.shared.Blocked): m.plan(c)
    c = two_plan(); c['declared_children'] = 'true'
    with pytest.raises(m.shared.Blocked): m.plan(c)
    c = two_plan(); del c['declared_children']
    with pytest.raises(m.shared.Blocked): m.plan(c)


def test_two_children_first_child_omission_still_only_before_any_child():
    c = first_child_plan(); c['entries'] = old_plan()['entries']; c['declared_children'] = 2
    r, model = first_child_run(c)
    assert r['phase'] == 'VERIFIED' and len(model.posts) == 2
    r, model = first_child_run(c, after_omitted=True)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1


def test_two_markers_and_receipts_replay_cannot_recreate_first():
    c = two_plan(); st = Store(); run(c, store=st)
    c['expires_at'] += 50
    r, _, model, _, _ = run(c, store=st)
    assert r['phase'] == 'STOPPED' and not model.posts
    import geni_uploader.core.geni_protected_household_model as old
    assert old.marker(c, c['entries'][0]) != old.marker(c, c['entries'][1])


def n_plan(count):
    import copy
    c = plan(); template = c['entries'][0]
    c['entries'] = []
    for i in range(count):
        entry = copy.deepcopy(template); entry['key'] = 'zz-entry-' + str(i)
        entry['payload']['first_name'] = 'ZZ-Child-' + str(i)
        entry['payload']['names']['en']['first_name'] = 'ZZ-Child-' + str(i)
        entry['payload']['names']['he']['first_name'] = 'שם בדוי ' + str(i)
        c['entries'].append(entry)
    c['declared_children'] = count
    return c


def test_declared_n_not_fixed_two_or_old_four_cap():
    for count in [1, 3, 5]:
        c = n_plan(count); r, v, model, calls, _ = run(c)
        assert r['phase'] == 'VERIFIED' and len(model.posts) == count
        assert v.calls == len(calls) == v.budget
        assert len({item['marker'] for item in r['items']}) == count


@pytest.mark.parametrize('declared', [0, -1, True, 2.0, '2'])
def test_declared_count_not_truthy_or_empty(declared):
    c = n_plan(2); c['declared_children'] = declared
    with pytest.raises(m.shared.Blocked): m.plan(c)


def test_declared_count_mismatch_uses_unique_valid_entries():
    for actual, declared in [(1, 2), (3, 2), (5, 3)]:
        c = n_plan(actual)
        assert len({e['key'] for e in c['entries']}) == actual
        assert len({e['payload']['first_name'] for e in c['entries']}) == actual
        c['declared_children'] = declared
        with pytest.raises(m.shared.Blocked): m.plan(c)


def test_transport_admission_pending_latch_direct_not_masked_by_io():
    v = p.ScopedVendor(TOKEN, two_plan()); route = '/api/' + UNION + '/add-child'
    v.admit_vendor('POST', route)
    with pytest.raises(m.shared.Blocked): v.admit_vendor('POST', route)
    assert v.post_count == 1


def test_io_pending_latch_and_payload_binding_direct():
    c = two_plan(); v, model, _, io = wired(c, evidence=lambda _: None)
    wrong = m.vendor_payload(c['entries'][1]['payload'])
    with pytest.raises(m.shared.Blocked): io.add(ANCHOR, 'child', wrong)
    assert not model.posts and v.post_count == 0
    actual = io.add(ANCHOR, 'child', m.vendor_payload(c['entries'][0]['payload']))
    assert actual['id'] == 'profile-99201'
    with pytest.raises(m.shared.Blocked): io.add(ANCHOR, 'child', wrong)
    assert len(model.posts) == 1


def test_io_pending_guard_independent_of_transport_admission():
    c = two_plan(); v = p.ScopedVendor(TOKEN, c); v.pending = True
    called = []
    v.request = lambda *a: called.append(a) or {'id': 'profile-99201'}
    with pytest.raises(m.shared.Blocked):
        p.IO(v, evidence=lambda _: None).add(ANCHOR, 'child', m.vendor_payload(c['entries'][0]['payload']))
    assert not called


@pytest.mark.parametrize('missing', ['profile', 'anchor', 'reciprocal', 'union'])
def test_io_verified_independent_proof_block_cannot_be_removed(missing):
    c = two_plan(); v, model, _, io = wired(c, evidence=lambda _: None)
    created = io.add(ANCHOR, 'child', m.vendor_payload(c['entries'][0]['payload']))['id']
    graph = model.spec
    # Populate real returned proofs without invoking the model execution path.
    io.get_profile(created); io.get_family(ANCHOR); io.get_family(created); io.get_union(UNION)
    assert io.proofs['graph'] == graph
    io.proofs.pop(missing)
    with pytest.raises((m.shared.Blocked, KeyError)):
        io.verified(created, UNION, graph)
    assert v.pending
