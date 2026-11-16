"""Synthetic execution of the workflow's sanitized final outcome step."""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).parents[1] / '.github/workflows/geni-upload.yml'


@pytest.mark.parametrize('mode', ['plan', 'details-plan', 'run', 'details-repair',
                                  'whoami', 'contrast', 'guidmap', 'pguid', 'listing-shape'])
@pytest.mark.parametrize('value,exit_code', [('0', 0), ('1', 1), ('47', 1),
                                          ('ZZprivate', 1), ('999', 1), ('', 1)])
def test_failure_reported_only_after_ciphertext_retention(tmp_path, value, exit_code, mode):
    text = WORKFLOW.read_text()
    retention = text.index('echo "ciphertext committed: yes"')
    final = text.index('- name: Enforce clean container result after preserving protected output')
    assert retention < final
    assert 'continue-on-error' not in text[retention:]
    steps = yaml.safe_load(text)['jobs']['upload']['steps']
    step = next(s for s in steps if s['name'].startswith('Enforce clean'))
    assert step['if'] == 'always()'
    script = step['run']
    (tmp_path / 'container-exit-code').write_text(value)
    result = subprocess.run(['bash', '-c', script], check=False, text=True,
                            capture_output=True, env=dict(os.environ,
                            RUNNER_TEMP=str(tmp_path), MODE=mode))
    assert result.returncode == exit_code
    assert 'ZZprivate' not in result.stdout + result.stderr
    assert 'raw.log' not in script


def test_expected_selftest_error_not_reported_as_plan_failure(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['upload']['steps']
    script = next(s for s in steps if s['name'].startswith('Enforce clean'))['run']
    # Successful selftest requires an actual bounded nonzero result, not merely
    # MODE=selftest with a missing result file after an interrupted step.
    (tmp_path / 'container-exit-code').write_text('1')
    result = subprocess.run(['bash', '-c', script], check=False, text=True,
                            capture_output=True, env=dict(os.environ,
                            RUNNER_TEMP=str(tmp_path), MODE='selftest'))
    assert result.returncode == 0
