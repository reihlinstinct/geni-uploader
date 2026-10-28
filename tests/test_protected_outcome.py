"""Synthetic execution of the workflow's sanitized final outcome step."""
import os
import subprocess
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parents[1] / '.github/workflows/geni-upload.yml'


@pytest.mark.parametrize('mode', ['plan', 'details-plan', 'run', 'details-repair',
                                  'whoami', 'contrast', 'guidmap', 'pguid', 'listing-shape'])
@pytest.mark.parametrize('value,exit_code', [('0', 0), ('1', 1), ('47', 1),
                                          ('ZZprivate', 1), ('999', 1), ('', 1)])
def test_failure_reported_only_after_ciphertext_retention(tmp_path, value, exit_code, mode):
    text = WORKFLOW.read_text()
    retention = text.index('echo "ciphertext committed: yes"')
    final = text.index('- name: Report protected container outcome after ciphertext retention')
    assert retention < final
    assert 'continue-on-error' not in text[retention:]
    block = text[final:]
    script = block.split('run: |\n', 1)[1]
    (tmp_path / 'container-exit-code').write_text(value)
    result = subprocess.run(['bash', '-c', script], check=False, text=True,
                            capture_output=True, env=dict(os.environ,
                            RUNNER_TEMP=str(tmp_path), MODE=mode))
    assert result.returncode == exit_code
    assert 'ZZprivate' not in result.stdout + result.stderr
    assert 'raw.log' not in script


def test_expected_selftest_error_not_reported_as_plan_failure(tmp_path):
    text = WORKFLOW.read_text().split('- name: Report protected container outcome', 1)[1]
    script = text.split('run: |\n', 1)[1]
    result = subprocess.run(['bash', '-c', script], check=False, text=True,
                            capture_output=True, env=dict(os.environ,
                            RUNNER_TEMP=str(tmp_path), MODE='selftest'))
    assert result.returncode == 0
