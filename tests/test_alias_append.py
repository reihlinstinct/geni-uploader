"""Synthetic ZZ alternate-name append, no network."""
import copy

import pytest

from geni_uploader.core.people import Blocked
from geni_uploader.runners import bounded_alias_append as core
from geni_uploader.runners import protected_alias_append as protected
from tests.test_profile_name_update import Store

OWNER, TARGET = 'profile-990001', 'profile-990002'


def plan():
    return {'schema': 1, 'owner': OWNER, 'target': TARGET, 'expect_name': 'ZZ Owner',
            'expires_at': 900, 'accept_unknown_merge_metadata': True,
            'expected': {'first_name': 'ZZ First', 'last_name': 'ZZ Before',
                         'gender': 'female', 'is_alive': False, 'public': False,
                         'claimed': False, 'merge_pending': False, 'unions': ['union-980001'],
                         'names': {'en-US': {'first_name': 'ZZ First', 'last_name': 'ZZ Before'},
                                   'he': {'first_name': 'ZZ Given', 'last_name': 'ZZ Birth'}},
                         'nicknames': ['ZZ Old'], 'display_name': 'ZZ Display'},
            'append': ['ZZ Alternate', 'ZZ Other']}


class IO:
    def __init__(self, c, anomaly=None):
        self.value = dict(copy.deepcopy(c['expected']), id=TARGET)
        self.anomaly, self.posts = anomaly, []

    def get_profile(self, target):
        if target == 'profile':
            return {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Owner'}
        value = copy.deepcopy(self.value)
        if self.anomaly == 'stale':
            value['nicknames'] = ['ZZ Surprise']
        if self.anomaly == 'missing_claimed':
            value.pop('claimed', None)
        if self.posts and self.anomaly in ('public', 'is_alive', 'claimed'):
            value[self.anomaly] = True
        if self.posts and self.anomaly == 'primary':
            value['last_name'] = 'ZZ Changed'
        if self.posts and self.anomaly == 'localized':
            value['names']['he']['first_name'] = 'ZZ Changed'
        return value

    def get_family(self, target):
        edges = {'union-980001': {'rel': 'partner'}}
        if self.posts and self.anomaly == 'graph':
            edges['union-980002'] = {'rel': 'child'}
        return {'focus': {'id': target}, 'nodes': {target: {'edges': edges}}}

    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        self.value['nicknames'] = body['nicknames'].split(',')
        if self.anomaly == 'drop_old':
            self.value['nicknames'].pop(0)
        return {'id': TARGET if self.anomaly != 'wrong_id' else 'profile-990003'}


def run(c=None, anomaly=None, store=None, read_only=False):
    c = c or plan()
    io, store = IO(c, anomaly), store or Store()
    return core.execute(c, io, store, lambda _: b'ZZ-encrypted', lambda: 200,
                        read_only=read_only), io, store


def test_verified_append_preserves_existing_and_primary():
    r, io, store = run()
    assert r['phase'] == 'VERIFIED'
    assert io.posts == [(TARGET, {'nicknames': 'ZZ Old,ZZ Alternate,ZZ Other'})]
    assert io.value['nicknames'] == ['ZZ Old', 'ZZ Alternate', 'ZZ Other']
    assert io.value['display_name'] == 'ZZ Display'
    assert store.receipts == ['before', 'ack', 'final']


def test_read_only_no_effects():
    r, io, store = run(read_only=True)
    assert r['phase'] == 'READ_ONLY_ALIAS_VERIFIED'
    assert not io.posts and not store.used and not store.receipts


def test_omitted_alias_field_is_empty_not_synthesized_in_baseline():
    c = plan()
    del c['expected']['nicknames']
    assert 'nicknames' not in core.plan(c)['expected']
    r, io, _ = run(c)
    assert r['phase'] == 'VERIFIED' and io.value['nicknames'] == c['append']


@pytest.mark.parametrize('value', [None, '', [''], ['ZZ,A'], [' ZZ A'], ['ZZ\nA'],
                                   ['ZZ A', 'ZZ A'], [False], ['ZZ A'] * 33])
def test_bad_existing_aliases_block(value):
    c = plan()
    c['expected']['nicknames'] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('value', [[], ['ZZ Old'], ['ZZ A', 'ZZ A'], ['ZZ,A'], ['ZZ A'] * 5])
def test_bad_additions_block(value):
    c = plan()
    c['append'] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('field,value', [('public', True), ('is_alive', True), ('claimed', True),
                                        ('merge_pending', True), ('merged_into', 'profile-990004')])
def test_unsafe_baseline_blocks(field, value):
    c = plan()
    c['expected'][field] = value
    with pytest.raises(Blocked):
        core.plan(c)


def test_unknown_merge_requires_explicit_risk_acceptance():
    c = plan()
    del c['expected']['merge_pending']
    assert core.plan(c)
    c['accept_unknown_merge_metadata'] = False
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('anomaly', ['stale', 'missing_claimed'])
def test_preflight_no_post(anomaly):
    r, io, _ = run(anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('anomaly', ['lost', 'wrong_id', 'drop_old', 'public', 'is_alive',
                                    'claimed', 'primary', 'localized', 'graph'])
def test_uncertain_or_changed_readback_terminal(anomaly):
    store = Store()
    r, io, _ = run(anomaly=anomaly, store=store)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(store.used) == 1
    assert 'final' not in store.receipts
    r, io, _ = run(store=store)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('failure', ['before', 'consume', 'ack', 'final'])
def test_retention_failure_blocks_completion(failure):
    r, io, _ = run(store=Store(fail=failure))
    assert r['phase'] == 'STOPPED'
    assert len(io.posts) == (failure in ('ack', 'final'))


def test_marker_cannot_rearm_by_baseline_or_expiry_change():
    c = plan()
    m = core.marker(c)
    c['append'].reverse()
    c['expires_at'] += 1
    c['expected']['display_name'] = 'ZZ Different'
    assert core.marker(c) == m


def test_payload_only_exact_nicknames(monkeypatch):
    c = plan()
    v = protected.ScopedVendor('zzzzzzzz', c, read_only=False)
    calls = []
    monkeypatch.setattr(v, 'request', lambda *args: calls.append(args) or {'id': TARGET})
    protected.IO(v).update(TARGET, core.payload(c))
    assert calls == [('POST', '/api/' + TARGET + '/update', core.payload(c))]
    with pytest.raises(Blocked):
        protected.IO(v).update(TARGET, {'last_name': 'ZZ Wrong'})


def test_closed_transport_order(monkeypatch):
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected.time, 'sleep', lambda _: None)
    v = protected.ScopedVendor('zzzzzzzz', plan(), read_only=False)
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/' + TARGET + '/update')
    assert v.calls == 0
    for method, route in v.sequence:
        v.admit_vendor(method, route)
    assert v.calls == 6 and v.post_count == 1
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/' + TARGET + '/update')


def test_projection_and_workflow_isolation():
    from pathlib import Path
    assert all(x in protected.NAME_FIELDS.split(',') for x in
               ('claimed', 'nicknames', 'display_name', 'title', 'suffix'))
    root = Path(__file__).resolve().parents[1]
    text = (root / '.github/workflows/protected-alias-append.yml').read_text()
    assert 'ALIAS_APPEND_JSON' in text and 'PROFILE_NAME_UPDATE_JSON' not in text
    assert 'refs/heads/master' in text and 'github.run_attempt == 1' in text
    assert 'APPEND_APPROVED_ALIASES' in text and 'READ_ONLY_ALIAS' in text
    assert 'workflow_dispatch:' in text and 'schedule:' not in text


def environment(c, tmp_path, mode='plan'):
    from tests.test_profile_name_update import environment as old_environment
    env = old_environment(c, tmp_path, mode)
    env['RELATIVE_CONFIRM'] = ('READ_ONLY_ALIAS' if mode == 'plan'
                               else 'APPEND_APPROVED_ALIASES')
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
            changed['append'] = ['ZZ Unapproved']
            return changed

    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'ScopedVendor', lambda *_a, **_k: pytest.fail('vendor boundary'))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'ZZ-encrypted')
    assert not protected.run(environment(c, tmp_path))
