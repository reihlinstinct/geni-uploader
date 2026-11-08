"""Keyed private-term scanner core contracts (#733 item B).

Synthetic only: every term comes from synthetic/personas.json (canonical
synthetic persona fields) and every digest is generated here from
PUBLIC_TEST_KEY. No real term, key or digest is committed, and no unkeyed
term hash appears anywhere.
"""
import ast
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tools.check_private_terms as checker

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / 'tools' / 'check_private_terms.py'

# PUBLIC, TEST-ONLY key. It is published here on purpose and must never be
# used for a real policy; the production key is a protected secret.
PUBLIC_TEST_KEY = b'public-test-key/geni-uploader/#733/not-a-secret'
OTHER_PUBLIC_TEST_KEY = b'other-public-test-key/geni-uploader/not-a-secret'
VERSION = 'synthetic-v1'

PERSONAS = json.loads((ROOT / 'synthetic' / 'personas.json').read_text(encoding='utf-8'))
PRIMARY = PERSONAS['personas'][0]
SPOUSE = PERSONAS['personas'][1]
TERM = PRIMARY['first_name']            # two tokens, e.g. word-digits
HE_TERM = PRIMARY['he_first_name']      # Hebrew prefix plus the Latin parts
OTHER_TERM = SPOUSE['last_name']


def policy_doc(terms, key=PUBLIC_TEST_KEY, version=VERSION, exceptions=None):
    doc = {
        'schema': 1,
        'algorithm': 'hmac-sha256',
        'normalization': 1,
        'policy_version': version,
        'entries': [{'length': len(checker.tokens(t)),
                     'digest': checker.term_digest(key, version, t).hex()}
                    for t in terms],
    }
    if exceptions is not None:
        doc['exceptions'] = exceptions
    return doc


def write_policy(tmp_path, doc, raw=None):
    path = tmp_path / 'policy.json'
    path.write_text(raw if raw is not None else json.dumps(doc), encoding='utf-8')
    return path


def make_tree(tmp_path, files):
    root = tmp_path / 'candidate'
    root.mkdir()
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding='utf-8')
    return root


def run(monkeypatch, capsys, policy, root, *extra, key=PUBLIC_TEST_KEY):
    if key is None:
        monkeypatch.delenv('PRIVATE_TERMS_KEY', raising=False)
    else:
        monkeypatch.setenv('PRIVATE_TERMS_KEY', key.decode('utf-8'))
    code = checker.main(['--policy', str(policy), '--root', str(root), *extra])
    out, err = capsys.readouterr()
    return code, out, err


def secret_forms(terms, key=PUBLIC_TEST_KEY):
    """Every value that must never appear in output."""
    forms = {key.decode('utf-8')}
    for term in terms:
        forms.add(term)
        forms.add(checker.normalize(term))
        forms.update(tok for tok in checker.tokens(term) if len(tok) > 2)
        forms.add(checker.term_digest(key, VERSION, term).hex())
        forms.add(checker.term_digest(key, VERSION, term).hex()[:16])
    return forms


def assert_value_free(text, terms):
    folded = text.casefold()
    for form in secret_forms(terms):
        assert form.casefold() not in folded, 'value leaked into output'


# --- normalization (version 1) -------------------------------------------

def test_normalize_applies_nfc():
    assert checker.normalize('e\u0301') == checker.normalize('\u00e9') == '\u00e9'


def test_normalize_case_folds():
    assert checker.tokens(TERM.upper()) == checker.tokens(TERM.lower())
    assert checker.normalize('STRASSE') == checker.normalize('stra\u00dfe')


def test_normalize_strips_hebrew_points_and_cantillation():
    pointed = '\u05d6\u05b8\u05d6\u0591\u05bc'
    assert checker.normalize(pointed) == '\u05d6\u05d6'
    for cp in checker.HEBREW_MARKS:
        assert checker.normalize('\u05d6' + chr(cp) + '\u05d6') == '\u05d6\u05d6'


