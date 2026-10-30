"""Release descriptor emitted by publish-image (issue #100, decision 6501945941).

Synthetic repositories only (the fixture of test_image_provenance). The baked
hashes are written as `sha256sum` output, standing in for the hashes the
workflow takes inside the built image. No registry, Docker, network, token or
Geni.
"""

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import image_descriptor as idesc
import image_provenance as ip
import test_image_provenance as tip

DIGEST = tip.DIGEST
NEW = "ghcr.io/reihlinstinct/geni-uploader@sha256:" + "e" * 64
commit = tip.commit
pytestmark = tip.pytestmark


@pytest.fixture
def repo(tmp_path):
    """The synthetic repository of test_image_provenance, committed once."""
    root = tmp_path / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "Dockerfile").write_text(tip.DOCKERFILE)
    (root / "entrypoint.sh").write_text("#!/bin/sh\nexec python /opt/engine.py \"$@\"\n")
    (root / "engine.py").write_text("VERSION = 'zz-1'\n")
    (root / "report.py").write_text("print('zz report')\n")
    (root / ip.WORKFLOW).write_text(tip.WORKFLOW)
    tip.git(root, "init", "-q")
    return root, commit(root, "synthetic release")


def baked(root, **override):
    """sha256sum output for every COPY destination, from the repo files."""
    copies, _ = ip.dockerfile_layout((root / "Dockerfile").read_text())
    hashes = {d: ip.sha256_bytes((root / s).read_bytes()) for d, s in copies.items()}
    hashes.update(override)
    return "".join(f"{h}  {d}\n" for d, h in sorted(hashes.items()) if h is not None)


def emit(root, rev, text, image=NEW):
    out = root / "out.json"
    return idesc.emit(root, image, rev, text, out), out


def refuses(root, rev, text, match, image=NEW):
    out = root / "out.json"
    with pytest.raises(ip.ProvenanceError, match=match):
        idesc.emit(root, image, rev, text, out)
    assert not out.exists(), "a refused descriptor must not be written"


# --- matching -----------------------------------------------------------------

def test_new_unpinned_image_gets_a_descriptor_that_the_pin_pr_can_commit(repo):
    root, rev = repo
    notes, out = emit(root, rev, baked(root))
    data = json.loads(out.read_text())
    assert data["image"] == NEW and data["engine_revision"] == rev
    assert set(data["files"]) == set(idesc.destinations(root))
    assert notes == ["IMAGE pin NOT checked (image not pinned yet)",
                     "engine_revision verified against local git objects"]
    # The strict check refuses it until the pin PR moves IMAGE to this digest.
    with pytest.raises(ip.ProvenanceError, match="IMAGE pin differs"):
        ip.check(root, out)
    wf = root / ip.WORKFLOW
    wf.write_text(wf.read_text().replace(DIGEST, NEW))
    commit(root, "pin the new image")
    assert ip.check(root, out) == ["engine_revision verified against local git objects"]


def test_binary_mode_sha256sum_lines_are_accepted(repo):
    root, rev = repo
    text = baked(root).replace("  /", " */")
    emit(root, rev, text)


def test_strict_check_still_checks_the_pin_by_default(repo):
    root, rev = repo
    _, out = emit(root, rev, baked(root))
    with pytest.raises(ip.ProvenanceError, match="IMAGE pin differs"):
        ip.check(root, out, allow_missing_revision=True)


# --- baked content ------------------------------------------------------------

def test_image_that_did_not_bake_the_reviewed_engine_is_refused(repo):
    root, rev = repo
    refuses(root, rev, baked(root, **{"/opt/engine.py": "0" * 64}), r"engine\.py differs")


def test_baked_entrypoint_mismatch_is_refused(repo):
    root, rev = repo
    entry = "/usr/local/bin/geni-uploader-entrypoint"
    refuses(root, rev, baked(root, **{entry: "1" * 64}), r"entrypoint\.sh differs")


def test_build_revision_must_hold_the_baked_files(repo):
    root, old = repo
    (root / "engine.py").write_text("VERSION = 'zz-2'\n")
    commit(root, "newer engine")
    # Hashes match the checked-out tree but the revision names the old commit.
    refuses(root, old, baked(root), r"engine\.py at engine_revision")


def test_unknown_build_revision_fails_closed(repo):
    root, _ = repo
    refuses(root, "d" * 40, baked(root), "not available locally")


# --- hash list shape ----------------------------------------------------------

