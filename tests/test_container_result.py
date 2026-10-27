"""A successful protected-log commit cannot hide a failed source container."""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]


def steps():
    return yaml.load((ROOT / '.github/workflows/geni-upload.yml').read_text(),
                     Loader=yaml.BaseLoader)['jobs']['upload']['steps']


@pytest.mark.parametrize('value,code', [('0\n', 0), ('1\n', 1), ('47\n', 1),
    ('ZZPrivatePayload\n', 1), ('0\nZZPrivatePayload', 1), ('', 1), (None, 1)])
def test_result_enforcement_is_fixed_output_and_fails_closed(tmp_path, value, code):
    if value is not None:
        (tmp_path / 'container-exit-status').write_text(value)
    shell = next(s for s in steps() if s['name'].startswith('Enforce clean'))['run']
    result = subprocess.run(['bash', '-c', shell], env={**os.environ, 'RUNNER_TEMP': str(tmp_path), 'MODE': 'details-plan'},
                            capture_output=True, text=True, check=False)
    assert result.returncode == code
    assert 'ZZPrivate' not in result.stdout + result.stderr


def test_order_preserves_ciphertext_before_failure_and_status_is_not_public_data():
    items = steps()
    capture = next(i for i, step in enumerate(items) if 'output fully captured' in step['name'])
    encrypt = next(i for i, step in enumerate(items) if 'Encrypt the captured log' in step['name'])
    final = next(i for i, s in enumerate(items) if s['name'].startswith('Enforce clean'))
    assert capture < encrypt < final
    assert items[final]['if'] == 'always()'
    assert '"$EXIT" > "$RUNNER_TEMP/container-exit-status"' in items[capture]['run']
    assert 'ciphertext committed: yes' in items[encrypt]['run']
    assert 'exit 1' in items[encrypt]['run']
    assert 'cat "$RAW"' not in items[final]['run']


@pytest.mark.parametrize('value,code', [('1\n', 0), ('47\n', 0), ('255\n', 0),
    ('0\n', 1), ('256\n', 1), ('-1\n', 1), ('01\n', 1),
    ('ZZPrivatePayload\n', 1), ('1\nZZPrivatePayload', 1), ('', 1), (None, 1)])
def test_selftest_preserves_expected_failure_without_claiming_clean_run(tmp_path, value, code):
    if value is not None:
        (tmp_path / 'container-exit-status').write_text(value)
    step = next(s for s in steps() if s['name'].startswith('Enforce clean'))
    assert step['env']['MODE'] == '${{ inputs.mode }}'
    result = subprocess.run(['bash', '-c', step['run']],
        env={**os.environ, 'RUNNER_TEMP': str(tmp_path), 'MODE': 'selftest'},
        capture_output=True, text=True, check=False)
    assert result.returncode == code
    assert 'ZZPrivate' not in result.stdout + result.stderr
    assert 'source container finished cleanly' not in result.stdout


def test_enforcement_selector_tolerates_later_cleanup_step(monkeypatch):
    original = steps()
    monkeypatch.setattr(__import__(__name__, fromlist=['steps']), 'steps',
        lambda: original + [{'name': 'Remove temporary plaintext', 'run': 'false'}])
    assert next(s for s in steps() if s['name'].startswith('Enforce clean')) == original[-1]
