"""Two-way doc-vs-code check for CLI entry points and environment variables (#511).

Every CLI flag and subcommand/choice of the repo's argparse entry points, every
entrypoint.sh container alias, and every environment variable the code reads
must be documented in its designated docs; every flag, subcommand and env token
the designated docs present in an invocation context must exist in the code.
Scope is the CLI/env surface only: module-internal Python APIs are covered by
their own pinned doc tests. Positional dest names are not a typed surface, so a
positional-bearing script is instead required to show an invocation span.
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
    'tools/build_man_pages.py': ['README.md'],
}

# Environment variable -> designated docs that must mention it.
ENV_DOCS = {
    **{key: ['docs/guarded-family-additions.md'] for key in (
        'FAMILY_CONFIG_JSON', 'FAMILY_CONFIG_SHA256', 'FAMILY_EXECUTOR_SHA',
        'FAMILY_CONFIRM', 'FAMILY_OUTPUT_DIR')},
    'GENI_ACCESS_TOKEN': ['docs/usage.md', 'docs/API-CLIENT-DESIGN.md'],
    'GENI_API_BASE': ['docs/API-CLIENT-DESIGN.md'],
    'GENI_UPLOAD_E2E': ['docs/API-CLIENT-DESIGN.md'],
    'GENI_PLAN_REPORT': ['docs/usage.md'],
    'GENI_UPLOAD_REF': ['docs/usage.md', 'README.md'],
    'GENI_VISUAL_PLAN': ['docs/private-visual-plan.md'],
    'GENI_UPLOAD_REPO': ['docs/usage.md', 'docs/geni-token.md', 'README.md'],
    'GENI_UPLOAD_EXPECT_SHA': ['docs/usage.md', 'README.md'],
    'GH_TOKEN_FILE': ['docs/usage.md'],
    'HOME': ['README.md'],
    'PREFIX': ['README.md'],
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
    'PILOT_DEBUG': ['docs/one-time-parent-pilot.md'],
    'PILOT_CONFIRM': ['docs/one-time-parent-pilot.md'],
    'PILOT_CONFIG_JSON': ['docs/one-time-parent-pilot.md'],
    'PILOT_CONFIG_SHA256': ['docs/one-time-parent-pilot.md'],
    'PILOT_EXECUTOR_SHA': ['docs/one-time-parent-pilot.md'],
    'PILOT_OUTPUT_DIR': ['docs/one-time-parent-pilot.md'],
    'DIAGNOSTIC_MODE': ['docs/pilot-get-diagnostics.md'],
    'DIAGNOSTIC_CONFIRM': ['docs/pilot-get-diagnostics.md'],
    'DIAGNOSTIC_CONFIG_JSON': ['docs/pilot-get-diagnostics.md'],
    'DIAGNOSTIC_CONFIG_SHA256': ['docs/pilot-get-diagnostics.md'],
    'DIAGNOSTIC_EXECUTOR_SHA': ['docs/pilot-get-diagnostics.md'],
    'DIAGNOSTIC_OUTPUT_DIR': ['docs/pilot-get-diagnostics.md'],
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

# Command spans are scanned only after one of these markers; the marker
# selects the entry point whose surface is valid there.
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
    'build_man_pages.py': 'tools/build_man_pages.py',
}

CODE_GLOBS = ['*.py', 'src/**/*.py', 'tools/**/*.py', 'scripts/**/*.py']
SHELL_GLOBS = ['*.sh', 'scripts/**/*.sh', 'tools/**/*.sh']


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


def shell_files():
    out = []
    for pattern in SHELL_GLOBS:
        out.extend(ROOT.glob(pattern))
    return sorted(set(out))


def _call_body(text, open_paren):
    """Return the argument body of a call, string-aware, from its '(' position."""
    depth, quote, i = 0, None, open_paren
    while i < len(text):
        c = text[i]
        if quote:
            if c == '\\':
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return text[open_paren + 1:i]
        i += 1
    return text[open_paren + 1:]


def _quoted(body):
    return [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", body)]


def cli_surface_text(text):
    """The typed CLI surface of one argparse script."""
    surface = {'flags': set(), 'bool_flags': set(), 'subcommands': set(),
               'choices': set(), 'positionals': set()}
    for match in re.finditer(r'add_argument\(', text):
        body = _call_body(text, match.end() - 1)
        tokens = _quoted(body)
        flags = [t for t in tokens if t.startswith('-')]
        boolean = re.search(r"action\s*=\s*['\"]store_(?:true|false)['\"]", body)
        if flags:
            surface['flags'].update(flags)
            if boolean:
                surface['bool_flags'].update(flags)
        elif tokens:
            surface['positionals'].add(tokens[0])
        choices = re.search(r'choices\s*=\s*[\[\(]([^\]\)]*)', body)
        if choices:
            surface['choices'].update(_quoted(choices.group(1)))
    for match in re.finditer(r'add_parser\(', text):
        body = _call_body(text, match.end() - 1)
        name = re.match(r'\s*[\'"]([a-z][a-z0-9-]*)[\'"]', body)
        if name:
            surface['subcommands'].add(name.group(1))
    # Loop-registered subcommands: ("plan", cmd_plan) fed to add_parser(name),
    # with or without extra arguments such as help=....
    if re.search(r'add_parser\(\s*[a-z_]+\s*[,)]', text):
        for match in re.finditer(r"[\(]['\"]([a-z][a-z-]*)['\"]\s*,\s*cmd_", text):
            surface['subcommands'].add(match.group(1))
    # Indirect registrations: sub.choices["run"].add_argument(...).
    for match in re.finditer(r"choices\[['\"][a-z-]+['\"]\]\.add_argument\(", text):
        body = _call_body(text, match.end() - 1)
        flags = [t for t in _quoted(body) if t.startswith('-')]
        surface['flags'].update(flags)
        if re.search(r"action\s*=\s*['\"]store_(?:true|false)['\"]", body):
            surface['bool_flags'].update(flags)
    return surface


def cli_surface(script):
    return cli_surface_text((ROOT / script).read_text(encoding='utf-8'))


def entrypoint_aliases():
    """Container subcommand aliases from entrypoint.sh case arms."""
    text = (ROOT / 'entrypoint.sh').read_text(encoding='utf-8')
    out = set()
    for arm in re.findall(r'(?m)^\s*([a-z0-9-]+(?:\|[a-z0-9-]+)*)\)', text):
        out.update(arm.split('|'))
    return out


def python_env_reads(text):
    out = set()
    out |= set(re.findall(r"\benviron\w*\.(?:get|pop)\(\s*['\"]([A-Z_][A-Z_0-9]*)['\"]", text))
    out |= set(re.findall(r"\benviron\w*\[\s*['\"]([A-Z_][A-Z_0-9]*)['\"]\s*\]", text))
    out |= set(re.findall(r"\benv\.(?:get|pop)\(\s*['\"]([A-Z_][A-Z_0-9]*)['\"]", text))
    out |= set(re.findall(r"\benv\[\s*['\"]([A-Z_][A-Z_0-9]*)['\"]\s*\]", text))
    out |= set(re.findall(r"\b(?:os\.)?getenv\(\s*['\"]([A-Z_][A-Z_0-9]*)['\"]", text))
    out |= set(re.findall(r"['\"]([A-Z_][A-Z_0-9]*)['\"]\s+in\s+[\w.]*environ\w*", text))
    return out


def shell_env_reads(text):
    """Env reads in a shell script: $X/${X} references to names never assigned.

    A self-defaulting assignment (X="${X:-default}") is a read with a
    fallback, not a local: the environment can override it.
    """
    assigned = set(re.findall(r'(?m)^\s*(?:export\s+)?([A-Z_][A-Z_0-9]*)=', text))
    self_defaulted = set(re.findall(
        r'(?m)^\s*(?:export\s+)?([A-Z_][A-Z_0-9]*)=["\']?\$\{\1:-', text))
    refs = set(re.findall(r'\$\{([A-Z_][A-Z_0-9]*)[^}]*\}', text))
    refs |= set(re.findall(r'\$([A-Z_][A-Z_0-9]*)', text))
    return refs - (assigned - self_defaulted)


def code_env_vars():
    out = set()
    for path in code_files():
        out |= python_env_reads(path.read_text(encoding='utf-8'))
    for path in shell_files():
        out |= shell_env_reads(path.read_text(encoding='utf-8'))
    return out


def doc_text(paths):
    return '\n'.join((ROOT / p).read_text(encoding='utf-8') for p in paths)


def code_spans(text):
    """Fenced blocks and inline backtick spans."""
    spans = re.findall(r'```[^\n]*\n(.*?)```', text, re.DOTALL)
    without_fences = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.DOTALL)
    spans += re.findall(r'`([^`\n]+)`', without_fences)
    return spans


def _marker_at(span):
    best = None
    for marker, script in MARKERS.items():
        idx = span.find(marker)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, script)
    return best


def walk_tokens(script, tokens, surface, allowed):
    """Flags and subcommand candidates from one command token stream."""
    stale_flags, stale_subcommands = [], []
    known_words = surface['subcommands'] | surface['choices']
    expect_value = False
    for token in tokens:
        token = token.rstrip('\\')
        if not token:
            continue
        if expect_value:
            expect_value = False
            continue
        flag = re.search(r'(?<![\w-])--[a-z][a-z0-9-]*', token)
        if token.startswith('-') and flag:
            name = flag.group(0)
            if name not in surface['flags'] and name not in allowed:
                stale_flags.append(name)
            elif '=' not in token and name not in surface['bool_flags']:
                expect_value = True
            continue
        if re.match(r'^[A-Z_][A-Z_0-9]*=', token):
            continue
        if '<' in token:
            expect_value = False
            if not token.endswith('>'):
                expect_value = True  # multi-word placeholder: skip through '>'
            continue
        if re.match(r'^([$/"\']|\d)', token):
            continue
        word = token.strip("`',;")
        if not re.fullmatch(r'[a-z][a-z0-9-]*', word):
            continue
        if known_words and word not in known_words and word not in allowed:
            stale_subcommands.append(word)
    return stale_flags, stale_subcommands


def stale_invocations(paths, surfaces, allowed):
    """Docs->code walk over the designated docs."""
    stale_flags, stale_subcommands = [], []
    for path in sorted(paths):
        for span in code_spans((ROOT / path).read_text(encoding='utf-8')):
            for script, tokens in command_windows(span):
                flags, subs = walk_tokens(script, tokens, surfaces[script], allowed)
                stale_flags += [f'{path}: {f} (as {script})' for f in flags]
                stale_subcommands += [f'{path}: {w} (as {script})' for w in subs]
    return stale_flags, stale_subcommands


def flags_in_spans(spans):
    """Flags appearing on marker lines (and continuations) in command spans."""
    out = {}
    for span in spans:
        for script, tokens in command_windows(span):
            for token in tokens:
                flag = re.search(r'(?<![\w-])--[a-z][a-z0-9-]*', token)
                if flag:
                    out.setdefault(script, set()).add(flag.group(0))
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


def documented_in_context(paths, token):
    """True when token appears in a command span after that script's marker."""
    for path in paths:
        for span in code_spans((ROOT / path).read_text(encoding='utf-8')):
            found = _marker_at(span)
            if found and re.search(r'(?<![\w-])' + re.escape(token) + r'(?![\w-])',
                                   span[found[0]:]):
                return True
    return False


