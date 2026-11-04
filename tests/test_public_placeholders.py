"""Public-placeholder scanner contracts (#725). Synthetic fixtures only."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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

    def event(labels, sha=base_sha):
        path = repo / 'event.json'
        path.write_text(json.dumps({'pull_request': {
            'base': {'sha': sha},
            'labels': [{'name': n} for n in labels]}}), encoding='utf-8')
        return {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_PATH': str(path),
                'GITHUB_BASE_REF': 'master'}

    result = run_checker('--root', str(repo), env=event([]))
    assert result.returncode == 1
    assert 'synthetic-baseline-grow' in result.stdout
    result = run_checker('--root', str(repo), env=event(['synthetic-baseline-grow']))
    assert result.returncode == 0, result.stdout


# ---- complete persona validation (#729 review) ----

import copy as _copy
import re as _re

# Approved synthetic persona values, pinned literally: adding or editing a
# persona requires updating this contract in the same reviewed change.
EXPECTED_PERSONAS = [
    {'key': 'primary', 'first_name': 'Abqef-2465', 'last_name': 'Torlin-3352',
     'he_first_name': 'זז-Abqef-2465', 'he_last_name': 'זז-Torlin-3352',
     'maiden_name': 'Droban-3656', 'phone': '+999-266-298-3188',
     'phone_us': '+1-255-555-0177', 'national_id': '488127359',
     'profile_id': 'profile-990001', 'union_id': 'union-980001'},
    {'key': 'spouse', 'first_name': 'Veshka-3935', 'last_name': 'Droban-6120',
     'he_first_name': 'זז-Veshka-3935', 'he_last_name': 'זז-Droban-6120',
     'maiden_name': 'Sarpia-6257', 'phone': '+999-565-859-6567',
     'phone_us': '+1-664-555-0136', 'national_id': '381014388',
     'profile_id': 'profile-990002', 'union_id': 'union-980002'},
    {'key': 'parent', 'first_name': 'Kelmut-4714', 'last_name': 'Sarpia-2856',
     'he_first_name': 'זז-Kelmut-4714', 'he_last_name': 'זז-Sarpia-2856',
     'maiden_name': 'Vindar-7524', 'phone': '+999-473-141-2392',
     'phone_us': '+1-696-555-0126', 'national_id': '394409153',
     'profile_id': 'profile-990003', 'union_id': 'union-980003'},
    {'key': 'child', 'first_name': 'Olmek-8128', 'last_name': 'Vindar-4785',
     'he_first_name': 'זז-Olmek-8128', 'he_last_name': 'זז-Vindar-4785',
     'maiden_name': 'Torlin-8841', 'phone': '+999-117-763-9099',
     'phone_us': '+1-369-555-0115', 'national_id': '281618195',
     'profile_id': 'profile-990004', 'union_id': 'union-980004'},
]

PERSONA_FIELDS = set(EXPECTED_PERSONAS[0]) | {'invalidity'}


def validate_personas(persons):
    """Every persona value must be provably synthetic; raises AssertionError."""
    assert len(persons) >= 4, 'persona set shrunk'
    keys, profiles, unions = set(), set(), set()
    for p in persons:
        assert set(p) == PERSONA_FIELDS, set(p) ^ PERSONA_FIELDS
        assert p['key'] not in keys, 'duplicate key'
        keys.add(p['key'])
        assert p['profile_id'] not in profiles, 'duplicate profile_id'
        profiles.add(p['profile_id'])
        assert p['union_id'] not in unions, 'duplicate union_id'
        unions.add(p['union_id'])
        for field in ('first_name', 'last_name', 'maiden_name'):
            # Invented syllable token + tag digits; real-name-shaped values fail.
            assert _re.fullmatch(r'(Abqef|Torlin|Droban|Veshka|Sarpia|Kelmut|'
                                 r'Vindar|Olmek)-\d{4}', p[field]), (field, p[field])
        for field in ('he_first_name', 'he_last_name'):
            assert p[field].startswith('זז-'), (field, p[field])
            latin = p[field][len('זז-'):]
            assert _re.fullmatch(r'(Abqef|Torlin|Droban|Veshka|Sarpia|Kelmut|'
                                 r'Vindar|Olmek)-\d{4}', latin), (field, p[field])
        assert _re.fullmatch(r'profile-9900\d\d', p['profile_id'])
        assert _re.fullmatch(r'union-9800\d\d', p['union_id'])
        assert _re.fullmatch(r'\d{9}', p['national_id'])
        assert not checker.checksum_valid(p['national_id'])
        assert _re.fullmatch(r'\+999-\d{3}-\d{3}-\d{4}', p['phone'])
        assert checker.RESERVED_PHONE.fullmatch(p['phone'])
        assert _re.fullmatch(r'\+1-\d{3}-555-01\d\d', p['phone_us'])
        assert checker.RESERVED_PHONE.fullmatch(p['phone_us'])
        assert set(p['invalidity']) == {'national_id', 'phone', 'phone_us'}


def personas_file():
    return json.loads((ROOT / 'synthetic/personas.json').read_text(
        encoding='utf-8'))['personas']


def test_personas_match_the_approved_values():
    actual = [{k: v for k, v in p.items() if k != 'invalidity'}
              for p in personas_file()]
    assert actual == EXPECTED_PERSONAS


def test_every_persona_value_is_synthetic():
    validate_personas(personas_file())


def test_persona_validation_rejects_mutations():
    base = personas_file()
    for mutate in (
        lambda p: p[0].update(first_name='David-1234'),       # real-name shape
        lambda p: p[0].update(first_name='Abqef2465'),        # missing tag digits
        lambda p: p[1].update(profile_id=p[0]['profile_id']),  # duplicate id
        lambda p: p[2].update(union_id=p[0]['union_id']),      # duplicate id
        lambda p: p[0].update(phone=p[0]['phone_us']),         # field swapped
        lambda p: p[0].update(key=p[1]['key']),                # duplicate key
    ):
        mutant = _copy.deepcopy(base)
        mutate(mutant)
        try:
            validate_personas(mutant)
        except AssertionError:
            continue
        raise AssertionError(f'mutant survived: {mutate}')


# ---- CI baseline growth guard (#729 review round 2) ----

def _guard_env(repo, labels, base_sha):
    ev = repo / 'event.json'
    ev.write_text(json.dumps({'pull_request': {
        'base': {'sha': base_sha},
        'labels': [{'name': n} for n in labels]}}), encoding='utf-8')
    return {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_PATH': str(ev),
            'GITHUB_BASE_REF': 'master'}


def _head(repo):
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def test_growth_guard_no_baseline_at_base(tmp_path):
    # Baseline absent at base = empty: the initial introduction is growth.
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base')
    base_sha = _head(repo)
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    env = _guard_env(repo, [], base_sha)
    result = run_checker('--root', str(repo), env=env)
    assert result.returncode == 1
    assert 'synthetic-baseline-grow' in result.stdout
    env = _guard_env(repo, ['synthetic-baseline-grow'], base_sha)
    assert run_checker('--root', str(repo), env=env).returncode == 0


def test_growth_guard_fails_closed_on_missing_base_object(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base')
    env = _guard_env(repo, [], '0' * 40)
    result = run_checker('--root', str(repo), env=env)
    assert result.returncode == 1
    assert 'unreadable' in result.stdout


def test_growth_guard_fails_closed_without_pr_payload(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    env = {'GITHUB_ACTIONS': 'true', 'GITHUB_BASE_REF': 'master'}
    result = run_checker('--root', str(repo), env=env)
    assert result.returncode == 1
    assert 'payload' in result.stdout


def test_growth_guard_covers_allowlist_moves_and_additions(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\ncall +972-50-123-4567\n'})
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base')
    base_sha = _head(repo)
    path = repo / 'synthetic/public-corpus-baseline.json'

    # Moving an entry findings -> allowlist (with reason) is not growth.
    data = json.loads(path.read_text(encoding='utf-8'))
    moved = data['findings'].pop()
    moved['reason'] = 'documented example kept intentionally'
    data['allowlist'] = [moved]
    path.write_text(json.dumps(data), encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    assert run_checker('--root', str(repo), env=_guard_env(repo, [], base_sha)).returncode == 0
    # Adding a NEW allowlist entry is growth and needs the label.
    data = json.loads(path.read_text(encoding='utf-8'))
    data['allowlist'].append({'file': 'docs/c.md', 'line': 1,
                              'value': '+972-50-000-0000', 'class': 'phone',
                              'reason': 'new grandfathered example'})
    path.write_text(json.dumps(data), encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    result = run_checker('--root', str(repo), env=_guard_env(repo, [], base_sha))
    assert result.returncode == 1
    assert 'synthetic-baseline-grow' in result.stdout


def test_growth_guard_fetches_base_in_shallow_checkout(tmp_path):
    # Mirror the real workflow: the checkout is shallow (fetch-depth 1).
    origin = make_repo(tmp_path / 'origin', {'a.md': 'id 000000000\n'})
    run_checker('--root', str(origin), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=origin, check=True)
    commit_all(origin, 'base')
    base_sha = _head(origin)
    (origin / 'docs' / 'b.md').write_text('call +972-50-123-4567\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=origin, check=True)
    commit_all(origin, 'pr head')
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', '--depth=1', f'file://{origin}',
                    str(clone)], check=True)
    env = _guard_env(clone, [], base_sha)
    # New phone is not in the baseline: violation (base fetched explicitly).
    result = run_checker('--root', str(clone), env=env)
    assert result.returncode == 1
    assert 'placeholder violation' in result.stdout


def test_intl_phone_space_separated_flagged(tmp_path):
    # International form with spaces: the [d -] character class must allow ' '.
    repo = make_repo(tmp_path, {'a.md': 'dial +972 50 123 4567\n'})
    assert run_checker('--root', str(repo)).returncode == 1


def test_growth_guard_base_allowlist_entries_not_growth(tmp_path):
    # An entry that lives in the BASE baseline's allowlist (with a reason) and
    # stays put is not growth; the guard must compare against the union.
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    path = repo / 'synthetic/public-corpus-baseline.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    moved = data['findings'].pop()
    moved['reason'] = 'documented example kept intentionally'
    data['allowlist'] = [moved]
    path.write_text(json.dumps(data), encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base with allowlist')
    base_sha = _head(repo)
    env = _guard_env(repo, [], base_sha)
    assert run_checker('--root', str(repo), env=env).returncode == 0


def test_growth_guard_clean_error_on_corrupt_base_json(tmp_path):
    # A syntactically corrupt baseline at base fails closed with a clean
    # error, not a traceback (#735).
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    run_checker('--root', str(repo), '--write-baseline')
    path = repo / 'synthetic/public-corpus-baseline.json'
    valid = path.read_text(encoding='utf-8')
    path.write_text('{not json', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base with corrupt baseline')
    base_sha = _head(repo)
    # The current-side baseline is valid again (not committed).
    path.write_text(valid, encoding='utf-8')
    env = _guard_env(repo, [], base_sha)
    result = run_checker('--root', str(repo), env=env)
    assert result.returncode == 1
    assert 'not valid JSON' in result.stdout
    assert 'Traceback' not in result.stderr


def test_growth_guard_tolerates_null_labels(tmp_path):
    # An event payload with "labels": null must not crash the guard (#735).
    repo = make_repo(tmp_path, {'a.md': 'id 000000000\n'})
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'base')
    base_sha = _head(repo)
    run_checker('--root', str(repo), '--write-baseline')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    ev = repo / 'event.json'
    ev.write_text(json.dumps({'pull_request': {
        'base': {'sha': base_sha}, 'labels': None}}), encoding='utf-8')
    env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_PATH': str(ev),
           'GITHUB_BASE_REF': 'master'}
    result = run_checker('--root', str(repo), env=env)
    assert result.returncode == 1  # growth (empty base) without the label
    assert 'synthetic-baseline-grow' in result.stdout
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('value', ['{not json', '[]'])
def test_current_baseline_malformed_fails_cleanly(tmp_path, value):
    repo = make_repo(tmp_path, {'a.md': 'ZZ safe fixture\n'})
    path = repo / 'synthetic/public-corpus-baseline.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(value, encoding='utf-8')
    result = run_checker('--root', str(repo))
    assert result.returncode == 1
    assert 'current baseline' in result.stdout
    assert 'Traceback' not in result.stderr


def test_base_baseline_wrong_type_fails_cleanly(tmp_path):
    repo = make_repo(tmp_path, {'a.md': 'ZZ safe fixture\n'})
    run_checker('--root', str(repo), '--write-baseline')
    path = repo / 'synthetic/public-corpus-baseline.json'
    valid = path.read_text(encoding='utf-8')
    path.write_text('[]', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    commit_all(repo, 'wrong-type base')
    base_sha = _head(repo)
    path.write_text(valid, encoding='utf-8')
    result = run_checker('--root', str(repo), env=_guard_env(repo, [], base_sha))
    assert result.returncode == 1
    assert 'base baseline must be a JSON object' in result.stdout
    assert 'Traceback' not in result.stderr
