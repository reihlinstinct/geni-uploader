"""Synthetic ZZ English-only updates; no network."""
import copy

import pytest

from geni_uploader.core.people import Blocked
from geni_uploader.runners import bounded_english_name_update as core
from geni_uploader.runners import protected_english_name_update as protected
from tests.test_profile_name_update import Store

OWNER, TARGET = 'profile-990001', 'profile-990002'


def plan():
    return {'schema': 1, 'owner': OWNER, 'target': TARGET, 'target_guid': '990002',
            'accept_english_default_projection': True, 'expect_name': 'ZZ Owner', 'expires_at': 900, 'accept_unknown_merge_metadata': True,
            'expected': {'guid': '990002', 'first_name': 'ZZ Before', 'gender': 'male',
                         'is_alive': False, 'public': False, 'claimed': False,
                         'unions': ['union-980001'], 'nicknames': ['ZZ Alias'],
                         'display_name': 'ZZ Display', 'title': 'ZZ Title', 'suffix': 'ZZ Suffix',
                         'names': {'en-US': {'first_name': 'ZZ Before', 'middle_name': 'ZZ Middle'},
                                   'he': {'first_name': 'ZZ Hebrew'}}},
            'set': {'names': {'en-US': {'first_name': 'ZZ After', 'middle_name': 'ZZ Middle',
                                        'last_name': 'ZZ Surname'}}}}


