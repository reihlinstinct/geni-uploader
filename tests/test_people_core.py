"""Synthetic only; no Geni transport exists in this core."""
import copy
import sqlite3
from functools import partial

import pytest

import people_core as p

DATA = {'schema_version': 1, 'owner': {'node': '99123', 'expect_name': 'ZZRoot ZZPerson'},
        'operator': 'ZZOperator', 'approval': {'source': 'ZZApproval', 'date': '2026-10-28',
        'requested_by_owner': True, 'private_storage_approved': True},
        'parents': [{'local_id': 'ZZParent', 'relation': 'parent', 'anchor': '99123',
        'names': {'he': {'first_name': 'ZZName'}}, 'gender': 'unknown',
        'is_alive': True, 'public': False}]}
R = {'manifest_hash': p.digest(DATA), 'data_sha': 'a' * 40, 'owner': '99123',
     'graph_hash': 'b' * 64, 'state_version': 0, 'workflow_sha': 'c' * 40,
     'image_digest': 'sha256:' + 'd' * 64, 'job_workflow_ref': 'ZZ/repo/.github/workflows/ZZ.yml@master',
     'run_id': '991', 'run_attempt': 1, 'created': 1000, 'expires': 1900, 'count': 1}


def test_valid_schema_and_no_production_adapter():
    assert p.validate(copy.deepcopy(DATA)) == DATA
    with pytest.raises(p.Blocked, match='production parent creation disabled'):
        p.production_adapter(DATA)


@pytest.mark.parametrize('field,value', [('relation', 'sibling'), ('anchor', 'ZZLocal'),
    ('is_alive', None), ('is_alive', 1), ('public', True), ('gender', 'guessed'),
    ('email', 'ZZPrivate@example.invalid'), ('names', {}), ('local_id', '../ZZ')])
def test_parent_mutations_block(field, value):
    data = copy.deepcopy(DATA)
    data['parents'][0][field] = value
    with pytest.raises(p.Blocked):
        p.validate(data)


@pytest.mark.parametrize('mutate', ['count', 'duplicate', 'approval', 'extra', 'name'])
def test_manifest_boundaries(mutate):
    data = copy.deepcopy(DATA)
    if mutate == 'count': data['parents'] *= 3
    if mutate == 'duplicate': data['parents'] *= 2
    if mutate == 'approval': data['approval']['requested_by_owner'] = False
    if mutate == 'extra': data['token'] = 'ZZSecret'
    if mutate == 'name': data['owner']['expect_name'] = 'ZZRoot'
    with pytest.raises(p.Blocked) as exc:
        p.validate(data)
    assert 'ZZ' not in str(exc.value)


@pytest.mark.parametrize('field', list(R))
def test_every_receipt_binding_rechecked(field):
    receipt = copy.deepcopy(R)
    receipt[field] = 'ZZChanged'
    with pytest.raises(p.Blocked):
        p.check_receipt(receipt, R, 1100)


@pytest.mark.parametrize('now', [999, 1900, 2000])
def test_receipt_time_boundary(now):
    with pytest.raises(p.Blocked):
        p.check_receipt(R, R, now)


def test_receipt_hash_and_canonical_input():
    assert p.check_receipt(R, R, 1100) == p.digest(R)
    assert p.digest(DATA) == p.digest(dict(reversed(list(DATA.items()))))


def test_monotonic_durable_cas_and_get_only_resume(tmp_path):
    path = tmp_path / 'journal'
    j = journal(path)
    assert j.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent') == 1
    j.close()  # crash/restart preserves intent, never replay
    j = journal(path)
    with pytest.raises(p.Blocked): j.resume('99123', 'ZZop')
    with pytest.raises(p.Blocked): j.transition('99123', 1, 'ZZnew', 'c'*64, 'd'*64, 'intent')
    with pytest.raises(p.Blocked): j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'intent')
    assert j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'acknowledged', '99222') == 2
    assert j.resume('99123', 'ZZop') == {'action': 'get_only', 'object_id': '99222'}
    with pytest.raises(p.Blocked): j.transition('99123', 2, 'ZZop', 'a'*64, 'b'*64, 'verified', '99333')
    assert j.transition('99123', 2, 'ZZop', 'a'*64, 'b'*64, 'verified', '99222') == 3
    assert j.transition('99123', 3, 'ZZnext', 'a'*64, 'c'*64, 'intent') == 4
    j.close()


def test_concurrent_stale_version_and_blocked_operation(tmp_path):
    a = journal(tmp_path / 'journal')
    b = journal(tmp_path / 'journal')
    a.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent')
    with pytest.raises(p.Blocked): b.transition('99123', 0, 'ZZrace', 'c'*64, 'd'*64, 'intent')
    a.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'blocked')
    with pytest.raises(p.Blocked): b.transition('99123', 2, 'ZZnewhash', 'c'*64, 'd'*64, 'intent')
    assert not hasattr(a, 'reset') and not hasattr(a, 'delete')
    a.close(); b.close()


