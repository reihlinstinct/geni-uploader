"""The repo layout contract holds (issues #721, #731).

The checker is the executable contract; these tests pin its semantics:
required community-standards files exist, no code at the repository root,
every top-level directory listed, and the version 2 per-directory
allow/deny/required rules (docs/repo-layout-v2-design.md). Fixture
repositories are built under tmp_path with synthetic file names only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_repo_layout.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_repo_layout", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_checker(root=ROOT, env=None):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        check=False, capture_output=True, text=True, env=env,
    )


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def contract_v2(directories=None, required=None, root_allow=None, root_deny=None):
    return {
        "version": 2,
        "required": required or [],
        "root": {"allow": root_allow or ["*.md", ".repo-layout.yml"], "deny": root_deny or ["*.py"]},
        "directories": directories if directories is not None else {"docs": {"allow": ["*.md"]}},
    }


def make_repo(path, contract, files, contract_text=None, add=True):
    """A git repo with the contract and files; every path tracked unless add=False."""
    path.mkdir(parents=True, exist_ok=True)
    text = contract_text if contract_text is not None else json.dumps(contract)
    (path / ".repo-layout.yml").write_text(text, encoding="utf-8")
    for rel, body in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git(path, "init", "-q")
    if add:
        git(path, "add", "-A")
    return path


def violations(result):
    return [line for line in result.stdout.splitlines() if line.startswith("layout violation:")]


# --- the real tracked repository -------------------------------------------


def test_repo_layout_conforms():
    result = run_checker()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "layout OK\n"


def test_real_contract_is_version_2():
    contract = json.loads((ROOT / ".repo-layout.yml").read_text(encoding="utf-8"))
    assert contract["version"] == 2
    normalized = load_checker().load_contract(ROOT)
    assert set(normalized["directories"]) == set(contract["directories"])


def test_no_python_at_repository_root():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    root_py = [p for p in tracked if "/" not in p and p.endswith(".py")]
    assert root_py == [], f"python files at repository root: {root_py}"


def test_checker_flags_root_python(tmp_path):
    shutil.copy(ROOT / ".repo-layout.yml", tmp_path / ".repo-layout.yml")
    (tmp_path / "stray.py").write_text("# should never live here\n", encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    result = run_checker(tmp_path)
    assert result.returncode == 1
    assert "denied at repository root: stray.py" in result.stdout


def test_checker_flags_missing_required(tmp_path):
    contract = contract_v2(required=["DEFINITELY-MISSING.md"], root_allow=["*"], directories={})
    make_repo(tmp_path, contract, {})
    result = run_checker(tmp_path)
    assert result.returncode == 1
    assert "required file missing: DEFINITELY-MISSING.md" in result.stdout


# --- positive v2 semantics --------------------------------------------------


def test_exact_name_allow(tmp_path):
    dirs = {"pkg": {"allow": ["Makefile", "*.txt"]}}
    make_repo(tmp_path, contract_v2(dirs), {"pkg/Makefile": "", "pkg/Makefile.bak": ""})
    result = run_checker(tmp_path)
    assert violations(result) == ["layout violation: type not allowed in pkg/: pkg/Makefile.bak"]


def test_extension_glob_applies_to_nested_files(tmp_path):
    files = {"docs/a.md": "", "docs/x/y/z.md": "", "docs/x/y/z.txt": ""}
    make_repo(tmp_path, contract_v2(), files)
    result = run_checker(tmp_path)
    assert violations(result) == ["layout violation: type not allowed in docs/: docs/x/y/z.txt"]


def test_globs_are_case_sensitive(tmp_path):
    make_repo(tmp_path, contract_v2(), {"docs/a.md": "", "docs/B.MD": ""})
    result = run_checker(tmp_path)
    assert violations(result) == ["layout violation: type not allowed in docs/: docs/B.MD"]


def test_valid_tracked_required_files_pass(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "deny": [], "required": ["README.md", "sub/INDEX.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/README.md": "", "docs/sub/INDEX.md": ""})
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "layout OK\n"


def test_absent_optional_lists_mean_empty(tmp_path):
    make_repo(tmp_path, contract_v2({"docs": {"allow": ["*.md"]}}), {"docs/a.md": ""})
    assert run_checker(tmp_path).returncode == 0
    normalized = load_checker().validate_v2(contract_v2({"docs": {"allow": ["*.md"]}}))
    assert normalized["directories"]["docs"] == {"allow": ["*.md"], "deny": [], "required": []}


def test_migrate_v1_to_v2_is_explicit_and_rule_preserving():
    checker = load_checker()
    v1 = {
        "version": 1,
        "comment": "synthetic",
        "required": ["README.md", ".github/"],
        "root": {"allow": ["*.md"], "deny": ["*.py"]},
        "directories": {"docs": {"allow": ["*.md", "*.json"]}},
    }
    before = copy.deepcopy(v1)
    v2 = checker.migrate_v1_to_v2(v1)
    assert v1 == before
    assert v2 == {
        "version": 2,
        "comment": "synthetic",
        "required": ["README.md", ".github/"],
        "root": {"allow": ["*.md"], "deny": ["*.py"]},
        "directories": {"docs": {"allow": ["*.md", "*.json"], "deny": [], "required": []}},
    }
    assert checker.validate_v2(v2)["version"] == 2
    with pytest.raises(checker.LayoutError):
        checker.migrate_v1_to_v2(v2)


def test_v1_contract_is_checked_through_migration(tmp_path):
    files = {"docs/a.md": "", "docs/b.txt": "", "stray.py": ""}
    v2 = contract_v2({"docs": {"allow": ["*.md"]}})
    v1 = dict(v2, version=1)
    out_v1 = run_checker(make_repo(tmp_path / "v1", v1, files))
    out_v2 = run_checker(make_repo(tmp_path / "v2", v2, files))
    assert out_v1.returncode == out_v2.returncode == 1
    assert out_v1.stdout == out_v2.stdout


def test_v1_contract_with_v2_keys_is_rejected(tmp_path):
    contract = contract_v2({"docs": {"allow": ["*.md"], "deny": ["x.md"]}})
    contract["version"] = 1
    result = run_checker(make_repo(tmp_path, contract, {"docs/x.md": ""}))
    assert result.returncode == 2
    assert "unknown key(s) in directories.docs: deny" in result.stderr


# --- negative v2 semantics --------------------------------------------------


def test_deny_wins_over_allow(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "deny": ["DRAFT-*.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/a.md": "", "docs/n/DRAFT-zz1.md": ""})
    result = run_checker(tmp_path)
    assert result.returncode == 1
    assert violations(result) == ["layout violation: denied in docs/: docs/n/DRAFT-zz1.md"]


def test_required_file_missing(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "required": ["README.md"]}}
    result = run_checker(make_repo(tmp_path, contract_v2(dirs), {"docs/a.md": ""}))
    assert result.returncode == 1
    assert violations(result) == [
        "layout violation: required file missing in docs/: docs/README.md"]


def test_required_file_untracked(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "required": ["README.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/a.md": ""})
    (tmp_path / "docs" / "README.md").write_text("", encoding="utf-8")
    result = run_checker(tmp_path)
    assert result.returncode == 1
    assert violations(result) == [
        "layout violation: required file untracked in docs/: docs/README.md"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_required_file_tracked_link(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "required": ["README.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/a.md": ""}, add=False)
    os.symlink("a.md", tmp_path / "docs" / "README.md")
    git(tmp_path, "add", "-A")
    result = run_checker(tmp_path)
    assert result.returncode == 1
    assert violations(result) == [
        "layout violation: required file is a tracked link in docs/: docs/README.md"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_required_file_replaced_by_link_on_disk(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "required": ["README.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/a.md": "", "docs/README.md": ""})
    (tmp_path / "docs" / "README.md").unlink()
    os.symlink("a.md", tmp_path / "docs" / "README.md")
    result = run_checker(tmp_path)
    assert violations(result) == [
        "layout violation: required file is a link in docs/: docs/README.md"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_required_file_escaping_through_linked_parent(tmp_path):
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "sub" / "INDEX.md").write_text("", encoding="utf-8")
    repo = tmp_path / "repo"
    dirs = {"docs": {"allow": ["*.md"], "required": ["sub/INDEX.md"]}}
    make_repo(repo, contract_v2(dirs), {"docs/sub/INDEX.md": ""})
    shutil.rmtree(repo / "docs" / "sub")
    os.symlink(outside / "sub", repo / "docs" / "sub")
    result = run_checker(repo)
    assert result.returncode == 1
    assert violations(result) == [
        "layout violation: required file escapes repository in docs/: docs/sub/INDEX.md"]


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="root reads files regardless of mode")
def test_required_file_unreadable(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "required": ["README.md"]}}
    make_repo(tmp_path, contract_v2(dirs), {"docs/README.md": ""})
    target = tmp_path / "docs" / "README.md"
    target.chmod(0)
    try:
        result = run_checker(tmp_path)
    finally:
        target.chmod(0o644)
    assert violations(result) == [
        "layout violation: required file unreadable in docs/: docs/README.md"]


@pytest.mark.parametrize("entry, message", [
    ({"allow": ["*.md"], "deny": ["README.md"], "required": ["README.md"]},
     "required file is denied"),
    ({"allow": ["*.md"], "deny": ["SKIP-*"], "required": ["n/SKIP-zz1.md"]},
     "required file is denied"),
    ({"allow": ["*.md"], "required": ["notes.txt"]}, "required file is not allowed"),
])
def test_required_policy_conflict_is_contract_error(tmp_path, entry, message):
    files = {"docs/README.md": "", "docs/n/SKIP-zz1.md": "", "docs/notes.txt": ""}
    result = run_checker(make_repo(tmp_path, contract_v2({"docs": entry}), files))
    assert result.returncode == 2
    assert message in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("bad", [
    "../README.md", "sub/../README.md", "./README.md", "/README.md", "sub//README.md",
    "sub/", "sub\\README.md", "*.md", "READ?E.md", "[R]EADME.md", "",
])
def test_required_path_syntax_rejected(tmp_path, bad):
    dirs = {"docs": {"allow": ["*.md", "*"], "required": [bad]}}
    result = run_checker(make_repo(tmp_path, contract_v2(dirs), {"docs/README.md": ""}))
    assert result.returncode == 2, result.stdout
    assert "layout error:" in result.stderr


@pytest.mark.parametrize("bad", ["../README.md", "/etc/", "a\\b.md", "a//b.md"])
def test_global_required_path_syntax_rejected(tmp_path, bad):
    result = run_checker(make_repo(tmp_path, contract_v2(required=[bad]), {}))
    assert result.returncode == 2
    assert "layout error: required:" in result.stderr


@pytest.mark.parametrize("text", [
    '{"version": 2, "version": 2, "required": [], "root": {"allow": ["*"]}, "directories": {}}',
    ('{"version": 2, "required": [], "root": {"allow": ["*"]},'
     ' "directories": {"docs": {"allow": ["*.md"], "allow": ["*"]}}}'),
    ('{"version": 2, "required": [], "root": {"allow": ["*"]},'
     ' "directories": {"docs": {"allow": ["*.md"]}, "docs": {"allow": ["*"]}}}'),
])
def test_duplicate_json_keys_rejected(tmp_path, text):
    result = run_checker(make_repo(tmp_path, None, {"docs/a.md": ""}, contract_text=text))
    assert result.returncode == 2
    assert "duplicate key" in result.stderr


@pytest.mark.parametrize("mutate, where", [
    (lambda c: c.update(extra=[]), ".repo-layout.yml: extra"),
    (lambda c: c["root"].update(required=[]), "root: required"),
    (lambda c: c["directories"]["docs"].update(allowed=["*"]), "directories.docs: allowed"),
])
def test_unknown_fields_rejected(tmp_path, mutate, where):
    contract = contract_v2()
    mutate(contract)
    result = run_checker(make_repo(tmp_path, contract, {"docs/a.md": ""}))
    assert result.returncode == 2
    assert f"unknown key(s) in {where}" in result.stderr


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("directories"),
    lambda c: c["directories"]["docs"].pop("allow"),
    lambda c: c["directories"]["docs"].update(deny="*.md"),
    lambda c: c["directories"]["docs"].update(required=[1]),
    lambda c: c["directories"].update({"a/b": {"allow": ["*"]}}),
])
def test_invalid_schema_rejected(tmp_path, mutate):
    contract = contract_v2()
    mutate(contract)
    result = run_checker(make_repo(tmp_path, contract, {"docs/a.md": ""}))
    assert result.returncode == 2
    assert "layout error:" in result.stderr


@pytest.mark.parametrize("version", [0, 3, "2", 2.0, True, None, "missing"])
def test_unsupported_version_rejected(tmp_path, version):
    contract = contract_v2()
    if version == "missing":
        contract.pop("version")
    else:
        contract["version"] = version
    result = run_checker(make_repo(tmp_path, contract, {"docs/a.md": ""}))
    assert result.returncode == 2
    assert "unsupported .repo-layout.yml version" in result.stderr


def test_missing_contract_is_error(tmp_path):
    make_repo(tmp_path, contract_v2(), {"docs/a.md": ""})
    (tmp_path / ".repo-layout.yml").unlink()
    result = run_checker(tmp_path)
    assert result.returncode == 2
    assert "missing layout contract" in result.stderr


def test_wrong_root_is_error(tmp_path):
    make_repo(tmp_path, contract_v2(), {"docs/a.md": ""})
    shutil.copy(tmp_path / ".repo-layout.yml", tmp_path / "docs" / ".repo-layout.yml")
    result = run_checker(tmp_path / "docs")
    assert result.returncode == 2
    assert "not the git top-level" in result.stderr


def test_missing_git_metadata_is_error(tmp_path):
    (tmp_path / ".repo-layout.yml").write_text(json.dumps(contract_v2()), encoding="utf-8")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path.parent))
    result = run_checker(tmp_path, env=env)
    assert result.returncode == 2
    assert "git metadata" in result.stderr
    assert "layout OK" not in result.stdout


def test_repository_location_env_is_isolated(tmp_path):
    good = make_repo(tmp_path / "good", contract_v2(), {"docs/a.md": ""})
    other = make_repo(tmp_path / "other", contract_v2(), {"docs/b.txt": ""})
    env = dict(os.environ, GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other),
               GIT_INDEX_FILE=str(other / ".git" / "index"))
    result = run_checker(good, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unicode_and_newline_paths_stay_single(tmp_path):
    files = {"docs/naïve-zz1.md": "", "docs/two\nlines.txt": "", "docs/tab\there.txt": ""}
    result = run_checker(make_repo(tmp_path, contract_v2(), files))
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines == [
        "layout violation: type not allowed in docs/: docs/tab\\there.txt",
        "layout violation: type not allowed in docs/: docs/two\\nlines.txt",
        "2 layout violation(s); see .repo-layout.yml and CONTRIBUTING.md",
    ]


def test_output_is_sorted_and_names_paths_only(tmp_path):
    dirs = {"docs": {"allow": ["*.md"], "deny": ["z*"], "required": ["A.md"]}}
    files = {"docs/zz.md": "SYNTHETIC-CONTENT-ZZ", "docs/b.txt": "SYNTHETIC-CONTENT-ZZ",
             "zz.py": "SYNTHETIC-CONTENT-ZZ", "other/x.md": "SYNTHETIC-CONTENT-ZZ"}
    result = run_checker(make_repo(tmp_path, contract_v2(dirs), files))
    found = violations(result)
    assert found == sorted(found)
    assert found == [
        "layout violation: denied at repository root: zz.py",
        "layout violation: denied in docs/: docs/zz.md",
        "layout violation: required file missing in docs/: docs/A.md",
        "layout violation: type not allowed in docs/: docs/b.txt",
        "layout violation: unlisted top-level directory: other/ (via other/x.md)",
    ]
    assert "SYNTHETIC-CONTENT-ZZ" not in result.stdout + result.stderr


def test_checker_does_not_edit_contract(tmp_path):
    v1 = dict(contract_v2(), version=1)
    repo = make_repo(tmp_path, v1, {"docs/a.md": ""})
    before = (repo / ".repo-layout.yml").read_bytes()
    assert run_checker(repo).returncode == 0
    assert (repo / ".repo-layout.yml").read_bytes() == before
