"""Keep the runtime-major ignore scoped to the Docker python dependency."""
from pathlib import Path

import yaml


def test_major_ignore_is_narrow():
    config = yaml.safe_load(Path('.github/dependabot.yml').read_text())
    docker = [u for u in config['updates'] if u['package-ecosystem'] == 'docker']
    assert len(docker) == 1
    assert docker[0]['ignore'] == [{'dependency-name': 'python', 'update-types': ['version-update:semver-major']}]
    assert all('ignore' not in u for u in config['updates'] if u['package-ecosystem'] != 'docker')
    assert next(line for line in Path('Dockerfile').read_text().splitlines() if line.startswith('FROM ')).startswith('FROM python:3.12-slim@sha256:')
