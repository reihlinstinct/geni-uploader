"""Synthetic ZZ post-review guard probes; no network. Refs #780."""
import copy

import pytest

from geni_uploader.core.people import Blocked
from geni_uploader.runners import bounded_alias_append as core
from geni_uploader.runners import protected_alias_append as protected
from tests.test_alias_append import IO, OWNER, environment, plan, run
from tests.test_profile_name_update import Store


@pytest.mark.parametrize('owner', [{'id': 'profile-990003', 'first_name': 'ZZ', 'last_name': 'Owner'},
                                   {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Stranger'}])
def test_probe_owner_guard_blocks_before_any_post(owner):
    c = plan(); io = IO(c); orig = io.get_profile
    io.get_profile = lambda t: copy.deepcopy(owner) if t == 'profile' else orig(t)
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_probe_expiry_between_consume_and_send_blocks_post():
    c = plan(); io = IO(c); store = Store(); state = {'consumed': False}
    orig = store.consume
    def consume(m):
        orig(m); state['consumed'] = True
    store.consume = consume
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 900 if state['consumed'] else 200,
                     read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_probe_vendor_rechecks_expiry_after_spacing_sleep(monkeypatch):
    t = {'now': 200}
    monkeypatch.setattr(protected.time, 'time', lambda: t['now'])
    monkeypatch.setattr(protected.time, 'sleep', lambda _: t.update(now=900))
    v = protected.ScopedVendor('zzzzzzzz', plan(), read_only=False)
    v.calls, v.last = 3, protected.time.monotonic()
    with pytest.raises(Blocked):
        v.admit_vendor(*v.sequence[3])
    assert v.calls == 3


def test_probe_five_distinct_additions_exceed_cap():
    c = plan(); c['append'] = ['ZZ A1', 'ZZ A2', 'ZZ A3', 'ZZ A4', 'ZZ A5']
    with pytest.raises(Blocked):
        core.plan(c)


def test_probe_plan_and_config_reject_owner_as_target(tmp_path):
    c = plan(); c['target'] = OWNER
    with pytest.raises(Blocked):
        core.plan(c)
    cfg = protected.decode(environment(plan(), tmp_path)['RELATIVE_CONFIG_JSON'].encode())
    cfg['target'] = OWNER
    with pytest.raises(Blocked):
        protected.config(cfg)


@pytest.mark.parametrize('field,value', [('expires_at', 899), ('expect_name', 'ZZ Other Owner'),
                                         ('target', 'profile-990003')])
def test_probe_config_must_match_approved_plan(tmp_path, monkeypatch, field, value):
    c = plan(); env = environment(c, tmp_path)
    cfg = protected.decode(env['RELATIVE_CONFIG_JSON'].encode()); cfg[field] = value
    raw = protected.canonical(cfg)
    env['RELATIVE_CONFIG_JSON'], env['RELATIVE_CONFIG_SHA256'] = raw.decode(), protected.sha(raw)

    class Private:
        def __init__(self, *_): pass
        def load(self, _): return protected.decode(protected.canonical(c))
    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'ScopedVendor', lambda *_a, **_k: pytest.fail('vendor boundary'))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'ZZ-encrypted')
    assert not protected.run(env)


@pytest.mark.parametrize('value', ['ZZ e\u0301', 'ZZ  Double', 'ZZ\u00a0Space',
    'ZZ\u200fMark', 'ZZ\u200bZero', 'ZZ\u0085Next', 'ZZ\u2028Line', 'ZZ\u2029Para'])
def test_ambiguous_new_alias_rejected_before_effects(value):
    c = plan()
    c['append'] = [value]
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('added', [['zz old'], ['ZZ New', 'zz new']])
def test_casefold_collision_rejected_before_effects(added):
    c = plan()
    c['append'] = added
    with pytest.raises(Blocked):
        core.plan(c)


def test_existing_ambiguous_alias_not_rewritten():
    c = plan()
    c['expected']['nicknames'] = ['ZZ  Existing']
    assert core.plan(c)['expected']['nicknames'] == ['ZZ  Existing']
    assert core.payload(c)['nicknames'] == 'ZZ  Existing,ZZ Alternate,ZZ Other'


def test_nfc_nonascii_alias_exact_not_normalized():
    c = plan()
    c['append'] = ['ZZ é']
    assert core.plan(c)['append'] == ['ZZ é']
    assert run(c)[0]['phase'] == 'VERIFIED'


def test_existing_only_casefold_collision_blocks_distinct_addition():
    c = plan()
    c['expected']['nicknames'] = ['ZZ Existing', 'zz existing']
    c['append'] = ['ZZ Distinct']
    original = copy.deepcopy(c)
    with pytest.raises(Blocked):
        core.plan(c)
    assert c == original
