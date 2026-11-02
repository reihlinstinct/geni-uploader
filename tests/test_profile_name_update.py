"""Synthetic one-profile update and read-only gate regressions. No network."""
import copy

import pytest

import bounded_profile_name_update as core
import protected_profile_name_update as p
from geni_uploader.core.people import Blocked

OWNER, TARGET = 'profile-101', 'profile-202'


def plan():
    return {'schema': 1, 'owner': OWNER, 'target': TARGET, 'expect_name': 'ZZ Owner',
            'expires_at': 900, 'expected': {
                'first_name': 'ZZ First', 'last_name': 'ZZ Before', 'gender': 'female',
                'is_alive': True, 'public': False, 'claimed': False, 'merge_pending': False,
                'unions': ['union-303'], 'names': {
                    'en-US': {'first_name': 'ZZ First', 'last_name': 'ZZ Before'},
                    'he': {'first_name': 'ZZ Given', 'last_name': 'ZZ Birth'}}},
            'set': {'last_name': 'ZZ After', 'maiden_name': 'ZZ Before', 'names': {
                'en-US': {'last_name': 'ZZ After', 'maiden_name': 'ZZ Before'},
                'he': {'last_name': 'ZZ Married', 'maiden_name': 'ZZ Birth'}}}}


class IO:
    def __init__(self, c, anomaly=None):
        self.c, self.anomaly, self.posts = c, anomaly, []
        self.value = dict(copy.deepcopy(c['expected']), id=TARGET)
        self.edges = {TARGET: {'edges': {'union-303': {'rel': 'partner'}}}}

    def get_profile(self, target):
        if target == 'profile':
            return {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Owner'}
        value = copy.deepcopy(self.value)
        if self.anomaly == 'claimed':
            value['claimed'] = True
        if self.anomaly == 'missing_claimed':
            del value['claimed']
        if self.anomaly == 'name':
            value['first_name'] = 'ZZ Other'
        if self.posts and self.anomaly == 'privacy':
            value['public'] = True
        return value

    def get_family(self, target):
        nodes = copy.deepcopy(self.edges)
        if self.posts and self.anomaly == 'graph':
            nodes[TARGET]['edges']['union-404'] = {'rel': 'child'}
        return {'focus': {'id': target}, 'nodes': nodes}

    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        for k in ('last_name', 'maiden_name'):
            self.value[k] = body[k]
        for locale, fields in body['names'].items():
            self.value['names'][locale].update(fields)
        return {'id': TARGET if self.anomaly != 'wrong_id' else 'profile-999'}


class Store:
    def __init__(self, fail=None):
        self.fail, self.used, self.receipts = fail, set(), []

    def consume(self, marker):
        if self.fail == 'consume' or marker in self.used:
            raise Blocked()
        self.used.add(marker)

    def receipt(self, marker, stage, value):
        if self.fail == stage:
            raise Blocked()
        self.receipts.append(stage)


def run(c=None, anomaly=None, store=None, read_only=False):
    c = c or plan()
    io, store = IO(c, anomaly), store or Store()
    result = core.execute(c, io, store, lambda _: b'ZZ-encrypted', lambda: 200,
                          read_only=read_only)
    return result, io, store


def test_verified_preserves_first_names_and_edges():
    r, io, store = run()
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert store.receipts == ['before', 'ack', 'final']
    assert io.value['first_name'] == 'ZZ First' and io.value['public'] is False
    assert io.value['names']['he']['first_name'] == 'ZZ Given'


def test_read_only_never_consumes_or_sends():
    r, io, store = run(read_only=True)
    assert r['phase'] == 'READ_ONLY_NAME_VERIFIED'
    assert io.posts == [] and store.used == set() and store.receipts == []


@pytest.mark.parametrize('anomaly', ['claimed', 'missing_claimed', 'name'])
def test_preflight_rejects_without_write(anomaly):
    r, io, _ = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('anomaly', ['lost', 'privacy', 'graph', 'wrong_id'])
def test_postwrite_failure_never_retries(anomaly):
    r, io, store = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(store.used) == 1
    assert 'final' not in store.receipts
    r, again, _ = run(store=store)
    assert r['phase'] == 'STOPPED' and not again.posts


@pytest.mark.parametrize('failure', ['before', 'consume', 'ack', 'final'])
def test_receipt_failures_stop(failure):
    r, io, _ = run(store=Store(failure))
    assert r['phase'] == 'STOPPED'
    assert len(io.posts) == (0 if failure in ('before', 'consume') else 1)


def test_expiry_changes_cannot_rearm():
    c = plan()
    m = core.marker(c)
    c['expires_at'] += 200
    assert core.marker(c) == m
    r = core.execute(c, IO(c), Store(), lambda _: b'ZZ', lambda: 2000, read_only=False)
    assert r['phase'] == 'STOPPED'


@pytest.mark.parametrize('where,key,value', [
    ('set', 'email', 'zz@example.invalid'), ('set', 'public', True),
    ('set', 'last_name', ''), ('expected', 'claimed', True),
    ('expected', 'public', True), ('expected', 'merge_pending', True),
    ('expected', 'merged_into', 'profile-555'), ('expected', 'is_alive', False),
    ('expected', 'maiden_name', 'ZZ Conflicting')])
def test_closed_schema_and_preserved_identity(where, key, value):
    c = plan()
    c[where][key] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('method,route', [('POST', '/api/profile-202/add-parent'),
                                        ('POST', '/api/profile-202/update'),
                                        ('GET', '/api/profile-999?fields=id')])
def test_route_cannot_jump_preflight(method, route, monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    v = p.ScopedVendor('ZZ-token-123', plan(), read_only=False)
    with pytest.raises(Blocked):
        v.admit_vendor(method, route)


def test_finite_sequence_and_readonly_no_post(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p.time, 'sleep', lambda _: None)
    for read_only in (True, False):
        v = p.ScopedVendor('ZZ-token-123', plan(), read_only=read_only)
        sequence = list(v.sequence)
        assert len(sequence) == (3 if read_only else 6)
        for method, route in sequence:
            v.admit_vendor(method, route)
        with pytest.raises(Blocked):
            v.admit_vendor('POST', '/api/' + TARGET + '/update')
        assert v.post_count == (0 if read_only else 1)


def environment(c, tmp_path, mode='plan'):
    cfg = {'schema': 1, 'data_repo': 'ZZ-owner/ZZ-source', 'data_sha': 'a' * 40,
           'data_path': 'ZZ/ZZ-plan.json', 'owner': c['owner'], 'target': c['target'],
           'expect_name': c['expect_name'], 'expires_at': c['expires_at'],
           'recipient': 'age1' + 'a' * 58, 'plan_sha256': p.sha(p.canonical(c))}
    raw = p.canonical(cfg)
    return {'RELATIVE_DEBUG': 'true', 'RELATIVE_MODE': mode,
            'RELATIVE_CONFIRM': 'READ_ONLY_NAME' if mode == 'plan' else 'UPDATE_APPROVED_NAME',
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
            'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
            'GITHUB_SHA': 'b' * 40, 'RELATIVE_EXECUTOR_SHA': 'b' * 40,
            'RELATIVE_CONFIG_JSON': raw.decode(), 'RELATIVE_CONFIG_SHA256': p.sha(raw),
            'RELATIVE_OUTPUT_DIR': str(tmp_path / 'ZZ-output'), 'GITHUB_RUN_ID': '99001',
            'RELATIVE_TREE_PAT': 'ZZ-token-123', 'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-token-123'}


@pytest.mark.parametrize('mode', ['plan', 'update'])
def test_real_entrypoint_admits_exact_private_plan(tmp_path, monkeypatch, mode):
    c = plan()
    env = environment(c, tmp_path, mode)
    io, store, captures = IO(c), Store(), []

    class Private:
        def __init__(self, github, repo, commit, owner):
            assert (repo, commit, owner) == ('ZZ-owner/ZZ-source', 'a' * 40, OWNER)

        def load(self, path):
            assert path == 'ZZ/ZZ-plan.json'
            return p.decode(p.canonical(c))

    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p, 'Store', lambda _: store)
    monkeypatch.setattr(p, 'IO', lambda vendor, **_: io)
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p, 'encrypt', lambda _, raw: captures.append(raw) or b'age-encryption.org/v1\nZZ')
    assert p.run(env) is True
    assert len(io.posts) == (mode == 'update')
    assert captures and list((tmp_path / 'ZZ-output').glob('*.age'))


