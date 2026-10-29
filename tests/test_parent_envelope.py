import copy
import socket

import pytest

import parent_envelope as p
from human_parent_gate import PROOFS
from parent_plan import proposal
from people_core import Blocked, digest
from tests.test_parent_plan import PINS
from tests.test_parent_runner import inputs


def fixture():
    data, _ = inputs(True)
    for parent in data['parents']: parent['gender'] = 'male'
    plan = proposal(data, PINS)
    value = {'owner': 'profile-' + data['owner']['node'], 'connection_id': 'ZZisolated',
             'operator': data['operator'], 'consent_refs': ['ZZconsent:1'],
             'manifest_hash': plan['manifest_hash'],
             'payload_hashes': [e['payload_hash'] for e in plan['entries']],
             'graph_hash': 'd'*64, 'data_sha': PINS['data_sha'],
             'executor_sha': PINS['workflow_sha'], 'image_digest': PINS['image_digest'],
             'journal_version': 0, 'plan_id': 'e'*64, 'created': 1000, 'expires': 1900,
             'count': 2}
    value['proof_refs'] = {key: {'content_hash': 'f'*64,
                               **{k: value[k] for k in ('owner', 'connection_id', 'manifest_hash')}}
                           for key in PROOFS}
    return plan, value


def test_matching_offline_draft_never_authenticates_or_enables(monkeypatch):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network forbidden'))
    plan, value = fixture()
    envelope = p.draft(plan, value)
    value['operator'] = 'ZZchanged'
    assert envelope['binding']['operator'] != value['operator']
    result = p.review(envelope, plan, envelope['binding'], 1000)
    assert result['status'] == 'offline_binding_matches_only'
    for field in ('creation_enabled', 'source_authenticated', 'signature_verified', 'replay_enforced'):
        assert result[field] is False
    # Same supplied input can pass twice: no replay enforcement is claimed.
    assert p.review(envelope, plan, envelope['binding'], 1001) == result


@pytest.mark.parametrize('field', p.BINDING_KEYS)
def test_any_candidate_binding_change_rejected_even_rehashed(field):
    plan, value = fixture()
    envelope = p.draft(plan, value)
    envelope['binding'][field] = None
    envelope['envelope_hash'] = digest({k: v for k, v in envelope.items() if k != 'envelope_hash'})
    with pytest.raises(Blocked): p.review(envelope, plan, value, 1100)


@pytest.mark.parametrize('field', ['creation_enabled', 'source_authenticated',
                                 'signature_verified', 'replay_enforced'])
def test_self_claimed_authority_rejected(field):
    plan, value = fixture()
    envelope = p.draft(plan, value)
    envelope[field] = True
    with pytest.raises(Blocked): p.review(envelope, plan, value, 1100)


@pytest.mark.parametrize('now', [999, 1900, True, '1100'])
def test_expired_future_or_bad_time(now):
    plan, value = fixture()
    with pytest.raises(Blocked): p.review(p.draft(plan, value), plan, value, now)


@pytest.mark.parametrize('change', ['missing-proof', 'unknown-proof', 'wrong-proof-owner',
                                  'wrong-proof-connection', 'wrong-proof-manifest',
                                  'unknown-hash', 'long-life', 'bool-version', 'bad-pin',
                                  'payload-order', 'wrong-count', 'duplicate-consent'])
def test_bad_bindings_or_unknown_references_never_form_draft(change):
    plan, value = fixture()
    if change == 'missing-proof': value['proof_refs'].pop(PROOFS[0])
    if change == 'unknown-proof': value['proof_refs'][PROOFS[0]]['content_hash'] = 'unknown'
    if change.startswith('wrong-proof-'):
        key = {'wrong-proof-owner': 'owner', 'wrong-proof-connection': 'connection_id',
               'wrong-proof-manifest': 'manifest_hash'}[change]
        value['proof_refs'][PROOFS[0]][key] = 'ZZwrong'
    if change == 'unknown-hash': value['graph_hash'] = None
    if change == 'long-life': value['expires'] = 1901
    if change == 'bool-version': value['journal_version'] = True
    if change == 'bad-pin': value['executor_sha'] = 'ZZbranch'
    if change == 'payload-order': value['payload_hashes'].reverse()
    if change == 'wrong-count': value['count'] = 1
    if change == 'duplicate-consent': value['consent_refs'] *= 2
    with pytest.raises(Blocked) as error: p.draft(plan, value)
    assert 'ZZ' not in str(error.value)


def test_changed_proposal_or_envelope_wrapper_blocked():
    plan, value = fixture()
    envelope = p.draft(plan, value)
    plan = copy.deepcopy(plan)
    plan['entries'][0]['proposed_payload']['public'] = True
    with pytest.raises(Blocked): p.review(envelope, plan, value, 1100)
    with pytest.raises(Blocked): p.review({'results': envelope}, plan, value, 1100)


def test_bool_schema_is_not_integer_schema():
    plan, value = fixture()
    envelope = p.draft(plan, value)
    envelope['schema_version'] = True
    with pytest.raises(Blocked): p.review(envelope, plan, value, 1100)


@pytest.mark.parametrize('field,bad', [('journal_version', False), ('count', 2.0),
                                     ('created', 1000.0), ('expires', 1900.0)])
@pytest.mark.parametrize('rehash', [False, True])
def test_candidate_numeric_type_tamper_cannot_pass_equality(field, bad, rehash):
    plan, value = fixture()
    envelope = p.draft(plan, value)
    envelope['binding'][field] = bad
    if rehash:
        envelope['envelope_hash'] = digest({k: v for k, v in envelope.items() if k != 'envelope_hash'})
    with pytest.raises(Blocked): p.review(envelope, plan, value, 1100)


@pytest.mark.parametrize('field,bad', [('readiness', 'unknown'), ('duplicate_status', 'unknown'),
                                     ('action', 'delete_person')])
def test_rehashed_proposal_entry_semantics_not_trusted(field, bad):
    plan, value = fixture()
    plan['entries'][0][field] = bad
    plan['proposal_hash'] = digest({k: v for k, v in plan.items() if k != 'proposal_hash'})
    with pytest.raises(Blocked): p.draft(plan, value)


@pytest.mark.parametrize('field,bad', [('public', True), ('gender', 'unknown'),
                                     ('names', None), ('first_name', 'ZZtampered')])
def test_rehashed_payload_cannot_evade_manifest_binding(field, bad):
    plan, value = fixture()
    entry = plan['entries'][0]
    entry['proposed_payload'][field] = bad
    entry['payload_hash'] = digest(entry['proposed_payload'])
    value['payload_hashes'][0] = entry['payload_hash']
    plan['proposal_hash'] = digest({k: v for k, v in plan.items() if k != 'proposal_hash'})
    with pytest.raises(Blocked): p.draft(plan, value)


@pytest.mark.parametrize('change', ['extra-proposal', 'extra-entry', 'anchor', 'payload-hash'])
def test_proposal_exact_schema_anchor_and_payload_hash(change):
    plan, value = fixture()
    if change == 'extra-proposal': plan['permit'] = True
    if change == 'extra-entry': plan['entries'][0]['permit'] = True
    if change == 'anchor': plan['entries'][0]['anchor'] = '99555'
    if change == 'payload-hash': plan['entries'][0]['payload_hash'] = 'f'*64
    plan['proposal_hash'] = digest({k: v for k, v in plan.items() if k != 'proposal_hash'})
    with pytest.raises(Blocked): p.draft(plan, value)
