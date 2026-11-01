"""Invented fixtures only; no network, credentials or live effects."""
import base64
import copy
import json
from pathlib import Path

import pytest

import relative_baseline as b
from tests.test_bounded_parent_addition import ANCHOR, IO, OWNER, SPOUSE, family, plan
from tests.test_protected_parent_addition import TOKEN


def approved():
    c = plan()
    return {k: copy.deepcopy(c[k]) for k in ('owner', 'anchor', 'expect_name', 'profiles',
            'family', 'allow_unknown_merge', 'expires_at')} | {
                'schema': 1, 'kind': 'read_only_relative_baseline',
                'external_edges': {SPOUSE: {'union-991099': 'child'}}}


def config(c):
    return {k: c[k] for k in ('owner', 'anchor', 'expect_name', 'allow_unknown_merge', 'expires_at')} | {
        'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a'*40,
        'data_path': 'ZZ/ZZ-baseline.json', 'recipient': 'age1'+'a'*58,
        'plan_sha256': b.sha(b.canonical(c))}


def client(c):
    model = IO(plan())

    class Fake:
        def __init__(self):
            self.trace = []

        def request(self, method, route):
            assert method == 'GET'
            self.trace.append(route)
            if '/immediate-family' in route:
                value = family(ANCHOR, c['family'])
                for p, edges in c['external_edges'].items():
                    value['nodes'][p]['edges'].update({u: {'rel': r} for u, r in edges.items()})
                return value
            if route.startswith('/api/union-'):
                return model.get_union(route.split('/')[2].split('?')[0])
            return model.get_profile(route.split('/')[2].split('?')[0])
    return Fake()


def test_verified_preserves_exact_external_edges_without_following():
    c = approved()
    v = client(c)
    snapshots = []
    r = b.observe(c, v, lambda x: snapshots.append(copy.deepcopy(x)), lambda: 200)
    assert r['phase'] == 'READ_ONLY_BASELINE_VERIFIED'
    assert r['create_enabled'] is False and r['retry_allowed'] is False
    assert snapshots[-1] == r and len(r['responses']) == 5
    assert all('991099' not in route for route in v.trace)


@pytest.mark.parametrize('bad', ['owner', 'name', 'profile', 'edge', 'union'])
def test_mismatch_stops_with_response_evidence(bad):
    c = approved()
    v = client(c)
    original = v.request

    def request(method, route):
        x = original(method, route)
        if bad == 'owner' and '/profile?' in route:
            x['id'] = 'profile-991099'
        if bad == 'name' and '/profile?' in route:
            x['first_name'] = 'ZZ-wrong'
        if bad == 'profile' and ANCHOR+'?' in route:
            x['public'] = True
        if bad == 'edge' and '/immediate-family' in route:
            x['nodes'][SPOUSE]['edges']['union-991099'] = {'rel': 'partner'}
        if bad == 'union' and '/union-' in route:
            x['children'] = []
        return x
    v.request = request
    snapshots = []
    assert b.observe(c, v, snapshots.append, lambda: 200)['phase'] == 'STOPPED'
    assert snapshots and snapshots[-1]['responses']


@pytest.mark.parametrize('change', [
    {'extra': True}, {'anchor': OWNER}, {'schema': True}, {'external_edges': {SPOUSE: {'union-991001': 'child'}}},
    {'external_edges': {'profile-991099': {'union-991099': 'child'}}},
    {'external_edges': {SPOUSE: {'union-991099': 'ZZ-invalid'}}},
])
def test_plan_rejects_unknown_or_ambiguous_scope(change):
    with pytest.raises(b.Blocked):
        b.plan(dict(approved(), **change))


def test_transport_get_once_no_dynamic_routes_and_expiry_after_wait(monkeypatch):
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    monkeypatch.setattr(b.time, 'sleep', lambda _: None)
    v = b.ReadOnlyVendor(TOKEN, approved())
    route = '/api/profile?fields='+b.FIELDS+'&only_ids=true'
    for method, target in [('POST', route), ('GET', '/api/union-991099?only_ids=true'),
                           ('GET', route+'&extra=true')]:
        with pytest.raises(b.Blocked):
            v.admit_vendor(method, target)
    v.admit_vendor('GET', route)
    with pytest.raises(b.Blocked):
        v.admit_vendor('GET', route)
    waits = []

    def wait(n):
        waits.append(n)
        monkeypatch.setattr(b.time, 'time', lambda: 999)
    monkeypatch.setattr(b.time, 'sleep', wait)
    with pytest.raises(b.Blocked):
        v.admit_vendor('GET', '/api/'+ANCHOR+'?fields='+b.FIELDS+'&only_ids=true')
    assert len(waits) == 1 and 0 < waits[0] <= 15 and v.calls == 1