def command_windows(span):
    """(script, tokens) per marker line in the span, with \\ continuations.

    Only the line holding the marker and its backslash-continuation lines are
    walked, so prose inside fences (tables, mermaid diagrams) is never read
    as a command.
    """
    out = []
    lines = span.splitlines()
    i = 0
    while i < len(lines):
        found = _marker_at(lines[i])
        if found is None:
            i += 1
            continue
        script = found[1]
        window = [lines[i]]
        while window[-1].rstrip().endswith('\\') and i + 1 < len(lines):
            i += 1
            window.append(lines[i])
        tokens = ' '.join(window).split()
        # Drop everything through the marker token.
        for pos, token in enumerate(tokens):
            for marker, owner in MARKERS.items():
                if owner == script and marker in token:
                    tail = token[token.find(marker) + len(marker):]
                    out.append((script, ([tail] if tail else []) + tokens[pos + 1:]))
                    break
            else:
                continue
            break
        i += 1
    return out


class CliDocsTest(unittest.TestCase):
    def test_every_cli_token_is_documented(self):
        allowed = allowlist()
        missing = []
        for script, docs in ENTRY_POINTS.items():
            text = doc_text(docs)
            surface = cli_surface(script)
            for token in sorted(surface['flags']):
                if token in allowed:
                    continue
                if not re.search(r'(?<![\w-])' + re.escape(token) + r'(?![\w-])', text):
                    missing.append(f'{script}: {token}')
            # Subcommands and choices name common words: require an
            # invocation context, not a bare-word mention.
            for token in sorted(surface['subcommands'] | surface['choices']):
                if token in allowed:
                    continue
                if not documented_in_context(docs, token):
                    missing.append(f'{script}: {token} (no invocation context)')
        for alias in sorted(entrypoint_aliases()):
            if alias not in allowed and not re.search(
                    r'(?<![\w-])' + re.escape(alias) + r'(?![\w-])',
                    doc_text(ENTRY_POINTS['source_details.py'])):
                missing.append(f'entrypoint.sh: {alias}')
        self.assertEqual(missing, [], f'CLI tokens missing from docs: {missing}')

    def test_every_entry_point_shows_an_invocation(self):
        missing = []
        for script, docs in ENTRY_POINTS.items():
            shown = False
            for path in docs:
                for span in code_spans((ROOT / path).read_text(encoding='utf-8')):
                    found = _marker_at(span)
                    if found and found[1] == script:
                        shown = True
            if not shown:
                missing.append(script)
        self.assertEqual(missing, [], f'entry points with no invocation span: {missing}')

    def test_documented_invocations_exist_in_code(self):
        allowed = allowlist()
        surfaces = {script: cli_surface(script) for script in ENTRY_POINTS}
        docs = sorted({d for ds in ENTRY_POINTS.values() for d in ds})
        stale_flags, stale_subcommands = stale_invocations(docs, surfaces, allowed)
        self.assertEqual(stale_flags, [], f'documented flags missing from code: {stale_flags}')
        self.assertEqual(stale_subcommands, [],
                         f'documented subcommands missing from code: {stale_subcommands}')

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
        allowed = set(allowlist())
        used = set()
        for path in code_files():
            rel = str(path.relative_to(ROOT))
            if rel in allowed:
                used.add(rel)
        used |= code_env_vars() & allowed
        for script in ENTRY_POINTS:
            surface = cli_surface(script)
            used |= allowed & (surface['flags'] | surface['subcommands'] | surface['choices'])
        docs = sorted({d for ds in ENV_DOCS.values() for d in ds})
        used |= documented_env_vars(docs) & allowed
        unused = sorted(allowed - used)
        self.assertEqual(unused, [], f'stale allowlist entries: {unused}')

    def test_extraction_regressions(self):
        # Loop subcommands survive extra add_parser arguments (#516 shape).
        surface = cli_surface_text(
            'p = sub.add_parser(name, help="x")\n'
            'for name, fn in (("plan", cmd_plan), ("run", cmd_run)):\n'
            '    p = sub.add_parser(name, help="x")\n')
        self.assertIn('plan', surface['subcommands'])
        # Long-form flags are extracted alongside short forms.
        surface = cli_surface_text("p.add_argument('-q', '--quiet-mode')")
        self.assertEqual({'-q', '--quiet-mode'}, surface['flags'])
        # argparse choices are extracted.
        surface = cli_surface_text(
            'p.add_argument("mode", choices=["validate", "purge"])')
        self.assertEqual({'validate', 'purge'}, surface['choices'])
        # store_true marks a flag boolean.
        surface = cli_surface_text('p.add_argument("--sync-state", action="store_true")')
        self.assertIn('--sync-state', surface['bool_flags'])
        # env read forms: getenv, membership, shell $X/${X} minus locals.
        self.assertIn('NEW', python_env_reads('os.getenv("NEW")'))
        self.assertIn('NEW', python_env_reads('if "NEW" in os.environ:'))
        self.assertIn('NEW', shell_env_reads('echo $NEW\necho ${NEW}\nLOCAL=1\necho $LOCAL'))
        # A self-defaulting assignment is a read, not a local.
        self.assertIn('PREFIX', shell_env_reads('PREFIX="${PREFIX:-/usr/local}"'))
        self.assertNotIn('LOCAL', shell_env_reads('LOCAL=1\necho $LOCAL'))

    def test_doc_scan_catches_fake_tokens(self):
        # A fake flag after a marker is attributed to that entry point...
        found = flags_in_spans(['python geni_upload.py --totally-fake-flag value'])
        self.assertEqual({'geni_upload.py': {'--totally-fake-flag'}}, found)
        # ...and is not part of its real surface, so the two-way test fails on it.
        self.assertNotIn('--totally-fake-flag', cli_surface('geni_upload.py')['flags'])
        # No marker in the span: nothing is attributed (wrapper flags excluded).
        self.assertEqual({}, flags_in_spans(['podman run --rm --totally-fake-flag x']))
        # A documented nonexistent subcommand after a marker is caught.
        surfaces = {'geni_upload.py': cli_surface('geni_upload.py')}
        _, stale = _stale_from_spans(['python geni_upload.py frobnicate'], surfaces, set())
        self.assertEqual(['frobnicate (as geni_upload.py)'], stale)
        # A boolean flag does not swallow a following real subcommand.
        _, stale = _stale_from_spans(
            ['python source_details.py repair --sync-state --manifest x'], surfaces | {
                'source_details.py': cli_surface('source_details.py')}, set())
        self.assertEqual([], stale)
        # Loop-registered subcommands are extracted from the real script.
        self.assertIn('plan', cli_surface('geni_upload.py')['subcommands'])
        # A fake env-shaped token is caught by the env scanner.
        self.assertIn('PILOT_TOTALLY_FAKE', ENV_TOKEN.findall('PILOT_TOTALLY_FAKE=1'))


def _stale_from_spans(spans, surfaces, allowed):
    stale_flags, stale_subcommands = [], []
    for span in spans:
        for script, tokens in command_windows(span):
            flags, subs = walk_tokens(script, tokens, surfaces[script], allowed)
            stale_flags += flags
            stale_subcommands += [f'{w} (as {script})' for w in subs]
    return stale_flags, stale_subcommands


if __name__ == '__main__':
    unittest.main()
