"""CI guard (issue #704, steps 1-2): every .py path referenced by the repo's
workflows, Dockerfiles, entrypoint, docs and tests must exist.

A reference that drifts (renamed source file, stale doc) fails here instead of
breaking a workflow run or the published image at runtime.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# A .py token, not a prefix of a longer dotted/hyphenated word (so GitHub
# expressions like ${{ matrix.python-version }} do not match as "matrix.py").
PY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_./-]+\.py(?![A-Za-z0-9_-])")
COPY_LINE = re.compile(r"^\s*COPY\s+(\S+)\s+\S+")
# python / python3 invocation, optional short flags, then a file or -m module
PY_RUN_FILE = re.compile(r"python3?(?:\s+-[A-Za-z])*\s+([A-Za-z0-9_./-]+\.py)")
PY_RUN_MODULE = re.compile(r"python3?\s+-m\s+([A-Za-z0-9_.]+)")
PYTHONPATH_SRC = re.compile(r"PYTHONPATH=src")
# ROOT / some.py and Path(...) / name.py literals inside tests/
TEST_PATH_LITERAL = re.compile(
    r"(?:ROOT|Path\([^)]*\))\s*/\s*['\"]([^'\"]+\.py)['\"]")

# Bare filename used as a unittest discovery pattern (-p), resolved under
# tests/security by `discover -s tests/security`, not relative to repo root.
ALLOWLIST_PATHS = {
    "test_scorecard_guard.py": "unittest -p pattern, resolved by discover -s tests/security",
}
# `python -m X` targets that are interpreter/library modules, not repo files.
ALLOWLIST_MODULES = {
    "coverage": "third-party coverage runner installed by CI, not a repo module",
    "pip": "standard library package installer, not a repo module",
    "pytest": "third-party test runner installed by CI, not a repo module",
    "unittest": "standard library module, not a repo module",
}

# Whole-file allowlist, with reasons:
ALLOWLIST_FILES = {
    # forward-looking layout plan: filenames are planned package members
    # under src/geni_uploader/, not current repo-root-relative paths
    "docs/src-layout-plan.md",
}

TEXT_SOURCES = (
    sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    + sorted(ROOT.glob("Dockerfile*"))
    + [ROOT / "entrypoint.sh", ROOT / "README.md",
       ROOT / "ARCHITECTURE.md", ROOT / "CONTRIBUTING.md"]
    + sorted((ROOT / "docs").rglob("*.md"))
    + sorted((ROOT / "man").rglob("*"))
)


def _fmt(file, lineno, token):
    return f"{file.relative_to(ROOT)}:{lineno} -> {token}"


def collect_text_references():
    missing = []
    for file in TEXT_SOURCES:
        if not file.is_file():
            continue
        for lineno, line in enumerate(
                file.read_text(encoding="utf-8").splitlines(), 1):
            for token in PY_TOKEN.findall(line):
                if token.startswith("/opt/"):
                    # container-internal path; the COPY source is checked
                    # separately by collect_dockerfile_copies
                    continue
                if token in ALLOWLIST_PATHS:
                    continue
                if file.relative_to(ROOT).as_posix() in ALLOWLIST_FILES:
                    continue
                # docs cite test files by bare name; resolve those under tests/
                if ("/" not in token and token.startswith("test_")
                        and (ROOT / "tests" / token).exists()):
                    continue
                if not (ROOT / token).exists():
                    missing.append(_fmt(file, lineno, token))
    return missing


def collect_dockerfile_copies():
    missing = []
    for file in sorted(ROOT.glob("Dockerfile*")):
        for lineno, line in enumerate(
                file.read_text(encoding="utf-8").splitlines(), 1):
            m = COPY_LINE.match(line)
            if m and not (ROOT / m.group(1)).exists():
                missing.append(_fmt(file, lineno, m.group(1)))
    return missing


def collect_workflow_python_targets():
    missing = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job in (data.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                run = (step or {}).get("run")
                if not isinstance(run, str):
                    continue
                for lineno, line in enumerate(run.splitlines(), 1):
                    mod = PY_RUN_MODULE.search(line)
                    if mod:
                        name = mod.group(1)
                        if name in ALLOWLIST_MODULES:
                            continue
                        rel = name.replace(".", "/")
                        cands = [ROOT / f"{rel}.py",
                                 ROOT / rel / "__init__.py"]
                        if PYTHONPATH_SRC.search(line):
                            cands += [ROOT / "src" / f"{rel}.py",
                                      ROOT / "src" / rel / "__init__.py"]
                        if not any(c.exists() for c in cands):
                            missing.append(_fmt(wf, lineno, name))
                        continue
                    target = PY_RUN_FILE.search(line)
                    if target and not (ROOT / target.group(1)).exists():
                        missing.append(_fmt(wf, lineno, target.group(1)))
    return missing


def collect_test_path_literals():
    missing = []
    for file in sorted((ROOT / "tests").rglob("*.py")):
        for lineno, line in enumerate(
                file.read_text(encoding="utf-8").splitlines(), 1):
            for token in TEST_PATH_LITERAL.findall(line):
                if not (ROOT / token).exists():
                    missing.append(_fmt(file, lineno, token))
    return missing


class TestPathReferences(unittest.TestCase):
    def test_referenced_py_files_exist(self):
        self.assertEqual([], collect_text_references())

    def test_dockerfile_copy_sources_exist(self):
        self.assertEqual([], collect_dockerfile_copies())

    def test_workflow_python_targets_exist(self):
        self.assertEqual([], collect_workflow_python_targets())

    def test_test_dir_path_literals_exist(self):
        self.assertEqual([], collect_test_path_literals())


if __name__ == "__main__":
    unittest.main()
