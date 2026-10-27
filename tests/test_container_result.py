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


def assert_order(items):
    capture = next(i for i, step in enumerate(items) if 'output fully captured' in step['name'])
    encrypt = next(i for i, step in enumerate(items) if 'Encrypt the captured log' in step['name'])
    final = next(i for i, s in enumerate(items) if s['name'].startswith('Enforce clean'))
    assert capture < encrypt < final
    assert items[final]['if'] == 'always()'
    assert '"$EXIT" > "$RUNNER_TEMP/container-exit-status"' in items[capture]['run']
    assert 'ciphertext committed: yes' in items[encrypt]['run']
    assert 'exit 1' in items[encrypt]['run']
    assert 'cat "$RAW"' not in items[final]['run']
    return final


def test_order_preserves_ciphertext_before_failure_and_status_is_not_public_data():
    assert_order(steps())


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


CLEANUP = {'name': 'Remove temporary plaintext', 'if': 'always()', 'run': 'false'}


def _without_enforcement(items):
    return [s for s in items if not s['name'].startswith('Enforce clean')]


def test_order_check_accepts_appended_cleanup_after_enforcement():
    items = steps() + [CLEANUP]
    final = assert_order(items)
    # Independent expectation: enforcement sits immediately before the
    # appended cleanup, which is now the last step.
    assert items[-1] is CLEANUP
    assert final == len(items) - 2


@pytest.mark.parametrize('mutant', ['cleanup_replaces_enforcement',
                                    'enforcement_before_encrypt',
                                    'enforcement_not_always'])
def test_order_check_rejects_replaced_or_misordered_enforcement(mutant):
    items = [dict(s) for s in steps()]
    enforce = next(s for s in items if s['name'].startswith('Enforce clean'))
    if mutant == 'cleanup_replaces_enforcement':
        items = _without_enforcement(items) + [CLEANUP]
    elif mutant == 'enforcement_before_encrypt':
        rest = _without_enforcement(items)
        encrypt = next(i for i, s in enumerate(rest) if 'Encrypt the captured log' in s['name'])
        items = rest[:encrypt] + [enforce] + rest[encrypt:] + [CLEANUP]
    else:
        enforce['if'] = 'success()'
        items = items + [CLEANUP]
    with pytest.raises((AssertionError, StopIteration)):
        assert_order(items)
