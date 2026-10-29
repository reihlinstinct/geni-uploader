"""Synthetic semantics only. A fake CAS is not evidence of shared durability."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock

import pytest

from parent_intent_model import advance, binding_hash, consume, validate
from people_core import Blocked


def binding():
    return {'owner': 'profile-999001', 'connection_id': 'ZZ-secondary',
                'operation': 'single_father_add_parent', 'plan_hash': '1'*64,
                'payload_hash': '2'*64, 'artifact_hash': '3'*64, 'policy_hash': '4'*64}


def test_acknowledge_verify_is_terminal_and_input_immutable():
    first = consume(binding(), 0)
    original = deepcopy(first)
    ack = advance(first, 1, 'acknowledge', 'a'*64, 'profile-999002')
    final = advance(ack, 2, 'verify', 'b'*64)
    assert first == original
    assert final['phase'] == 'verified' and final['version'] == 3
    assert final['production_enabled'] is False
    with pytest.raises(Blocked):
        advance(final, 3, 'verify', 'c'*64)


def test_uncertain_before_ack_only_read_reconciliation_can_finish():
    uncertain = advance(consume(binding(), 0), 1, 'uncertain', 'a'*64)
    with pytest.raises(Blocked):
        advance(uncertain, 2, 'acknowledge', 'b'*64, 'profile-999002')
    final = advance(uncertain, 2, 'reconcile_verified', 'b'*64, 'profile-999002')
    assert final['phase'] == 'verified' and final['version'] == 3


def test_uncertain_after_ack_preserves_id():
    ack = advance(consume(binding(), 0), 1, 'acknowledge', 'a'*64, 'profile-999002')
    uncertain = advance(ack, 2, 'uncertain', 'b'*64)
    with pytest.raises(Blocked):
        advance(uncertain, 3, 'reconcile_verified', 'c'*64, 'profile-999003')
    assert advance(uncertain, 3, 'reconcile_verified', 'c'*64,
                   'profile-999002')['version'] == 4


@pytest.mark.parametrize('event', ['reset', 'release', 'retry', 'expire', 'delete', 'POST'])
def test_no_reset_replay_or_expiry(event):
    with pytest.raises(Blocked):
        advance(consume(binding(), 0), 1, event, 'a'*64)


@pytest.mark.parametrize('version', [True, -1, 1, 2**32, '0', None])
def test_consume_requires_exact_empty_version(version):
    with pytest.raises(Blocked):
        consume(binding(), version)


@pytest.mark.parametrize('change', ['owner', 'connection', 'hash', 'operation', 'extra'])
def test_binding_validation(change):
    value = binding()
    if change == 'owner': value['owner'] = 'profile-self'
    if change == 'connection': value['connection_id'] = 'ZZ/other'
    if change == 'hash': value['plan_hash'] = 'ZZ-invalid'
    if change == 'operation': value['operation'] = 'mother'
    if change == 'extra': value['ZZ-extra'] = True
    with pytest.raises(Blocked):
        binding_hash(value)


def test_changed_binding_stale_cas_and_plaintext_reference_rejected():
    value = consume(binding(), 0)
    for key, replacement in [('binding_hash', 'a'*64), ('production_enabled', True),
                             ('version', True), ('phase', 'verified')]:
        changed = deepcopy(value)
        changed[key] = replacement
        with pytest.raises(Blocked):
            validate(changed)
    for reference in ['ZZ-name', 'https://ZZ.example/ciphertext', 'A'*64]:
        with pytest.raises(Blocked):
            advance(value, 1, 'uncertain', reference)
    with pytest.raises(Blocked):
        advance(value, 0, 'uncertain', 'a'*64)
    with pytest.raises(Blocked):
        advance(value, 1, 'acknowledge', 'a'*64, 'profile-999001')


def test_fake_shared_cas_contract_one_owner_not_plan_or_connection():
    # The ONLY exclusion here is this synthetic lock, not the pure model.
    lock, rows = Lock(), {}

    def fake_backend(value):
        with lock:
            if value['owner'] in rows:
                return False
            rows[value['owner']] = consume(value, 0)
            return True

    alternatives = []
    for n in range(20):
        value = binding()
        value['connection_id'] = 'ZZ-' + str(n)
        value['plan_hash'] = f'{n:064x}'
        alternatives.append(value)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(fake_backend, alternatives)) == 1
    assert len(rows) == 1


@pytest.mark.parametrize('ident', ['profile-0', 'profile-01', 'profile-١',
                                   'profile-1?x=2', 'https://ZZ.example/profile-1'])
def test_noncanonical_ids(ident):
    value = binding()
    value['owner'] = ident
    with pytest.raises(Blocked):
        consume(value, 0)


def test_duplicate_evidence_and_invalid_phase_shapes():
    ack = advance(consume(binding(), 0), 1, 'acknowledge', 'a'*64, 'profile-999002')
    with pytest.raises(Blocked):
        advance(ack, 2, 'verify', 'a'*64)
    for changes in [{'phase': []}, {'version': 3}, {'created_id': None},
                    {'evidence_refs': []}, {'evidence_refs': ['a'*64, 'a'*64]}]:
        value = deepcopy(ack)
        value.update(changes)
        with pytest.raises(Blocked):
            validate(value)
    first = consume(binding(), 0)
    with pytest.raises(Blocked):
        advance(first, 1, [], 'a'*64)


@pytest.mark.parametrize('shape', ['consumed', 'acknowledged', 'uncertain_unknown',
                                   'uncertain_known', 'verified_direct',
                                   'verified_reconciled_unknown', 'verified_reconciled_known'])
@pytest.mark.parametrize('event', ['acknowledge', 'uncertain', 'verify',
                                   'reconcile_verified', 'reset', 'release', 'retry'])
def test_complete_phase_event_matrix(shape, event):
    consumed = consume(binding(), 0)
    ack = advance(consumed, 1, 'acknowledge', 'a'*64, 'profile-999002')
    unknown = advance(consumed, 1, 'uncertain', 'a'*64)
    known = advance(ack, 2, 'uncertain', 'b'*64)
    states = {
        'consumed': consumed,
        'acknowledged': ack,
        'uncertain_unknown': unknown,
        'uncertain_known': known,
        'verified_direct': advance(ack, 2, 'verify', 'b'*64),
        'verified_reconciled_unknown': advance(unknown, 2, 'reconcile_verified',
                                               'b'*64, 'profile-999002'),
        'verified_reconciled_known': advance(known, 3, 'reconcile_verified',
                                             'c'*64, 'profile-999002'),
    }
    # This independent literal matrix must not derive expectations from the
    # production transition table; otherwise a weakened table mutates both.
    accepted = {
        'consumed': {'acknowledge': 'acknowledged', 'uncertain': 'uncertain'},
        'acknowledged': {'uncertain': 'uncertain', 'verify': 'verified'},
        'uncertain_unknown': {'reconcile_verified': 'verified'},
        'uncertain_known': {'reconcile_verified': 'verified'},
        'verified_direct': {},
        'verified_reconciled_unknown': {},
        'verified_reconciled_known': {},
    }
    state = states[shape]
    before = deepcopy(state)
    ident = 'profile-999002' if event in ('acknowledge', 'reconcile_verified') else None
    if event in accepted[shape]:
        result = advance(state, state['version'], event, 'd'*64, ident)
        assert result['phase'] == accepted[shape][event]
        assert result['version'] == state['version'] + 1
        assert result['binding'] == state['binding']
        assert result['created_id'] == (ident or state['created_id'])
        assert result['evidence_refs'] == state['evidence_refs'] + ['d'*64]
    else:
        with pytest.raises(Blocked):
            advance(state, state['version'], event, 'd'*64, ident)
    assert state == before
