import copy
import json
import socket

import pytest

import parent_plan as p
from people_core import Blocked
from tests.test_parent_runner import inputs

PINS = {'data_sha': 'a'*40, 'workflow_sha': 'b'*40, 'image_digest': 'sha256:'+'c'*64}


def test_exact_two_parent_proposal_no_network(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('network forbidden')
    monkeypatch.setattr(socket, 'socket', deny)
    data, _ = inputs(True)
    for parent in data['parents']: parent['gender'] = 'male'
    result = p.proposal(data, PINS)
    assert p.verify_proposal(result) == result['proposal_hash']
    assert len(result['entries']) == 2 and result['creation_enabled'] is False
    assert result['approval_grants_write'] is False and result['live_checks_performed'] is False
    assert all(e['duplicate_status'] == 'not_checked' for e in result['entries'])
    assert result['entries'][0]['proposed_payload']['names'] == data['parents'][0]['names']
    with pytest.raises(Blocked): p.apply(result['proposal_hash'])


@pytest.mark.parametrize('change', ['payload', 'owner', 'pin', 'enable', 'blockers'])
def test_changed_plan_hash_cannot_verify(change):
    data, _ = inputs()
    data['parents'][0]['gender'] = 'female'
    value = p.proposal(data, PINS)
    if change == 'payload': value['entries'][0]['proposed_payload']['public'] = True
    if change == 'owner': value['owner']['node'] = '99555'
    if change == 'pin': value['pins']['data_sha'] = 'd'*40
    if change == 'enable': value['creation_enabled'] = True
    if change == 'blockers': value['blockers'] = []
    with pytest.raises(Blocked): p.verify_proposal(value)


@pytest.mark.parametrize('change', ['missing_he', 'missing_en', 'unknown_gender', 'third', 'birthplace'])
def test_incomplete_or_out_of_scope_fields_block(change):
    data, _ = inputs()
    data['parents'][0]['gender'] = 'female'
    if change == 'missing_he': del data['parents'][0]['names']['he']
    if change == 'missing_en': del data['parents'][0]['names']['en']
    if change == 'unknown_gender': data['parents'][0]['gender'] = 'unknown'
    if change == 'third': data['parents'] *= 3
    if change == 'birthplace': data['parents'][0]['birthplace'] = 'ZZplace'
    with pytest.raises(Blocked): p.proposal(data, PINS)


def test_html_escapes_names_no_script_or_external_resources():
    data, _ = inputs()
    data['parents'][0]['gender'] = 'female'
    data['parents'][0]['names']['he']['first_name'] = '<script>ZZsentinel</script>'
    value = p.proposal(data, PINS)
    page = p.render(value)
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert '<form' not in page and '<button' not in page and '<iframe' not in page
    assert "default-src 'none'" in page and value['proposal_hash'] in page


def test_main_private_outputs_and_public_fixed_summary(tmp_path, capsys):
    data, _ = inputs()
    data['parents'][0]['gender'] = 'female'
    manifest, pins, out = tmp_path/'manifest', tmp_path/'pins', tmp_path/'out'
    for path, value in [(manifest,data),(pins,PINS)]:
        path.write_text(json.dumps(value));path.chmod(0o600)
    assert p.main(['--manifest-file',str(manifest),'--pins-file',str(pins),
                   '--output-dir',str(out)]) == 0
    assert out.stat().st_mode & 0o777 == 0o700
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in out.iterdir())
    assert 'ZZ' not in capsys.readouterr().out
    assert p.verify_proposal(json.loads((out/'proposal.json').read_text()))


def test_pins_and_output_failure_no_private_error(tmp_path, capsys):
    data, _ = inputs()
    data['parents'][0]['gender'] = 'female'
    pins = copy.deepcopy(PINS);pins['token'] = 'ZZsecret'
    with pytest.raises(Blocked) as exc: p.proposal(data,pins)
    assert 'ZZsecret' not in str(exc.value)
    assert p.main(['--manifest-file',str(tmp_path/'ZZprivate'),
                   '--pins-file','ZZprivate','--output-dir','ZZprivate']) == 1
    assert 'ZZprivate' not in capsys.readouterr().out
