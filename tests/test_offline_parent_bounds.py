import hashlib
import http.client
import json
import os
import socket
import subprocess
import urllib.request

import pytest

import parent_envelope
import parent_plan
from people_core import Blocked, digest
from tests.test_parent_envelope import fixture


@pytest.mark.parametrize('bad', [object(), {1: 'ZZprivate'}, {'ZZ': object()}])
def test_unsupported_hash_is_fixed_blocked(bad):
    with pytest.raises(Blocked) as error: digest(bad)
    assert 'ZZ' not in str(error.value)


def test_depth_and_cycle_blocked_before_serializer():
    value = {}
    value['cycle'] = value
    with pytest.raises(Blocked): digest(value)
    value = []
    for _ in range(34): value = [value]
    with pytest.raises(Blocked): digest(value)


def test_valid_hash_bytes_unchanged():
    value = {'ZZ': ['שם', True, False, None, 2, 1.5]}
    expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False).encode()).hexdigest()
    assert digest(value) == expected


@pytest.fixture
def offline_guard(monkeypatch):
    def deny(*a, **k): pytest.fail('offline operation attempted process or network')
    for target, name in [(socket, 'socket'), (subprocess, 'run'), (subprocess, 'Popen'),
                         (urllib.request, 'urlopen'), (urllib.request.OpenerDirector, 'open'),
                         (http.client.HTTPConnection, 'request')]:
        monkeypatch.setattr(target, name, deny)
    for name in dir(os):
        if name in ('system', 'popen', 'startfile') or name.startswith(
                ('exec', 'spawn', 'fork', 'posix_spawn')):
            monkeypatch.setattr(os, name, deny)


def test_proposal_render_envelope_never_network_or_subprocess(offline_guard):
    plan, value = fixture()  # also constructs and validates a proposal
    assert '<html' in parent_plan.render(plan)
    envelope = parent_envelope.draft(plan, value)
    assert parent_envelope.review(envelope, plan, value, 1100)['creation_enabled'] is False


def test_cli_nested_json_fixed_failure(tmp_path, capsys):
    manifest, pins = tmp_path/'manifest', tmp_path/'pins'
    manifest.write_text('[' * 1500 + '0' + ']' * 1500)
    pins.write_text('{}')
    for path in (manifest, pins): path.chmod(0o600)
    assert parent_plan.main(['--manifest-file', str(manifest), '--pins-file', str(pins),
                             '--output-dir', str(tmp_path/'out')]) == 1
    assert capsys.readouterr().out == 'parent-plan blocked; review protected inputs\n'


OS_HELPERS = sorted({name for name in dir(os)
                     if name in ('system', 'popen', 'startfile') or name.startswith(
                         ('exec', 'spawn', 'fork', 'posix_spawn'))} | {'startfile'})
NETWORK_HELPERS = [(socket, 'socket'), (urllib.request, 'urlopen'),
                   (urllib.request.OpenerDirector, 'open'),
                   (http.client.HTTPConnection, 'request')]


@pytest.mark.parametrize('name', OS_HELPERS)
def test_each_process_guard_is_exercised_without_real_process(name, monkeypatch, request):
    # Every platform helper gets a harmless sentinel before installing the guard.
    monkeypatch.setattr(os, name, lambda *a, **k: 'ZZ-unguarded', raising=False)
    request.getfixturevalue('offline_guard')
    with pytest.raises(pytest.fail.Exception, match='offline operation attempted'):
        getattr(os, name)('ZZ-synthetic')


@pytest.mark.parametrize('target,name', NETWORK_HELPERS + [(subprocess, 'run'), (subprocess, 'Popen')])
def test_all_network_and_subprocess_guards_exercised(target, name, monkeypatch, request):
    monkeypatch.setattr(target, name, lambda *a, **k: 'ZZ-unguarded')
    request.getfixturevalue('offline_guard')
    with pytest.raises(pytest.fail.Exception, match='offline operation attempted'):
        getattr(target, name)('ZZ-synthetic')


def test_guarded_set_equals_every_discovered_helper(monkeypatch, request):
    installed = set()
    original = monkeypatch.setattr

    def record(target, name, value, *args, **kwargs):
        installed.add((target, name))
        return original(target, name, value, *args, **kwargs)

    original(monkeypatch, 'setattr', record)
    # startfile is not present on POSIX; add safely before deriving expectations.
    original(os, 'startfile', lambda *a, **k: None, raising=False)
    expected_os = {name for name in dir(os)
                   if name in ('system', 'popen', 'startfile') or name.startswith(
                       ('exec', 'spawn', 'fork', 'posix_spawn'))}
    request.getfixturevalue('offline_guard')
    assert installed == {(os, name) for name in expected_os} | set(NETWORK_HELPERS) | {
        (subprocess, 'run'), (subprocess, 'Popen')}


def test_exact_hash_depth_boundary_32_allowed_33_blocked():
    allowed = 0
    for _ in range(32):
        allowed = [allowed]
    assert digest(allowed) == hashlib.sha256(json.dumps(allowed, separators=(',', ':')).encode()).hexdigest()
    with pytest.raises(Blocked):
        digest([allowed])


def test_local_consumption_doc_whole_file_pin():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / 'docs/human-parent-local-consumption.md').read_text()
    assert hashlib.sha256(' '.join(text.split()).encode()).hexdigest() == '0c34bc584ca5fe19e89afbff210f97c55062532d00f53b252d9742de5993864d'
