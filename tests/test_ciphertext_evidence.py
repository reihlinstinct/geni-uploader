"""Synthetic offline tests for ciphertext_evidence (#257). No network, keys or real data."""
import hashlib
from copy import deepcopy

import pytest

import ciphertext_evidence as ce
from people_core import Blocked

OP = hashlib.sha256(b'ZZ-operation').hexdigest()
RCPT = hashlib.sha256(b'ZZ-recipient').hexdigest()
RUN = '1234567890'
COMMIT = 'c' * 40


def blob(n=64, seed=b'ZZ'):
    """Deterministic binary bytes that do not look like plaintext (linear time)."""
    return (b'\x00\xff' + hashlib.shake_256(seed).digest(max(n - 2, 0)))[:n]


def desc(data, stage='pre_write', **changes):
    return {'schema_version': 1, 'mode': 'offline_ciphertext_descriptor',
            'production_enabled': False, 'schema': ce.SCHEMA, 'stage': stage,
            'sha256': hashlib.sha256(data).hexdigest(), 'byte_length': len(data),
            'recipient': RCPT, 'operation_binding': OP, 'run_id': RUN, 'run_attempt': 1,
            'blob_id': ce.git_blob_id(data), 'commit': COMMIT} | changes


def ledger():
    return ce.new_ledger(OP, RUN, RCPT)


def test_git_blob_id_matches_git():
    # Known value: `printf 'hello\n' | git hash-object --stdin`
    assert ce.git_blob_id(b'hello\n') == 'ce013625030ba8dba906f756967f9e9ca394464a'


def test_valid_object_checks_and_returns_copy():
    data = blob()
    d = desc(data)
    assert ce.check_bytes(d, data) == d
    assert ce.check_bytes(d, data) is not d


@pytest.mark.parametrize('field,value', [
    ('sha256', 'f' * 64), ('byte_length', 65), ('blob_id', 'f' * 40)])
def test_bytes_must_match_descriptor(field, value):
    data = blob()
    with pytest.raises(Blocked):
        ce.check_bytes(desc(data, **{field: value}), data)


def test_one_flipped_byte_blocks():
    data = blob()
    d = desc(data)
    bad = bytes([data[0] ^ 1]) + data[1:]
    with pytest.raises(Blocked):
        ce.check_bytes(d, bad)


@pytest.mark.parametrize('data', [
    b'{"name": "ZZ"}', b'[1, 2]', b'<xml/>', b'-----BEGIN AGE ENCRYPTED FILE-----',
    b'%PDF-1.7 ZZ', b'PK\x03\x04ZZ', b'\xef\xbb\xbfZZ', b'ZZ plain synthetic note\n' * 4])
def test_plaintext_shaped_bytes_rejected(data):
    with pytest.raises(Blocked):
        ce.check_bytes(desc(data), data)


def test_empty_and_non_bytes_rejected():
    with pytest.raises(Blocked):
        ce.check_bytes(desc(b'x', byte_length=1), b'')
    data = blob()
    for bad in (bytearray(data), data.hex(), None):
        with pytest.raises(Blocked):
            ce.check_bytes(desc(data), bad)


def test_object_cap_exact():
    at_cap = blob(ce.OBJECT_CAP)
    assert ce.check_bytes(desc(at_cap), at_cap)['byte_length'] == ce.OBJECT_CAP
    over = blob(ce.OBJECT_CAP + 1)
    with pytest.raises(Blocked):
        ce.check_bytes(desc(over), over)
    with pytest.raises(Blocked):
        ce.validate_descriptor(desc(over))


@pytest.mark.parametrize('field,value', [
    ('schema_version', 2), ('schema_version', True), ('mode', 'live'),
    ('production_enabled', True), ('schema', 'other'), ('stage', 'upload'), ('stage', None),
    ('sha256', 'A' * 64), ('recipient', 'a' * 63), ('operation_binding', 'ZZ-not-a-hash'),
    ('blob_id', 'a' * 64), ('commit', 'g' * 40), ('byte_length', 0), ('byte_length', True),
    ('byte_length', 1.0), ('run_id', '0'), ('run_id', 7), ('run_attempt', 2),
    ('run_attempt', True)])
