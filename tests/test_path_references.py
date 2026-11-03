"""CI guard (issue #704, steps 1-2): every .py path referenced by the repo's
workflows, Dockerfiles, entrypoint, docs and tests must exist.

A reference that drifts (renamed source file, stale doc) fails here instead of
breaking a workflow run or the published image at runtime.
"""
import re
import unittest
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[1]

# A .py token, not a prefix of a longer dotted/hyphenated word (so GitHub
# expressions like ${{ matrix.python-version }} do not match as "matrix.py").
PY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_./-]+\.py(?![A-Za-z0-9_-])")
# COPY src dst, tolerating flag tokens (--chown=..., --from=...) before src
COPY_LINE = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*(\S+)\s+\S+")
# python / python3 invocation, optional short flags, then a file or -m module
PY_RUN_FILE = re.compile(r"python3?(?:\s+-[A-Za-z])*\s+([A-Za-z0-9_./-]+\.py)")
PY_RUN_MODULE = re.compile(r"python3?\s+-m\s+([A-Za-z0-9_.]+)")
# `python -m coverage run ... -m <mod>` re-executes <mod> as a module; only
# this runner pattern makes a later -m a python module (pytest's own -m
# marker, coverage report's -m flag, etc. must NOT match).
COVERAGE_RUN = re.compile(r"python3?\s+-m\s+coverage\s+run\b")
PYTHONPATH_SRC = re.compile(r"PYTHONPATH=src")
# ROOT / some.py and Path(...) / name.py literals inside tests/
TEST_PATH_LITERAL = re.compile(
    r"(?:ROOT|Path\([^)]*\))\s*/\s*['\"]([^'\"]+\.py)['\"]")

# Bare filenames used as unittest discovery patterns (-p), resolved under a
# specific directory by `discover -s <dir>`, not relative to repo root; the
# mapped location must exist.
PATTERN_PATHS = {
    "test_scorecard_guard.py": "tests/security/test_scorecard_guard.py",
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
    try:
        file = file.relative_to(ROOT)
    except ValueError:
        pass
    return f"{file}:{lineno} -> {token}"


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
                if token in PATTERN_PATHS:
                    if not (ROOT / PATTERN_PATHS[token]).exists():
                        missing.append(_fmt(file, lineno, token))
                    continue
                if file.relative_to(ROOT).as_posix() in ALLOWLIST_FILES:
                    continue
                # docs cite test files by bare name; resolve under tests/
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


def run_logical_lines(raw):
    """Yield (physical_lineno, logical_line, [physical_span]) for every
    `run:` scalar in a workflow, located via yaml.compose source marks so
    block-header comments and indentation indicators cannot confuse it.

    Literal blocks (|): each physical content line is one logical line.
    Folded blocks (>): consecutive non-blank physical lines join into one
    logical line (the YAML folding rule for commands); findings map back to
    the physical line holding the token. More-indented lines inside folded
    blocks are treated as regular lines (not present in this repo).
    """
    raw_lines = raw.splitlines()
    root = yaml.compose(raw)
    if root is None:
        return
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, SequenceNode):
            stack.extend(node.value)
        if isinstance(node, MappingNode):
            for key, value in node.value:
                stack.append(key)
                stack.append(value)
                if (isinstance(key, ScalarNode) and key.value == "run"
                        and isinstance(value, ScalarNode)):
                    if value.style in ("|", ">"):
                        first = value.start_mark.line + 1  # 0-based
                        key_col = key.start_mark.column
                        block = []  # (physical_lineno, text)
                        for j in range(first, len(raw_lines)):
                            bline = raw_lines[j]
                            if (bline.strip()
                                    and len(bline) - len(bline.lstrip())
                                    <= key_col):
                                break
                            block.append((j + 1, bline))
                        if value.style == "|":
                            for phys, text in block:
                                yield phys, text, [phys]
                        else:
                            buf = []
                            for phys, text in block:
                                if text.strip():
                                    buf.append((phys, text))
                                else:
                                    if buf:
                                        yield (buf[0][0],
                                               " ".join(t.strip()
                                                        for _, t in buf),
                                               [q for q, _ in buf])
                                        buf = []
                                    yield phys, "", [phys]
                            if buf:
                                yield (buf[0][0],
                                       " ".join(t.strip() for _, t in buf),
                                       [q for q, _ in buf])
                    else:
                        yield (value.start_mark.line + 1,
                               value.value, [value.start_mark.line + 1])


def _module_missing(name, line):
    if name in ALLOWLIST_MODULES:
        return False
    rel = name.replace(".", "/")
    cands = [ROOT / f"{rel}.py", ROOT / rel / "__init__.py"]
    if PYTHONPATH_SRC.search(line):
        cands += [ROOT / "src" / f"{rel}.py",
                  ROOT / "src" / rel / "__init__.py"]
    return not any(c.exists() for c in cands)


