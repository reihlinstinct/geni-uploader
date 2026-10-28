"""Behavioral test of entrypoint.sh's GENI_UPLOAD_EXPECT_SHA guard (issue #97).

Runs the real entrypoint script offline against a synthetic local git repo.
The only change to the script under test is its clone destination
(DEST=/work/repo -> a temp dir), asserted to be a single-line substitution,
so every guard line that runs is the shipped one. `python` is a stub on PATH
that records its invocation: if the stub ran, the uploader would have run.
No network, no credentials (GENI_UPLOAD_E2E=1 allows a local remote and no
token file), no Geni, no workflow dispatch.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("sh")), reason="needs git and sh"
)


def git(*args, cwd=None):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


@pytest.fixture
def harness(tmp_path):
    # Synthetic data-only repo with two commits; HEAD is the second.
    src = tmp_path / "src"
    src.mkdir()
    git("init", "-q", "-b", "main", str(src))
    for n in (1, 2):
        (src / "manifest.yaml").write_text(f"synthetic: {n}\n")
        git("add", "manifest.yaml", cwd=src)
        git("-c", "user.name=ZZ", "-c", "user.email=zz@example.invalid",
            "commit", "-q", "-m", f"synthetic {n}", cwd=src)
    head = git("rev-parse", "HEAD", cwd=src)
    parent = git("rev-parse", "HEAD~1", cwd=src)

    original = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    dest = tmp_path / "work" / "repo"
    assert original.count("DEST=/work/repo\n") == 1
    script = tmp_path / "entrypoint.sh"
    script.write_text(original.replace("DEST=/work/repo\n", f"DEST={dest}\n"))
    changed = [
        (a, b) for a, b in zip(original.splitlines(), script.read_text().splitlines())
        if a != b
    ]
    assert changed == [("DEST=/work/repo", f"DEST={dest}")]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "python-ran"
    stub = bin_dir / "python"
    stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{marker}"\n')
    stub.chmod(0o755)

    git_calls = tmp_path / 'git-calls'
    real_git = shutil.which('git')
    git_stub = bin_dir / 'git'
    git_stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{git_calls}"\nexec "{real_git}" "$@"\n')
    git_stub.chmod(0o755)

    def run(expect_sha=None, ref=None, args=("plan",)):
        if dest.exists():
            shutil.rmtree(dest)
        marker.unlink(missing_ok=True)
        git_calls.unlink(missing_ok=True)
        env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GENI_UPLOAD_E2E": "1",
            "GH_TOKEN_FILE": str(tmp_path / "no-token"),
            "GENI_UPLOAD_REPO": f"file://{src}",
        }
        if expect_sha is not None:
            env["GENI_UPLOAD_EXPECT_SHA"] = expect_sha
        if ref is not None:
            env["GENI_UPLOAD_REF"] = ref
        result = subprocess.run(["sh", str(script), *args], env=env,
                                capture_output=True, text=True, timeout=30, check=False)
        assert 'ls-remote' not in git_calls.read_text().splitlines(), 'unset pin must not silently derive remote HEAD'
        ran = marker.read_text().split() if marker.exists() else None
        return result, ran

    return run, head, parent


def test_matching_sha_runs_the_pinned_uploader(harness):
    run, head, _ = harness
    result, ran = run(expect_sha=head, args=("plan", "--manifest", "m.yaml"))
    assert result.returncode == 0, result.stderr
    assert ran == ["/opt/geni_upload.py", "plan", "--manifest", "m.yaml"]
    assert f"pulled {head[:7]}" in result.stdout


def test_matching_sha_with_ref_routes_details_mode(harness):
    run, head, _ = harness
    result, ran = run(expect_sha=head, ref="main", args=("details-plan", "--x"))
    assert result.returncode == 0, result.stderr
    assert ran == ["/opt/source_details.py", "plan", "--x"]


@pytest.mark.parametrize("kind", ["older_commit", "short_prefix", "uppercase",
                                  "not_hex", "trailing_space", "last_nibble"])
def test_any_non_exact_expected_sha_refuses_before_python(harness, kind):
    run, head, parent = harness
    expected = {
        "older_commit": parent,           # a real commit, but not the cloned HEAD
        "short_prefix": head[:12],        # abbreviations are not accepted
        "uppercase": head.upper(),        # exact lower-case hex match only
        "not_hex": "zz" * 20,
        "trailing_space": head + " ",
        "last_nibble": head[:-1] + ("0" if head[-1] != "0" else "1"),
    }[kind]
    result, ran = run(expect_sha=expected)
    assert result.returncode == 1
    assert ran is None, "the uploader must not start after a SHA mismatch"
    assert "!= GENI_UPLOAD_EXPECT_SHA" in result.stderr
    assert "running the pinned uploader" not in result.stdout


def test_unset_or_empty_expected_sha_is_no_pin(harness):
    # Current, explicit policy: the guard is opt-in. Unset or empty means
    # "no pin" and the uploader runs on the cloned HEAD. The workflow is
    # responsible for always passing a pin (see the PR for the policy question).
    run, _, _ = harness
    for value in (None, ""):
        result, ran = run(expect_sha=value)
        assert result.returncode == 0, result.stderr
        assert ran is not None


@pytest.mark.parametrize('mode', ['plan', 'run', 'details-plan', 'details-repair',
                                  'details-validate', 'details-snapshot'])
@pytest.mark.parametrize('ref', [None, 'main'])
def test_mismatch_blocks_every_mode_even_when_ref_set(harness, mode, ref):
    run, _, parent = harness
    result, ran = run(expect_sha=parent, ref=ref, args=(mode, '--manifest', 'ZZ.yaml'))
    assert result.returncode == 1
    assert ran is None
    assert '!= GENI_UPLOAD_EXPECT_SHA' in result.stderr
    assert 'running the pinned uploader' not in result.stdout