def test_descriptor_shape(field, value):
    with pytest.raises(Blocked):
        ce.validate_descriptor(desc(blob(), **{field: value}))


def test_descriptor_exact_keys():
    for mutate in (lambda d: d.pop('commit'), lambda d: d.update(plaintext='ZZ')):
        d = desc(blob())
        mutate(d)
        with pytest.raises(Blocked):
            ce.validate_descriptor(d)


@pytest.mark.parametrize('stage', ce.STAGES)
def test_every_known_stage_accepted(stage):
    data = blob()
    assert ce.check_bytes(desc(data, stage), data)['stage'] == stage


# Accounting

def test_account_appends_and_totals():
    a, b = blob(100, b'A'), blob(200, b'B')
    one = ce.account(ledger(), desc(a), a)
    two = ce.account(one, desc(b, 'readback'), b)
    assert two['total_bytes'] == 300 and len(two['objects']) == 2
    assert len(one['objects']) == 1  # earlier ledger unchanged


def test_duplicate_or_conflicting_objects_rejected():
    a = blob(100, b'A')
    one = ce.account(ledger(), desc(a), a)
    with pytest.raises(Blocked):
        ce.account(one, desc(a), a)
    with pytest.raises(Blocked):
        ce.account(one, desc(a, 'readback'), a)  # same bytes under another stage


@pytest.mark.parametrize('field,value', [('operation_binding', 'f' * 64), ('run_id', '42'),
                                         ('recipient', 'e' * 64)])
def test_wrong_pins_rejected(field, value):
    a = blob()
    with pytest.raises(Blocked):
        ce.account(ledger(), desc(a, **{field: value}), a)


def test_operation_cap_exact():
    led = ledger()
    for i in range(8):
        part = blob(ce.OBJECT_CAP, bytes([65 + i]))
        led = ce.account(led, desc(part), part)
    assert led['total_bytes'] == ce.OPERATION_CAP
    extra = blob(1 + 2, b'Z')
    with pytest.raises(Blocked):
        ce.account(led, desc(extra), extra)


def test_ledger_tampering_rejected():
    a, b = blob(100, b'A'), blob(100, b'B')
    led = ce.account(ce.account(ledger(), desc(a), a), desc(b), b)
    for mutate in (lambda x: x.update(total_bytes=100),
                   lambda x: x['objects'].pop(),
                   lambda x: x['objects'].append(deepcopy(x['objects'][0])),
                   lambda x: x['objects'][0].update(run_id='42'),
                   lambda x: x.update(extra=1), lambda x: x.update(mode='live')):
        bad = deepcopy(led)
        mutate(bad)
        with pytest.raises(Blocked):
            ce.validate_ledger(bad)


def test_ledger_over_cap_rejected_on_validate():
    led = ledger()
    item = desc(blob(ce.OBJECT_CAP))
    led['objects'] = [dict(item, sha256=f'{i:064x}', blob_id=f'{i:040x}') for i in range(9)]
    led['total_bytes'] = 9 * ce.OBJECT_CAP
    with pytest.raises(Blocked):
        ce.validate_ledger(led)


def test_new_ledger_shape():
    for args in [('ZZ', RUN, RCPT), (OP, '0', RCPT), (OP, RUN, 'x')]:
        with pytest.raises(Blocked):
            ce.new_ledger(*args)


# Readback

def test_readback_exact_result_and_never_authority():
    data = blob()
    assert ce.verify_readback(desc(data, 'readback'), data, COMMIT) == {
        'mode': 'offline_ciphertext_readback', 'content_consistent': True,
        'ciphertext_proved': False, 'retention_proved': False, 'authority': False,
        'production_enabled': False}


def test_readback_mismatches_block():
    data = blob()
    d = desc(data, 'readback')
    for remote, commit in [(data[:-1], COMMIT), (data + b'\x00', COMMIT),
                           (bytes([data[5] ^ 1]) + data[1:], COMMIT), (data, 'd' * 40),
                           (data, None), (data, COMMIT.upper())]:
        with pytest.raises(Blocked):
            ce.verify_readback(d, remote, commit)


def test_inputs_not_mutated():
    data = blob()
    d, led = desc(data), ledger()
    before = deepcopy((d, led))
    ce.account(led, d, data)
    ce.verify_readback(d, data, COMMIT)
    assert (d, led) == before


