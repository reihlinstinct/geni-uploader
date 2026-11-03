"""Synthetic ZZ household fixtures, all effects injected."""
import base64
import copy
import json

import pytest

import geni_uploader.core.geni_protected_household_model as m
import geni_uploader.runners.geni_protected_household_create as p
from tests.test_bounded_parent_addition import family
from tests.test_guarded_family_additions import Store

OWNER = 'profile-99101'
ANCHOR = 'profile-99102'
PARTNER = 'profile-99103'
UNION = 'union-99101'
TOKEN = 'ZZ-token-123456'


def payload(name='ZZ-New'):
    return {'names': {'en': {'first_name': name}, 'he': {'first_name': 'שם בדוי'}},
            'first_name': name, 'is_alive': True, 'public': False,
            'about_me': 'דיווח משפחתי. ZZ family report, not independently verified.'}


def plan(mode='child'):
    graph = {UNION: {OWNER: 'child', ANCHOR: 'partner', PARTNER: 'partner'}}
    return {'schema': 1, 'mode': mode, 'owner': OWNER, 'expect_name': 'ZZ Owner',
            'anchor': ANCHOR, 'target_union': UNION if mode == 'child' else None,
            'profiles': {OWNER: {'first_name': 'ZZ', 'last_name': 'Owner', 'is_alive': True,
                                 'public': False, 'claimed': True},
                         ANCHOR: {'first_name': 'ZZ-Anchor', 'is_alive': True, 'public': False},
                         PARTNER: {'first_name': 'ZZ-Partner', 'is_alive': True, 'public': False}},
            'family': graph, 'external_edges': {}, 'entries': [
                {'key': 'zz-first', 'payload': payload()},
                *([{'key': 'zz-second', 'payload': payload('ZZ-Next')}] if mode == 'child' else [])],
            'expires_at': 900, 'allow_unknown_merge': True,
            'accept_hidden_duplicate_risk': True, 'accept_private_create_risk': True,
            'accept_union_selection_risk': True, 'accept_omitted_union_fields': True}


class ModelIO:
    def __init__(self, c, anomaly=None):
        self.c, self.anomaly, self.posts = c, anomaly, []
        self.spec = copy.deepcopy(c['family'])
        self.profiles = {k: dict(v, id=k) for k, v in c['profiles'].items()}
        self.target = c['target_union']

    def get_profile(self, node):
        actual = copy.deepcopy(self.profiles[OWNER if node == 'profile' else node])
        if node not in ('profile', *self.c['profiles']):
            if self.anomaly == 'privacy': actual['public'] = True
            if self.anomaly == 'description': actual['about_me'] = 'ZZ-wrong'
            if self.anomaly == 'claimed': actual['claimed'] = True
        return actual

    def get_family(self, node):
        if node == ANCHOR:
            graph = self.spec
        else:
            graph = {self.target: self.spec[self.target]}
        r = family(node, graph)
        for profile in r['nodes']:
            if profile.startswith('profile-'):
                for u, members in self.c['family'].items():
                    if u not in graph and profile in members:
                        r['nodes'][profile]['edges'][u] = {'rel': members[profile]}
        if self.anomaly == 'extra_edge' and self.posts:
            r['nodes'][ANCHOR]['edges']['union-99999'] = {'rel': 'partner'}
        return r

    def get_union(self, node):
        r = {'id': node, 'partners': [p for p, role in self.spec[node].items() if role == 'partner'],
             'children': [p for p, role in self.spec[node].items() if role == 'child']}
        if self.anomaly == 'omitted': del r['children']
        if self.anomaly == 'wrong_union' and self.posts: r['children'].append('profile-99999')
        return r

    def add(self, anchor, mode, body):
        assert anchor == ANCHOR and mode == self.c['mode']
        self.posts.append(body)
        if self.anomaly == 'lost_response': raise OSError()
        node = 'profile-' + str(99200 + len(self.posts))
        self.profiles[node] = dict(body, id=node, claimed=False)
        if mode == 'partner':
            self.target = 'union-99200'
            self.spec[self.target] = {ANCHOR: 'partner', node: 'partner'}
        else:
            self.spec[self.target][node] = 'child'
        return {'id': node}

    def verified(self, *_): pass


def run(c=None, anomaly=None, store=None):
    c = c or plan(); io = ModelIO(c, anomaly); store = store or Store(); saved = []
    r = m.execute(c, io, store, lambda v: saved.append(copy.deepcopy(v)) or b'ZZ-cipher', lambda: 200)
    return r, io, store, saved


