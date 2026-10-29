"""Migration regression guards, preserving compatibility without duplicate logic."""
import ast
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
    before = subprocess.check_output(
        ["git", "show", "782fadd5934c63a1eb91bd740b7a8e8c6b8c9468:people_core.py"], cwd=ROOT)
    assert (ROOT / "src/geni_uploader/core/people.py").read_bytes() == before


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
