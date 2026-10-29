import copy
import json
import socket

import pytest

import parent_output as p
from people_core import Blocked

CONFIG = {'schema_version': 1, 'connection_id': 'ZZisolated',
          'owner_node': 'profile-99123', 'expect_name': 'ZZRoot ZZPerson'}
PROFILE = {'id': CONFIG['owner_node'], 'merge_pending': False, 'first_name': 'ZZRoot',
           'last_name': 'ZZPerson'}
VALUE = {'schema_version': 1, 'connection_id': 'ZZisolated', 'collected_at_unix': 1000,
         'mode': 'human_read_only_probe', 'self': dict(PROFILE), 'owner': dict(PROFILE),
         'family': {'focus': dict(PROFILE), 'nodes': {PROFILE['id']: dict(PROFILE)}},
         'unions': [], 'create_enabled': False, 'hidden_parent_completeness': 'unproved',
         'slot_semantics': 'unproved', 'privacy_create_behavior': 'unproved'}


def test_adapter_never_promotes_recent_matching_claim_to_authority(monkeypatch):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network forbidden'))
    result = p.review_output(VALUE, CONFIG, 1000)
    assert result['create_enabled'] is False and result['source_authenticated'] is False
    assert result['hidden_parent_completeness'] == 'unknown'
    assert result['supplied_connection_matches'] is True
    assert result['name_checked'] is False
    assert not result['live_checks_performed_by_reviewer']
    assert not any(word in str(result) for word in ['ZZRoot', '99123', 'ZZisolated'])


@pytest.mark.parametrize('key,bad', [('schema_version', True), ('connection_id', 'ZZother'),
                                   ('mode', 'ZZwrapper'), ('create_enabled', True),
                                   ('hidden_parent_completeness', 'proved'),
                                   ('slot_semantics', 'proved'),
                                   ('privacy_create_behavior', 'proved'),
                                   ('collected_at_unix', True)])
def test_bad_envelope_is_blocked_without_values(key, bad):
    value = copy.deepcopy(VALUE)
    value[key] = bad
    with pytest.raises(Blocked) as error: p.review_output(value, CONFIG, 1000)
    assert 'ZZ' not in str(error.value)


@pytest.mark.parametrize('now', [999, 1901, True, '1000'])
def test_future_stale_and_invalid_clock_blocked(now):
    with pytest.raises(Blocked): p.review_output(VALUE, CONFIG, now)


def test_exact_envelope_and_owner_binding():
    for value in [{**VALUE, 'ZZextra': True}, {'results': VALUE}]:
        with pytest.raises(Blocked): p.review_output(value, CONFIG, 1000)
    value = copy.deepcopy(VALUE)
    value['owner']['id'] = 'profile-99555'
    with pytest.raises(Blocked): p.review_output(value, CONFIG, 1000)


def test_unknown_merge_preserved_without_relaxing_live_collector():
    value = copy.deepcopy(VALUE)
    value['self'].pop('merge_pending')
    result = p.review_output(value, CONFIG, 1000)
    assert result['merge_status'] == 'unknown' and result['create_enabled'] is False


def inputs(tmp_path):
    config, evidence = tmp_path/'config', tmp_path/'evidence'
    for path, value in [(config, CONFIG), (evidence, VALUE)]:
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    return config, evidence


def test_cli_protected_inputs_no_network_or_data_output(tmp_path, monkeypatch, capsys):
    config, evidence = inputs(tmp_path)
    monkeypatch.setattr(p.time, 'time', lambda: 1000)
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network forbidden'))
    assert p.main(['--connection-file', str(config), '--evidence-file', str(evidence)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result['create_enabled'] and 'ZZ' not in str(result)


@pytest.mark.parametrize('bad', ['shared', 'symlink', 'invalid', 'large'])
def test_cli_unsafe_or_bad_input_fixed_failure(tmp_path, bad, capsys):
    config, evidence = inputs(tmp_path)
    if bad == 'shared': evidence.chmod(0o644)
    if bad == 'symlink':
        link = tmp_path/'link'
        link.symlink_to(evidence)
        evidence = link
    if bad == 'invalid': evidence.write_text('ZZprivate invalid')
    if bad == 'large': evidence.write_text('ZZprivate' * 140000)
    assert p.main(['--connection-file', str(config), '--evidence-file', str(evidence)]) == 1
    assert capsys.readouterr().out == 'offline human probe review blocked; inspect protected inputs\n'
