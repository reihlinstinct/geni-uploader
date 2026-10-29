"""Migration regression guards, preserving compatibility without duplicate logic."""
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_and_canonical_module_identity(monkeypatch):
    import people_core
    from geni_uploader.core import people
    assert people_core is people
    assert people_core.Blocked is people.Blocked
    assert people_core.Journal is people.Journal
    marker = object()
    monkeypatch.setattr(people_core, "digest", marker)
    assert people.digest is marker
    assert Path(people.__file__).resolve() == ROOT / "src/geni_uploader/core/people.py"


def test_fresh_import_order_identity():
    for imports in ["import people_core; from geni_uploader.core import people",
                    "from geni_uploader.core import people; import people_core"]:
        subprocess.run([sys.executable, "-c", imports + "; assert people_core is people"],
                       cwd=ROOT, check=True, capture_output=True, text=True)


def test_move_is_byte_identical_to_reviewed_pre_move_source():
    # Reviewed pre-move bytes, independent of shallow-checkout git history.
    assert hashlib.sha256((ROOT / "src/geni_uploader/core/people.py").read_bytes()).hexdigest() == (
        "fb5878fe39ca2f245ed9e520c17c7fafd86fa6c8fb2393fd6fe4ca4b28ebf651"
    )


def test_runtime_callers_use_canonical_import_not_legacy_facade():
    for path in ROOT.glob("*.py"):
        if path.name == "people_core.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "people_core", path.name
            if isinstance(node, ast.Import):
                assert all(alias.name != "people_core" for alias in node.names), path.name
    # This first offline core move does not change image/runtime entrypoints.
    docker = (ROOT / "Dockerfile").read_text()
    assert "people_core" not in docker and "geni_uploader" not in docker
    assert "COPY geni_upload.py /opt/geni_upload.py" in docker
    assert "COPY source_details.py /opt/source_details.py" in docker


def test_existing_offline_cli_from_outside_checkout(tmp_path):
    for name in ["parent_plan.py", "parent_output.py", "parent_probe.py"]:
        result = subprocess.run([sys.executable, str(ROOT / name), "--help"],
                                check=False, cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()


def test_offline_node_parity_workflow_installs_project_before_subprocesses():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/oauth-bootstrap-test.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["offline"]["steps"]
    setup = next(i for i, step in enumerate(steps)
                 if step.get("uses", "").startswith("actions/setup-python@"))
    install = next(i for i, step in enumerate(steps)
                   if step.get("run") == "python -m pip install -r requirements-dev.txt")
    runtime = next(i for i, step in enumerate(steps)
                   if step.get("run") == "node --test runtime.test.mjs")
    assert steps[setup]["with"]["python-version"] == "3.12"
    assert setup < install < runtime
    assert "-e ." in (ROOT / "requirements-dev.txt").read_text().splitlines()
