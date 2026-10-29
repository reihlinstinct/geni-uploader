import copy
import socket

import pytest

import parent_runner as p
from people_core import Blocked, Journal, digest
from tests.test_people_core import DATA, R


def inputs(two=False):
    data = copy.deepcopy(DATA)
    data['parents'][0]['names']['en'] = {'first_name': 'ZZEnglish'}
    if two:
        data['parents'].append({**copy.deepcopy(data['parents'][0]),
                                'local_id': 'ZZSecond',
                                'names': {'he': {'first_name': 'ZZHebrewSecond'},
                                          'en': {'first_name': 'ZZEnglishSecond'}}})
    receipt = {**R, 'manifest_hash': digest(data), 'count': len(data['parents'])}
    return data, receipt


def test_two_parent_gate_and_no_network(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket, 'socket', deny)
    data, receipt = inputs(True)
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    result = p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    assert result == {'mode': 'synthetic_only', 'version': 6,
                      'verified_count': 2, 'production_enabled': False}
    assert transport.posts == transport.gets == 2
    assert transport.created['99001']['payload']['names'] == data['parents'][0]['names']
    assert transport.created['99001']['payload']['first_name'] == 'ZZEnglish'
    journal.close()


def test_full_batch_bilingual_validation_precedes_intent(tmp_path):
    data, receipt = inputs(True)
    del data['parents'][1]['names']['en']
    receipt['manifest_hash'] = digest(data)
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    assert transport.posts == 0
    assert journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0
    journal.close()


@pytest.mark.parametrize('field,value', [('count', 2), ('owner', '99555'),
                                       ('manifest_hash', 'e'*64)])
def test_changed_receipt_never_reaches_intent(tmp_path, field, value):
    data, receipt = inputs()
    receipt[field] = value
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    assert transport.posts == 0
    assert journal.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0
    journal.close()


def test_expiry_after_intent_blocks_without_post_and_cannot_retry(tmp_path):
    data, receipt = inputs()
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    times = iter([1100, 1100, 1900])
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: next(times), journal, 0, transport)
    assert transport.posts == 0
    assert journal.db.execute('SELECT phase FROM events').fetchone()[0] == 'intent'
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    journal.close()


def test_lost_ack_never_replays_under_new_manifest(tmp_path):
    data, receipt = inputs()
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    transport.fail_after_create = True
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    assert transport.posts == 1
    data['parents'][0]['local_id'] = 'ZZNewOperation'
    receipt.update(manifest_hash=digest(data), state_version=1)
    transport.fail_after_create = False
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 1, transport)
    assert transport.posts == 1
    journal.close()


def test_ack_get_failure_resumes_get_only_without_verifying(tmp_path):
    data, receipt = inputs()
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    transport.fail_get = True
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    transport.fail_get = False
    result = p.resume_synthetic(journal, '99123', 'ZZParent', transport)
    assert result['action'] == 'get_only' and transport.posts == 1
    assert journal.db.execute('SELECT phase FROM events ORDER BY version DESC').fetchone()[0] == 'acknowledged'
    journal.close()


def test_get_tamper_never_marks_verified(tmp_path):
    data, receipt = inputs()
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    original = transport.read
    def tamper(object_id):
        observed = original(object_id)
        observed['payload']['public'] = True
        return observed
    transport.read = tamper
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: 1100, journal, 0, transport)
    assert journal.db.execute('SELECT MAX(version) FROM events').fetchone()[0] == 2
    journal.close()


def test_no_custom_transport_or_production():
    with pytest.raises(Blocked): p.simulate(None, None, None, None, None, 0, object())
    with pytest.raises(Blocked): p.run_production('ZZsecret')


def test_ack_and_verification_continue_after_expiry(tmp_path):
    data, receipt = inputs()
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    clock = [1100]
    original = transport.create
    def create(anchor, payload):
        object_id = original(anchor, payload)
        clock[0] = 2000
        return object_id
    transport.create = create
    result = p.simulate(data, receipt, receipt, lambda: clock[0], journal, 0, transport)
    assert result['verified_count'] == 1 and clock[0] > receipt['expires']
    journal.close()


def test_expiry_between_parents_keeps_first_verified(tmp_path):
    data, receipt = inputs(True)
    journal = Journal(tmp_path / 'journal')
    transport = p.SyntheticTransport()
    clock = [1100]
    original = transport.read
    def read(object_id):
        clock[0] = 2000
        return original(object_id)
    transport.read = read
    with pytest.raises(Blocked):
        p.simulate(data, receipt, receipt, lambda: clock[0], journal, 0, transport)
    assert transport.posts == 1
    assert journal.db.execute('SELECT phase FROM events ORDER BY version DESC').fetchone()[0] == 'verified'
    journal.close()
