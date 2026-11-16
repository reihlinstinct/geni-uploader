"""Existing-parent read-only reconciliation; invented ZZ fixture only."""
import copy
from pathlib import Path

import pytest

import geni_uploader.runners.reconcile_parent_addition as r
from tests.test_bounded_parent_addition import ANCHOR, IO, NEW, OWNER, PARENTS, plan
from tests.test_protected_parent_addition import TOKEN, config


def fixture():
    c = plan()
    io = IO(c)
    io.add_parent(ANCHOR, r.core.vendor_parent_payload(c['entry']['payload']))
    io.posts = []
    return c, io


def test_verified_no_post_and_retains_boundary_edges():
    c, io = fixture()
    snapshots = []
    result = r.reconcile(c, io, NEW, PARENTS, lambda x: snapshots.append(copy.deepcopy(x)), lambda: 200)
    assert result['phase'] == 'READ_ONLY_VERIFIED' and not io.posts
    assert result['create_enabled'] is False and snapshots[-1] == result


@pytest.mark.parametrize('bad', ['wrong_union', 'bad_profile', 'unknown_edge', 'missing_edge'])
def test_read_only_mismatch_stops_without_write(bad):
    c, io = fixture()
    target = PARENTS
    if bad == 'wrong_union':
        target = 'union-991099'
    elif bad == 'bad_profile':
        io.profiles[NEW]['public'] = True
    else:
        original = io.get_family

        def get(p):
            x = original(p)
            if p == NEW:
                if bad == 'unknown_edge':
                    x['nodes'][ANCHOR]['edges']['union-991099'] = {'rel': 'partner'}
                else:
                    x['nodes'][ANCHOR]['edges'].pop('union-991001')
            return x
        io.get_family = get
    result = r.reconcile(c, io, NEW, target, lambda x: None, lambda: 200)
    assert result['phase'] == 'STOPPED' and not io.posts


def test_read_only_routes_cannot_mutate_or_repeat(monkeypatch):
    c = plan()
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r.time, 'sleep', lambda _: None)
    v = r.ReadOnlyVendor(TOKEN, c, NEW, PARENTS)
    for method, route in [('POST', '/api/'+ANCHOR+'/add-parent'),
        ('GET', '/api/profile-991099?fields='+r.FIELDS+'&only_ids=true'),
        ('GET', '/api/union-991099?only_ids=true')]:
        with pytest.raises(r.Blocked):
            v.admit_vendor(method, route)
    v.admit_vendor('GET', '/api/'+PARENTS+'?only_ids=true')
    with pytest.raises(r.Blocked):
        v.admit_vendor('GET', '/api/'+PARENTS+'?only_ids=true')


def test_config_pins_existing_target_and_union():
    c = dict(config(plan()), created_id=NEW, union_id=PARENTS)
    assert r.config(c) == c
    for key, val in [('created_id', OWNER), ('union_id', 'ZZ-invalid'), ('extra', True)]:
        x = dict(c, **{key: val})
        with pytest.raises(r.Blocked):
            r.config(x)


def test_workflow_read_only_confirmation_and_gate():
    from pathlib import Path
    s = Path('.github/workflows/reconcile-parent-addition.yml').read_text()
    for x in ['environment: father-create', 'READ_ONLY_EXISTING_PARENT',
        'secrets.RECONCILE_PARENT_ADDITION_JSON', 'inputs.debug == true',
        'github.run_attempt == 1', 'geni_uploader.runners.reconcile_parent_addition']:
        assert x in s


def test_reconciliation_module_has_no_mutation_method_or_storage():
    from pathlib import Path
    s = Path('src/geni_uploader/runners/reconcile_parent_addition.py').read_text()
    assert "request('POST'" not in s and '.consume(' not in s and '.receipt(' not in s
    assert 'def add_parent' not in s


