"""Synthetic-only seam tests; no vendor behavior or durable storage proved."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

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
               'operation': 'single_father_add_parent', 'plan_hash': '1'*64,
               'payload_hash': digest(payload), 'artifact_hash': '3'*64, 'policy_hash': '4'*64}
    return binding, payload, SyntheticOwnerStore(), SyntheticFatherTransport()


def test_exact_descriptor_and_single_ack_not_verified():
    binding, payload, store, transport = fixtures()
    expected = descriptor(binding, payload)
    before = deepcopy(payload)
    result = simulate_once(binding, payload, store, transport)
    assert result == {'mode': 'synthetic_only', 'phase': 'acknowledged',
                      'production_enabled': False}
    assert transport.requests == [expected]
    assert expected == {'kind': 'offline_request_descriptor', 'method': 'POST',
                        'route': 'profile-999001/add-parent', 'body': payload,
                        'body_hash': digest(payload), 'credential_included': False,
                        'redirects_allowed': False, 'retries_allowed': False,
                        'production_enabled': False}
    assert payload == before
    assert store.rows[binding['owner']]['created_id'] == transport.created_id
    with pytest.raises(Blocked):
        simulate_once(binding, payload, store, transport)
    assert len(transport.requests) == 1


def test_intent_precedes_post_and_ambiguous_result_never_replayed(monkeypatch):
    binding, payload, store, transport = fixtures()
    transport.fail_after_send = True
    original = SyntheticFatherTransport.post

    def checked_post(self, request):
        assert store.rows[binding['owner']]['phase'] == 'consumed'
        return original(self, request)

    monkeypatch.setattr(SyntheticFatherTransport, 'post', checked_post)
    assert simulate_once(binding, payload, store, transport)['phase'] == 'uncertain'
    for changed in [dict(binding), {**binding, 'plan_hash': 'a'*64},
                    {**binding, 'connection_id': 'ZZ-other'}]:
        with pytest.raises(Blocked):
            simulate_once(changed, payload, store, transport)
    assert len(transport.requests) == 1


def test_concurrent_proposals_same_owner_only_one_post():
    binding, payload, store, transport = fixtures()

    def run(n):
        try:
            return simulate_once({**binding, 'plan_hash': f'{n:064x}'}, payload, store, transport)
        except Blocked:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(20)))
    assert sum(x is not None for x in results) == 1
    assert len(transport.requests) == 1


@pytest.mark.parametrize('change', ['hash', 'extra', 'public', 'gender', 'locale', 'main'])
def test_payload_rejected_before_intent(change):
    binding, payload, store, transport = fixtures()
    if change == 'hash': binding['payload_hash'] = 'f'*64
    if change == 'extra': payload['marriage'] = {}
    if change == 'public': payload['public'] = True
    if change == 'gender': payload['gender'] = 'female'
    if change == 'locale': payload['names']['fr'] = payload['names']['en']
    if change == 'main': payload['first_name'] = 'ZZOther'
    with pytest.raises(Blocked):
        simulate_once(binding, payload, store, transport)
    assert store.rows == {} and transport.requests == []


def test_caller_network_or_subclass_injection_blocked():
    binding, payload, store, transport = fixtures()

    class Other(SyntheticFatherTransport):
        pass

    for bad in [Other(), object(), lambda _: None]:
        with pytest.raises(Blocked):
            simulate_once(binding, payload, store, bad)
    assert store.rows == {} and transport.requests == []


def test_invalid_ack_is_uncertain_not_verified_or_retried():
    binding, payload, store, transport = fixtures()
    transport.created_id = binding['owner']
    assert simulate_once(binding, payload, store, transport)['phase'] == 'uncertain'
    assert store.rows[binding['owner']]['phase'] == 'uncertain'
    with pytest.raises(Blocked):
        simulate_once(binding, payload, store, transport)
    assert len(transport.requests) == 1


def test_failed_intent_storage_sends_nothing(monkeypatch):
    binding, payload, store, transport = fixtures()

    def fail(*args):
        raise OSError('ZZ unavailable')

    monkeypatch.setattr(SyntheticOwnerStore, 'consume', fail)
    with pytest.raises(OSError):
        simulate_once(binding, payload, store, transport)
    assert transport.requests == []


def test_post_intent_storage_failure_not_claimed_saved(monkeypatch):
    binding, payload, store, transport = fixtures()

    def fail(*args):
        raise OSError('ZZ unavailable')

    monkeypatch.setattr(SyntheticOwnerStore, 'transition', fail)
    assert simulate_once(binding, payload, store, transport)['phase'] == 'uncertain_storage_unverified'
    assert store.rows[binding['owner']]['phase'] == 'consumed'
    with pytest.raises(Blocked):
        simulate_once(binding, payload, store, transport)
    assert len(transport.requests) == 1


def test_changed_every_binding_field_blocks_before_second_send():
    binding, payload, store, transport = fixtures()
    simulate_once(binding, payload, store, transport)
    for field in ['connection_id', 'plan_hash', 'artifact_hash', 'policy_hash']:
        changed = dict(binding)
        changed[field] = 'ZZ-other' if field == 'connection_id' else 'f'*64
        with pytest.raises(Blocked):
            simulate_once(changed, payload, store, transport)
    assert len(transport.requests) == 1


def test_non_secondary_connection_blocks_before_intent():
    binding, payload, store, transport = fixtures()
    binding['connection_id'] = 'ZZ-primary'
    with pytest.raises(Blocked):
        simulate_once(binding, payload, store, transport)
    assert store.rows == {} and transport.requests == []