def replay(tmp_path, monkeypatch, env_change=None, source_change=None):
    c = approved()
    cfg = config(c)
    raw = b.canonical(cfg)
    env = {'BASELINE_CONFIRM': 'READ_ONLY_RELATIVE_BASELINE', 'BASELINE_CONFIG_JSON': raw.decode(),
           'BASELINE_CONFIG_SHA256': b.sha(raw), 'BASELINE_EXECUTOR_SHA': 'b'*40,
           'GITHUB_SHA': 'b'*40, 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
           'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
           'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
           'GITHUB_RUN_ID': '991001', 'BASELINE_TREE_PAT': TOKEN,
           'GENI_SECONDARY_ACCESS_TOKEN': TOKEN, 'BASELINE_OUTPUT_DIR': str(tmp_path/'ZZ-evidence')}
    env.update(env_change or {})
    source = copy.deepcopy(c)
    source.update(source_change or {})
    content = b.canonical(source)
    trace = []

    class Git:
        def request(self, method, route):
            assert method == 'GET'
            trace.append(route)
            if '/contents/' not in route:
                return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            return {'type': 'file', 'encoding': 'base64', 'size': len(content),
                    'content': base64.b64encode(content).decode()}
    real_get_only = b.GetOnly
    monkeypatch.setattr(b, 'GetOnly', lambda host, token, routes:
                        real_get_only(host, token, routes, factory=lambda *a, **k: Git()))
    monkeypatch.setattr(b, 'ReadOnlyVendor', lambda *a: client(c))
    monkeypatch.setattr(b, 'encrypt', lambda recipient, raw: b'age-encryption.org/v1\n'+raw)
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    try:
        result = b.run(env)
    except b.Blocked:
        result = False
    return result, trace


def test_entrypoint_full_offline_source_decode_hash_and_encrypted_evidence(tmp_path, monkeypatch):
    ok, trace = replay(tmp_path, monkeypatch)
    assert ok and len(trace) == 2
    reports = sorted((tmp_path/'ZZ-evidence').glob('*.age'))
    assert len(reports) == 6
    final = json.loads(reports[-1].read_bytes().split(b'\n', 1)[1])
    assert final['phase'] == 'READ_ONLY_BASELINE_VERIFIED'
    assert final['production_enabled'] is False
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in reports)


@pytest.mark.parametrize('key,value', [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTOR', 'ZZ-other'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ-other'), ('GITHUB_REF', 'refs/heads/ZZ-other'),
    ('GITHUB_EVENT_NAME', 'push'), ('BASELINE_CONFIRM', 'ZZ-invalid'),
    ('BASELINE_CONFIG_SHA256', '0'*64), ('BASELINE_EXECUTOR_SHA', 'c'*40), ('GITHUB_SHA', 'ZZ')])
def test_environment_failures_precede_network(tmp_path, monkeypatch, key, value):
    ok, trace = replay(tmp_path, monkeypatch, {key: value})
    assert not ok and trace == []


def test_source_hash_drift_stops_before_vendor(tmp_path, monkeypatch):
    ok, trace = replay(tmp_path, monkeypatch, source_change={'expect_name': 'ZZ-changed ZZ-name'})
    assert not ok and len(trace) == 2


def test_workflow_gate_and_no_mutation_primitives():
    workflow = Path('.github/workflows/relative-baseline.yml').read_text()
    for marker in ('environment: father-create', 'github.run_attempt == 1',
                   'READ_ONLY_RELATIVE_BASELINE', 'secrets.RELATIVE_BASELINE_JSON',
                   'relative_baseline.py', 'if: always()'):
        assert marker in workflow
    source = Path('relative_baseline.py').read_text()
    assert "request('POST'" not in source and '.consume(' not in source and '.receipt(' not in source


@pytest.mark.parametrize('change', [{'extra': True}, {'schema': True},
    {'anchor': OWNER}, {'plan_sha256': 'ZZ-invalid'}, {'expires_at': True},
    {'data_repo': '../ZZ'}, {'data_path': '../ZZ.json'}])
def test_config_rejects_unpinned_input(change):
    with pytest.raises(b.Blocked):
        b.config(dict(config(approved()), **change))


def test_expiry_and_storage_failure_stop_before_followup():
    c = approved()
    v = client(c)
    snapshots = []
    assert b.observe(c, v, snapshots.append, lambda: 999)['phase'] == 'STOPPED'
    assert v.trace == []
    calls = []

    def save(r):
        calls.append(r)
        raise OSError('ZZ-storage-unavailable')
    with pytest.raises(OSError):
        b.observe(c, v, save, lambda: 200)
    assert len(v.trace) == 1


def test_token_self_wrong_id_stops_before_graph_even_if_name_matches():
    c = approved()
    v = client(c)
    original = v.request

    def request(method, route):
        value = original(method, route)
        if '/profile?' in route:
            value['id'] = ANCHOR
        return value
    v.request = request
    assert b.observe(c, v, lambda _: None, lambda: 200)['phase'] == 'STOPPED'
    assert len(v.trace) == 1


