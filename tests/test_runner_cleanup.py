"""Always-run cleanup removes only fixed temporary plaintext paths."""
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def cleanup():
    data = yaml.load((ROOT / '.github/workflows/geni-upload.yml').read_text(),
                     Loader=yaml.BaseLoader)
    return data['jobs']['upload']['steps']


def test_cleanup_is_last_and_always_after_preservation():
    steps = cleanup()
    assert steps[-1]['if'] == 'always()'
    assert steps[-1]['name'].startswith('Remove temporary plaintext')
    assert next(i for i, s in enumerate(steps) if s['name'].startswith('Encrypt')) < len(steps)-1
    assert 'cat ' not in steps[-1]['run']


def test_cleanup_removes_known_paths_only_and_is_idempotent(tmp_path):
    temp, workspace = tmp_path / 'temp', tmp_path / 'workspace'
    temp.mkdir()
    workspace.mkdir()
    for name in ('raw.log', 'gh-token', 'geni-token', 'git-cred'):
        (temp / name).write_text('ZZPrivateSecret')
    (temp / 'plan-report').mkdir()
    (workspace / 'logrepo').mkdir()
    (workspace / 'logrepo' / 'ZZmetadata').write_text('ZZPrivateURL')
    keep = temp / 'upload-log.age'
    keep.write_text('ZZciphertext')
    env = {**os.environ, 'RUNNER_TEMP': str(temp), 'GITHUB_WORKSPACE': str(workspace)}
    for _ in range(2):
        result = subprocess.run(['bash', '-c', cleanup()[-1]['run']], env=env,
                                capture_output=True, text=True, check=True)
        assert result.stdout == result.stderr == ''
    assert list(temp.iterdir()) == [keep]
    assert list(workspace.iterdir()) == []