def replay(tmp_path, monkeypatch, bad_ack=False, *, config_change=None, env_change=None):
    import base64
    import json

    from tests.test_protected_parent_addition import env
    c, model = fixture()
    cfg = dict(config(c), created_id=NEW, union_id=PARENTS)
    if config_change:
        cfg.update(config_change)
    raw = r.canonical(cfg)
    e = {k.replace('PARENT_', 'RECONCILE_'): v for k, v in env(c, tmp_path).items()}
    e.update(RECONCILE_CONFIG_JSON=raw.decode(), RECONCILE_CONFIG_SHA256=r.sha(raw),
             RECONCILE_CONFIRM='READ_ONLY_EXISTING_PARENT')
    if env_change:
        e.update(env_change)
    requests, reports = [], []
    marker = r.core.marker(c)

    class Git:
        def __init__(self, *a, **kw):
            pass

        def request(self, method, route, body=None):
            assert method == 'GET' and body is None
            requests.append(route)
            prefix = '/repos/ZZ-owner/ZZ-source'
            if route == prefix:
                return {'private': True, 'full_name': 'ZZ-owner/ZZ-source'}
            if '/contents/' in route:
                source = r.canonical(c)
                return {'type': 'file', 'encoding': 'base64', 'size': len(source),
                        'content': base64.b64encode(source).decode()}
            if route.endswith('/git/ref/tags/'+marker):
                return {'object': {'sha': 'a'*40}}
            if route.endswith('/git/ref/tags/'+marker+'-ack'):
                return {'object': {'sha': 'd'*40}}
            assert route.endswith('/git/tags/'+'d'*40)
            return {'object': {'sha': ('f' if bad_ack else 'a')*40}, 'tag': marker+'-ack'}

    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', Git)
    monkeypatch.setattr(r, 'encrypt', lambda _, raw: reports.append(raw) or b'ZZ-cipher')
    monkeypatch.setattr(r, 'ReadOnlyVendor', lambda *a: object())
    monkeypatch.setattr(r, 'ReadOnlyIO', lambda *a: model)
    ok = r.run(e)
    return ok, json.loads(reports[-1]), model, requests


@pytest.mark.parametrize('bad_ack', [False, True])
def test_runner_full_source_ref_and_read_only_replay(tmp_path, monkeypatch, bad_ack):
    ok, result, model, requests = replay(tmp_path, monkeypatch, bad_ack)
    assert ok is not bad_ack
    assert not model.posts and len(requests) == 5
    assert result['production_enabled'] is False
    if bad_ack:
        assert result['phase'] == 'STOPPED' and not model.reads
    else:
        assert result['phase'] == 'READ_ONLY_VERIFIED' and result['create_enabled'] is False


