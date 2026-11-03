"""The repo layout contract holds (issue #721).

The checker is the executable contract; these tests pin its semantics:
required community-standards files exist, no code at the repository root,
every top-level directory listed, per-directory type allowlists enforced.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_repo_layout.py"


def run_checker():
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT)],
        check=False, capture_output=True, text=True,
    )


def test_repo_layout_conforms():
    result = run_checker()
    assert result.returncode == 0, result.stdout


def test_no_python_at_repository_root():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    root_py = [p for p in tracked if "/" not in p and p.endswith(".py")]
    assert root_py == [], f"python files at repository root: {root_py}"


def test_checker_flags_root_python(tmp_path):
    import shutil

    shutil.copy(ROOT / ".repo-layout.yml", tmp_path / ".repo-layout.yml")
    (tmp_path / "stray.py").write_text("# should never live here\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "denied at repository root: stray.py" in result.stdout


def test_checker_flags_missing_required(tmp_path):
    import json

    contract = json.loads((ROOT / ".repo-layout.yml").read_text(encoding="utf-8"))
    contract["required"] = ["DEFINITELY-MISSING.md"]
    contract["root"] = {"allow": ["*"], "deny": []}
    contract["directories"] = {}
    (tmp_path / ".repo-layout.yml").write_text(json.dumps(contract), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "required file missing: DEFINITELY-MISSING.md" in result.stdout
