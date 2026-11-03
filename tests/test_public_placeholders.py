"""Public-placeholder scanner contracts (#725). Synthetic fixtures only."""
import json
import os
import subprocess
import sys
from pathlib import Path

import tools.check_public_placeholders as checker

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / 'tools' / 'check_public_placeholders.py'
CI_VARS = ('CI', 'GITHUB_ACTIONS', 'GITHUB_EVENT_PATH')


def run_checker(*args, cwd=ROOT, env=None):
    scrubbed = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    scrubbed.update(env or {})
    return subprocess.run([sys.executable, str(SCANNER), *args],
                          check=False, capture_output=True, text=True, cwd=cwd,
                          env=scrubbed)


def valid_id9(prefix):
    # smallest check digit making the Israeli-style checksum validate
    for d in range(10):
        if checker.checksum_valid(prefix + str(d)):
            return prefix + str(d)
    raise AssertionError(prefix)


def test_tree_is_clean_against_baseline():
    result = run_checker()
    assert result.returncode == 0, result.stdout


def test_every_persona_national_id_fails_the_checksum():
    personas = json.loads((ROOT / 'synthetic/personas.json').read_text(encoding='utf-8'))
    assert personas['personas']
    for p in personas['personas']:
        assert not checker.checksum_valid(p['national_id']), p


def test_persona_phones_use_reserved_forms():
    personas = json.loads((ROOT / 'synthetic/personas.json').read_text(encoding='utf-8'))
    for p in personas['personas']:
        assert checker.RESERVED_PHONE.fullmatch(p['phone'])
        assert checker.RESERVED_PHONE.fullmatch(p['phone_us'])


