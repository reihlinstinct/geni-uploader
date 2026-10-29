"""Extra synthetic seam tests for #232. Offline only; no runtime change.

Targets the merged father_once_simulation seam (#246). Proves nothing about
vendor behaviour, durable storage or authentication.
"""
import threading
from copy import deepcopy

import pytest

import father_once_simulation as seam
from father_once_simulation import (
    SyntheticFatherTransport,
    SyntheticOwnerStore,
    descriptor,
    simulate_once,
)
from people_core import Blocked, digest


def fixtures():
    payload = {'first_name': 'ZZFather', 'last_name': 'ZZExample',
               'names': {'en': {'first_name': 'ZZFather', 'last_name': 'ZZExample'},
                         'he': {'first_name': 'ZZHebrew', 'last_name': 'ZZExample'}},
               'gender': 'male', 'is_alive': True, 'public': False}
    binding = {'owner': 'profile-999001', 'connection_id': 'ZZ-secondary',
               'operation': 'single_father_add_parent', 'plan_hash': '1' * 64,
               'payload_hash': digest(payload), 'artifact_hash': '3' * 64,
               'policy_hash': '4' * 64}
    return binding, payload, SyntheticOwnerStore(), SyntheticFatherTransport()


EVIDENCE = digest({'synthetic_event': 'ZZ-test-evidence'})


# 1. Direct transition with a mismatched binding leaves the stored state unchanged.

@pytest.mark.parametrize('field', ['connection_id', 'operation', 'plan_hash', 'payload_hash',
                                   'artifact_hash', 'policy_hash', 'extra'])
@pytest.mark.parametrize('event', ['acknowledge', 'uncertain'])
def test_transition_with_mismatched_binding_leaves_state_unchanged(field, event):
    binding, _payload, store, _transport = fixtures()
    store.consume(binding)
    before = deepcopy(store.rows)
    changed = dict(binding)
    if field == 'extra':
        changed['ZZ-extra'] = 'x'
    elif field in ('connection_id', 'operation'):
        changed[field] = 'ZZ-other'
    else:
        changed[field] = 'f' * 64
    created = 'profile-999002' if event == 'acknowledge' else None
    with pytest.raises(Blocked):
        store.transition(changed, 1, event, EVIDENCE, created)
    assert store.rows == before
    assert store.rows[binding['owner']]['phase'] == 'consumed'
    assert store.rows[binding['owner']]['version'] == 1
    # The correct binding still works afterwards: the failed call consumed nothing.
    state = store.transition(binding, 1, event, EVIDENCE, created)
    assert state['version'] == 2


def test_transition_after_mismatch_does_not_leak_stored_row():
    binding, _payload, store, _transport = fixtures()
    store.consume(binding)
    with pytest.raises(Blocked):
        store.transition({**binding, 'plan_hash': 'f' * 64}, 1, 'acknowledge', EVIDENCE,
                         'profile-999002')
    returned = store.transition(binding, 1, 'acknowledge', EVIDENCE, 'profile-999002')
    returned['created_id'] = 'profile-123'
    returned['binding']['owner'] = 'profile-123'
    assert store.rows[binding['owner']]['created_id'] == 'profile-999002'
    assert store.rows[binding['owner']]['binding'] == binding


# 2. Concurrent consume race, interleaving forced with a real barrier.

def test_barrier_forced_concurrent_consume_only_one_post(monkeypatch):
    binding, payload, store, transport = fixtures()
    barrier = threading.Barrier(2, timeout=10)
    original_consume = SyntheticOwnerStore.consume
    inner = seam.consume
    inside = {'now': 0, 'max': 0, 'calls': 0}
    count_lock = threading.Lock()

    def consume_after_barrier(self, b):
        barrier.wait()  # both threads are released into the store together
        return original_consume(self, b)

    def counted_consume(b, version):
        with count_lock:
            inside['now'] += 1
            inside['calls'] += 1
            inside['max'] = max(inside['max'], inside['now'])
        try:
            assert store.lock.locked()
            return inner(b, version)
        finally:
            with count_lock:
                inside['now'] -= 1

    monkeypatch.setattr(SyntheticOwnerStore, 'consume', consume_after_barrier)
    monkeypatch.setattr(seam, 'consume', counted_consume)
    results = [None, None]

    def run(i):
        try:
            results[i] = simulate_once({**binding, 'plan_hash': f'{i + 1:064x}'}, payload,
                                       store, transport)
        except Blocked:
            results[i] = 'blocked'

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
        assert not t.is_alive()
    assert sorted(map(str, results)).count('blocked') == 1
    winner = next(r for r in results if r != 'blocked')
    assert winner == {'mode': 'synthetic_only', 'phase': 'acknowledged',
                      'production_enabled': False}
    assert len(transport.requests) == 1
    assert list(store.rows) == [binding['owner']]
    assert inside['max'] == 1
    # The loser was rejected by the owner-global check before the intent model ran.
    assert inside['calls'] == 1


# 3. A transport that mutates what it is given cannot reach caller inputs or the store.

def test_transport_mutating_descriptor_cannot_reach_caller_or_store(monkeypatch):
    binding, payload, store, transport = fixtures()
    caller_binding, caller_payload = deepcopy(binding), deepcopy(payload)
    expected = descriptor(binding, payload)
    original_post = SyntheticFatherTransport.post
    seen = []

    def hostile_post(self, request):
        result = original_post(self, request)
        seen.append(request)
        request['route'] = 'profile-1/add-parent'
        request['body']['first_name'] = 'ZZMutated'
        request['body']['names']['he']['first_name'] = 'ZZMutated'
        request['body']['public'] = True
        request['credential_included'] = True
        request.pop('body_hash')
        return result

    monkeypatch.setattr(SyntheticFatherTransport, 'post', hostile_post)
    result = simulate_once(binding, payload, store, transport)
    assert result['phase'] == 'acknowledged'
    assert binding == caller_binding
    assert payload == caller_payload
    assert transport.requests == [expected]
    assert seen[0] is not transport.requests[0]
    row = store.rows[binding['owner']]
    assert row['binding'] == caller_binding
    assert row['created_id'] == transport.created_id


def test_transport_mutating_before_record_cannot_reach_caller_inputs(monkeypatch):
    binding, payload, store, transport = fixtures()
    caller_binding, caller_payload = deepcopy(binding), deepcopy(payload)
    original_post = SyntheticFatherTransport.post

    def mutate_first(self, request):
        request['body']['names']['en']['last_name'] = 'ZZMutated'
        request['body']['gender'] = 'female'
        return original_post(self, request)

    monkeypatch.setattr(SyntheticFatherTransport, 'post', mutate_first)
    simulate_once(binding, payload, store, transport)
    assert binding == caller_binding
    assert payload == caller_payload
    assert store.rows[binding['owner']]['binding'] == caller_binding


def test_caller_mutating_inputs_after_call_does_not_change_records():
    binding, payload, store, transport = fixtures()
    expected = descriptor(binding, payload)
    simulate_once(binding, payload, store, transport)
    stored = deepcopy(store.rows)
    payload['names']['en']['first_name'] = 'ZZLater'
    binding['plan_hash'] = 'e' * 64
    assert transport.requests == [expected]
    assert store.rows == stored