@pytest.mark.parametrize('mode', ['child', 'partner'])
def test_complete(mode):
    c = plan(mode); r, io, st, saved = run(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == len(c['entries'])
    assert st.events == ['before', 'consume', 'ack', 'final'] * len(c['entries'])
    assert saved[-1] == r
    assert all(body['public'] is False and 'gender' not in body and body['about_me'] for body in io.posts)


@pytest.mark.parametrize('anomaly', ['privacy', 'description', 'claimed', 'extra_edge', 'wrong_union', 'lost_response'])
def test_uncertainty_no_second(anomaly):
    r, io, _, _ = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1


def test_omitted_not_empty_with_explicit_risk_and_complete_graph():
    r, io, _, _ = run(anomaly='omitted')
    assert r['phase'] == 'VERIFIED' and r['unknown_union_fields']
    c = plan(); c['accept_omitted_union_fields'] = False
    r, io, _, _ = run(c, anomaly='omitted')
    assert r['phase'] == 'STOPPED' and not io.posts


def test_replay_consumed_stops():
    c = plan(); _, _, st, _ = run(c); c['expires_at'] = 950
    r, io, _, _ = run(c, store=st)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('field', ['public', 'is_alive'])
def test_living_private_required(field):
    c = plan(); c['entries'][0]['payload'][field] = field == 'public'
    with pytest.raises(m.shared.Blocked): m.plan(c)


def test_dates_email_and_undeclared_fields_rejected():
    for field in ('email', 'birth', 'death', 'relationship_modifier'):
        c = plan(); c['entries'][0]['payload'][field] = 'ZZ'
        with pytest.raises(m.shared.Blocked): m.plan(c)


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)


def wired(c, anomaly=None):
    vendor = p.ScopedVendor(TOKEN, c); model = ModelIO(c, anomaly); calls = []
    def request(method, route, body=None):
        vendor.admit_vendor(method, route); calls.append((method, route))
        if method == 'POST': return model.add(c['anchor'], c['mode'], body)
        node = route.split('/api/')[1].split('?')[0].split('/')[0]
        if '/immediate-family?' in route: return model.get_family(node)
        if '/union-' in route: return model.get_union(node)
        return model.get_profile(node)
    vendor.request = request
    return vendor, model, calls