def test_normalize_maps_hebrew_final_letters():
    finals = '\u05da\u05dd\u05df\u05e3\u05e5'
    bases = '\u05db\u05de\u05e0\u05e4\u05e6'
    assert checker.normalize(finals) == bases


def test_hebrew_punctuation_stays_a_boundary():
    # maqaf, paseq, sof pasuq and geresh are punctuation, not stripped marks
    for cp in (0x05BE, 0x05C0, 0x05C3, 0x05F3):
        assert checker.tokens('\u05d6\u05d6' + chr(cp) + '\u05d6\u05d6') == [
            '\u05d6\u05d6', '\u05d6\u05d6']


def test_tokens_split_on_underscore_and_punctuation():
    assert checker.tokens('ab_cd-ef.gh') == ['ab', 'cd', 'ef', 'gh']


# --- keyed digest and domain separation -------------------------------------

def test_digest_message_format_is_pinned():
    seq = checker.tokens(TERM)
    expected = hmac.new(
        PUBLIC_TEST_KEY,
        b'geni-uploader/private-terms/v1\x00n1\x00' + VERSION.encode()
        + b'\x00' + str(len(seq)).encode() + b'\x00' + '\x1f'.join(seq).encode(),
        'sha256').digest()
    assert checker.term_digest(PUBLIC_TEST_KEY, VERSION, TERM) == expected
    bare = hmac.new(PUBLIC_TEST_KEY, '\x1f'.join(seq).encode(), 'sha256').digest()
    assert checker.term_digest(PUBLIC_TEST_KEY, VERSION, TERM) != bare


def test_digest_separates_policy_version_length_and_key():
    seq = checker.tokens(TERM)
    base = checker.sequence_digest(PUBLIC_TEST_KEY, VERSION, seq)
    assert base != checker.sequence_digest(PUBLIC_TEST_KEY, 'synthetic-v2', seq)
    assert base != checker.sequence_digest(OTHER_PUBLIC_TEST_KEY, VERSION, seq)
    assert (checker.sequence_digest(PUBLIC_TEST_KEY, VERSION, [''.join(seq)])
            != checker.sequence_digest(PUBLIC_TEST_KEY, VERSION, seq))


def test_policy_version_mismatch_gives_no_match(tmp_path, monkeypatch, capsys):
    doc = policy_doc([TERM], version='synthetic-v1')
    doc['policy_version'] = 'synthetic-v2'
    root = make_tree(tmp_path, {'a.md': TERM + '\n'})
    code, out, _ = run(monkeypatch, capsys, write_policy(tmp_path, doc), root)
    assert code == 0, out


# --- matching ------------------------------------------------------------

def test_match_blocks_with_fixed_value_free_result(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'docs/a.md': 'intro\nsee ' + TERM.upper() + ' here\n'})
    code, out, err = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])), root)
    assert code == 1
    assert out == f'private-terms: blocked scanner=1 policy={VERSION}\n'
    assert 'docs/a.md' not in out
    assert_value_free(out + err, [TERM])


def test_findings_print_position_and_category_only(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {
        'docs/b.md': 'x\n\nalpha ' + TERM + '\n',
        'docs/a.md': OTHER_TERM.lower() + '\n',
    })
    policy = write_policy(tmp_path, policy_doc([TERM, OTHER_TERM]))
    code, out, err = run(monkeypatch, capsys, policy, root, '--findings')
    assert code == 1
    assert out.splitlines() == [
        'docs/a.md:1:1: private-term',
        'docs/b.md:3:2: private-term',
        f'private-terms: blocked scanner=1 policy={VERSION}',
    ]
    assert_value_free(out + err, [TERM, OTHER_TERM])