def check_workflow_text(wf, raw):
    """Check one workflow's text; returns file:line -> token findings."""
    yaml.safe_load(raw)  # validates the file parses (issue #704 step 3)
    raw_lines = raw.splitlines()
    missing = []

    def add(lineno, spans, line, token):
        # pinpoint the physical line holding the token (folded paragraphs
        # span several physical lines)
        for phys in spans:
            if token in raw_lines[phys - 1]:
                lineno = phys
                break
        missing.append(_fmt(wf, lineno, token))

    for lineno, line, spans in run_logical_lines(raw):
        for m in PY_RUN_MODULE.finditer(line):
            if _module_missing(m.group(1), line):
                add(lineno, spans, line, m.group(1))
        crun = COVERAGE_RUN.search(line)
        if crun:
            # `coverage run -m <mod>` executes <mod> as a module; coverage
            # consumes exactly one -m, so later -m args belong to the
            # invoked tool (e.g. pytest's -m marker), not to python
            m = re.search(r"-m\s+([A-Za-z0-9_.]+)", line[crun.end():])
            if m and _module_missing(m.group(1), line):
                add(lineno, spans, line, m.group(1))
        target = PY_RUN_FILE.search(line)
        if target and not (ROOT / target.group(1)).exists():
            add(lineno, spans, line, target.group(1))
    seen, out = set(), []
    for item in missing:  # a token must be reported once per line
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def collect_workflow_python_targets():
    missing = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        missing.extend(check_workflow_text(
            wf, wf.read_text(encoding="utf-8")))
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


class TestWorkflowParsingRegressions(unittest.TestCase):
    """Regression tests against synthetic workflow text (review findings)."""

    @staticmethod
    def check(raw):
        return check_workflow_text(Path(".github/workflows/synthetic.yml"),
                                   raw)

    def test_pytest_marker_is_not_a_module(self):
        # `pytest -m smoke`: the marker belongs to pytest, not to python
        raw = ("jobs:\n  t:\n    steps:\n"
               "      - run: python -m pytest -m smoke tests/\n")
        self.assertEqual([], self.check(raw))

    def test_coverage_run_chained_module_checked(self):
        raw = ("jobs:\n  t:\n    steps:\n      - run: |\n"
               "          python -m coverage run -m no_such_mod_704 tests/\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        self.assertIn("no_such_mod_704", findings[0])

    def test_missing_module_reported_once(self):
        raw = ("jobs:\n  t:\n    steps:\n"
               "      - run: python3 -m no_such_mod_704\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        self.assertIn("no_such_mod_704", findings[0])

    def test_literal_block_leading_blank_line_number(self):
        raw = ("jobs:\n  t:\n    steps:\n      - run: |\n"
               "\n"
               "          python3 -m no_such_mod_704\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        lineno = int(findings[0].split(" -> ")[0].rsplit(":", 1)[1])
        self.assertIn("no_such_mod_704", raw.splitlines()[lineno - 1])

    def test_coverage_run_consumes_one_nested_module(self):
        raw = ("jobs:\n  t:\n    steps:\n      - run: |\n"
               "          python -m coverage run -m pytest -m smoke tests/\n")
        self.assertEqual([], self.check(raw))
        raw = ("jobs:\n  t:\n    steps:\n      - run: |\n"
               "          python -m coverage run -m no_such_mod_704 -m smoke\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        self.assertIn("no_such_mod_704", findings[0])

    def test_block_header_comment_keeps_block(self):
        raw = ("jobs:\n  t:\n    steps:\n"
               "      - run: | # run tests\n"
               "          python3 -m no_such_mod_704\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        lineno = int(findings[0].split(" -> ")[0].rsplit(":", 1)[1])
        self.assertIn("no_such_mod_704", raw.splitlines()[lineno - 1])

    def test_block_indentation_indicator_keeps_block(self):
        raw = ("jobs:\n  t:\n    steps:\n"
               "      - run: |2\n"
               "          python3 -m no_such_mod_704\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        self.assertIn("no_such_mod_704", findings[0])

    def test_folded_block_physical_line_number(self):
        raw = ("jobs:\n  t:\n    steps:\n      - run: >-\n"
               "          echo start\n"
               "          echo middle\n"
               "          python3 -m no_such_mod_704\n")
        findings = self.check(raw)
        self.assertEqual(1, len(findings))
        lineno = int(findings[0].split(" -> ")[0].rsplit(":", 1)[1])
        self.assertIn("no_such_mod_704", raw.splitlines()[lineno - 1])


if __name__ == "__main__":
    unittest.main()
