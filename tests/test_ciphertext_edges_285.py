"""#285: ciphertext edge cases and strict scalar types. Synthetic bytes only."""
import hashlib

import pytest

import ciphertext_evidence as ce
from people_core import Blocked

OP = hashlib.sha256(b'ZZ-operation').hexdigest()
RCPT = hashlib.sha256(b'ZZ-recipient').hexdigest()
RUN = '1234567890'
TAIL = b'\xff\xfe' + hashlib.shake_256(b'ZZ-285').digest(62)  # not valid UTF-8


def desc(data, stage='pre_write', **changes):
    return {'schema_version': 1, 'mode': 'offline_ciphertext_descriptor',
            'production_enabled': False, 'schema': ce.SCHEMA, 'stage': stage,
            'sha256': hashlib.sha256(data).hexdigest(), 'byte_length': len(data),
            'recipient': RCPT, 'operation_binding': OP, 'run_id': RUN, 'run_attempt': 1,
            'blob_id': ce.git_blob_id(data), 'commit': 'c' * 40} | changes


@pytest.mark.parametrize('space', [b'\n', b'\r', b'\t'])
def test_whitespace_counts_as_printable(space):
    # 90 % letters + 10 % of one whitespace byte: rejected only because the
    # whitespace byte counts as printable (100 %, over the 95 % threshold).
    data = b'a' * 900 + space * 100
    with pytest.raises(Blocked):
        ce.check_bytes(desc(data), data)


@pytest.mark.parametrize('prefix', [b'-----BEGI', b'%PD', b'PK\x03'])
def test_near_miss_prefixes_are_accepted(prefix):
    data = prefix + TAIL
    assert ce.check_bytes(desc(data), data)['byte_length'] == len(data)


def test_valid_reconciliation_stage_descriptor():
    data = b'\x00' + TAIL
    result = ce.check_bytes(desc(data, 'reconciliation'), data)
    assert result['stage'] == 'reconciliation'
    assert ce.verify_readback(desc(data, 'reconciliation'), data, 'c' * 40)['authority'] is False


@pytest.mark.parametrize('value', [0, 0.0, None, '', [], 'False', 1, True])
def test_production_enabled_must_be_exactly_false(value):
    data = b'\x00' + TAIL
    with pytest.raises(Blocked):
        ce.validate_descriptor(desc(data, production_enabled=value))


@pytest.mark.parametrize('value', [False, True])
def test_total_bytes_rejects_bool(value):
    ledger = ce.new_ledger(OP, RUN, RCPT)
    if value:
        data = b'\x00'
        item = desc(data)
        ledger['objects'] = [item]
    ledger['total_bytes'] = value  # False == 0 and True == 1, but neither is an int
    with pytest.raises(Blocked):
        ce.validate_ledger(ledger)


def test_total_bytes_int_still_accepted():
    ledger = ce.new_ledger(OP, RUN, RCPT)
    assert ce.validate_ledger(ledger)['total_bytes'] == 0
