
import pytest

from approval_record import EXCLUDED_ACTIONS
from people_core import Blocked
from single_human_approval_record import ASSURANCE, SOURCE_KINDS, check, validate


def fixture():
    pins = {'owner': 'profile-999001', 'connection_id': 'ZZ-secondary',
            'operation': 'single_father_add_parent',
            **{k: 'a' * 64 for k in ('payload_hash', 'graph_hash', 'data_hash',
                'artifact_hash', 'policy_hash', 'recipient', 'nonce')},
            **{k: 'b' * 40 for k in ('executor_sha', 'workflow_sha', 'service_sha')},
            'run_id': '999002', 'run_attempt': 1, 'issued_at': 100, 'expires_at': 500}
    sources = {role: {'kind': kind, 'principal_id': str(999003 + i),
                     'source_ref': str(i + 1) * 64, 'content_hash': str(i + 5) * 64}
               for i, (role, kind) in enumerate(SOURCE_KINDS.items())}
    sources['protected_review']['principal_id'] = sources['owner_grant']['principal_id']
    for key in ('source_ref', 'content_hash'):
        sources['protected_review'][key] = sources['owner_grant'][key]
    return {'schema_version': 2, 'mode': 'single_human_approval_content',
            'assurance': ASSURANCE, 'human_count': 1, 'production_enabled': False,
            'pins': pins, 'exclusions': list(EXCLUDED_ACTIONS), 'risk_hash': 'c' * 64,
            'sources': sources, 'reviewed_executor_sha': pins['executor_sha'],
            'revocation_epoch': 0}


def test_exact_content_never_provenance_or_two_humans():
    r = fixture()
    out = check(r, r, 200)
    assert out['human_count'] == 1 and out['two_humans_verified'] is False
    assert out['content_consistent'] is True
    for k in ('owner_approval_verified', 'protected_human_action_verified',
              'dispatch_provenance_verified', 'independent_review_verified',
              'revocation_verified', 'post_permitted', 'production_enabled'):
        assert out[k] is False
    copy = validate(r)
    copy['sources']['owner_grant']['principal_id'] = '1'
    assert r['sources']['owner_grant']['principal_id'] == '999003'


@pytest.mark.parametrize('field,value', [('human_count', 2), ('human_count', True),
    ('assurance', 'two_humans'), ('schema_version', 1), ('mode', 'authenticated'),
    ('production_enabled', True), ('risk_hash', 'ZZ'), ('revocation_epoch', -1),
    ('revocation_epoch', True), ('reviewed_executor_sha', 'c' * 40)])
def test_invariants_even_when_expected_matches(field, value):
    r = fixture()
    r[field] = value
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('role', SOURCE_KINDS)
def test_role_kind_is_not_identity_claim(role):
    r = fixture()
    r['sources'][role]['kind'] = 'comment_claiming_human'
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('role,other', [('protected_review', 'dispatch'),
    ('dispatch', 'owner_grant'), ('code_review', 'dispatch'), ('code_review', 'owner_grant')])
def test_person_agent_distinction(role, other):
    r = fixture()
    r['sources'][role]['principal_id'] = r['sources'][other]['principal_id']
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('field', fixture()['pins'])
def test_every_exact_pin_mismatch(field):
    r, expected = fixture(), fixture()
    expected['pins'][field] = expected['pins'][field] + 1 if type(expected['pins'][field]) is int else 'ZZ'
    with pytest.raises(Blocked):
        check(r, expected, 200)


@pytest.mark.parametrize('field', ['risk_hash', 'revocation_epoch'])
def test_exact_risk_revocation_mismatch(field):
    r, e = fixture(), fixture()
    e[field] = 'd' * 64 if field == 'risk_hash' else 1
    with pytest.raises(Blocked):
        check(r, e, 200)


@pytest.mark.parametrize('now', [99, 500, True, 1.5])
def test_time_bound(now):
    r = fixture()
    with pytest.raises(Blocked):
        check(r, r, now)


def test_refs_distinct_and_exclusions_complete():
    r = fixture()
    r['sources']['dispatch']['source_ref'] = r['sources']['owner_grant']['source_ref']
    with pytest.raises(Blocked):
        check(r, r, 200)
    r = fixture()
    r['exclusions'].pop()
    with pytest.raises(Blocked):
        check(r, r, 200)


def test_extra_unknown_field_rejected():
    r = fixture()
    r['caller_claims_human'] = True
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('field', ['source_ref', 'content_hash'])
def test_owner_grant_is_same_exact_protected_review_action(field):
    r = fixture()
    r['sources']['protected_review'][field] = 'e' * 64
    with pytest.raises(Blocked):
        check(r, r, 200)


def test_revocation_epoch_upper_bound_independent_of_expectation():
    r = fixture()
    r['revocation_epoch'] = 2**40
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('role', SOURCE_KINDS)
def test_leading_zero_principal_id_even_with_correct_role_relations(role):
    r = fixture()
    r['sources'][role]['principal_id'] = '0' + r['sources'][role]['principal_id']
    if role in ('owner_grant', 'protected_review'):
        r['sources']['owner_grant']['principal_id'] = '0999003'
        r['sources']['protected_review']['principal_id'] = '0999003'
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('role', SOURCE_KINDS)
def test_unknown_field_inside_each_source(role):
    r = fixture()
    r['sources'][role]['caller_human_claim'] = True
    with pytest.raises(Blocked):
        check(r, r, 200)


def test_production_none_is_not_bool_false():
    r = fixture()
    r['production_enabled'] = None
    with pytest.raises(Blocked):
        check(r, r, 200)


@pytest.mark.parametrize('field', ['payload_hash', 'executor_sha'])
def test_uppercase_hex_pin_even_when_expected_and_review_head_agree(field):
    r = fixture()
    r['pins'][field] = r['pins'][field].upper()
    if field == 'executor_sha':
        r['reviewed_executor_sha'] = r['pins'][field]
    with pytest.raises(Blocked):
        check(r, r, 200)


def test_non_int_now_in_valid_time_window():
    r = fixture()
    with pytest.raises(Blocked):
        check(r, r, 200.0)