B = {'receipt': 'e'*64, 'run_id': '991', 'attempt': 1, 'anchor': '99123'}


def journal(path):
    j = p.Journal(path)
    j.transition = partial(j.transition, binding=B)
    return j


def test_bind_manifest_count_owner_and_hash():
    assert p.bind(DATA, R, R, 1100) == p.digest(R)
    for field, value in [('count', 2), ('owner', '99124'), ('manifest_hash', 'e'*64)]:
        r = {**R, field: value}
        with pytest.raises(p.Blocked): p.bind(DATA, r, r, 1100)


@pytest.mark.parametrize('value', ['ZZ\x7f', 'ZZ\u202e', 'ZZ\u200d', 'e\u0301'])
def test_text_rejects_controls_formats_and_non_nfc(value):
    with pytest.raises(p.Blocked): p.text(value)


@pytest.mark.parametrize('changes', [{'expires': 1901}, {'count': 0}, {'count': 3}])
def test_invalid_receipt_window_and_count(changes):
    r = {**R, **changes}
    with pytest.raises(p.Blocked): p.check_receipt(r, r, 1100)


def test_terminal_duplicate_and_raw_tamper(tmp_path):
    j = journal(tmp_path / 'journal')
    j.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent')
    with pytest.raises(p.Blocked): j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'acknowledged')
    j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'acknowledged', '99222')
    j.transition('99123', 2, 'ZZop', 'a'*64, 'b'*64, 'verified', '99222')
    with pytest.raises(p.Blocked): j.transition('99123', 3, 'ZZnew', 'a'*64, 'b'*64, 'intent')
    with pytest.raises(p.Blocked): j.transition('99123', 3, 'ZZop', 'a'*64, 'b'*64, 'blocked', '99222')
    for sql in ['UPDATE events SET phase="intent"', 'DELETE FROM events']:
        with pytest.raises(sqlite3.IntegrityError): j.db.execute(sql)
    j.db.execute('UPDATE owners SET version=99')
    with pytest.raises(p.Blocked): j.transition('99123', 99, 'ZZnew', 'a'*64, 'c'*64, 'intent')
    j.close()


def test_binding_mismatch_and_blocked_resume(tmp_path):
    j = journal(tmp_path / 'journal')
    j.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent')
    with pytest.raises(p.Blocked):
        j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'acknowledged', '99222',
                     binding={**B, 'attempt': 2})
    j.transition('99123', 1, 'ZZop', 'a'*64, 'b'*64, 'blocked')
    with pytest.raises(p.Blocked): j.resume('99123', 'ZZop')
    j.close()


def test_parent_review_warnings():
    d = copy.deepcopy(DATA)
    d['parents'][0]['gender'] = 'female'
    d['parents'].append({**copy.deepcopy(d['parents'][0]), 'local_id': 'ZZOther'})
    assert len(p.warnings(d)) == 2


def test_database_busy_is_fixed_blocked(tmp_path):
    a = journal(tmp_path / 'journal')
    b = journal(tmp_path / 'journal')
    b.db.execute('PRAGMA busy_timeout=1')
    a.db.execute('BEGIN IMMEDIATE')
    with pytest.raises(p.Blocked, match='journal unavailable'):
        b.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent')
    a.db.execute('ROLLBACK'); a.close(); b.close()


@pytest.mark.parametrize('receipt', [None, [], 'ZZreceipt', 1, {}])
def test_bind_rejects_non_receipt(receipt):
    with pytest.raises(p.Blocked): p.bind(DATA, receipt, R, 1100)


@pytest.mark.parametrize('error', [sqlite3.OperationalError, sqlite3.DatabaseError,
                                  sqlite3.IntegrityError])
def test_init_database_errors_are_blocked(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error('ZZprivate error')
    monkeypatch.setattr(p.sqlite3, 'connect', fail)
    with pytest.raises(p.Blocked, match='journal unavailable'): p.Journal('ZZpath')


def test_resume_database_error_is_blocked(tmp_path):
    j = journal(tmp_path / 'journal')
    j.db.execute('DROP TABLE events')
    with pytest.raises(p.Blocked, match='journal unavailable'): j.resume('99123', 'ZZop')
    j.close()


def test_transition_integrity_error_is_blocked_and_rolled_back(tmp_path):
    j = journal(tmp_path / 'journal')
    j.db.execute("CREATE TRIGGER ZZreject BEFORE INSERT ON events "
                 "BEGIN SELECT RAISE(ABORT,'ZZprivate error'); END")
    with pytest.raises(p.Blocked, match='journal unavailable'):
        j.transition('99123', 0, 'ZZop', 'a'*64, 'b'*64, 'intent')
    assert not j.db.in_transaction
    assert j.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0
    j.close()