def make_repo(tmp_path, docs):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / '.repo-layout.yml').write_text('{}', encoding='utf-8')
    (tmp_path / 'docs').mkdir(parents=True)
    for name, text in docs.items():
        (tmp_path / 'docs' / name).write_text(text, encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    return tmp_path


def test_valid_checksum_id_flagged(tmp_path):
    # 9-digit value whose check digit validates (generated, not a real ID):
    good = '00000000' + str((10 - 0) % 10)  # 000000000 validates trivially
    repo = make_repo(tmp_path, {'a.md': f'call {good} now\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    repo = make_repo(tmp_path / 'b', {'a.md': 'no digits here\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_real_range_phone_flagged_and_reserved_forms_pass(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'dial +972-50-123-4567 or 050-123-4567\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    repo = make_repo(tmp_path / 'b', {'a.md': 'dial +999-266-298-3188 or +1-201-555-0123\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_structured_numeric_id_flagged_outside_personas(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'profile_id: "1234567" and union-42\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    repo = make_repo(tmp_path / 'b', {'a.md': 'profile_id: "990001"\n'})
    # no personas.json in the scratch repo -> persona allowlist empty -> flagged
    assert run_checker('--root', str(repo)).returncode == 1


def test_baseline_entry_passes_but_new_violation_fails(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    assert run_checker('--root', str(repo), '--write-baseline').returncode == 0
    assert run_checker('--root', str(repo)).returncode == 0
    (repo / 'docs' / 'b.md').write_text('call +972-50-123-4567\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1


def test_doc_shape_notation_is_not_an_id(tmp_path):
    # Convention examples like profile-99xxxx / union-98xxxx are shapes, not IDs.
    repo = make_repo(tmp_path, {'a.md': 'use profile-99xxxx / union-98xxxx shapes\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_allowlist_entry_requires_a_reason(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    import json as j
    path = repo / 'synthetic/public-corpus-baseline.json'
    data = j.loads(path.read_text(encoding='utf-8'))
    data['allowlist'] = [{'file': 'docs/c.md', 'line': 1, 'value': 'x', 'class': 'phone'}]
    path.write_text(j.dumps(data), encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1


def test_baseline_anchor_is_exact_line_and_value(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    (repo / 'docs' / 'a.md').write_text('\nid 000000000\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    # same value moved to line 2: the line-1 anchor no longer matches
    assert run_checker('--root', str(repo)).returncode == 1


# ---- detector bite: positive + negative fixtures per detector (#729 review) ----

def test_checksum_detector_beyond_all_zero(tmp_path):
    # Not phone-shaped (leading digit 3): only the checksum detector can flag it.
    good = valid_id9('30000012')
    assert good != '000000000' and checker.checksum_valid(good)
    repo = make_repo(tmp_path, {'a.md': f'id {good}\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert not checker.checksum_valid(bad)
    repo = make_repo(tmp_path / 'b', {'a.md': f'id {bad}\n'})  # checksum fails
    assert run_checker('--root', str(repo)).returncode == 0


def test_id8_unpadded_detector(tmp_path):
    good = valid_id9('03000034')
    unpadded = good[1:]  # 8-digit form; the scanner re-pads with 0
    assert len(unpadded) == 8 and unpadded[0] == '3'
    repo = make_repo(tmp_path, {'a.md': f'id {unpadded}\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    repo = make_repo(tmp_path / 'b', {'a.md': 'id 12345678\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_local_phone_separator_variants(tmp_path):
    for text in ('050-123-4567', '0501234567', '050 123 4567', '054-765-4321'):
        repo = make_repo(tmp_path / text.replace('/', '_'), {'a.md': f'dial {text}\n'})
        assert run_checker('--root', str(repo)).returncode == 1, text
    repo = make_repo(tmp_path / 'clean', {'a.md': 'version 0.5.0123 paragraph 4567\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_00_prefix_phone_flagged(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'dial 00972-50-123-4567\n'})
    assert run_checker('--root', str(repo)).returncode == 1
    repo = make_repo(tmp_path / 'b', {'a.md': 'no phone here\n'})
    assert run_checker('--root', str(repo)).returncode == 0


def test_persona_allowlist_exempts_only_persona_ids(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'profile-990001 ok, profile-1234567 not\n'})
    (repo / 'synthetic').mkdir()
    (repo / 'synthetic' / 'personas.json').write_text(json.dumps(
        {'personas': [{'profile_id': 'profile-990001', 'union_id': 'union-980001'}]}),
        encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1  # non-persona id flags
    (repo / 'docs' / 'a.md').write_text('profile-990001 and union-980001 only\n',
                                        encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 0


def test_baseline_value_change_fails(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\ncall +972-50-123-4567\n'})
    run_checker('--root', str(repo), '--write-baseline')
    assert run_checker('--root', str(repo)).returncode == 0
    path = repo / 'synthetic/public-corpus-baseline.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    phone = next(e for e in data['findings'] if e['class'] == 'phone')
    phone['value'] = '+972-50-999-9999'  # same file/line/class, changed value
    path.write_text(json.dumps(data), encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1


def test_tests_directory_is_scanned(tmp_path):
    repo = make_repo(tmp_path, {})
    (repo / 'tests').mkdir()
    (repo / 'tests' / 'test_x.py').write_text("PHONE = '+972-50-123-4567'\n",
                                              encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1


def test_full_length_structured_ids_flagged(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'profile-1000000000000000001 and '
                                        'union_id: "9800000000000000001"\n'})
    assert run_checker('--root', str(repo)).returncode == 1


def test_suffixless_text_files_scanned_binary_skipped(tmp_path):
    repo = make_repo(tmp_path, {})
    (repo / 'Makefile').write_text('echo +972-50-123-4567\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 1
    (repo / 'Makefile').write_text('echo hello\n', encoding='utf-8')
    (repo / 'blob').write_bytes(bytes([0, 159]) + b'dial 050-123-4567' + bytes([0]))
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo)).returncode == 0


# ---- CI baseline guards (#729 review) ----

def commit_all(repo, message):
    subprocess.run(['git', '-c', 'user.email=zz@zz.invalid', '-c', 'user.name=ZZ',
                    'commit', '-qm', message], cwd=repo, check=True)


def test_write_baseline_refused_in_ci(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    result = run_checker('--root', str(repo), '--write-baseline',
                         env={'CI': 'true'})
    assert result.returncode == 1
    assert not (repo / 'synthetic/public-corpus-baseline.json').exists()


def test_stale_baseline_entry_fails(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\ncall +972-50-123-4567\n'})
    run_checker('--root', str(repo), '--write-baseline')
    assert run_checker('--root', str(repo)).returncode == 0
    (repo / 'docs' / 'a.md').write_text('id 000000000\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    result = run_checker('--root', str(repo))
    assert result.returncode == 1
    assert 'stale baseline entry' in result.stdout


def test_pr_baseline_growth_needs_label(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base')
    base_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()
    (repo / 'docs' / 'b.md').write_text('call +972-50-123-4567\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)

    def event(labels):
        path = repo / 'event.json'
        path.write_text(json.dumps({'pull_request': {
            'base': {'sha': base_sha},
            'labels': [{'name': n} for n in labels]}}), encoding='utf-8')
        return {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_PATH': str(path)}

    result = run_checker('--root', str(repo), env=event([]))
    assert result.returncode == 1
    assert 'synthetic-baseline-grow' in result.stdout
    result = run_checker('--root', str(repo), env=event(['synthetic-baseline-grow']))
    assert result.returncode == 0, result.stdout


# ---- complete persona validation (#729 review) ----

def test_every_persona_value_is_synthetic():
    import re as re_
    persons = json.loads((ROOT / 'synthetic/personas.json').read_text(
        encoding='utf-8'))['personas']
    assert len(persons) >= 4
    keys = set()
    for p in persons:
        assert p['key'] not in keys
        keys.add(p['key'])
        for field in ('first_name', 'last_name', 'maiden_name'):
            assert re_.fullmatch(r'[A-Z][a-z]+-\d{4}', p[field]), (field, p[field])
        for field in ('he_first_name', 'he_last_name'):
            assert re_.fullmatch('זז-[A-Z][a-z]+-\\d{4}', p[field]), (field, p[field])
        assert re_.fullmatch(r'profile-9900\d\d', p['profile_id'])
        assert re_.fullmatch(r'union-9800\d\d', p['union_id'])
        assert re_.fullmatch(r'\d{9}', p['national_id'])
        assert not checker.checksum_valid(p['national_id'])
        assert checker.RESERVED_PHONE.fullmatch(p['phone'])
        assert checker.RESERVED_PHONE.fullmatch(p['phone_us'])
        assert set(p['invalidity']) == {'national_id', 'phone', 'phone_us'}