def test_output_is_deterministic(tmp_path, monkeypatch, capsys):
    files = {f'z/{n}.md': ('pad ' * n) + TERM + '\n' for n in range(5)}
    root = make_tree(tmp_path, files)
    policy = write_policy(tmp_path, policy_doc([TERM]))
    first = run(monkeypatch, capsys, policy, root, '--findings')
    second = run(monkeypatch, capsys, policy, root, '--findings')
    assert first == second
    lines = first[1].splitlines()[:-1]
    assert lines == sorted(lines) and len(lines) == 5


def test_hebrew_variant_with_points_and_case_matches(tmp_path, monkeypatch, capsys):
    pointed = HE_TERM[0] + '\u05b8' + HE_TERM[1:]
    root = make_tree(tmp_path, {'a.md': pointed.upper() + '\n'})
    code, out, _ = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([HE_TERM])),
                       root, '--findings')
    assert code == 1
    assert out.splitlines()[0] == 'a.md:1:1: private-term'


def test_whole_tokens_only_no_substring_match(tmp_path, monkeypatch, capsys):
    parts = checker.tokens(TERM)
    root = make_tree(tmp_path, {'a.md': f'x{parts[0]}y {parts[1]}\n{parts[0]}q {parts[1]}\n'})
    code, out, _ = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])), root)
    assert code == 0, out


def test_multi_token_term_needs_consecutive_tokens(tmp_path, monkeypatch, capsys):
    parts = checker.tokens(TERM)
    policy = write_policy(tmp_path, policy_doc([TERM]))
    apart = make_tree(tmp_path, {'a.md': f'{parts[0]} and {parts[1]}\n'})
    assert run(monkeypatch, capsys, policy, apart)[0] == 0
    wrapped = tmp_path / 'wrapped'
    wrapped.mkdir()
    (wrapped / 'b.md').write_text(f'text {parts[0]}\n  {parts[1]} more\n', encoding='utf-8')
    code, out, _ = run(monkeypatch, capsys, policy, wrapped, '--findings')
    assert code == 1
    assert out.splitlines()[0] == 'b.md:1:2: private-term'


def test_invalid_utf8_bytes_are_boundaries_not_skips(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'blob.bin': b'\x89\xff\x00' + TERM.encode() + b'\xfe\x00'})
    code, _, _ = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])), root)
    assert code == 1


def test_path_names_are_scanned_and_redacted(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n',
                                'docs/' + TERM + '.md': TERM + '\n'})
    code, out, err = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])),
                         root, '--findings')
    assert code == 1
    assert out.splitlines()[:2] == ['<file #2>:0:2: private-term',
                                    '<file #2>:1:1: private-term']
    assert_value_free(out + err, [TERM])