def test_validate_ledger_alone_rejects_duplicates_and_foreign_recipient():
    a = blob(100, b'A')
    led = ce.account(ledger(), desc(a), a)
    dup = deepcopy(led)
    dup['objects'].append(deepcopy(dup['objects'][0]))
    dup['total_bytes'] = 200
    with pytest.raises(Blocked):
        ce.validate_ledger(dup)
    foreign = deepcopy(led)
    foreign['objects'][0]['recipient'] = 'e' * 64
    with pytest.raises(Blocked):
        ce.validate_ledger(foreign)


# #277 follow-ups: each guard isolated; candidate caps pinned independently.

MIB = 1024 * 1024


def test_candidate_caps_pinned_independently():
    assert ce.OBJECT_CAP == 1 * MIB
    assert ce.OPERATION_CAP == 8 * MIB


def fake_ledger(sizes, **object_changes):
    """A ledger of synthetic descriptors with distinct ids; validate_ledger alone."""
    led = ledger()
    for i, size in enumerate(sizes):
        item = desc(blob(), byte_length=size, sha256=f'{i + 1:064x}', blob_id=f'{i + 1:040x}')
        led['objects'].append(item | object_changes)
    led['total_bytes'] = sum(sizes)
    return led


def test_validate_ledger_alone_operation_cap_boundary():
    at_cap = fake_ledger([MIB] * 8)
    assert ce.validate_ledger(at_cap)['total_bytes'] == 8 * MIB
    with pytest.raises(Blocked):
        ce.validate_ledger(fake_ledger([MIB] * 8 + [1]))


@pytest.mark.parametrize('printable,rejected', [(900, False), (949, False), (950, True),
                                                (990, True)])
def test_printable_ratio_threshold(printable, rejected):
    data = b'a' * printable + b'\x01' * (1000 - printable)
    if rejected:
        with pytest.raises(Blocked):
            ce.check_bytes(desc(data), data)
    else:
        assert ce.check_bytes(desc(data), data)['byte_length'] == 1000


@pytest.mark.parametrize('prefix', [b'%PDF', b'-----BEGIN', b'[', b'{', b'<', b'PK\x03\x04',
                                    b'\xef\xbb\xbf'])
def test_each_prefix_rejected_with_binary_tail(prefix):
    tail = b'\xff\xfe' + blob(62)  # not valid UTF-8: only the prefix rule can block
    data = prefix + tail
    with pytest.raises(Blocked):
        ce.check_bytes(desc(data), data)
    assert ce.check_bytes(desc(b'\x00' + data), b'\x00' + data)  # same bytes, no prefix


def test_validate_ledger_duplicate_sha_only_and_blob_only():
    sha_dup = fake_ledger([10, 10])
    sha_dup['objects'][1]['sha256'] = sha_dup['objects'][0]['sha256']
    blob_dup = fake_ledger([10, 10])
    blob_dup['objects'][1]['blob_id'] = blob_dup['objects'][0]['blob_id']
    for bad in (sha_dup, blob_dup):
        with pytest.raises(Blocked):
            ce.validate_ledger(bad)
    assert ce.validate_ledger(fake_ledger([10, 10]))['total_bytes'] == 20


def test_validate_ledger_per_object_operation_binding():
    led = fake_ledger([10, 10])
    led['objects'][1]['operation_binding'] = 'f' * 64
    with pytest.raises(Blocked):
        ce.validate_ledger(led)


def test_run_id_length_boundary():
    data = blob()
    assert ce.check_bytes(desc(data, run_id='9' * 20), data)['run_id'] == '9' * 20
    with pytest.raises(Blocked):
        ce.validate_descriptor(desc(data, run_id='9' * 21))
    with pytest.raises(Blocked):
        ce.new_ledger(OP, '9' * 21, RCPT)


@pytest.mark.parametrize('field,value', [('run_id', 1234567890), ('run_id', None),
                                         ('run_id', b'1234567890'), ('objects', ()),
                                         ('objects', {}), ('objects', None)])
def test_validate_ledger_types(field, value):
    led = ledger()
    led[field] = value
    with pytest.raises(Blocked):
        ce.validate_ledger(led)
