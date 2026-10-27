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
    shell = steps()[-1]['run']
    result = subprocess.run(['bash', '-c', shell], env={**os.environ, 'RUNNER_TEMP': str(tmp_path)},
                            capture_output=True, text=True, check=False)
    assert result.returncode == code
    assert 'ZZPrivate' not in result.stdout + result.stderr


def test_order_preserves_ciphertext_before_failure_and_status_is_not_public_data():
    items = steps()
    capture = next(i for i, step in enumerate(items) if 'output fully captured' in step['name'])
    encrypt = next(i for i, step in enumerate(items) if 'Encrypt the captured log' in step['name'])
    final = len(items) - 1
    assert capture < encrypt < final
    assert items[final]['if'] == 'always()'
    assert '"$EXIT" > "$RUNNER_TEMP/container-exit-status"' in items[capture]['run']
    assert 'ciphertext committed: yes' in items[encrypt]['run']
    assert 'exit 1' in items[encrypt]['run']
    assert 'cat "$RAW"' not in items[final]['run']