@pytest.mark.parametrize('field,value', [
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTOR', 'ZZ-other'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ-other'), ('GITHUB_REF', 'refs/heads/ZZ-other'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ/ZZ'),
    ('RELATIVE_EXECUTOR_SHA', 'c' * 40), ('RELATIVE_CONFIG_SHA256', 'c' * 64),
    ('RELATIVE_CONFIRM', 'YES'), ('RELATIVE_MODE', 'run'), ('RELATIVE_DEBUG', 'false')])
def test_entrypoint_gates_before_credentials(tmp_path, monkeypatch, field, value):
    env = environment(plan(), tmp_path)
    env[field] = value
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p, 'encrypt', lambda *_: pytest.fail('must not encrypt'))
    with pytest.raises(Blocked):
        p.run(env)


def test_private_source_hash_mismatch_cannot_reach_vendor(tmp_path, monkeypatch):
    c = plan()
    env = environment(c, tmp_path)

    class Private:
        def __init__(self, *_):
            pass

        def load(self, _):
            bad = copy.deepcopy(c)
            bad['set']['last_name'] = 'ZZ Unapproved'
            return bad

    monkeypatch.setattr(p, 'PrivateGit', Private)
    monkeypatch.setattr(p, 'ScopedVendor', lambda *_a, **_k: pytest.fail('must not reach vendor'))
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(p, 'encrypt', lambda *_: b'age-encryption.org/v1\nZZ')
    assert p.run(env) is False


