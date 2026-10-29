"""Offline image provenance regression (issue #100).

Synthetic repositories only: a tiny Dockerfile, entrypoint, two engine files
and an upload workflow, committed to a throwaway local git repo. No registry,
Docker, network, token or Geni.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import image_provenance as ip

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")

DIGEST = "ghcr.io/reihlinstinct/geni-uploader@sha256:" + "a" * 64
OTHER = "ghcr.io/reihlinstinct/geni-uploader@sha256:" + "b" * 64
ENTRY = "/usr/local/bin/geni-uploader-entrypoint"

DOCKERFILE = f"""FROM python:3.12-slim@sha256:{'c' * 64}
RUN pip install --no-cache-dir \\
    "PyYAML==6.0.3"
COPY engine.py /opt/engine.py
COPY report.py /opt/report.py
COPY entrypoint.sh {ENTRY}
ENTRYPOINT ["{ENTRY}"]
CMD []
"""

WORKFLOW = f"""name: synthetic upload
jobs:
  run:
    env:
      IMAGE: {DIGEST}
    steps:
      - run: |
          docker run "${{ARGS[@]}}" "$IMAGE" plan
          docker run --rm --network none --entrypoint python \\
            -v "$RUNNER_TEMP/r:/run/r:ro" \\
            "$IMAGE" /opt/report.py /run/r/report.json || true
