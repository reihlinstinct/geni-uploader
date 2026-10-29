"""Best-effort cleanup after step failure preserves partial private output."""
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def preservation_step():
    data = yaml.load((ROOT / '.github/workflows/geni-upload.yml').read_text(),
                     Loader=yaml.BaseLoader)
    steps = data['jobs']['upload']['steps']
    return next(step for step in steps if step['name'].startswith('Encrypt the captured log'))


def test_cleanup_always_runs_and_encryption_failure_still_fails():
    step = preservation_step()
    assert step['if'] == 'always()'
    shell = step['run']
    assert shell.index('if [ ! -f "$RAW" ]') < shell.index('age -r')
    assert 'age -r "$RECIPIENT" -o "$CT" "$RAW" || exit 31' in shell
    assert 'exit 1' in shell


def test_missing_log_initialized_but_partial_log_not_truncated(tmp_path):
    # Select the actual initialization prefix without running encryption or git.
    prefix = preservation_step()['run'].split('\nEXIT=0')[0]
    for contents in (None, 'ZZPrivatePartialOutput'):
        raw = tmp_path / 'raw.log'
        if contents is not None:
            raw.write_text(contents)
        result = subprocess.run(['bash', '-c', prefix],
                                env={**os.environ, 'RUNNER_TEMP': str(tmp_path)},
                                capture_output=True, text=True, check=True)
        assert raw.read_text() == (contents or '')
        assert 'ZZPrivate' not in result.stdout + result.stderr
        assert raw.stat().st_mode & 0o077 == 0