def test_workflow_has_no_automatic_trigger_and_fixed_protection():
    from pathlib import Path

    import yaml
    value = yaml.safe_load((Path(__file__).parents[1] /
                           '.github/workflows/protected-profile-name-update.yml').read_text())
    assert set(value.get('on', value.get(True))) == {'workflow_dispatch'}
    job = value['jobs']['pilot']
    assert job['environment'] == 'father-create'
    assert 'github.run_attempt == 1' in job['if']
    assert 'inputs.mode' in job['if'] and 'UPDATE_APPROVED_NAME' in job['if']
    assert value['concurrency']['group'] == 'one-time-parent-pilot'
    assert value['concurrency']['cancel-in-progress'] is False


@pytest.mark.parametrize('key,value', [('email', 'zz@example.invalid'), ('public', True),
                                     ('first_name', 'ZZ Wrong'), ('last_name', 'ZZ Wrong')])
def test_io_rejects_unapproved_body(key, value, monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    v = p.ScopedVendor('ZZ-token-123', plan(), read_only=False)
    io = p.IO(v)
    body = copy.deepcopy(plan()['set'])
    body[key] = value
    with pytest.raises(Blocked):
        io.update(TARGET, body)
    assert v.calls == 0


def test_io_uses_only_pinned_update_body(monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    v = p.ScopedVendor('ZZ-token-123', plan(), read_only=False)
    calls = []
    v.request = lambda *args: calls.append(args) or {'id': TARGET}
    assert p.IO(v).update(TARGET, plan()['set']) == {'id': TARGET}
    assert calls == [('POST', '/api/' + TARGET + '/update', plan()['set'])]


def test_unapproved_locale_and_conflicting_maiden_block():
    c = plan()
    c['expected']['names']['ZZ-other'] = {'first_name': 'ZZ'}
    with pytest.raises(Blocked):
        core.plan(c)
    c = plan()
    c['expected']['names']['he']['maiden_name'] = 'ZZ Conflict'
    with pytest.raises(Blocked):
        core.plan(c)


def test_new_workflow_uses_only_own_config_secret():
    from pathlib import Path
    text = (Path(__file__).parents[1] /
            '.github/workflows/protected-profile-name-update.yml').read_text()
    assert 'secrets.PROFILE_NAME_UPDATE_JSON' in text
    assert 'secrets.RELATIVE_SIBLINGS_JSON' not in text
    assert 'PYTHONPATH=src python3 protected_profile_name_update.py' in text
