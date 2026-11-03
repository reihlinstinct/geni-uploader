"""Public-placeholder scanner contracts (#725). Synthetic fixtures only."""
import json
import subprocess
import sys
from pathlib import Path

import tools.check_public_placeholders as checker

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / 'tools' / 'check_public_placeholders.py'


def run_checker(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(SCANNER), *args],
                          check=False, capture_output=True, text=True, cwd=cwd)


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