def test_destination_missing_from_hash_list_is_refused(repo):
    root, rev = repo
    refuses(root, rev, baked(root, **{"/opt/report.py": None}),
            r"not hashed \['/opt/report.py'\]")


def test_extra_path_in_hash_list_is_refused(repo):
    root, rev = repo
    refuses(root, rev, baked(root) + f"{'2' * 64}  /opt/ghost.py\n",
            r"not copied \['/opt/ghost.py'\]")


def test_duplicate_path_in_hash_list_is_refused(repo):
    root, rev = repo
    text = baked(root)
    refuses(root, rev, text + text.splitlines(keepends=True)[0], "twice")


@pytest.mark.parametrize("line", [
    "sha256sum: /opt/engine.py: No such file or directory",
    f"{'3' * 63}  /opt/engine.py",
    f"{'A' * 64}  /opt/engine.py",
    f"{'4' * 64} /opt/engine.py",
    f"{'5' * 64}  opt/engine.py",
])
def test_line_that_is_not_sha256sum_output_is_refused(repo, line):
    root, rev = repo
    refuses(root, rev, baked(root) + line + "\n", "not sha256sum output")


def test_empty_hash_list_is_refused(repo):
    root, rev = repo
    refuses(root, rev, "", "not hashed")


@pytest.mark.parametrize("image", [
    "ghcr.io/reihlinstinct/geni-uploader:latest",
    "ghcr.io/someone-else/geni-uploader@sha256:" + "a" * 64,
    "",
])
def test_pushed_reference_must_be_the_uploader_digest(repo, image):
    root, rev = repo
    refuses(root, rev, baked(root), "pinned by digest", image=image)


# --- CLI ----------------------------------------------------------------------

def test_cli_lists_destinations_and_reports_value_free_failure(repo, capsys):
    root, rev = repo
    assert idesc.main(["--root", str(root), "--list-destinations"]) == 0
    assert capsys.readouterr().out.split() == idesc.destinations(root)

    hashes = root / "baked.sha256"
    hashes.write_text(baked(root))
    out = root / "release.json"
    args = ["--root", str(root), "--image", NEW, "--revision", rev,
            "--hashes", str(hashes), "--out", str(out)]
    assert idesc.main(args) == 0 and out.exists()

    out.unlink()
    (root / "engine.py").write_text("VERSION = 'zz-secret-marker'\n")
    assert idesc.main(args) == 1
    err = capsys.readouterr().err
    assert "FAIL" in err and "zz-secret-marker" not in err and not out.exists()


def test_shipped_dockerfile_destinations():
    assert idesc.destinations(ROOT) == sorted([
        "/opt/geni_upload.py", "/opt/source_details.py", "/opt/plan_report.py",
        "/opt/visual_plan.py", "/usr/local/bin/geni-uploader-entrypoint",
    ])


# --- publish-image.yml contract -------------------------------------------------

def _build_steps():
    text = (ROOT / ".github/workflows/publish-image.yml").read_text()
    data = yaml.load(text, Loader=yaml.BaseLoader)
    return data, data["jobs"]["build"]["steps"]


def test_publish_image_emits_descriptor_after_the_push():
    _, steps = _build_steps()
    names = [s.get("name") for s in steps]
    push = names.index("Push to ghcr.io")
    emit_at = names.index("Emit release descriptor from the built image")
    upload = names.index("Upload release descriptor")
    assert push < emit_at < upload

    run = steps[emit_at]["run"]
    assert "set -euo pipefail" in run
    assert "{{index .RepoDigests 0}}" in run
    assert "tools/image_descriptor.py --list-destinations" in run
    # Hashes come from inside the built image, offline.
    assert '--network none --entrypoint sha256sum "$TAG"' in run
    assert '--revision "$GITHUB_SHA"' in run
    assert "GITHUB_STEP_SUMMARY" in run

    up = steps[upload]
    assert up["uses"] == "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    assert up["with"]["if-no-files-found"] == "error"


def test_publish_image_authority_is_unchanged():
    data, steps = _build_steps()
    assert set(data["on"]) == {"workflow_dispatch"}
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["build"]["permissions"] == {"contents": "read", "packages": "write"}
    assert set(data["jobs"]) == {"build", "summary"}
    assert data["jobs"]["summary"]["permissions"] == {"contents": "read"}
    for step in steps:
        if "uses" in step:
            assert "@" in step["uses"] and len(step["uses"].split("@")[1].split()[0]) == 40