@pytest.mark.parametrize('key,value', [('RECONCILE_DEBUG', 'false'),
    ('RECONCILE_CONFIRM', 'CREATE_APPROVED_ONE_PARENT'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ-owner/ZZ-other'),
    ('GITHUB_REF', 'refs/heads/ZZ'), ('GITHUB_ACTOR', 'ZZ'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('RECONCILE_EXECUTOR_SHA', 'c' * 40),
    ('RECONCILE_CONFIG_SHA256', '0' * 64)])
def test_runner_environment_guards_precede_credentials(tmp_path, monkeypatch, key, value):
    from tests.test_protected_parent_addition import env
    c = plan()
    raw = r.canonical(dict(config(c), created_id=NEW, union_id=PARENTS))
    e = {k.replace('PARENT_', 'RECONCILE_'): v for k, v in env(c, tmp_path).items()}
    e.update(RECONCILE_CONFIG_JSON=raw.decode(), RECONCILE_CONFIG_SHA256=r.sha(raw),
             RECONCILE_CONFIRM='READ_ONLY_EXISTING_PARENT')
    e[key] = value
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    with pytest.raises(r.Blocked):
        r.run(e)


def test_runner_expiry_precedes_credentials(tmp_path, monkeypatch):
    from tests.test_protected_parent_addition import env
    c = plan()
    raw = r.canonical(dict(config(c), created_id=NEW, union_id=PARENTS))
    e = {k.replace('PARENT_', 'RECONCILE_'): v for k, v in env(c, tmp_path).items()}
    e.update(RECONCILE_CONFIG_JSON=raw.decode(), RECONCILE_CONFIG_SHA256=r.sha(raw),
             RECONCILE_CONFIRM='READ_ONLY_EXISTING_PARENT')
    monkeypatch.setattr(r.time, 'time', lambda: 999)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    with pytest.raises(r.Blocked):
        r.run(e)


def test_created_profile_distinct_from_every_approved_profile(tmp_path, monkeypatch):
    import json
    ok, report, model, _ = replay(tmp_path, monkeypatch, config_change={'created_id': 'profile-991003'})
    assert not ok and not model.reads and not model.posts
    assert report['failure']['setup_stage'] == 'plan_config_consistency'
    assert 'profile-991003' not in json.dumps(report['failure'])


def test_every_derived_read_route_once_and_finite_budget(monkeypatch):
    c = plan()
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r.time, 'sleep', lambda _: None)
    v = r.ReadOnlyVendor(TOKEN, c, NEW, PARENTS)
    expected = {'/api/' + x + '?fields=' + r.FIELDS + '&only_ids=true'
                for x in {'profile', *c['profiles'], NEW}}
    expected |= {'/api/' + x + '/immediate-family?only_ids=true' for x in (ANCHOR, NEW)}
    expected.add('/api/' + PARENTS + '?only_ids=true')
    assert v.routes == expected
    for route in sorted(expected):
        v.admit_vendor('GET', route)
    assert v.seen == expected and v.calls == len(expected)
    for route in expected:
        with pytest.raises(r.Blocked):
            v.admit_vendor('GET', route)
    v = r.ReadOnlyVendor(TOKEN, c, NEW, PARENTS)
    v.calls = 20
    with pytest.raises(r.Blocked):
        v.admit_vendor('GET', min(expected))


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'])
def test_no_non_get_method_even_on_approved_route(monkeypatch, method):
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    v = r.ReadOnlyVendor(TOKEN, plan(), NEW, PARENTS)
    with pytest.raises(r.Blocked):
        v.admit_vendor(method, '/api/' + PARENTS + '?only_ids=true')
    assert v.calls == 0 and not v.seen


def test_expiry_after_pacing_never_sends_second_read(monkeypatch):
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    v = r.ReadOnlyVendor(TOKEN, plan(), NEW, PARENTS)
    v.admit_vendor('GET', '/api/' + PARENTS + '?only_ids=true')
    monkeypatch.setattr(r.time, 'sleep', lambda _: monkeypatch.setattr(r.time, 'time', lambda: 999))
    with pytest.raises(r.Blocked):
        v.admit_vendor('GET', '/api/' + NEW + '/immediate-family?only_ids=true')
    assert v.calls == 1


@pytest.mark.parametrize('change', ['external_unknown_profile', 'external_internal_union',
                                  'external_bad_role', 'duplicate_node', 'adopted', 'focus_edges'])
def test_graph_defensive_guards_reject_drift(change):
    c, io = fixture()
    actual = io.get_family(NEW)
    expected = {PARENTS: io.spec[PARENTS]}
    external = r.core.boundary_edges(c, PARENTS, io.spec[PARENTS])
    if change == 'external_unknown_profile':
        external['profile-991099'] = {}
    elif change == 'external_internal_union':
        external[ANCHOR][PARENTS] = 'child'
    elif change == 'external_bad_role':
        external[ANCHOR]['union-991001'] = 'unknown'
    elif change == 'duplicate_node':
        actual['nodes']['profile-991099'] = copy.deepcopy(actual['nodes'][NEW])
    elif change == 'adopted':
        actual['nodes'][ANCHOR]['adopted_children'] = []
    else:
        actual['focus']['edges'] = {}
    with pytest.raises(r.Blocked):
        r.core.graph_check(actual, NEW, expected, external_edges=external)


def test_workflow_step_name_is_truthful_and_keeps_read_only_boundary():
    from pathlib import Path
    s = Path('.github/workflows/reconcile-parent-addition.yml').read_text()
    assert 'name: Read-only existing parent reconciliation' in s
    assert 'Exact one parent addition' not in s
    assert 'permissions:\n  contents: read' in s
    assert 'READ_ONLY_EXISTING_PARENT' in s



def _perfect_env(tmp_path, c):
    from tests.test_protected_parent_addition import env
    raw = r.canonical(dict(config(c), created_id=NEW, union_id=PARENTS))
    e = {k.replace('PARENT_', 'RECONCILE_'): v for k, v in env(c, tmp_path).items()}
    e.update(RECONCILE_CONFIG_JSON=raw.decode(), RECONCILE_CONFIG_SHA256=r.sha(raw),
             RECONCILE_CONFIRM='READ_ONLY_EXISTING_PARENT')
    return e


@pytest.mark.parametrize('key,value', [('RECONCILE_DEBUG', 'false'),
    ('RECONCILE_CONFIRM', 'CREATE_APPROVED_ONE_PARENT'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ-owner/ZZ-other'),
    ('GITHUB_REF', 'refs/heads/ZZ'), ('GITHUB_ACTOR', 'ZZ'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('RECONCILE_EXECUTOR_SHA', 'c' * 40),
    ('RECONCILE_CONFIG_SHA256', '0' * 64)])
def test_each_env_guard_is_the_only_rejection(tmp_path, monkeypatch, key, value):
    """Positive control (#619): every other input is perfect and unexpired, so
    only the named guard can stop admission. The encryption preflight is armed
    as a sentinel: if the guard is deleted the run reaches it and fails here."""
    c = plan()
    e = _perfect_env(tmp_path, c)
    e[key] = value
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached; guard deleted: ' + key)
    monkeypatch.setattr(r, 'encrypt', preflight_sentinel)
    with pytest.raises(r.Blocked):
        r.run(e)


def test_expiry_guard_is_the_only_rejection(tmp_path, monkeypatch):
    """Positive control (#619): expired config with every other input perfect;
    only the expiry require can stop admission before the encryption preflight."""
    c = plan()
    e = _perfect_env(tmp_path, c)
    monkeypatch.setattr(r.time, 'time', lambda: 999)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached; expiry guard deleted')
    monkeypatch.setattr(r, 'encrypt', preflight_sentinel)
    with pytest.raises(r.Blocked):
        r.run(e)


def test_workflow_gate_is_a_single_conjunction_of_every_admission_term():
    """Sentinel (tightened in #624): the protected job gate must be a single
    && conjunction of exactly these terms. Substring presence is not enough:
    an 'A || B' rewrite or a silently dropped term must fail here."""
    import re as _re
    s = (Path(__file__).resolve().parents[1] / '.github/workflows/reconcile-parent-addition.yml').read_text()
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
        "inputs.confirm == 'READ_ONLY_EXISTING_PARENT'",
    }



@pytest.mark.parametrize('bad_sha', ['g' * 40, 'C' * 40])
def test_github_sha_hex_shape_guard_is_the_only_rejection(tmp_path, monkeypatch, bad_sha):
    """Positive control (#619, uppercase case in #624): executor SHA equality
    holds but the value is not lowercase hex, so only the GITHUB_SHA hex-shape
    clause can stop admission. 'C'*40 pins against case-insensitive relaxation."""
    c = plan()
    e = _perfect_env(tmp_path, c)
    e['GITHUB_SHA'] = bad_sha
    e['RECONCILE_EXECUTOR_SHA'] = bad_sha
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached; hex-shape guard deleted')
    monkeypatch.setattr(r, 'encrypt', preflight_sentinel)
    with pytest.raises(r.Blocked):
        r.run(e)


def test_perfect_env_reaches_encryption_preflight(tmp_path, monkeypatch):
    """Baseline (#619): with every input perfect the run must reach the
    encryption preflight, proving the positive controls' sentinel premise."""
    c = plan()
    e = _perfect_env(tmp_path, c)
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    def preflight_sentinel(*a, **k):
        raise AssertionError('encryption preflight reached')
    monkeypatch.setattr(r, 'encrypt', preflight_sentinel)
    with pytest.raises(AssertionError, match='encryption preflight reached'):
        r.run(e)


FOREIGN = f'profile-{991099}'
FOREIGN_UNION, ANCHOR_UNION = [f'union-{n}' for n in (991099, 991001)]


def _armed(monkeypatch, sentinel=False):
    """Unexpired clock, credential boundary as a tripwire, encryption stubbed
    (or armed as a sentinel) so only the guard under test can stop the run."""
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *a, **k: pytest.fail('credential boundary reached'))
    if sentinel:
        def preflight_sentinel(*a, **k):
            raise AssertionError('encryption preflight reached')
        monkeypatch.setattr(r, 'encrypt', preflight_sentinel)
    else:
        monkeypatch.setattr(r, 'encrypt', lambda *a: b'ZZ-cipher')


def test_relative_output_dir_is_rejected_before_credentials(tmp_path, monkeypatch):
    """#587: evidence goes only to an absolute, fresh directory."""
    monkeypatch.chdir(tmp_path)
    e = _perfect_env(tmp_path, plan())
    e['RECONCILE_OUTPUT_DIR'] = 'ZZ-relative-out'
    _armed(monkeypatch)
    with pytest.raises(r.Blocked):
        r.run(e)
    assert not (tmp_path / 'ZZ-relative-out').exists()


def test_existing_output_dir_is_rejected_before_credentials(tmp_path, monkeypatch):
    """#587: an existing evidence directory is never reused or overwritten."""
    e = _perfect_env(tmp_path, plan())
    Path(e['RECONCILE_OUTPUT_DIR']).mkdir()
    _armed(monkeypatch)
    with pytest.raises(r.Blocked):
        r.run(e)
    assert list(Path(e['RECONCILE_OUTPUT_DIR']).iterdir()) == []


def test_config_expiry_must_equal_approved_plan_expiry(tmp_path, monkeypatch):
    """#587: run-level expiry is pinned to the approved plan, not only to the clock."""
    ok, report, model, _ = replay(tmp_path, monkeypatch, config_change={'expires_at': 998})
    assert not ok and not model.reads and not model.posts
    assert report['failure']['setup_stage'] == 'plan_config_consistency'


def test_expiry_before_a_later_read_stops_without_that_read():
    """#587: the per-read expiry check stops reconciliation mid-sequence."""
    c, io = fixture()
    ticks = iter([200])
    result = r.reconcile(c, io, NEW, PARENTS, lambda x: None, lambda: next(ticks, 999))
    assert result['phase'] == 'STOPPED' and not io.posts
    assert [x['target'] for x in result['responses']] == ['profile']


def test_expiry_after_the_last_read_is_not_verified():
    """#587: the closing expiry check holds even when every read was in time."""
    c, io = fixture()
    reads = r.reconcile(c, io, NEW, PARENTS, lambda x: None, lambda: 200)['responses']
    c, io = fixture()
    ticks = iter([200] * len(reads))
    result = r.reconcile(c, io, NEW, PARENTS, lambda x: None, lambda: next(ticks, 999))
    assert result['phase'] == 'STOPPED' and result['stage'] == 'read_union' and not io.posts
    assert len(result['responses']) == len(reads)


def test_owner_name_mismatch_stops_after_owner_read():
    """#587: the owner identity check precedes every other read."""
    c, io = fixture()
    c['expect_name'] = 'ZZ-Nobody'
    result = r.reconcile(c, io, NEW, PARENTS, lambda x: None, lambda: 200)
    assert result['phase'] == 'STOPPED' and not io.posts
    assert [x['target'] for x in result['responses']] == ['profile']


def test_wrong_union_stops_before_reading_created_family():
    """#587: the union-identity check stops before the created profile's family read."""
    c, io = fixture()
    result = r.reconcile(c, io, NEW, FOREIGN_UNION, lambda x: None, lambda: 200)
    assert result['phase'] == 'STOPPED' and not io.posts
    families = [x['target'] for x in result['responses'] if x['kind'] == 'family']
    assert families == [ANCHOR]


@pytest.mark.parametrize('created,union', [(ANCHOR, PARENTS), ('ZZ-invalid', PARENTS),
                                           (NEW, None)])
def test_config_rejects_created_anchor_malformed_or_missing_ids(created, union):
    """#587: the created profile is distinct from the anchor, well formed, and
    both pinned ids are required."""
    c = dict(config(plan()), created_id=created, union_id=union)
    if union is None:
        c.pop('union_id')
    with pytest.raises(r.Blocked):
        r.config(c)


def test_expired_admission_records_no_route_or_call(monkeypatch):
    """#587: an expired vendor admission consumes neither the route nor budget."""
    monkeypatch.setattr(r.time, 'time', lambda: 999)
    v = r.ReadOnlyVendor(TOKEN, plan(), NEW, PARENTS)
    with pytest.raises(r.Blocked):
        v.admit_vendor('GET', '/api/' + PARENTS + '?only_ids=true')
    assert v.calls == 0 and not v.seen


def test_read_pacing_waits_the_full_fifteen_seconds(monkeypatch):
    """#587: consecutive reads are paced by the full 15 s."""
    sleeps = []
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r.time, 'monotonic', lambda: 500)
    monkeypatch.setattr(r.time, 'sleep', sleeps.append)
    v = r.ReadOnlyVendor(TOKEN, plan(), NEW, PARENTS)
    v.admit_vendor('GET', '/api/' + PARENTS + '?only_ids=true')
    v.admit_vendor('GET', '/api/' + NEW + '/immediate-family?only_ids=true')
    assert sleeps == [15] and v.calls == 2