def test_all_allowlisted_routes_exhaust_and_no_other_method(monkeypatch):
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    monkeypatch.setattr(b.time, 'sleep', lambda _: None)
    v = b.ReadOnlyVendor(TOKEN, approved())
    assert len(v.routes) <= 16
    for route in sorted(v.routes):
        v.admit_vendor('GET', route)
    assert v.calls == len(v.routes)
    for method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
        with pytest.raises(b.Blocked):
            v.admit_vendor(method, next(iter(v.routes)))


@pytest.mark.parametrize('code', ['transport_unavailable', 'response_oversize',
    'response_deadline', 'response_status', 'response_redirect', 'response_malformed'])
def test_first_read_transport_failure_retains_safe_enum_and_structure(code):
    c = approved()
    trace = []
    secret = 'ZZ-must-not-survive'

    class Failure:
        def request(self, method, route):
            trace.append((method, route))
            raise b.TransportStop(code, evidence={'http_status': 401,
                'body_media': 'application/json', 'body_parse': 'json', 'error_shape': 'object',
                'retry_after_state': 'numeric', 'retry_after_seconds': 60,
                'body_over_cap': False, 'body_bytes_observed': 42,
                'location_present': True, 'link_present': False,
                'geni_error_message': secret, 'geni_error_type': secret,
                'Location': secret, 'token': secret, 'url': secret})
    snapshots = []
    r = b.observe(c, Failure(), snapshots.append, lambda: 200)
    assert r['phase'] == 'STOPPED' and r['responses'] == [] and len(trace) == 1
    assert r['failure_code'] == code and r['http_failure']['http_status'] == 401
    assert r['http_failure']['retry_after_seconds'] == 60
    assert r['http_failure']['location_present'] is True
    assert secret not in json.dumps(snapshots)
    assert r['create_enabled'] is False and r['retry_allowed'] is False


@pytest.mark.parametrize('evidence', [
    {'http_status': True, 'body_media': 'ZZ-private', 'body_bytes_observed': -1,
     'location_present': 'ZZ-private', 'link_present': 1},
    {'http_status': 999, 'retry_after_seconds': 10**20, 'request_id_present': 'ZZ-private'},
])
def test_failure_evidence_rejects_nonstructural_or_out_of_range_values(evidence):
    class Failure:
        def request(self, method, route):
            raise b.TransportStop('response_status', evidence=evidence)
    r = b.observe(approved(), Failure(), lambda _: None, lambda: 200)
    assert r['http_failure'] == {}


def test_validation_failure_has_fixed_code_not_exception_text():
    class Failure:
        def request(self, method, route):
            raise ValueError('ZZ-private-exception')
    r = b.observe(approved(), Failure(), lambda _: None, lambda: 200)
    assert r['failure_code'] == 'validation_or_storage'
    assert 'http_failure' not in r and 'ZZ-private-exception' not in json.dumps(r)


def test_pacing_waits_the_full_15_seconds(monkeypatch):
    # #638: the pacing constant is load-bearing (vendor request rate), not any
    # small delay: 15 -> 1 must fail a test.
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    monkeypatch.setattr(b.time, 'monotonic', lambda: 100.0)
    waits = []
    monkeypatch.setattr(b.time, 'sleep', waits.append)
    v = b.ReadOnlyVendor(TOKEN, approved())
    v.admit_vendor('GET', '/api/profile?fields='+b.FIELDS+'&only_ids=true')
    v.admit_vendor('GET', '/api/'+ANCHOR+'?fields='+b.FIELDS+'&only_ids=true')
    assert waits == [15]


def test_failed_admission_still_consumes_the_route(monkeypatch):
    # #638: a route is consumed before the pacing wait: an admission that
    # fails only at the post-wait expiry recheck has still spent its route,
    # so it can never be retried.
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    v = b.ReadOnlyVendor(TOKEN, approved())
    v.admit_vendor('GET', '/api/profile?fields='+b.FIELDS+'&only_ids=true')
    family_route = '/api/'+ANCHOR+'/immediate-family?only_ids=true'

    def wait(_):
        monkeypatch.setattr(b.time, 'time', lambda: 999)
    monkeypatch.setattr(b.time, 'sleep', wait)
    with pytest.raises(b.Blocked):
        v.admit_vendor('GET', family_route)
    monkeypatch.setattr(b.time, 'time', lambda: 200)
    monkeypatch.setattr(b.time, 'sleep', lambda _: None)
    with pytest.raises(b.Blocked):
        v.admit_vendor('GET', family_route)


def test_expiry_at_final_check_stops_before_verified():
    # #638: plan expiry is re-checked after the last read, before the snapshot
    # may be called VERIFIED: expiry in that gap stops the run.
    c = approved()
    v = client(c)
    total_reads = len(c['profiles']) + 1 + len(c['family'])

    def clock():
        return 999 if len(v.trace) >= total_reads else 200
    assert b.observe(c, v, lambda _: None, clock)['phase'] == 'STOPPED'
    assert len(v.trace) == total_reads