"""


def git(root, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def commit(root, message):
    git(root, "add", "-A")
    git(root, "-c", "user.name=ZZ Synthetic", "-c", "user.email=zz@example.invalid",
        "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def descriptor_for(root, rev, **overrides):
    copies, entry = ip.dockerfile_layout((root / "Dockerfile").read_text())
    data = {
        "schema": 1,
        "image": DIGEST,
        "engine_revision": rev,
        "entrypoint": entry,
        "files": {d: ip.sha256_bytes((root / s).read_bytes()) for d, s in copies.items()},
    }
    data.update(overrides)
    path = root / "release.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "Dockerfile").write_text(DOCKERFILE)
    (root / "entrypoint.sh").write_text("#!/bin/sh\nexec python /opt/engine.py \"$@\"\n")
    (root / "engine.py").write_text("VERSION = 'zz-1'\n")
    (root / "report.py").write_text("print('zz report')\n")
    (root / ip.WORKFLOW).write_text(WORKFLOW)
    git(root, "init", "-q")
    rev = commit(root, "synthetic release")
    return root, rev


def fails(root, desc, match, **kw):
    with pytest.raises(ip.ProvenanceError, match=match):
        ip.check(root, desc, **kw)


# --- matching -------------------------------------------------------------

def test_matching_descriptor_passes_and_verifies_revision(repo):
    root, rev = repo
    notes = ip.check(root, descriptor_for(root, rev))
    assert notes == ["engine_revision verified against local git objects"]


def test_cli_exit_codes_and_value_free_failure(repo, capsys):
    root, rev = repo
    desc = descriptor_for(root, rev)
    assert ip.main([str(desc), "--root", str(root)]) == 0
    (root / "engine.py").write_text("VERSION = 'zz-secret-marker'\n")
    assert ip.main([str(desc), "--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "stale" in err and "zz-secret-marker" not in err


# --- stale image / engine revision ---------------------------------------

def test_engine_fix_merged_after_image_is_stale(repo):
    root, rev = repo
    desc = descriptor_for(root, rev)
    (root / "engine.py").write_text("VERSION = 'zz-2-fixed'\n")
    commit(root, "fix merged, image not rebuilt")
    fails(root, desc, r"engine\.py differs .* stale")


def test_entrypoint_change_without_rebuild_is_stale(repo):
    root, rev = repo
    desc = descriptor_for(root, rev)
    (root / "entrypoint.sh").write_text("#!/bin/sh\nexit 0\n")
    fails(root, desc, r"entrypoint\.sh differs")


def test_revision_whose_blobs_differ_is_rejected(repo):
    root, old = repo
    (root / "engine.py").write_text("VERSION = 'zz-2'\n")
    commit(root, "newer engine")
    # Hashes describe the new files, but the revision names the old commit.
    fails(root, descriptor_for(root, old), r"engine\.py at engine_revision")


def test_unknown_revision_fails_closed_unless_explicitly_allowed(repo):
    root, _ = repo
    desc = descriptor_for(root, "d" * 40)
    fails(root, desc, "not available locally")
    notes = ip.check(root, desc, allow_missing_revision=True)
    assert notes == ["engine_revision not available locally; revision blobs NOT verified"]


@pytest.mark.parametrize("rev", ["abc123", "D" * 40, "e" * 39, 7, None])
def test_malformed_revision_is_rejected(repo, rev):
    root, _ = repo
    fails(root, descriptor_for(root, rev), "40-hex commit")


# --- digest -----------------------------------------------------------------

def test_workflow_pin_differs_from_descriptor(repo):
    root, rev = repo
    fails(root, descriptor_for(root, rev, image=OTHER), "IMAGE pin differs")


@pytest.mark.parametrize("image", [
    "ghcr.io/reihlinstinct/geni-uploader:latest",
    "ghcr.io/reihlinstinct/geni-uploader:" + "a" * 40,
    "ghcr.io/someone-else/geni-uploader@sha256:" + "a" * 64,
    "ghcr.io/reihlinstinct/geni-uploader@sha256:" + "A" * 64,
    DIGEST + "x",
])
def test_descriptor_must_pin_the_uploader_by_digest(repo, image):
    root, rev = repo
    fails(root, descriptor_for(root, rev, image=image), "pinned by digest")


def test_workflow_must_have_exactly_one_pin(repo):
    root, rev = repo
    wf = root / ip.WORKFLOW
    wf.write_text(wf.read_text().replace(f"IMAGE: {DIGEST}", f"IMAGE: {DIGEST}\n      IMAGE: {DIGEST}"))
    fails(root, descriptor_for(root, rev), "exactly one IMAGE pin")


# --- file set ---------------------------------------------------------------

def test_descriptor_listing_a_file_not_copied_fails(repo):
    root, rev = repo
    desc = descriptor_for(root, rev)
    data = json.loads(desc.read_text())
    data["files"]["/opt/ghost.py"] = "f" * 64
    desc.write_text(json.dumps(data))
    fails(root, desc, r"not copied \['/opt/ghost.py'\]")


def test_new_copy_without_descriptor_entry_fails(repo):
    root, rev = repo
    desc = descriptor_for(root, rev)
    (root / "extra.py").write_text("")
    df = root / "Dockerfile"
    df.write_text(df.read_text().replace("COPY report.py", "COPY extra.py /opt/extra.py\nCOPY report.py"))
    fails(root, desc, r"not described \['/opt/extra.py'\]")


@pytest.mark.parametrize("line", [
    "ADD engine.py /opt/engine2.py",
    "COPY --chown=1 engine.py /opt/engine2.py",
    "COPY engine.py report.py /opt/",
    "COPY engine.py /opt/engine.py",
])
def test_unsupported_or_duplicate_copy_forms_fail(repo, line):
    root, rev = repo
    desc = descriptor_for(root, rev)
    df = root / "Dockerfile"
    df.write_text(df.read_text().replace("CMD []", line + "\nCMD []"))
    fails(root, desc, "unsupported|duplicate")


@pytest.mark.parametrize("bad", [
    {"schema": 2},
    {"files": {}},
    {"files": {"/opt/engine.py": "not-a-hash"}},
    {"entrypoint": 5},
])
def test_malformed_descriptor_fields_fail(repo, bad):
    root, rev = repo
    fails(root, descriptor_for(root, rev, **bad), "schema|files|sha256|entrypoint")


def test_unknown_or_missing_descriptor_keys_fail(repo):
    root, rev = repo
    desc = descriptor_for(root, rev, extra="x")
    fails(root, desc, "keys must be exactly")
    data = json.loads(desc.read_text())
    del data["extra"], data["entrypoint"]
    desc.write_text(json.dumps(data))
    fails(root, desc, "keys must be exactly")
    desc.write_text("{not json")
    fails(root, desc, "not valid JSON")


# --- entrypoint routing ----------------------------------------------------

def test_descriptor_entrypoint_mismatch_fails(repo):
    root, rev = repo
    fails(root, descriptor_for(root, rev, entrypoint="/opt/engine.py"), "ENTRYPOINT differs")


def test_entrypoint_must_be_the_copied_entrypoint_script(repo):
    root, rev = repo
    df = root / "Dockerfile"
    df.write_text(df.read_text().replace(f'ENTRYPOINT ["{ENTRY}"]', 'ENTRYPOINT ["/opt/engine.py"]'))
    fails(root, descriptor_for(root, rev), "not the entrypoint.sh")


@pytest.mark.parametrize("entry", ['ENTRYPOINT /x', 'ENTRYPOINT ["/a", "/b"]', ""])
def test_entrypoint_forms(repo, entry):
    root, rev = repo
    desc = descriptor_for(root, rev)
    df = root / "Dockerfile"
    df.write_text(df.read_text().replace(f'ENTRYPOINT ["{ENTRY}"]', entry))
    fails(root, desc, "ENTRYPOINT")


@pytest.mark.parametrize("old,new,match", [
    ('"$IMAGE" plan', f'{OTHER} plan', 'target the pinned'),
    ('"$IMAGE" plan', '"$IMAGE" "$IMAGE" plan', 'target the pinned'),
    ('"$IMAGE" plan', f'"$IMAGE" {OTHER} plan', 'other than the pinned'),
    ('/opt/report.py', '/opt/missing.py', r'/opt/missing\.py'),
    ('--entrypoint python', '--entrypoint sh', 'entrypoint override'),
    ('docker run "${ARGS[@]}"', 'ARGS+=(--entrypoint sh)\n          docker run "${ARGS[@]}"',
     'only appear literally'),
])
def test_workflow_routing_mismatches_fail(repo, old, new, match):
    root, rev = repo
    wf = root / ip.WORKFLOW
    wf.write_text(wf.read_text().replace(old, new))
    fails(root, descriptor_for(root, rev), match)


def test_workflow_without_docker_run_fails(repo):
    root, rev = repo
    wf = root / ip.WORKFLOW
    wf.write_text(wf.read_text().replace("docker run", "echo"))
    fails(root, descriptor_for(root, rev), "no docker run")


# --- the real repository -----------------------------------------------------

def test_real_dockerfile_and_workflow_routing_are_consistent():
    """Routing half of the check on the shipped files; no descriptor exists yet."""
    copies, entry = ip.dockerfile_layout((ROOT / "Dockerfile").read_text())
    assert copies[entry] == "entrypoint.sh"
    workflow = (ROOT / ip.WORKFLOW).read_text()
    assert ip.IMAGE_RE.fullmatch(ip.workflow_image(workflow))
    runs = ip.workflow_runs(workflow)
    ip.check_runs(runs, set(copies))
    assert workflow.count("--entrypoint") == sum(t.count("--entrypoint") for t in runs)
    for src in copies.values():
        assert (ROOT / src).is_file()