@pytest.mark.parametrize('mode', ['child', 'partner'])
def test_transport_latch_exact_proofs(mode):
    c = plan(mode); v, io, calls = wired(c)
    r = m.execute(c, p.IO(v), Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'VERIFIED' and not v.pending and len(io.posts) == len(c['entries'])
    assert v.calls == len(calls) < 60


@pytest.mark.parametrize('anomaly', ['privacy', 'description', 'claimed', 'extra_edge', 'wrong_union', 'lost_response'])
def test_transport_pending_never_reopens_after_stop(anomaly):
    c = plan(); v, io, _ = wired(c, anomaly)
    r = m.execute(c, p.IO(v), Store(), lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and v.pending and len(io.posts) == 1
    with pytest.raises(m.shared.Blocked): p.IO(v).add(ANCHOR, 'child', m.vendor_payload(c['entries'][1]['payload']))


def test_arbitrary_routes_and_unsolicited_new_union_rejected():
    v = p.ScopedVendor(TOKEN, plan())
    for method, route in [('GET', '/api/union-99200?fields=id,partners,children,status&only_ids=true'),
        ('POST', '/api/' + OWNER + '/add-child'), ('POST', '/api/' + ANCHOR + '/update'),
        ('GET', '/api/profile-9999?fields=' + p.FIELDS + '&only_ids=true'),
        ('DELETE', '/api/' + ANCHOR)]:
        with pytest.raises(m.shared.Blocked): v.admit_vendor(method, route)


def config(c):
    return {'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a' * 40,
            'data_path': 'ZZ/ZZ-plan.json', 'owner': c['owner'], 'anchor': c['anchor'],
            'target_union': c['target_union'], 'expect_name': c['expect_name'],
            'recipient': 'age1' + 'a' * 58, 'allow_unknown_merge': True,
            'accept_hidden_parent_risk': True, 'accept_private_create_risk': True,
            'expires_at': c['expires_at'], 'plan_sha256': p.sha(p.canonical(c))}


def env(c, tmp_path):
    raw = p.canonical(config(c))
    return {'HOUSEHOLD_CREATE_DEBUG': 'true', 'HOUSEHOLD_CREATE_CONFIRM': 'CREATE_APPROVED_HOUSEHOLD',
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
            'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
            'GITHUB_SHA': 'b' * 40, 'HOUSEHOLD_CREATE_EXECUTOR_SHA': 'b' * 40,
            'HOUSEHOLD_CREATE_CONFIG_JSON': raw.decode(), 'HOUSEHOLD_CREATE_CONFIG_SHA256': p.sha(raw),
            'HOUSEHOLD_CREATE_OUTPUT_DIR': str(tmp_path / 'ZZ-out'), 'GITHUB_RUN_ID': '991001',
            'HOUSEHOLD_CREATE_TREE_PAT': TOKEN, 'GENI_SECONDARY_ACCESS_TOKEN': TOKEN}


def test_actual_private_source_decode_unicode_hash_and_reaches_vendor(tmp_path, monkeypatch):
    c = plan(); raw = json.dumps(c).encode(); e = env(c, tmp_path); requests = []
    class Git:
        def request(self, method, route, body=None):
            requests.append((method, route))
            if '/contents/' not in route: return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(raw).decode(), 'size': len(raw)}
    monkeypatch.setattr(p, 'HTTPS', lambda *_a, **_k: Git())
    monkeypatch.setattr(p, 'encrypt', lambda *_: b'ZZ-cipher')
    seen = []
    def boundary(*args):
        seen.append(args[1]); raise OSError()
    monkeypatch.setattr(p, 'ScopedVendor', boundary)
    assert not p.run(e) and seen == [c]
    cfg = config(c); cfg['plan_sha256'] = p.sha(raw)
    e['HOUSEHOLD_CREATE_CONFIG_JSON'] = p.canonical(cfg).decode()
    e['HOUSEHOLD_CREATE_CONFIG_SHA256'] = p.sha(p.canonical(cfg))
    e['HOUSEHOLD_CREATE_OUTPUT_DIR'] = str(tmp_path / 'ZZ-other'); seen.clear()
    assert not p.run(e) and not seen
    assert requests and all(method == 'GET' for method, _ in requests)


@pytest.mark.parametrize('field,value', [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTOR', 'ZZ-other'),
    ('GITHUB_REF', 'refs/heads/ZZ-other'), ('HOUSEHOLD_CREATE_DEBUG', 'false'),
    ('HOUSEHOLD_CREATE_CONFIG_SHA256', 'a' * 64), ('HOUSEHOLD_CREATE_EXECUTOR_SHA', 'c' * 40)])
def test_setup_gates(tmp_path, field, value):
    e = env(plan(), tmp_path); e[field] = value
    with pytest.raises(m.shared.Blocked): p.run(e)


def test_consumption_failure_prevents_send():
    class Denied(Store):
        def consume(self, marker): raise OSError()
    r, io, _, _ = run(store=Denied())
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('stage', ['before', 'ack', 'final'])
def test_durable_receipt_failure_stops(stage):
    class Denied(Store):
        def receipt(self, marker, actual, cipher):
            if actual == stage: raise OSError()
            return super().receipt(marker, actual, cipher)
    r, io, _, _ = run(store=Denied())
    assert r['phase'] == 'STOPPED' and len(io.posts) == (0 if stage == 'before' else 1)


def test_duplicate_present_union_refs_and_wrong_domain_rejected():
    for refs in ([OWNER, 'https://www.geni.com/api/' + OWNER],
                 ['https://evil.invalid/api/' + OWNER], None):
        with pytest.raises(m.shared.Blocked):
            m.union_check({'id': UNION, 'children': refs}, UNION, plan()['family'][UNION], True)


def test_pending_latch_cannot_be_opened_without_proofs():
    c = plan(); v, _, _ = wired(c); io = p.IO(v)
    actual = io.add(ANCHOR, 'child', m.vendor_payload(c['entries'][0]['payload']))
    with pytest.raises((m.shared.Blocked, KeyError)):
        io.verified(actual['id'], UNION, c['family'])
    assert v.pending
    with pytest.raises(m.shared.Blocked): io.add(ANCHOR, 'child', m.vendor_payload(c['entries'][1]['payload']))


def test_workflow_protection_and_clear_route_name():
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/geni-protected-household-create.yml').read_text()
    for text in ('Geni protected - household', 'environment: father-create',
                 'group: one-time-parent-pilot', 'cancel-in-progress: false',
                 'github.sha == inputs.executor_sha', 'github.run_attempt == 1',
                 'inputs.debug == true', 'CREATE_APPROVED_HOUSEHOLD',
                 'PILOT_PRIVATE_EVIDENCE_WRITER', 'HOUSEHOLD_CREATE_PACKAGE_JSON',
                 'persist-credentials: false', 'if: always()', 'retention-days: 1'):
        assert text in s
    assert 'GENI_ACCESS_TOKEN:' not in s and 'geni_uploader.runners.geni_protected_household_create' in s


def test_failed_graph_raw_saved_before_proof_with_latch_closed():
    c = plan(); v, model, _ = wired(c, 'extra_edge'); evidence = []
    r = m.execute(c, p.IO(v, evidence=evidence.append), Store(),
                  lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending
    raw = [x for x in evidence if x['stage'] == 'family_raw'][-1]
    assert raw['value']['nodes'][ANCHOR]['edges']['union-99999'] == {'rel': 'partner'}
    proof = evidence[-1]
    assert proof['failure'] == 'exact_graph_mismatch' and proof['node_set_equal'] is True
    assert proof['expected_graph'][UNION]['profile-99201'] == 'child'
    assert proof['retry_allowed'] is False and 'graph' not in p.IO(v).proofs
    with pytest.raises(m.shared.Blocked):
        p.IO(v).add(ANCHOR, 'child', m.vendor_payload(c['entries'][1]['payload']))


def test_evidence_storage_failure_before_proof_blocks_next_send():
    c = plan(); v, model, _ = wired(c)
    def fail_after_create(value):
        if model.posts: raise OSError()
    r = m.execute(c, p.IO(v, evidence=fail_after_create), Store(),
                  lambda _: b'ZZ-cipher', lambda: 200)
    assert r['phase'] == 'STOPPED' and len(model.posts) == 1 and v.pending
