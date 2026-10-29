import json
from pathlib import Path

import pytest

import secondary_probe_action as p
from people_core import Blocked
from tests.test_parent_probe import C, Client


def env(tmp_path):
    return {'PROBE_CONFIRM': 'READ_ONLY', 'PROBE_RUN_ATTEMPT': '1',
            'SECONDARY_PROBE_CONNECTION_JSON': json.dumps(C),
            'SECONDARY_PROBE_TOKEN': 'ZZsecondary', 'PROBE_RECIPIENT': 'age1'+'a'*58,
            'PROBE_MERGE_POLICY': 'STRICT', 'PROBE_OUTPUT_DIR': str(tmp_path/'out')}


def test_action_uses_only_secondary_and_writes_only_ciphertext(tmp_path, monkeypatch):
    seen = []
    def client(token):
        seen.append(token)
        return Client()
    monkeypatch.setattr(p, 'ReadOnly', client)
    monkeypatch.setattr(p, 'encrypt', lambda *a: b'age-encryption.org/v1\nZZciphertext')
    environment = env(tmp_path)
    environment['GENI_ACCESS_TOKEN'] = 'ZZprimaryMustNotUse'
    p.run(environment)
    assert seen == ['ZZsecondary']
    output = tmp_path/'out'
    assert list(output.iterdir()) == [output/'parent-evidence.age']
    assert (output/'parent-evidence.age').stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('change', ['rerun', 'confirm', 'policy', 'recipient', 'no-secondary'])
def test_bad_setup_stops_before_network(tmp_path, monkeypatch, change):
    environment = env(tmp_path)
    if change == 'rerun': environment['PROBE_RUN_ATTEMPT'] = '2'
    if change == 'confirm': environment['PROBE_CONFIRM'] = 'ZZwrong'
    if change == 'policy': environment['PROBE_MERGE_POLICY'] = 'CUSTODY'
    if change == 'recipient':
        monkeypatch.setattr(p, 'encrypt', lambda *a: (_ for _ in ()).throw(Blocked()))
    else: monkeypatch.setattr(p, 'encrypt', lambda *a: b'age-encryption.org/v1\nZZ')
    if change == 'no-secondary': environment.pop('SECONDARY_PROBE_TOKEN')
    monkeypatch.setattr(p, 'ReadOnly', lambda *a: (_ for _ in ()).throw(Blocked()))
    with pytest.raises(Blocked): p.run(environment)


def test_workflow_is_manual_secondary_only_no_primary_or_refresh():
    text = Path('.github/workflows/secondary-readonly-evidence.yml').read_text()
    assert 'workflow_dispatch:' in text and 'pull_request:' not in text
    assert 'secrets.GENI_SECONDARY_ACCESS_TOKEN' in text
    assert 'secrets.GENI_ACCESS_TOKEN' not in text
    assert 'REFRESH' not in text and 'contents: write' not in text
    assert 'environment: secondary-readonly-evidence' in text
    assert 'github.run_attempt == 1' in text and 'retention-days: 1' in text
    assert 'parent-evidence.age' in text
