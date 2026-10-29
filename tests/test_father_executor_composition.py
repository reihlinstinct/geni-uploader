from copy import deepcopy

import pytest

from father_executor_composition import FixtureBoundaries, execute_fixture, execute_production
from people_core import Blocked, digest


def fixture():
    payload = {'names': {'he': {'first_name': 'ZZאב'}, 'en': {'first_name': 'ZZFather'}},
               'first_name': 'ZZFather', 'gender': 'male', 'is_alive': True, 'public': False}
    pins = {'owner': 'profile-999001', 'payload_hash': digest(payload),
            'run_hash': '1' * 64, 'artifact_hash': '2' * 64, 'approval_hash': '3' * 64}
    plan = {'mode': 'synthetic_father_composition', 'production_enabled': False,
            'pins': pins, 'payload': payload, 'issued_at': 100, 'expires_at': 500,
            'field_origins': {'names': 'direct_source_person',
                             'relationship': 'direct_source_person',
                             'control_facts': 'explicitly_reviewed'},
            'preflight': {'owner': pins['owner'], 'collected_at': 200,
                          'merge_status': 'UNKNOWN', 'existing_parent_status': 'UNKNOWN',
                          'unknown_risk_explicit': True, 'adverse': False}}
    observed = {'profile_id': 'profile-999002',
                'profile_url': 'https://www.geni.com/people/ZZFather/9990003',
                'payload': deepcopy(payload), 'child': pins['owner'], 'parents': ['profile-999002']}
    return plan, FixtureBoundaries(observed)


def test_full_fixture_order_and_no_source_claim():
    plan, b = fixture()
    out = execute_fixture(plan, b, 201)
    assert out['phase'] == 'fixture_profile_verified_sources_pending'
    assert out['unknown_graph_preserved'] is True
    assert out['production_enabled'] is False and out['authenticated'] is False
    assert b.posts == 1
    assert b.events.index('consume_after') < b.events.index('pre_write_store_after')
    assert b.events.index('pre_write_store_after') < b.events.index('post_before')
    assert b.events.index('readback_after') < b.events.index('result_store_after')
    assert out['result']['source_refs'] == []


@pytest.mark.parametrize('fault', ['consume_before', 'consume_after', 'pre_write_store_before',
    'pre_write_store_after', 'post_before', 'post_after', 'acknowledgment_store_before',
    'acknowledgment_store_after', 'readback_before', 'readback_after',
    'readback_store_before', 'readback_store_after', 'result_store_before', 'result_store_after'])
def test_fault_each_boundary_never_retries(fault):
    plan, b = fixture()
    b.fault = fault
    result = execute_fixture(plan, b, 201)
    assert result['retry_allowed'] is False
    assert b.posts <= 1
    if fault != 'consume_before':
        assert plan['pins']['owner'] in b.consumed
        b.fault = None
        before = b.posts
        assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
        assert b.posts == before


@pytest.mark.parametrize('field,value', [('payload', {}), ('child', 'profile-999009'),
    ('parents', ['profile-999002', 'profile-999008'])])
def test_readback_mismatch_consumed(field, value):
    plan, b = fixture()
    b.observed[field] = value
    assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
    assert b.posts == 1


@pytest.mark.parametrize('field,value', [('owner', 'profile-999009'), ('collected_at', 1),
    ('collected_at', 202), ('merge_status', 'MERGED'), ('existing_parent_status', 'PRESENT'),
    ('unknown_risk_explicit', False), ('adverse', True)])
def test_preflight_blocks_before_consumption(field, value):
    plan, b = fixture()
    plan['preflight'][field] = value
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201)
    assert b.posts == 0 and not b.consumed


def test_changed_plan_cannot_bypass_owner_consumption():
    plan, b = fixture()
    execute_fixture(plan, b, 201)
    plan['pins']['run_hash'] = '4' * 64
    assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
    assert b.posts == 1


def test_production_always_closed_and_no_foreign_boundary():
    with pytest.raises(Blocked):
        execute_production()
    with pytest.raises(Blocked):
        execute_fixture(fixture()[0], object(), 201)


@pytest.mark.parametrize('field', ['names', 'relationship', 'control_facts'])
def test_source_only_origin_contract(field):
    plan, b = fixture()
    plan['field_origins'][field] = 'research'
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201)
    assert not b.consumed


def test_female_payload_is_not_one_father_even_when_hash_matches():
    plan, b = fixture()
    plan['payload']['gender'] = 'female'
    plan['pins']['payload_hash'] = digest(plan['payload'])
    b.observed['payload'] = deepcopy(plan['payload'])
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201)
    assert not b.consumed


def test_bad_payload_pin_and_expiry_block_before_consumption():
    for mutate in [lambda p: p['pins'].update(payload_hash='0' * 64),
                   lambda p: p.update(expires_at=201),
                   lambda p: p.update(issued_at=202),
                   lambda p: p.update(expires_at=1001)]:
        plan, b = fixture()
        mutate(plan)
        with pytest.raises(Blocked):
            execute_fixture(plan, b, 201)
        assert not b.consumed


def test_production_flag_must_be_false():
    plan, b = fixture()
    plan['production_enabled'] = True
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201)
    assert not b.consumed


def test_post_method_itself_requires_consumed_owner():
    plan, b = fixture()
    with pytest.raises(Blocked):
        b.post(plan['pins']['owner'], plan['payload'])
    assert b.posts == 0


def test_now_type_guard_independent_of_time_range():
    plan, b = fixture()
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201.0)
    assert not b.consumed


def test_result_shape_must_validate_before_consumption():
    plan, b = fixture()
    b.observed['profile_url'] = 'https://ZZ.invalid/ZZ'
    with pytest.raises(Blocked):
        execute_fixture(plan, b, 201)
    assert not b.consumed and b.posts == 0


def test_ack_mismatch_even_if_readback_parent_matches_ack():
    plan, b = fixture()
    b.observed['parents'] = ['profile-999009']
    b.post = lambda owner, proposed: {'id': 'profile-999009'}
    assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
    assert not any(stage == 'readback' for stage, _ in b.saved)


def test_extra_readback_key_blocks_after_post():
    plan, b = fixture()
    b.observed['unapproved'] = 'ZZextra'
    assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
    assert b.posts == 1


def test_final_result_validation_rejects_equal_evidence_refs():
    plan, b = fixture()
    original = b.store
    def store(stage, value):
        ref = original(stage, value)
        if stage == 'readback':
            return digest({'id': b.observed['profile_id']})
        return ref
    b.store = store
    assert execute_fixture(plan, b, 201)['phase'] == 'fixture_consumed_uncertain'
    assert not any(stage == 'result' for stage, _ in b.saved)


def test_fixture_constructor_copies_observed_nested_data():
    _, existing = fixture()
    observed = existing.observed
    b = FixtureBoundaries(observed)
    observed['payload']['names']['en']['first_name'] = 'ZZchanged'
    observed['parents'].append('profile-999009')
    assert b.observed['payload']['names']['en']['first_name'] == 'ZZFather'
    assert b.observed['parents'] == ['profile-999002']