def test_wrong_key_gives_no_match(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': TERM + '\n'})
    policy = write_policy(tmp_path, policy_doc([TERM]))
    code, out, _ = run(monkeypatch, capsys, policy, root, key=OTHER_PUBLIC_TEST_KEY)
    assert code == 0, out
    assert run(monkeypatch, capsys, policy, root)[0] == 1


def test_compare_digest_decides_equality(tmp_path, monkeypatch, capsys):
    calls = []

    def never_equal(a, b):
        calls.append((len(a), len(b)))
        return False

    root = make_tree(tmp_path, {'a.md': TERM + '\n'})
    policy = write_policy(tmp_path, policy_doc([TERM]))
    monkeypatch.setattr(checker.hmac, 'compare_digest', never_equal)
    code, _, _ = run(monkeypatch, capsys, policy, root)
    assert code == 0
    assert calls and all(pair == (32, 32) for pair in calls)


# --- fail closed --------------------------------------------------------------

def test_missing_key_is_not_evaluated(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    policy = write_policy(tmp_path, policy_doc([TERM]))
    code, out, err = run(monkeypatch, capsys, policy, root, key=None)
    assert code == 2 and out == ''
    assert err == 'private-terms: not evaluated: key missing (PRIVATE_TERMS_KEY unset or empty)\n'
    code, out, err = run(monkeypatch, capsys, policy, root, key=b'')
    assert code == 2 and 'not evaluated' in err


def test_short_key_is_not_evaluated(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    policy = write_policy(tmp_path, policy_doc([TERM]))
    short = b'short-public-test-key'
    code, out, err = run(monkeypatch, capsys, policy, root, key=short)
    assert code == 2 and out == ''
    assert err == 'private-terms: not evaluated: key shorter than 32 bytes\n'
    assert short.decode() not in err


def test_missing_policy_is_not_evaluated(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    code, out, err = run(monkeypatch, capsys, tmp_path / 'absent.json', root)
    assert code == 2 and out == ''
    assert err == 'private-terms: not evaluated: policy file missing or unreadable\n'


def _mutate(doc, path, value):
    target = doc
    for step in path[:-1]:
        target = target[step]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value


EXC = {'path': 'a.md', 'line': 1, 'token': 1, 'length': 2, 'binding': '0' * 64,
       'reason': 'synthetic test exception', 'expires': '2099-01-01'}

SCHEMA_CASES = {
    'unknown top-level field': (('extra',), 1),
    'missing entries': (('entries',), KeyError),
    'schema version 2': (('schema',), 2),
    'schema as bool': (('schema',), True),
    'algorithm': (('algorithm',), 'sha256'),
    'normalization version 2': (('normalization',), 2),
    'policy_version shape': (('policy_version',), 'bad version'),
    'empty entries': (('entries',), []),
    'unknown entry field': (('entries', 0, 'term'), 'x'),
    'missing entry digest': (('entries', 0, 'digest'), KeyError),
    'uppercase digest': (('entries', 0, 'digest'), 'A' * 64),
    'short digest': (('entries', 0, 'digest'), 'a' * 63),
    'length zero': (('entries', 0, 'length'), 0),
    'length over cap': (('entries', 0, 'length'), 9),
    'length as bool': (('entries', 0, 'length'), True),
    'exceptions not a list': (('exceptions',), {}),
    'exception without reason': (('exceptions',), [{**EXC, 'reason': ' '}]),
    'exception bad expiry': (('exceptions',), [{**EXC, 'expires': '2099-02-30'}]),
    'exception unknown field': (('exceptions',), [{**EXC, 'note': 'x'}]),
    'exception missing expiry': (('exceptions',), [{k: v for k, v in EXC.items()
                                                    if k != 'expires'}]),
    'duplicate exception': (('exceptions',), [EXC, dict(EXC)]),
}


@pytest.mark.parametrize('case', sorted(SCHEMA_CASES))
def test_policy_schema_is_validated(case, tmp_path, monkeypatch, capsys):
    doc = policy_doc([TERM])
    path, value = SCHEMA_CASES[case]
    _mutate(doc, path, value)
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    code, out, err = run(monkeypatch, capsys, write_policy(tmp_path, doc), root)
    assert code == 2, case
    assert out == '' and err.startswith('private-terms: not evaluated: policy')


def test_policy_duplicate_json_key_and_entry_rejected(tmp_path, monkeypatch, capsys):
    doc = policy_doc([TERM])
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    raw = json.dumps(doc)[:-1] + ', "schema": 1}'
    code, _, err = run(monkeypatch, capsys, write_policy(tmp_path, None, raw), root)
    assert code == 2 and 'duplicate JSON key' in err
    doc['entries'].append(dict(doc['entries'][0]))
    code, _, err = run(monkeypatch, capsys, write_policy(tmp_path, doc), root)
    assert code == 2 and 'duplicate entry' in err
    raw = json.dumps(policy_doc([TERM])).replace('"schema": 1', '"schema": NaN')
    code, _, err = run(monkeypatch, capsys, write_policy(tmp_path, None, raw), root)
    assert code == 2


@pytest.mark.parametrize('cap, files', [
    ('MAX_FILE_BYTES', {'a.md': 'x' * 65}),
    ('MAX_TOTAL_BYTES', {'a.md': 'x' * 40, 'b.md': 'y' * 40}),
    ('MAX_FILES', {f'{n:02d}.md': 'x' for n in range(65)}),
    ('MAX_TOKENS', {'a.md': 'w ' * 70}),
])
def test_caps_stop_the_scan(cap, files, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(checker, cap, 64)
    root = make_tree(tmp_path, files)
    code, out, err = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])), root)
    assert code == 2 and out == '' and 'cap exceeded' in err


def test_policy_caps_stop_the_scan(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    policy = write_policy(tmp_path, policy_doc([TERM, OTHER_TERM]))
    monkeypatch.setattr(checker, 'MAX_ENTRIES', 1)
    code, _, err = run(monkeypatch, capsys, policy, root)
    assert code == 2 and 'entry cap exceeded' in err
    monkeypatch.setattr(checker, 'MAX_ENTRIES', 10)
    monkeypatch.setattr(checker, 'MAX_POLICY_BYTES', 16)
    code, _, err = run(monkeypatch, capsys, policy, root)
    assert code == 2 and 'byte cap' in err


def test_symlink_in_candidate_stops(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    outside = tmp_path / 'outside.md'
    outside.write_text(TERM + '\n', encoding='utf-8')
    (root / 'link.md').symlink_to(outside)
    code, out, err = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])), root)
    assert code == 2 and out == '' and 'symlink' in err


@pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0,
                    reason='root reads files regardless of permissions')
def test_unreadable_file_stops(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n', 'b.md': 'clean\n'})
    (root / 'b.md').chmod(0)
    try:
        code, out, err = run(monkeypatch, capsys,
                             write_policy(tmp_path, policy_doc([TERM])), root)
    finally:
        (root / 'b.md').chmod(0o644)
    assert code == 2 and out == '' and 'unreadable file' in err


def test_git_directory_is_never_read(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n', '.git/config': TERM + '\n',
                                'sub/.git': TERM + '\n'})
    code, out, _ = run(monkeypatch, capsys, write_policy(tmp_path, policy_doc([TERM])),
                       root, '--findings')
    assert code == 1
    assert out.splitlines()[0] == 'sub/.git:1:1: private-term'


# --- exact-tree binding -----------------------------------------------------

def git_tree(root):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    for args in (['init', '-q'], ['add', '-A']):
        subprocess.run(['git', *args], cwd=root, check=True, env=env)
    return subprocess.run(['git', 'write-tree'], cwd=root, check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def test_expect_tree_binds_the_exact_candidate(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n', 'docs/n/b.md': 'also clean\n',
                                'docs.md': 'x\n', 'run.sh': '#!/bin/sh\n'})
    (root / 'run.sh').chmod(0o755)
    tree = git_tree(root)
    policy = write_policy(tmp_path, policy_doc([TERM]))
    code, out, _ = run(monkeypatch, capsys, policy, root, '--expect-tree', tree)
    assert code == 0
    assert out == f'private-terms: clean scanner=1 policy={VERSION} tree={tree}\n'


