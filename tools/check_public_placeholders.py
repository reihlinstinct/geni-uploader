"""Flag real-looking personal data in public files; pattern-only (#725).

Scans tracked text files for:
  * 9-digit (and unpadded 8-digit) sequences whose Israeli-style check digit
    VALIDATES (synthetic persona IDs fail the checksum by construction);
  * phone-shaped numbers outside the reserved fictional forms
    (+999-... E.164-reserved, +1-<NPA>-555-0100..0199 NANPA fictional);
  * structured numeric Geni ID references (profile_id:/union_id: JSON/YAML
    forms, profile-<digits>/union-<digits> tokens) not in the persona set.

Contains only regexes, the check-digit function and reserved-range rules -
no real personal data, no external lookups. Matches listed in
synthetic/public-corpus-baseline.json (anchored by exact file+line+value)
pass; everything else is a violation. Exit 0 when clean, 1 otherwise.

Usage: python tools/check_public_placeholders.py [--root DIR] [--write-baseline]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ID9 = re.compile(r'(?<![\d-])\d{9}(?![\d-])')
ID8 = re.compile(r'(?<![\d-])\d{8}(?![\d-])')
PHONE_INTL = re.compile(r'\+\d[\d -]{6,16}\d')
PHONE_00 = re.compile(r'(?<![\d+])00\d[\d -]{6,14}\d')
PHONE_LOCAL = re.compile(r'(?<![\d+])0\d{1,2}[ -]?\d{3}[ -]?\d{4}(?!\d)')
# Full digit runs: truncating to a bounded length silently passes longer tokens.
STRUCTURED_ID = re.compile(
    r'(?:profile_id|union_id)["\']?\s*[:=]\s*["\']?(\d+)'
    r'|\b(?:profile|union)-(\d+)(?![\w-])')
RESERVED_PHONE = re.compile(r'^(?:\+999-[\d-]{3,12}\d|\+1-\d{3}-555-01\d\d)$')
SKIP_DIRS = {'.git', 'synthetic'}
SKIP_FILES = {'tools/check_public_placeholders.py', 'tests/test_public_placeholders.py'}
TEXT_SUFFIX = {'.md', '.txt', '.yml', '.yaml', '.json', '.py', '.mjs', '.sh',
               '.html', '.example', '.jsonc', '.rst', '.1', '.toml'}


def checksum_valid(digits):
    """Israeli-style check digit: weights 1,2 repeating; valid iff total%10==0."""
    total = 0
    for i, ch in enumerate(digits):
        product = int(ch) * (1 if i % 2 == 0 else 2)
        total += product // 10 + product % 10
    return total % 10 == 0


def tracked_files(root):
    out = subprocess.run(['git', 'ls-files'], cwd=root, check=False,
                         capture_output=True, text=True)
    for name in out.stdout.splitlines():
        path = root / name
        top = name.split('/', 1)[0]
        if top in SKIP_DIRS or name in SKIP_FILES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIX:
            # Suffixless files (Makefile, Dockerfile, ...): sniff as text.
            try:
                chunk = path.read_bytes()[:4096]
            except OSError:
                continue
            if b'\0' in chunk:
                continue
            try:
                chunk.decode('utf-8')
            except UnicodeDecodeError:
                continue
        yield name, path


def load_json(root, rel, default):
    path = root / rel
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def findings(root):
    personas = load_json(root, 'synthetic/personas.json', {'personas': []})
    persona_ids = set()
    for p in personas.get('personas', []):
        for key in ('profile_id', 'union_id'):
            if key in p:
                persona_ids.add(str(p[key]).split('-')[-1])
    for name, path in tracked_files(root):
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            for m in ID9.finditer(line):
                if checksum_valid(m.group()):
                    yield name, lineno, m.group(), 'id9'
            for m in ID8.finditer(line):
                if checksum_valid('0' + m.group()):
                    yield name, lineno, m.group(), 'id8'
            for pattern, cls in ((PHONE_INTL, 'phone'), (PHONE_00, 'phone'),
                                 (PHONE_LOCAL, 'phone')):
                for m in pattern.finditer(line):
                    if not RESERVED_PHONE.fullmatch(m.group()):
                        yield name, lineno, m.group(), cls
            for m in STRUCTURED_ID.finditer(line):
                value = m.group(1) or m.group(2)
                if value not in persona_ids:
                    yield name, lineno, m.group(), 'structured-id'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default='.')
    parser.add_argument('--write-baseline', action='store_true',
                        help='rewrite synthetic/public-corpus-baseline.json findings '
                             'from the current tree (migration tooling)')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        baseline = load_json(root, 'synthetic/public-corpus-baseline.json',
                             {'findings': [], 'allowlist': []})
    except (OSError, UnicodeError, json.JSONDecodeError):
        print('placeholder violation: current baseline is unreadable or not valid JSON')
        return 1
    if not isinstance(baseline, dict):
        print('placeholder violation: current baseline must be a JSON object')
        return 1
    ci = os.environ.get('GITHUB_ACTIONS') == 'true' or os.environ.get('CI') == 'true'
    if args.write_baseline:
        if ci:
            print('placeholder violation: --write-baseline is disabled in CI; '
                  'regenerate the baseline locally and commit it')
            return 1
        seen = set()
        unique = []
        for f, n, v, c in findings(root):
            if (f, n, v, c) not in seen:
                seen.add((f, n, v, c))
                unique.append({'file': f, 'line': n, 'value': v, 'class': c})
        baseline['findings'] = sorted(unique, key=lambda e: (e['file'], e['line'], e['value']))
        path = root / 'synthetic/public-corpus-baseline.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + '\n',
                        encoding='utf-8')
        print(f'baseline written: {len(baseline["findings"])} entries')
        return 0
    for entry in baseline.get('allowlist', []):
        if not entry.get('reason'):
            print(f"placeholder violation: allowlist entry without reason: {entry}")
            return 1
    known = {(e['file'], e['line'], e['value'], e['class'])
             for e in baseline.get('findings', []) + baseline.get('allowlist', [])}
    found = set(findings(root))
    bad = sorted(found - known)
    # An entry no longer matching any finding is stale: the baseline mirrors
    # the corpus exactly, so removals require a regenerated (smaller) baseline.
    stale = sorted(known - found - {(e['file'], e['line'], e['value'], e['class'])
                                    for e in baseline.get('allowlist', [])})
    for f, n, v, c in bad:
        print(f'placeholder violation: {f}:{n}: {c} {v}')
    for f, n, v, c in stale:
        print(f'stale baseline entry: {f}:{n}: {c} {v}')
    growth_violations = 0
    is_pr = bool(os.environ.get('GITHUB_BASE_REF'))
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if ci and is_pr:
        # Fail closed: on a PR the growth guard must be able to evaluate.
        event = {}
        if event_path and Path(event_path).is_file():
            try:
                event = json.loads(Path(event_path).read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                event = {}
        pr = event.get('pull_request') or {}
        base_sha = (pr.get('base') or {}).get('sha')
        if not base_sha:
            print('baseline growth guard: pull-request payload missing or unreadable')
            growth_violations += 1
        else:
            base_known = None
            for attempt in range(2):
                exists = subprocess.run(
                    ['git', 'cat-file', '-e', f'{base_sha}^{{commit}}'],
                    cwd=root, check=False, capture_output=True, text=True)
                if exists.returncode != 0:
                    # Shallow checkout: fetch the base commit explicitly, then retry.
                    subprocess.run(['git', 'fetch', '--depth=1', 'origin', base_sha],
                                   cwd=root, check=False, capture_output=True, text=True)
                    continue
                base = subprocess.run(
                    ['git', 'show', f'{base_sha}:synthetic/public-corpus-baseline.json'],
                    cwd=root, check=False, capture_output=True, text=True)
                if base.returncode == 0:
                    try:
                        data = json.loads(base.stdout)
                    except json.JSONDecodeError:
                        print(f'baseline growth guard: baseline at base {base_sha} '
                              'is not valid JSON')
                        growth_violations += 1
                        break
                    if not isinstance(data, dict):
                        print('baseline growth guard: base baseline must be a JSON object')
                        growth_violations += 1
                        break
                    base_known = {(e['file'], e['line'], e['value'], e['class'])
                                  for e in data.get('findings', []) + data.get('allowlist', [])}
                else:
                    # Commit exists; the path is verifiably absent at base.
                    base_known = set()  # absent at base: introduction is growth
                break
            if base_known is None:
                print(f'baseline growth guard: base {base_sha} unreadable after fetch')
                growth_violations += 1
            else:
                now_known = {(e['file'], e['line'], e['value'], e['class'])
                             for e in baseline.get('findings', []) + baseline.get('allowlist', [])}
                grown = sorted(now_known - base_known)
                labels = {l.get('name') for l in pr.get('labels') or []}
                if grown and 'synthetic-baseline-grow' not in labels:
                    growth_violations += len(grown)
                    for f, n, v, c in grown:
                        print(f'baseline growth without review label: {f}:{n}: {c} {v}')
                    print('baseline additions in a PR require the '
                          "'synthetic-baseline-grow' label (owner-reviewed)")
    violations = len(bad) + len(stale) + growth_violations
    print(f'public placeholder check: {violations} violations')
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