class IO:
    def __init__(self, c, anomaly=None):
        self.value = dict(copy.deepcopy(c['expected']), id=TARGET)
        self.anomaly, self.posts = anomaly, []

    def get_profile(self, target):
        if target == 'profile':
            return {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Owner'}
        v = copy.deepcopy(self.value)
        if self.anomaly == 'stale':
            v['first_name'] = 'ZZ Changed'
        if self.posts:
            if self.anomaly in ('public', 'is_alive', 'claimed'):
                v[self.anomaly] = True
            if self.anomaly == 'hebrew':
                v['names']['he']['last_name'] = 'ZZ Added'
            if self.anomaly == 'alias':
                v['nicknames'] = ['ZZ Changed']
            if self.anomaly == 'guid':
                v['guid'] = '990003'
            if self.anomaly == 'display':
                v['display_name'] = 'ZZ Changed'
        return v

    def get_family(self, target):
        e = {'union-980001': {'rel': 'partner'}}
        if self.posts and self.anomaly == 'graph':
            e['union-980002'] = {'rel': 'child'}
        return {'focus': {'id': target}, 'nodes': {target: {'edges': e}}}

    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        self.value['names'].update(copy.deepcopy(body['names']))
        if self.anomaly in ('projection', 'partial_projection', 'unexpected_projection'):
            self.value['first_name'] = body['names']['en-US']['first_name']
            if self.anomaly != 'partial_projection':
                self.value['last_name'] = (body['names']['en-US']['last_name']
                                           if self.anomaly == 'projection' else 'ZZ Other')
        return {'id': TARGET if self.anomaly != 'wrong_id' else 'profile-990003'}


def run(c=None, anomaly=None, store=None, read_only=False):
    c = c or plan()
    io, store = IO(c, anomaly), store or Store()
    return core.execute(c, io, store, lambda _: b'ZZ encrypted', lambda: 200,
                        read_only=read_only), io, store


def test_exact_payload_preserves_hebrew_and_other_fields():
    c = plan()
    r, io, store = run(c)
    assert r['phase'] == 'VERIFIED'
    assert io.posts == [(TARGET, c['set'])]
    assert io.value['names']['he'] == c['expected']['names']['he']
    assert 'last_name' not in io.value['names']['he']
    assert io.value['nicknames'] == ['ZZ Alias']
    assert store.receipts == ['before', 'ack', 'final']


def test_surname_only_and_existing_hebrew_surname_preserved():
    c = plan()
    c['set']['names']['en-US']['first_name'] = 'ZZ Before'
    c['expected']['names']['he']['last_name'] = 'ZZ Hebrew Surname'
    assert run(c)[0]['phase'] == 'VERIFIED'


def test_plan_no_effects():
    r, io, store = run(read_only=True)
    assert r['phase'] == 'READ_ONLY_ENGLISH_NAME_VERIFIED'
    assert not io.posts and not store.used and not store.receipts


@pytest.mark.parametrize('field,value', [('is_alive', True), ('public', True), ('claimed', True),
                                        ('merge_pending', True), ('merged_into', 'profile-990004'),
                                        ('merged_into', {}), ('guid', None), ('names', {})])
def test_unsafe_baseline(field, value):
    c = plan()
    c['expected'][field] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('field', ['claimed', 'is_alive', 'public', 'guid', 'first_name'])
def test_missing_required(field):
    c = plan()
    del c['expected'][field]
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('value', ['', ' ZZ', 'ZZ ', 'ZZ\nX', 'ZZ\x7fX', False])
def test_bad_proposed_name(value):
    c = plan()
    c['set']['names']['en-US']['last_name'] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('change', ['hebrew', 'middle', 'maiden', 'extra', 'locale', 'guid', 'unknown'])
def test_out_of_scope_plan(change):
    c = plan()
    if change == 'hebrew':
        c['set']['names']['he'] = {'first_name': 'ZZ Changed'}
    elif change == 'middle':
        c['set']['names']['en-US']['middle_name'] = 'ZZ Changed'
    elif change == 'maiden':
        c['set']['names']['en-US']['maiden_name'] = 'ZZ Inferred'
    elif change == 'extra':
        c['set']['public'] = True
    elif change == 'locale':
        c['set']['names']['de'] = {'first_name': 'ZZ Added'}
    elif change == 'guid':
        c['target_guid'] = '990003'
    else:
        c['accept_unknown_merge_metadata'] = False
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('anomaly', ['lost', 'wrong_id', 'public', 'is_alive', 'claimed',
                                    'hebrew', 'alias', 'guid', 'display', 'graph',
                                    'partial_projection', 'unexpected_projection'])
def test_unknown_or_mismatch_stops_without_final(anomaly):
    r, io, store = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(store.used) == 1
    assert 'final' not in store.receipts


def test_stale_before_send():
    r, io, store = run(anomaly='stale')
    assert r['phase'] == 'STOPPED' and not io.posts and not store.used


def test_stable_marker_blocks_rearm_and_double_send():
    c = plan()
    other = copy.deepcopy(c)
    other['expires_at'] += 100
    other['expected']['display_name'] = 'ZZ Different Baseline'
    assert core.marker(c) == core.marker(other)
    store = Store()
    assert run(c, store=store)[0]['phase'] == 'VERIFIED'
    r, io, _ = run(other, store=store)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_closed_transport_and_body(monkeypatch):
    monkeypatch.setattr(protected.time, 'sleep', lambda _: None)
    c = plan()
    c['expires_at'] = 2**39
    vendor = protected.ScopedVendor('ZZtoken123', c, read_only=False)
    assert len(vendor.sequence) == 6
    for method, route in vendor.sequence:
        vendor.admit_vendor(method, route)
    with pytest.raises(Blocked):
        vendor.admit_vendor('POST', '/api/' + TARGET + '/update')
    vendor = protected.ScopedVendor('ZZtoken123', c, read_only=True)
    with pytest.raises(Blocked):
        vendor.admit_vendor('POST', '/api/' + TARGET + '/update')
    io = protected.IO(vendor, debug=True)
    with pytest.raises(Blocked):
        io.update(TARGET, {'nicknames': 'ZZ Bad'})


@pytest.mark.parametrize('anomaly,classification', [(None, 'UNCHANGED'),
                                                   ('projection', 'ENGLISH_DERIVED')])
def test_primary_projection_reported_never_posted(anomaly, classification):
    r, io, _ = run(anomaly=anomaly)
    assert r['phase'] == 'VERIFIED'
    assert r['primary_projection']['classification'] == classification
    assert r['primary_projection']['written_keys'] == []
    assert set(io.posts[0][1]) == {'names'}
    assert set(io.posts[0][1]['names']) == {'en-US'}


def test_noop_blocked():
    c = plan()
    c['expected']['names']['en-US'] = copy.deepcopy(c['set']['names']['en-US'])
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('field', ['first_name', 'last_name', 'display_name'])
def test_primary_writes_blocked(field):
    c = plan()
    c['set'][field] = 'ZZ Not Allowed'
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('failure', ['before', 'consume', 'ack', 'final'])
def test_retention_failure_blocks_completion(failure):
    r, io, _ = run(store=Store(fail=failure))
    assert r['phase'] == 'STOPPED'
    assert len(io.posts) == (failure in ('ack', 'final'))


def test_explicit_projection_acceptance_required():
    c = plan()
    c['accept_english_default_projection'] = False
    with pytest.raises(Blocked):
        core.plan(c)


def test_projection_and_workflow_isolation():
    from pathlib import Path
    assert all(x in protected.NAME_FIELDS.split(',') for x in
               ('guid', 'names', 'claimed', 'nicknames', 'display_name', 'title', 'suffix'))
    root = Path(__file__).resolve().parents[1]
    text = (root / '.github/workflows/protected-english-name-update.yml').read_text()
    assert 'ENGLISH_NAME_UPDATE_JSON' in text and 'PROFILE_NAME_UPDATE_JSON' not in text
    assert 'refs/heads/master' in text and 'github.run_attempt == 1' in text
    assert 'UPDATE_APPROVED_ENGLISH_NAME' in text and 'READ_ONLY_ENGLISH_NAME' in text
    assert 'workflow_dispatch:' in text and 'schedule:' not in text


def environment(c, tmp_path, mode='plan'):
    from tests.test_profile_name_update import environment as old_environment
    env = old_environment(c, tmp_path, mode)
    env['RELATIVE_CONFIRM'] = ('READ_ONLY_ENGLISH_NAME' if mode == 'plan'
                               else 'UPDATE_APPROVED_ENGLISH_NAME')
    return env


@pytest.mark.parametrize('mode', ['plan', 'update'])
def test_entrypoint_exact_decode_hash_path(tmp_path, monkeypatch, mode):
    c, store, captures = plan(), Store(), []
    io = IO(c)

    class Private:
        def __init__(self, github, repo, commit, owner):
            assert (repo, commit, owner) == ('ZZ-owner/ZZ-source', 'a' * 40, OWNER)

        def load(self, path):
            assert path == 'ZZ/ZZ-plan.json'
            return protected.decode(protected.canonical(c))

    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'Store', lambda _: store)
    monkeypatch.setattr(protected, 'IO', lambda vendor, **_: io)
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda _, raw: captures.append(raw) or b'ZZ-encrypted')
    assert protected.run(environment(c, tmp_path, mode))
    assert len(io.posts) == (mode == 'update')
    assert captures and list((tmp_path / 'ZZ-output').glob('*.age'))


@pytest.mark.parametrize('field,value', [
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTOR', 'ZZ-other'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ-other'), ('GITHUB_REF', 'refs/heads/ZZ-other'),
    ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ/ZZ'),
    ('RELATIVE_EXECUTOR_SHA', 'c' * 40), ('RELATIVE_CONFIG_SHA256', 'c' * 64),
    ('RELATIVE_CONFIRM', 'YES'), ('RELATIVE_MODE', 'run'), ('RELATIVE_DEBUG', 'false')])
def test_entrypoint_gate_before_credentials(tmp_path, monkeypatch, field, value):
    env = environment(plan(), tmp_path)
    env[field] = value
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: pytest.fail('must not encrypt'))
    with pytest.raises(Blocked):
        protected.run(env)


def test_source_tamper_cannot_reach_vendor(tmp_path, monkeypatch):
    c = plan()

    class Private:
        def __init__(self, *_):
            pass

        def load(self, _):
            changed = copy.deepcopy(c)
            changed['set']['names']['en-US']['first_name'] = 'ZZ Unapproved'
            return changed

    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'ScopedVendor', lambda *_a, **_k: pytest.fail('vendor boundary'))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'ZZ-encrypted')
    assert not protected.run(environment(c, tmp_path))