def test_stale_or_wrong_tree_is_not_evaluated(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': 'clean\n'})
    tree = git_tree(root)
    policy = write_policy(tmp_path, policy_doc([TERM]))
    (root / 'a.md').write_text('clean, edited after binding\n', encoding='utf-8')
    code, out, err = run(monkeypatch, capsys, policy, root, '--expect-tree', tree)
    assert code == 2 and out == '' and 'does not match' in err
    code, _, err = run(monkeypatch, capsys, policy, root, '--expect-tree', 'HEAD')
    assert code == 2 and 'tree id' in err


# --- exceptions -----------------------------------------------------------

def exception_for(root, rel, line, token, length, expires='2099-01-01'):
    content = (root / rel).read_bytes()
    binding = checker.exception_binding(PUBLIC_TEST_KEY, VERSION, rel, line, token,
                                        length, content)
    return {'path': rel, 'line': line, 'token': token, 'length': length,
            'binding': binding.hex(), 'reason': 'synthetic reviewed exception',
            'expires': expires}


def test_exception_suppresses_only_its_exact_bound_position(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': f'ok {TERM}\nok {TERM}\n{TERM}\n'})
    exc = exception_for(root, 'a.md', 1, 2, 2)
    policy = write_policy(tmp_path, policy_doc([TERM], exceptions=[exc]))
    code, out, _ = run(monkeypatch, capsys, policy, root, '--findings')
    assert code == 1
    assert out.splitlines()[:-1] == ['a.md:2:2: private-term', 'a.md:3:1: private-term']


def test_exception_is_content_bound(tmp_path, monkeypatch, capsys):
    root = make_tree(tmp_path, {'a.md': f'ok {TERM}\n'})
    exc = exception_for(root, 'a.md', 1, 2, 2)
    policy = write_policy(tmp_path, policy_doc([TERM], exceptions=[exc]))
    assert run(monkeypatch, capsys, policy, root)[0] == 0
    (root / 'a.md').write_text(f'ok {TERM}\nmore\n', encoding='utf-8')
    assert run(monkeypatch, capsys, policy, root)[0] == 1


def test_expired_exception_no_longer_applies(tmp_path, monkeypatch, capsys):
    import datetime
    root = make_tree(tmp_path, {'a.md': f'ok {TERM}\n'})
    exc = exception_for(root, 'a.md', 1, 2, 2, expires='2030-06-01')
    policy = write_policy(tmp_path, policy_doc([TERM], exceptions=[exc]))
    monkeypatch.setattr(checker, '_today', lambda: datetime.date(2030, 6, 1))
    assert run(monkeypatch, capsys, policy, root)[0] == 0
    monkeypatch.setattr(checker, '_today', lambda: datetime.date(2030, 6, 2))
    assert run(monkeypatch, capsys, policy, root)[0] == 1


# --- candidate is data only ---------------------------------------------------

def test_candidate_scripts_never_execute(tmp_path):
    marker = tmp_path / 'executed'
    payload = f'open({str(marker)!r}, "w").write("ran")\n'
    root = make_tree(tmp_path, {
        'hmac.py': payload, 'json.py': payload, 'unicodedata.py': payload,
        'sitecustomize.py': payload, 'conftest.py': payload,
        'tools/check_private_terms.py': payload, 'a.md': TERM + '\n',
        '.git/hooks/post-checkout': f'#!/bin/sh\ntouch {marker}\n',
        '.git/config': f'[core]\n\tfsmonitor = touch {marker}\n',
    })
    policy = write_policy(tmp_path, policy_doc([TERM]))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'PYTHON'))}
    env['PRIVATE_TERMS_KEY'] = PUBLIC_TEST_KEY.decode()
    result = subprocess.run([sys.executable, str(SCANNER), '--policy', str(policy),
                             '--root', '.'], cwd=root, env=env, check=False,
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    assert not marker.exists()


def test_scanner_imports_only_fixed_stdlib_and_no_exec():
    tree = ast.parse(SCANNER.read_text(encoding='utf-8'))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {'exec', 'eval', 'compile', '__import__'}
    assert imported == {'__future__', 'argparse', 'datetime', 'hashlib', 'hmac', 'json',
                        'os', 're', 'stat', 'sys', 'unicodedata'}


def test_cli_clean_tree_subprocess(tmp_path):
    root = make_tree(tmp_path, {'a.md': 'nothing private here\n'})
    policy = write_policy(tmp_path, policy_doc([TERM]))
    env = dict(os.environ, PRIVATE_TERMS_KEY=PUBLIC_TEST_KEY.decode())
    result = subprocess.run([sys.executable, str(SCANNER), '--policy', str(policy),
                             '--root', str(root)], env=env, check=False,
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout == f'private-terms: clean scanner=1 policy={VERSION}\n'
    assert result.stderr == ''
