"""Probe for #779 review: guards unpinned by tests/test_english_name_update.py. Synthetic, offline."""
import copy

import pytest

from geni_uploader.core.people import Blocked
from geni_uploader.runners import bounded_english_name_update as core
from geni_uploader.runners import protected_english_name_update as protected
from tests.test_english_name_update import IO, OWNER, TARGET, environment, plan
from tests.test_profile_name_update import Store


class OwnerIO(IO):
    def __init__(self, c, owner):
        super().__init__(c)
        self.owner = owner

    def get_profile(self, target):
        return copy.deepcopy(self.owner) if target == 'profile' else super().get_profile(target)


@pytest.mark.parametrize('owner', [
    {'id': 'profile-990004', 'first_name': 'ZZ', 'last_name': 'Owner'},   # wrong account
    {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Other'}])             # wrong expect_name
def test_probe_account_binding_before_any_write(owner):
    c, store = plan(), Store()
    io = OwnerIO(c, owner)
    r = core.execute(c, io, store, lambda _: b'x', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts and not store.used


def test_probe_expiry_between_consume_and_send():
    c, flag = plan(), []

    class LateStore(Store):
        def consume(self, marker):
            super().consume(marker)
            flag.append(1)

    io = IO(c)
    r = core.execute(c, io, LateStore(), lambda _: b'x',
                     lambda: 10**6 if flag else 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_probe_expired_plan_reads_nothing():
    c = plan()
    io = IO(c)
    r = core.execute(c, io, Store(), lambda _: b'x', lambda: 10**6, read_only=True)
    assert r['phase'] == 'STOPPED' and r['responses'] == []


@pytest.mark.parametrize('mutate', ['claimed', 'dup_union', 'self_target'])
def test_probe_plan_shape(mutate):
    c = plan()
    if mutate == 'claimed':
        c['expected']['claimed'] = True
    elif mutate == 'dup_union':
        c['expected']['unions'] = ['union-980001', 'https://www.geni.com/api/union-980001']
    else:
        c['owner'] = c['target']
    with pytest.raises(Blocked):
        core.plan(c)


def test_probe_readback_must_be_target():
    c = plan()

    class WrongReadback(IO):
        def get_profile(self, target):
            v = super().get_profile(target)
            if target != 'profile' and self.posts:
                v['id'] = 'profile-990003'
            return v

    store = Store()
    io = WrongReadback(c)
    r = core.execute(c, io, store, lambda _: b'x', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and 'final' not in store.receipts


def _vendor(monkeypatch, read_only=False, now=200):
    monkeypatch.setattr(protected.time, 'sleep', lambda _: None)
    monkeypatch.setattr(protected.time, 'time', lambda: now)
    c = plan()
    c['expires_at'] = 900
    return protected.ScopedVendor('ZZtoken123', c, read_only=read_only)


def test_probe_vendor_route_order(monkeypatch):
    v = _vendor(monkeypatch)
    for method, route in v.sequence[:3]:
        v.admit_vendor(method, route)
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/profile-990003/update')
    v = _vendor(monkeypatch)
    with pytest.raises(Blocked):
        v.admit_vendor('GET', '/api/profile-990003?fields=names&only_ids=true')


def test_probe_vendor_expiry_on_admission(monkeypatch):
    v = _vendor(monkeypatch, now=10**6)
    with pytest.raises(Blocked):
        v.admit_vendor(*v.sequence[0])
    assert v.calls == 0


def test_probe_vendor_expiry_after_pacing_sleep(monkeypatch):
    v = _vendor(monkeypatch)
    v.admit_vendor(*v.sequence[0])
    times = iter([200, 10**6])
    monkeypatch.setattr(protected.time, 'time', lambda: next(times))
    with pytest.raises(Blocked):
        v.admit_vendor(*v.sequence[1])
    assert v.calls == 1


def test_probe_io_body_pinned_before_transport(monkeypatch):
    sent = []
    monkeypatch.setattr(protected.parent.IO, 'request', lambda self, *a: sent.append(a) or {})
    io = protected.IO(_vendor(monkeypatch), debug=True)
    with pytest.raises(Blocked):
        io.update(TARGET, {'names': {'en-US': {'first_name': 'ZZ Unapproved'}}})
    assert sent == []


@pytest.mark.parametrize('mode,confirm', [('update', 'READ_ONLY_ENGLISH_NAME'),
                                          ('plan', 'UPDATE_APPROVED_ENGLISH_NAME')])
def test_probe_confirm_is_mode_exact(tmp_path, monkeypatch, mode, confirm):
    env = environment(plan(), tmp_path, mode)
    env['RELATIVE_CONFIRM'] = confirm
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: pytest.fail('must not encrypt'))
    with pytest.raises(Blocked):
        protected.run(env)


def _env_with_config(tmp_path, c, **cfg_changes):
    env = environment(c, tmp_path, 'update')
    cfg = protected.decode(env['RELATIVE_CONFIG_JSON'].encode())
    cfg.update(cfg_changes)
    raw = protected.canonical(cfg)
    env['RELATIVE_CONFIG_JSON'], env['RELATIVE_CONFIG_SHA256'] = raw.decode(), protected.sha(raw)
    return env


@pytest.mark.parametrize('changes', [{'expires_at': 899}, {'expect_name': 'ZZ Someone Else'},
                                     {'owner': 'profile-990004'}])
def test_probe_plan_config_consistency(tmp_path, monkeypatch, changes):
    c = plan()

    class Private:
        def __init__(self, *_):
            pass

        def load(self, _):
            return protected.decode(protected.canonical(c))

    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'ScopedVendor', lambda *_a, **_k: pytest.fail('vendor boundary'))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'ZZ-encrypted')
    assert not protected.run(_env_with_config(tmp_path, c, **changes))


def test_probe_config_rejects_self_target(tmp_path):
    env = _env_with_config(tmp_path, plan(), target=OWNER)
    with pytest.raises(Blocked):
        protected.config(protected.decode(env['RELATIVE_CONFIG_JSON'].encode()))


def test_probe_entry_expiry_and_fresh_output(tmp_path, monkeypatch):
    monkeypatch.setattr(protected, 'encrypt', lambda *_: pytest.fail('must not encrypt'))
    monkeypatch.setattr(protected.time, 'time', lambda: 10**6)
    with pytest.raises(Blocked):
        protected.run(environment(plan(), tmp_path))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'ZZ-encrypted')
    (tmp_path / 'ZZ-output').mkdir()
    with pytest.raises(Blocked):
        protected.run(environment(plan(), tmp_path))


def test_probe_encrypt_preflight_before_output(tmp_path, monkeypatch):
    def broken(*_):
        raise ValueError('ZZ bad recipient')

    monkeypatch.setattr(protected, 'encrypt', broken)
    monkeypatch.setattr(protected, 'PrivateGit', lambda *_: pytest.fail('source boundary'))
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    with pytest.raises(ValueError, match='ZZ bad recipient'):
        protected.run(environment(plan(), tmp_path))
    assert not (tmp_path / 'ZZ-output').exists()


@pytest.mark.parametrize('expired_call', range(1, 11))
def test_expiry_at_each_clock_boundary_stops(expired_call):
    calls = []
    def clock():
        calls.append(1)
        return 10**6 if len(calls) >= expired_call else 200
    c, store = plan(), Store()
    io = IO(c)
    r = core.execute(c, io, store, lambda _: b'ZZ-cipher', clock, read_only=False)
    assert r['phase'] == 'STOPPED' and 'final' not in store.receipts
    assert len(io.posts) == (0 if expired_call <= 6 else 1)


@pytest.mark.parametrize('mode', ['plan', 'update'])
@pytest.mark.parametrize('variant', ['lower', 'space', 'newline'])
def test_confirmation_remains_exact(tmp_path, monkeypatch, mode, variant):
    env = environment(plan(), tmp_path, mode)
    good = env['RELATIVE_CONFIRM']
    env['RELATIVE_CONFIRM'] = {'lower': good.lower(), 'space': ' ' + good,
                               'newline': good + '\n'}[variant]
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: pytest.fail('ZZ encryption boundary'))
    with pytest.raises(Blocked): protected.run(env)
