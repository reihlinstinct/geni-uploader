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
import re
import subprocess
import sys
from pathlib import Path

ID9 = re.compile(r'(?<![\d-])\d{9}(?![\d-])')
ID8 = re.compile(r'(?<![\d-])\d{8}(?![\d-])')
PHONE_INTL = re.compile(r'\+\d[\d -]{6,16}\d')
PHONE_00 = re.compile(r'(?<![\d+])00\d[\d -]{6,14}\d')
PHONE_LOCAL = re.compile(r'(?<![\d+])0\d{1,2}-\d{3}-?\d{4}(?!\d)')
STRUCTURED_ID = re.compile(
    r'(?:profile_id|union_id)["\']?\s*[:=]\s*["\']?(\d{1,12})'
    r'|\b(?:profile|union)-(\d{1,12})(?![\w-])')
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
        if top in SKIP_DIRS or name in SKIP_FILES or path.suffix.lower() not in TEXT_SUFFIX:
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
    baseline = load_json(root, 'synthetic/public-corpus-baseline.json',
                         {'findings': [], 'allowlist': []})
    if args.write_baseline:
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
    bad = [(f, n, v, c) for f, n, v, c in findings(root)
           if (f, n, v, c) not in known]
    for f, n, v, c in bad:
        print(f'placeholder violation: {f}:{n}: {c} {v}')
    print(f'public placeholder check: {len(bad)} violations')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
