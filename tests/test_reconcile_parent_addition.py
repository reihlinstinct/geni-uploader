"""Existing-parent read-only reconciliation; invented ZZ fixture only."""
import copy

import pytest

import reconcile_parent_addition as r
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
        'github.run_attempt == 1', 'reconcile_parent_addition.py']:
        assert x in s


def test_reconciliation_module_has_no_mutation_method_or_storage():
    from pathlib import Path
    s = Path('reconcile_parent_addition.py').read_text()
    assert "request('POST'" not in s and '.consume(' not in s and '.receipt(' not in s
    assert 'def add_parent' not in s


@pytest.mark.parametrize('bad_ack', [False, True])
def test_runner_full_source_ref_and_read_only_replay(tmp_path, monkeypatch, bad_ack):
    import base64
    import json

    from tests.test_protected_parent_addition import env
    c, model = fixture()
    cfg = dict(config(c), created_id=NEW, union_id=PARENTS)
    raw = r.canonical(cfg)
    e = {k.replace('PARENT_', 'RECONCILE_'): v for k, v in env(c, tmp_path).items()}
    e.update(RECONCILE_CONFIG_JSON=raw.decode(), RECONCILE_CONFIG_SHA256=r.sha(raw),
             RECONCILE_CONFIRM='READ_ONLY_EXISTING_PARENT')
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
    assert r.run(e) is not bad_ack
    result = json.loads(reports[-1])
    assert not model.posts and len(requests) == 5
    assert result['production_enabled'] is False
    if bad_ack:
        assert result['phase'] == 'STOPPED' and not model.reads
    else:
        assert result['phase'] == 'READ_ONLY_VERIFIED' and result['create_enabled'] is False