def _graph():
    c, io = fixture()
    actual = io.get_family(NEW)
    expected = {PARENTS: io.spec[PARENTS]}
    return actual, expected, r.core.boundary_edges(c, PARENTS, io.spec[PARENTS])


def test_graph_baseline_is_accepted():
    """Baseline for the isolated graph cases below: the unmodified graph passes."""
    actual, expected, external = _graph()
    r.core.graph_check(actual, NEW, expected, external_edges=external)


@pytest.mark.parametrize('change', [
    'focus_wrong_id', 'focus_error', 'focus_not_member', 'focus_url', 'focus_adopted',
    'focus_foster', 'external_not_dict', 'external_malformed_union', 'external_role_parent',
    'node_error', 'node_foster', 'node_url', 'node_id', 'union_status', 'union_url',
    'union_id'])
def test_each_graph_guard_is_the_only_rejection(change):
    """#587: each drift breaks exactly one graph_check term; everything else stays
    consistent, so deleting that term would let the graph through."""
    import types
    actual, expected, external = _graph()
    focus = NEW
    if change == 'focus_wrong_id':
        actual['focus']['id'] = ANCHOR
    elif change == 'focus_error':
        actual['focus']['error'] = 'ZZ'
    elif change == 'focus_not_member':
        focus = actual['focus']['id'] = OWNER
    elif change == 'focus_url':
        actual['focus']['url'] = 'https://www.geni.com/api/' + FOREIGN
    elif change == 'focus_adopted':
        actual['focus']['adopted_children'] = []
    elif change == 'focus_foster':
        actual['focus']['foster_children'] = []
    elif change == 'external_not_dict':
        external = types.MappingProxyType(external)
    elif change == 'external_malformed_union':
        external[ANCHOR]['union-ZZ'] = 'partner'
        actual['nodes'][ANCHOR]['edges']['union-ZZ'] = {'rel': 'partner'}
    elif change == 'external_role_parent':
        external[ANCHOR][ANCHOR_UNION] = 'parent'
        actual['nodes'][ANCHOR]['edges'][ANCHOR_UNION] = {'rel': 'parent'}
    elif change == 'node_error':
        actual['nodes'][ANCHOR]['error'] = 'ZZ'
    elif change == 'node_foster':
        actual['nodes'][ANCHOR]['foster_children'] = []
    elif change == 'node_url':
        actual['nodes'][ANCHOR]['url'] = 'https://www.geni.com/api/' + FOREIGN
    elif change == 'node_id':
        actual['nodes'][ANCHOR]['id'] = FOREIGN
    elif change == 'union_status':
        actual['nodes'][PARENTS]['status'] = 'ex_spouse'
    elif change == 'union_url':
        actual['nodes'][PARENTS]['url'] = 'https://www.geni.com/api/' + FOREIGN_UNION
    else:
        actual['nodes'][PARENTS]['id'] = FOREIGN_UNION
    with pytest.raises(r.Blocked):
        r.core.graph_check(actual, focus, expected, external_edges=external)
