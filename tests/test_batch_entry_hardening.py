"""Synthetic ZZ batch entry positive-control probes. Refs #780."""
import pytest

from geni_uploader.runners import parent_pair_batch_create as r
from tests import test_protected_parent_pair_batch as f
from tests.test_parent_pair_batch_create import env


class Reached(Exception):
    pass


def boundary(monkeypatch, now=200):
    monkeypatch.setattr(r.time, 'time', lambda: now)
    monkeypatch.setattr(r, 'encrypt', lambda *_a: (_ for _ in ()).throw(Reached()))
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: pytest.fail('ZZ credential construction'))


def test_probe_valid_entry_reaches_encryption_preflight(tmp_path, monkeypatch):
    e, _, _, _ = env(tmp_path); boundary(monkeypatch)
    with pytest.raises(Reached):
        r.run(e)


@pytest.mark.parametrize('field,bad', [('PAIR_DEBUG', 'false'), ('PAIR_CONFIRM', 'ZZ'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/ZZ'),
    ('GITHUB_ACTOR', 'ZZ'), ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('PAIR_EXECUTOR_SHA', 'a' * 40),
    ('PAIR_CONFIG_SHA256', '0' * 64), ('GITHUB_REPOSITORY', 'ZZ/tree'),
    ('GITHUB_SHA', 'ZZ'), ('PAIR_EXECUTOR_SHA', None)])
def test_probe_entry_gate_blocks_before_encryption(tmp_path, monkeypatch, field, bad):
    e, _, _, _ = env(tmp_path); boundary(monkeypatch)
    if field == 'GITHUB_SHA':
        e['GITHUB_SHA'] = e['PAIR_EXECUTOR_SHA'] = bad
    elif bad is None:
        del e[field]
    else:
        e[field] = bad
    with pytest.raises(f.p.core.Blocked):
        r.run(e)


def test_probe_expired_config_blocks_before_encryption(tmp_path, monkeypatch):
    e, cfg, _, _ = env(tmp_path); boundary(monkeypatch, now=cfg['expires_at'])
    with pytest.raises(f.p.core.Blocked):
        r.run(e)


def test_probe_existing_output_dir_blocks(tmp_path, monkeypatch):
    e, _, _, _ = env(tmp_path); (tmp_path / 'ZZ-out').mkdir()
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'encrypt', lambda *_a: b'ZZ-cipher')
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: pytest.fail('ZZ credential construction'))
    with pytest.raises(f.p.core.Blocked):
        r.run(e)


def test_probe_non_verified_phase_returns_false(tmp_path, monkeypatch):
    e, cfg, plan, audit = env(tmp_path)
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: object())
    monkeypatch.setattr(r, 'PrivateGit', lambda *_a: f.Private(cfg, plan, audit))
    monkeypatch.setattr(r, 'ScopedVendor', lambda *_a: object())
    monkeypatch.setattr(r, 'IO', lambda v, **_k: v)
    monkeypatch.setattr(r, 'Store', lambda _p: object())
    monkeypatch.setattr(r, 'encrypt', lambda *_a: b'ZZ-cipher')
    monkeypatch.setattr(r.core, 'execute', lambda *_a: {'phase': 'STOPPED'})
    assert r.run(e) is False


@pytest.mark.parametrize('phase,code', [('STOPPED', 1), ('VERIFIED', 0)])
def test_phase_maps_to_exit_code(tmp_path, monkeypatch, phase, code):
    e, cfg, plan, audit = env(tmp_path)
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: object())
    monkeypatch.setattr(r, 'PrivateGit', lambda *_a: f.Private(cfg, plan, audit))
    monkeypatch.setattr(r, 'ScopedVendor', lambda *_a: object())
    monkeypatch.setattr(r, 'IO', lambda v, **_k: v)
    monkeypatch.setattr(r, 'Store', lambda _p: object())
    monkeypatch.setattr(r, 'encrypt', lambda *_a: b'ZZ-cipher')
    monkeypatch.setattr(r.core, 'execute', lambda *_a: {'phase': phase})
    monkeypatch.setattr(r.os, 'environ', e)
    assert r.main() == code


def test_evidence_exclusive_and_fsynced(tmp_path, monkeypatch):
    e, cfg, plan, audit = env(tmp_path)
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: object())
    monkeypatch.setattr(r, 'PrivateGit', lambda *_a: f.Private(cfg, plan, audit))
    monkeypatch.setattr(r, 'ScopedVendor', lambda *_a: object())
    monkeypatch.setattr(r, 'IO', lambda v, **_k: v)
    monkeypatch.setattr(r, 'Store', lambda _p: object())
    monkeypatch.setattr(r, 'encrypt', lambda *_a: b'ZZ-cipher')
    opened, synced = [], []
    original_open, original_sync = r.os.open, r.os.fsync
    def opened_file(path, flags, mode):
        opened.append((flags, mode))
        return original_open(path, flags, mode)
    def sync(fd):
        synced.append(fd)
        original_sync(fd)
    def execute(_plan, _io, _store, save, _clock):
        save({'phase': 'STOPPED'})
        return {'phase': 'STOPPED'}
    monkeypatch.setattr(r.os, 'open', opened_file)
    monkeypatch.setattr(r.os, 'fsync', sync)
    monkeypatch.setattr(r.core, 'execute', execute)
    assert r.run(e) is False
    assert opened == [(r.os.O_WRONLY | r.os.O_CREAT | r.os.O_EXCL, 0o600)]
    assert len(synced) == 1
