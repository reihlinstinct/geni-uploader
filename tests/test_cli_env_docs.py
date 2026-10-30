"""Two-way doc-vs-code check for CLI entry points and environment variables (#513).

Every CLI flag, subcommand and positional of the repo's argparse entry points,
and every environment variable the code reads, must be documented in its
designated docs; every flag/env token the designated docs present must exist
in the code. Scope is the CLI/env surface only: module-internal Python APIs are
covered by their own pinned doc tests.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / '.github' / 'docs-vs-code-allowlist.txt'

# Entry point script -> designated docs that must document its CLI surface.
ENTRY_POINTS = {
    'geni_upload.py': ['docs/usage.md', 'docs/geni-token.md',
                       'docs/API-CLIENT-DESIGN.md', 'docs/guid-resolution.md',
                       'README.md'],
    'source_details.py': ['docs/usage.md', 'docs/source-details-design.md'],
    'parent_probe.py': ['docs/local-parent-probe.md'],
    'parent_plan.py': ['docs/parent-plan.md'],
    'parent_output.py': ['docs/human-parent-output-review.md'],
    'visual_plan.py': ['docs/private-visual-plan.md'],
    'tools/image_provenance.py': ['docs/image-release.md'],
    'tools/image_descriptor.py': ['docs/image-release.md'],
}

# Environment variable -> designated docs that must mention it.
ENV_DOCS = {
    'GENI_ACCESS_TOKEN': ['docs/usage.md', 'docs/API-CLIENT-DESIGN.md'],
    'GENI_API_BASE': ['docs/API-CLIENT-DESIGN.md'],
    'GENI_UPLOAD_E2E': ['docs/API-CLIENT-DESIGN.md'],
    'GENI_PLAN_REPORT': ['docs/usage.md'],
    'GENI_UPLOAD_REF': ['docs/usage.md', 'README.md'],
    'GENI_VISUAL_PLAN': ['docs/private-visual-plan.md'],
    'GENI_UPLOAD_REPO': ['docs/usage.md', 'docs/geni-token.md', 'README.md'],
    'GENI_UPLOAD_EXPECT_SHA': ['docs/usage.md', 'README.md'],
    'GH_TOKEN_FILE': ['docs/usage.md'],
    'FATHER_JOB_READ_TOKEN': ['docs/protected-father-job.md'],
    'FATHER_JOB_RELEASE_JSON': ['docs/protected-father-job.md'],
    'FATHER_JOB_RELEASE_SHA256': ['docs/protected-father-job.md'],
    'GITHUB_ACTOR_ID': ['docs/protected-father-job.md'],
    'GITHUB_EVENT_NAME': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'GITHUB_REF': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'GITHUB_REPOSITORY': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'GITHUB_RUN_ATTEMPT': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'GITHUB_RUN_ID': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'GITHUB_SHA': ['docs/protected-father-job.md', 'docs/one-time-parent-pilot.md'],
    'PROBE_CONFIRM': ['docs/secondary-readonly-evidence.md'],
    'PROBE_MERGE_POLICY': ['docs/secondary-readonly-evidence.md'],
    'PROBE_OUTPUT_DIR': ['docs/secondary-readonly-evidence.md'],
    'PROBE_RECIPIENT': ['docs/secondary-readonly-evidence.md'],
    'PROBE_RUN_ATTEMPT': ['docs/secondary-readonly-evidence.md'],
    'SECONDARY_PROBE_CONNECTION_JSON': ['docs/secondary-readonly-evidence.md'],
    'SECONDARY_PROBE_TOKEN': ['docs/secondary-readonly-evidence.md'],
    'TOKEN_PROBE_CREDENTIAL': ['docs/token-probe.md'],
    'PILOT_CONFIRM': ['docs/one-time-parent-pilot.md'],
    'PILOT_CONFIG_JSON': ['docs/one-time-parent-pilot.md'],
    'PILOT_CONFIG_SHA256': ['docs/one-time-parent-pilot.md'],
    'PILOT_EXECUTOR_SHA': ['docs/one-time-parent-pilot.md'],
    'PILOT_OUTPUT_DIR': ['docs/one-time-parent-pilot.md'],
    'FAMILY_TREE_PAT': ['docs/one-time-parent-pilot.md'],
    'GENI_SECONDARY_ACCESS_TOKEN': ['docs/one-time-parent-pilot.md',
                                    'docs/secondary-readonly-evidence.md'],
    'GITHUB_ACTOR': ['docs/one-time-parent-pilot.md'],
    'GITHUB_TRIGGERING_ACTOR': ['docs/one-time-parent-pilot.md'],
}

# Doc-side token patterns treated as environment variables.
ENV_TOKEN = re.compile(
    r'\b(GENI_[A-Z0-9_]+|FATHER_JOB_[A-Z0-9_]+|PILOT_[A-Z0-9_]+'
    r'|(?:SECONDARY_)?PROBE_[A-Z0-9_]+|ONE_TIME_[A-Z0-9_]+'
    r'|GITHUB_[A-Z0-9_]+|GH_TOKEN_FILE|TOKEN_PROBE_CREDENTIAL|FAMILY_TREE_PAT)\b')

# Code spans are scanned for doc-side flags only after one of these markers;
# the marker selects the entry point whose flags are valid there.
MARKERS = {
    'geni_upload.py': 'geni_upload.py',
    'ghcr.io/reihlinstinct/geni-uploader@': 'geni_upload.py',
    'source_details.py': 'source_details.py',
    'details-validate': 'source_details.py',
    'details-plan': 'source_details.py',
    'details-repair': 'source_details.py',
    'details-snapshot': 'source_details.py',
    'parent_probe.py': 'parent_probe.py',
    'parent_plan.py': 'parent_plan.py',
    'parent_output.py': 'parent_output.py',
    'visual_plan.py': 'visual_plan.py',
    'image_provenance.py': 'tools/image_provenance.py',
    'image_descriptor.py': 'tools/image_descriptor.py',
}

CODE_GLOBS = ['*.py', 'src/**/*.py', 'tools/**/*.py', 'scripts/**/*.py']


def allowlist():
    out = {}
    if ALLOWLIST.is_file():
        for line in ALLOWLIST.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            token, _, reason = line.partition('#')
            token = token.strip()
            if not reason.strip():
                raise AssertionError(f'allowlist entry without a reason: {line}')
            out[token] = reason.strip()
    return out


def code_files():
    out = []
    for pattern in CODE_GLOBS:
        out.extend(ROOT.glob(pattern))
    return [p for p in out if 'test' not in p.name]


def cli_surface(script):
    """Flags, subcommands and positionals of one argparse script."""
    text = (ROOT / script).read_text(encoding='utf-8')
    flags, subcommands, positionals = set(), set(), set()
    # Multi-line tolerant: capture the first quoted argument of each call.
    for match in re.finditer(r'add_argument\(\s*[\'"]([^\'"]+)[\'"]', text):
        token = match.group(1)
        (flags if token.startswith('-') else positionals).add(token)
    for match in re.finditer(r'add_parser\(\s*[\'"]([^\'"]+)[\'"]', text):
        subcommands.add(match.group(1))
    # Loop-registered subcommands: ("plan", cmd_plan) fed to add_parser(name).
    if re.search(r'add_parser\([a-z_]+\)', text):
        for match in re.finditer(r"[\(]['\"]([a-z][a-z-]*)['\"]\s*,\s*cmd_", text):
            subcommands.add(match.group(1))
    # Indirect registrations: sub.choices["run"].add_argument(...) on one line.
    for match in re.finditer(r'choices\[[\'"][a-z-]+[\'"]\]\.add_argument\(\s*[\'"]([^\'"]+)[\'"]',
                             text):
        flags.add(match.group(1))
    return flags, subcommands, positionals


def code_env_vars():
    out = set()
    for path in code_files():
        text = path.read_text(encoding='utf-8')
        out |= set(re.findall(r"\benviron\w*\.(?:get|pop)\(['\"]([A-Z_0-9]+)['\"]", text))
        out |= set(re.findall(r"\benviron\w*\[['\"]([A-Z_0-9]+)['\"]\]", text))
        out |= set(re.findall(r"\benv\.(?:get|pop)\(['\"]([A-Z_0-9]+)['\"]", text))
        out |= set(re.findall(r"\benv\[['\"]([A-Z_0-9]+)['\"]\]", text))
    entrypoint = (ROOT / 'entrypoint.sh').read_text(encoding='utf-8')
    out |= set(re.findall(r'\$\{([A-Z_][A-Z_0-9]*)[:-]', entrypoint))
    return out


def doc_text(paths):
    return '\n'.join((ROOT / p).read_text(encoding='utf-8') for p in paths)


def code_spans(text):
    """Fenced blocks and inline backtick spans."""
    spans = re.findall(r'```[^\n]*\n(.*?)```', text, re.DOTALL)
    without_fences = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.DOTALL)
    spans += re.findall(r'`([^`\n]+)`', without_fences)
    return spans


def flags_in_spans(spans):
    """Flags appearing in command spans after an entry-point marker."""
    out = {}  # script -> set of flags
    for span in spans:
        best = None
        for marker, script in MARKERS.items():
            idx = span.find(marker)
            if idx >= 0 and (best is None or idx < best[0]):
                best = (idx, script)
        if best is None:
            continue
        idx, script = best
        for flag in re.findall(r'(?<![\w-])--[a-z][a-z0-9-]*', span[idx:]):
            out.setdefault(script, set()).add(flag)
    return out


def documented_flags(paths):
    spans = []
    for path in paths:
        spans += code_spans((ROOT / path).read_text(encoding='utf-8'))
    return flags_in_spans(spans)


def documented_env_vars(paths):
    out = set()
    for path in paths:
        out |= set(ENV_TOKEN.findall((ROOT / path).read_text(encoding='utf-8')))
    return out


class CliDocsTest(unittest.TestCase):
    def test_every_cli_token_is_documented(self):
        allowed = allowlist()
        missing = []
        for script, docs in ENTRY_POINTS.items():
            text = doc_text(docs)
            flags, subcommands, positionals = cli_surface(script)
            for token in sorted(flags | subcommands | positionals):
                if token in allowed:
                    continue
                if not re.search(r'(?<![\w-])' + re.escape(token) + r'(?![\w-])', text):
                    missing.append(f'{script}: {token}')
        self.assertEqual(missing, [], f'CLI tokens missing from docs: {missing}')

    def test_every_documented_flag_exists(self):
        allowed = allowlist()
        stale = []
        scripts = set(ENTRY_POINTS)
        docs_by_script = {s: set(d) for s, d in ENTRY_POINTS.items()}
        all_docs = sorted({d for docs in docs_by_script.values() for d in docs})
        for script, flags in documented_flags(all_docs).items():
            if script not in scripts:
                continue
            known = cli_surface(script)[0]
            for flag in sorted(flags):
                if flag not in known and flag not in allowed:
                    stale.append(f'{script}: {flag}')
        self.assertEqual(stale, [], f'documented flags missing from code: {stale}')

    def test_every_argparse_script_is_covered(self):
        allowed = allowlist()
        uncovered = []
        for path in code_files():
            rel = str(path.relative_to(ROOT))
            if rel in ENTRY_POINTS or rel in allowed:
                continue
            if 'add_argument(' in path.read_text(encoding='utf-8'):
                uncovered.append(rel)
        self.assertEqual(uncovered, [],
                         f'argparse scripts neither mapped nor allowlisted: {uncovered}')

    def test_every_env_var_is_documented(self):
        allowed = allowlist()
        missing = []
        for var in sorted(code_env_vars()):
            if var in allowed:
                continue
            docs = ENV_DOCS.get(var)
            if docs is None:
                missing.append(f'{var}: no designated doc')
                continue
            if not re.search(r'\b' + re.escape(var) + r'\b', doc_text(docs)):
                missing.append(f'{var}: not in {docs}')
        self.assertEqual(missing, [], f'env vars missing from docs: {missing}')

    def test_every_documented_env_var_exists(self):
        known = code_env_vars() | set(allowlist())
        docs = sorted({d for ds in ENV_DOCS.values() for d in ds})
        stale = sorted(v for v in documented_env_vars(docs) if v not in known)
        self.assertEqual(stale, [], f'documented env vars missing from code: {stale}')

    def test_allowlist_entries_are_used(self):
        allowed = allowlist()
        used = set()
        for path in code_files():
            rel = str(path.relative_to(ROOT))
            if rel in allowed:
                used.add(rel)
        used |= code_env_vars() & set(allowed)
        docs = sorted({d for ds in ENV_DOCS.values() for d in ds} | {'docs/one-time-parent-pilot.md'})
        used |= documented_env_vars(docs) & set(allowed)
        unused = sorted(set(allowed) - used)
        self.assertEqual(unused, [], f'stale allowlist entries: {unused}')

    def test_doc_scan_catches_fake_tokens(self):
        # A fake flag after a marker is attributed to that entry point...
        found = flags_in_spans(['python geni_upload.py --totally-fake-flag value'])
        self.assertEqual({'geni_upload.py': {'--totally-fake-flag'}}, found)
        # ...and is not part of its real surface, so the two-way test fails on it.
        self.assertNotIn('--totally-fake-flag', cli_surface('geni_upload.py')[0])
        # No marker in the span: nothing is attributed (wrapper flags excluded).
        self.assertEqual({}, flags_in_spans(['podman run --rm --totally-fake-flag x']))
        # Loop-registered subcommands are extracted.
        self.assertIn('plan', cli_surface('geni_upload.py')[1])
        # A fake env-shaped token is caught by the env scanner.
        self.assertIn('PILOT_TOTALLY_FAKE', ENV_TOKEN.findall('PILOT_TOTALLY_FAKE=1'))


if __name__ == '__main__':
    unittest.main()
