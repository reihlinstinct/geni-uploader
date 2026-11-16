"""Keep the runtime-major ignore scoped to the Docker python dependency."""
from pathlib import Path

import yaml


def test_major_minor_ignore_is_narrow():
    config = yaml.safe_load(Path('.github/dependabot.yml').read_text())
    docker = [u for u in config['updates'] if u['package-ecosystem'] == 'docker']
    assert len(docker) == 1
    assert docker[0]['ignore'] == [{'dependency-name': 'python', 'update-types': ['version-update:semver-major', 'version-update:semver-minor']}]
    assert all('ignore' not in u for u in config['updates'] if u['package-ecosystem'] != 'docker')
    assert next(line for line in Path('Dockerfile').read_text().splitlines() if line.startswith('FROM ')).startswith('FROM python:3.12-slim@sha256:')


def test_policy_covers_315_without_disabling_patch_updates():
    config = yaml.safe_load(Path('.github/dependabot.yml').read_text())
    docker = next(u for u in config['updates'] if u['package-ecosystem'] == 'docker')
    ignored = docker['ignore'][0]['update-types']
    # Dependabot reads 3.12 -> 3.15 as semver-minor, not semver-major.
    assert 'version-update:semver-minor' in ignored
    assert 'version-update:semver-major' in ignored
    assert 'version-update:semver-patch' not in ignored
    assert 'versions' not in docker['ignore'][0]
