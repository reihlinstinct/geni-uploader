"""Offline entry and workflow gates; no network or credentials."""
import base64
import copy
from pathlib import Path

import pytest

from geni_uploader.runners import parent_pair_batch_create as r
from tests import test_protected_parent_pair_batch as f


def env(tmp_path):
    cfg, plan, audit = f.source_fixture(); raw = r.canonical(cfg)
    e = {'PAIR_DEBUG': 'true', 'PAIR_CONFIRM': 'CREATE_APPROVED_PARENT_PAIR_BATCH',
         'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
         'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader', 'GITHUB_REF': 'refs/heads/master',
         'GITHUB_ACTOR': 'reihlinstinct', 'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
         'GITHUB_SHA': 'b' * 40, 'PAIR_EXECUTOR_SHA': 'b' * 40,
         'PAIR_CONFIG_JSON': raw.decode(), 'PAIR_CONFIG_SHA256': r.sha(raw),
         'PAIR_OUTPUT_DIR': str(tmp_path / 'ZZ-out'), 'GITHUB_RUN_ID': '990001',
         'PAIR_TREE_PAT': 'ZZ-private-token', 'GENI_SECONDARY_ACCESS_TOKEN': 'ZZ-vendor-token'}
    return e, cfg, plan, audit


@pytest.mark.parametrize('field,bad', [('PAIR_DEBUG', 'false'), ('PAIR_CONFIRM', 'ZZ'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/ZZ'),
    ('GITHUB_ACTOR', 'ZZ'), ('GITHUB_TRIGGERING_ACTOR', 'ZZ'), ('PAIR_EXECUTOR_SHA', 'a' * 40),
    ('PAIR_CONFIG_SHA256', '0' * 64), ('GITHUB_REPOSITORY', 'ZZ/tree')])
def test_bad_entry_no_credentials_or_network(tmp_path, monkeypatch, field, bad):
    e, _, _, _ = env(tmp_path); e[field] = bad
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k:
                        (_ for _ in ()).throw(AssertionError('ZZ credential construction')))
    monkeypatch.setattr(r, 'encrypt', lambda *_a: pytest.fail('ZZ encryption boundary'))
    with pytest.raises(f.p.core.Blocked): r.run(e)


def test_real_private_source_decoder_precedes_vendor(tmp_path, monkeypatch):
    e, cfg, plan, audit = env(tmp_path); calls = []; saved = []
    class Git:
        def request(self, method, route, body=None):
            calls.append((method, route))
            assert method == 'GET' and body is None
            if '/contents/' not in route: return {'private': True, 'full_name': cfg['data_repo']}
            raw = r.canonical(audit if cfg['overlap_path'] in route else plan)
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}
    def vendor(token, admitted):
        assert token == 'ZZ-vendor-token' and admitted == plan and len(calls) == 4
        raise RuntimeError('ZZ stop at vendor boundary')
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: Git())
    monkeypatch.setattr(r, 'encrypt', lambda _recipient, raw: saved.append(raw) or b'ZZ-cipher')
    monkeypatch.setattr(r, 'ScopedVendor', vendor)
    assert r.run(e) is False
    assert len(calls) == 4 and Path(e['PAIR_OUTPUT_DIR']).joinpath('evidence-0.age').exists()
    assert b'ZZ-vendor-token' not in saved[-1]


def test_full_entry_simulated_execution_encrypted_receipts(tmp_path, monkeypatch):
    e, cfg, plan, audit = env(tmp_path); saved = []
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: object())
    monkeypatch.setattr(r, 'PrivateGit', lambda *_a: f.Private(cfg, plan, audit))
    monkeypatch.setattr(r, 'ScopedVendor', lambda _token, approved: f.f.IO(approved))
    monkeypatch.setattr(r, 'IO', lambda v, **_k: v)
    monkeypatch.setattr(r, 'Store', lambda _private: f.f.Store())
    monkeypatch.setattr(r, 'encrypt', lambda _recipient, raw: saved.append(copy.deepcopy(raw)) or b'ZZ-cipher')
    assert r.run(e)
    final = r.decode(saved[-1]); assert final['phase'] == 'VERIFIED'
    assert final['mode'] == 'protected_parent_pair_batch' and final['production_enabled']
    assert len(list(Path(e['PAIR_OUTPUT_DIR']).glob('*.age'))) == len(saved) - 1


def test_workflow_immutable_gate_and_shared_concurrency():
    text = Path('.github/workflows/parent-pair-batch-create.yml').read_text()
    for required in ['workflow_dispatch:', 'environment: father-create',
                     'group: one-time-parent-pilot', 'cancel-in-progress: false',
                     'timeout-minutes: 300', 'github.sha == inputs.executor_sha',
                     'github.run_attempt == 1', 'inputs.debug == true',
                     'CREATE_APPROVED_PARENT_PAIR_BATCH', 'PARENT_PAIR_BATCH_JSON',
                     'if: always()', 'retention-days: 1', 'persist-credentials: false']:
        assert required in text
    assert 'pull_request:' not in text and 'schedule:' not in text


def test_source_mismatch_never_constructs_vendor(tmp_path, monkeypatch):
    e, cfg, plan, audit = env(tmp_path); plan['allow_new_unknown_merge'] = False
    monkeypatch.setattr(r.time, 'time', lambda: 200)
    monkeypatch.setattr(r, 'HTTPS', lambda *_a, **_k: object())
    monkeypatch.setattr(r, 'PrivateGit', lambda *_a: f.Private(cfg, plan, audit))
    monkeypatch.setattr(r, 'encrypt', lambda *_a: b'ZZ-cipher')
    monkeypatch.setattr(r, 'ScopedVendor', lambda *_a:
                        (_ for _ in ()).throw(AssertionError('ZZ vendor must not exist')))
    assert r.run(e) is False


def test_main_has_fixed_value_free_output(monkeypatch, capsys):
    monkeypatch.setattr(r, 'run', lambda _: (_ for _ in ()).throw(RuntimeError('ZZ-sensitive')))
    assert r.main() == 1
    text = capsys.readouterr().out
    assert text == 'batch stopped; inspect encrypted evidence; no retry or automatic repair\n'
    assert 'ZZ-sensitive' not in text
