"""Synthetic offline tests for profile_outcome_model (#244). No network, no real data."""
from copy import deepcopy

import pytest

import profile_outcome_model as pom
from parent_intent_model import advance, consume
from people_core import Blocked, digest

ART = 'a' * 64
ART2 = 'b' * 64
URL = 'https://www.example.test/people/ZZ-Example/999002'


def ev(n):
    return digest({'synthetic_event': f'ZZ-{n}'})


def intent(phase='verified'):
    binding = {'owner': 'profile-999001', 'connection_id': 'ZZ-secondary',
               'operation': 'single_father_add_parent', 'plan_hash': '1' * 64,
               'payload_hash': '2' * 64, 'artifact_hash': '3' * 64, 'policy_hash': '4' * 64}
    state = consume(binding, 0)
    if phase == 'consumed':
        return state
    if phase == 'uncertain':
        return advance(state, 1, 'uncertain', ev('i1'))
    state = advance(state, 1, 'acknowledge', ev('i1'), 'profile-999002')
    if phase == 'verified':
        state = advance(state, 2, 'verify', ev('i2'))
    return state


def verified_record():
    return pom.from_intent(intent())


def uploaded(record=None, art=ART, n=0):
    record = record or verified_record()
    record = pom.add_stage(record, 'source_upload', f'ZZ approve upload {art} {n}', art)
    i = len(record['stages']) - 1
    record = pom.advance_stage(record, i, 'approved', 'consume')
    record = pom.advance_stage(record, i, 'consumed', 'acknowledge', ev(f'u{n}a'),
                               'document-' + str(500 + n))
    return pom.advance_stage(record, i, 'acknowledged', 'verify', ev(f'u{n}v'))


# Record creation and the profile

def test_from_intent_exact_record():
    assert verified_record() == {
        'schema_version': 1, 'mode': 'offline_outcome_model', 'production_enabled': False,
        'intent_binding_hash': intent()['binding_hash'],
        'profile': {'created_id': 'profile-999002', 'phase': 'verified', 'url': None,
                    'url_state': 'pending'},
        'stages': []}


@pytest.mark.parametrize('phase', ['consumed', 'uncertain'])
def test_no_record_without_known_created_profile(phase):
    with pytest.raises(Blocked):
        pom.from_intent(intent(phase))


def test_no_record_from_uncertain_intent_even_with_known_id():
    state = advance(intent('acknowledged'), 2, 'uncertain', ev('i2'))
    assert state['created_id'] == 'profile-999002'
    with pytest.raises(Blocked):
        pom.from_intent(state)


def test_verified_url_requires_verified_profile():
    record = pom.from_intent(intent('acknowledged'))
    record['profile'].update(url=URL, url_state='verified')
    with pytest.raises(Blocked):
        pom.validate(record)


def test_acknowledged_only_is_not_verified_and_blocks_stages():
    record = pom.from_intent(intent('acknowledged'))
    assert record['profile']['phase'] == 'acknowledged'
    assert pom.outcome(record) == 'profile_unverified'
    for kind in pom.KINDS:
        with pytest.raises(Blocked):
            pom.add_stage(record, kind, 'ZZ approval', ART)
    with pytest.raises(Blocked):
        pom.record_profile_url(record, URL, URL)


def test_sync_profile_mirrors_verified_intent_only():
    acked = intent('acknowledged')
    record = pom.from_intent(acked)
    with pytest.raises(Blocked):
        pom.sync_profile(record, acked)
    assert pom.sync_profile(record, advance(acked, 2, 'verify', ev('i2')))['profile']['phase'] \
        == 'verified'


def test_sync_profile_rejects_other_intent():
    record = pom.from_intent(intent('acknowledged'))
    other = intent()
    other_binding = {**other['binding'], 'plan_hash': '9' * 64}
    stranger = advance(advance(consume(other_binding, 0), 1, 'acknowledge', ev('x'),
                               'profile-999002'), 2, 'verify', ev('y'))
    with pytest.raises(Blocked):
        pom.sync_profile(record, stranger)


def test_success_from_create_alone_is_never_complete():
    record = verified_record()
    assert pom.outcome(record) == 'profile_created_source_pending'


# Profile URL

def test_url_accepted_only_from_response_confirmed_by_readback():
    record = pom.record_profile_url(verified_record(), URL, URL)
    assert record['profile']['url'] == URL and record['profile']['url_state'] == 'verified'


@pytest.mark.parametrize('readback', [None, URL + 'x', 'https://www.example.test/other'])
def test_url_readback_mismatch_blocked(readback):
    with pytest.raises(Blocked):
        pom.record_profile_url(verified_record(), URL, readback)


def test_no_url_in_response_is_its_own_state():
    record = pom.record_profile_url(verified_record(), None, None)
    assert record['profile'] == {'created_id': 'profile-999002', 'phase': 'verified',
                                 'url': None, 'url_state': 'not_in_response'}
    with pytest.raises(Blocked):
        pom.record_profile_url(verified_record(), None, URL)


def test_url_set_once():
    record = pom.record_profile_url(verified_record(), URL, URL)
    for args in [(URL, URL), (URL + '2', URL + '2'), (None, None)]:
        with pytest.raises(Blocked):
            pom.record_profile_url(record, *args)
    record = pom.record_profile_url(verified_record(), None, None)
    with pytest.raises(Blocked):
        pom.record_profile_url(record, URL, URL)


@pytest.mark.parametrize('bad', ['http://www.example.test/p', 'https://x y', '', 'https://\u05d0',
                                 'https://' + 'a' * 300, 7])
def test_url_shape(bad):
    with pytest.raises(Blocked):
        pom.record_profile_url(verified_record(), bad, bad)


# Stages and approvals

def test_approval_ref_is_digest_of_exact_text():
    assert pom.approval_ref('ZZ approve upload') == digest('ZZ approve upload')
    assert pom.approval_ref('ZZ approve upload') != pom.approval_ref('ZZ approve upload ')
    for bad in ['', '   ', None, 'x' * 4001]:
        with pytest.raises(Blocked):
            pom.approval_ref(bad)


def test_add_stage_targets_only_this_profile():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ approval 1', ART)
    assert record['stages'] == [{'kind': 'source_upload',
                                 'approval_ref': digest('ZZ approval 1'),
                                 'artifact_hash': ART, 'target': 'profile-999002',
                                 'phase': 'approved', 'object_id': None, 'evidence_refs': []}]
    tampered = deepcopy(record)
    tampered['stages'][0]['target'] = 'profile-999001'
    with pytest.raises(Blocked):
        pom.validate(tampered)


def test_no_duplicate_upload_even_with_new_approval():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ approval 1', ART)
    with pytest.raises(Blocked):
        pom.add_stage(record, 'source_upload', 'ZZ approval 2', ART)
    record = uploaded()
    with pytest.raises(Blocked):
        pom.add_stage(record, 'source_upload', 'ZZ approval again', ART)


def test_one_approval_one_stage():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ approval 1', ART)
    with pytest.raises(Blocked):
        pom.add_stage(record, 'source_upload', 'ZZ approval 1', ART2)


def test_tag_needs_verified_upload_of_same_artifact():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ approval 1', ART)
    with pytest.raises(Blocked):
        pom.add_stage(record, 'tag', 'ZZ tag', ART)
    record = uploaded()
    with pytest.raises(Blocked):
        pom.add_stage(record, 'tag', 'ZZ tag', ART2)
    record = pom.add_stage(record, 'tag', 'ZZ tag', ART)
    assert record['stages'][1]['kind'] == 'tag' and record['stages'][1]['phase'] == 'approved'


def test_verifying_a_stage_creates_no_next_stage():
    record = uploaded()
    assert len(record['stages']) == 1
    assert pom.outcome(record) == 'source_attached'


def test_fact_cite_is_unsupported_and_frozen():
    record = pom.add_stage(uploaded(), 'fact_cite', 'ZZ cite', ART)
    assert record['stages'][1]['phase'] == 'unsupported'
    for phase in pom.STAGE_PHASES:
        for event in ('consume', 'acknowledge', 'verify', 'uncertain', 'reconcile_verified'):
            with pytest.raises(Blocked):
                pom.advance_stage(record, 1, phase, event, ev('c'))
    tampered = deepcopy(record)
    tampered['stages'][1]['phase'] = 'verified'
    with pytest.raises(Blocked):
        pom.validate(tampered)


# Stage transitions

def test_full_upload_path_exact():
    record = uploaded()
    assert record['stages'][0] == {
        'kind': 'source_upload', 'approval_ref': digest(f'ZZ approve upload {ART} 0'),
        'artifact_hash': ART, 'target': 'profile-999002', 'phase': 'verified',
        'object_id': 'document-500', 'evidence_refs': [ev('u0a'), ev('u0v')]}


def test_acknowledged_upload_is_not_attached():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ a', ART)
    record = pom.advance_stage(record, 0, 'approved', 'consume')
    record = pom.advance_stage(record, 0, 'consumed', 'acknowledge', ev(1), 'document-7')
    assert pom.outcome(record) == 'profile_created_source_pending'


@pytest.mark.parametrize('start', ['consumed', 'acknowledged'])
def test_uncertain_finishes_only_by_reconciliation(start):
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ a', ART)
    record = pom.advance_stage(record, 0, 'approved', 'consume')
    if start == 'acknowledged':
        record = pom.advance_stage(record, 0, 'consumed', 'acknowledge', ev(1), 'document-7')
    record = pom.advance_stage(record, 0, start, 'uncertain', ev(2))
    assert pom.outcome(record) == 'partial_uncertain'
    for event in ('consume', 'acknowledge', 'verify', 'uncertain'):
        for obj in (None, 'document-7'):
            with pytest.raises(Blocked):
                pom.advance_stage(record, 0, 'uncertain', event, ev(3), obj)
    if start == 'acknowledged':
        with pytest.raises(Blocked):  # a known object ID cannot change
            pom.advance_stage(record, 0, 'uncertain', 'reconcile_verified', ev(3), 'document-8')
    record = pom.advance_stage(record, 0, 'uncertain', 'reconcile_verified', ev(3), 'document-7')
    assert record['stages'][0]['phase'] == 'verified'
    with pytest.raises(Blocked):
        pom.advance_stage(record, 0, 'verified', 'uncertain', ev(4))


def test_stale_expected_phase_and_bad_index_blocked():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ a', ART)
    for args in [(0, 'consumed', 'acknowledge', ev(1), 'document-7'), (1, 'approved', 'consume'),
                 (-1, 'approved', 'consume'), (True, 'approved', 'consume')]:
        with pytest.raises(Blocked):
            pom.advance_stage(record, *args)


def test_evidence_refs_never_reused():
    record = uploaded()
    record = pom.add_stage(record, 'tag', 'ZZ tag', ART)
    record = pom.advance_stage(record, 1, 'approved', 'consume')
    with pytest.raises(Blocked):
        pom.advance_stage(record, 1, 'consumed', 'acknowledge', ev('u0a'))


def test_consume_takes_no_evidence_or_object():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ a', ART)
    for kwargs in [{'evidence_ref': ev(1)}, {'object_id': 'document-7'}]:
        with pytest.raises(Blocked):
            pom.advance_stage(record, 0, 'approved', 'consume', **kwargs)


def test_upload_ack_needs_object_id_tag_ack_refuses_one():
    record = pom.add_stage(verified_record(), 'source_upload', 'ZZ a', ART)
    record = pom.advance_stage(record, 0, 'approved', 'consume')
    for obj in [None, 'profile-7', 'document-07', 'photo-']:
        with pytest.raises(Blocked):
            pom.advance_stage(record, 0, 'consumed', 'acknowledge', ev(1), obj)
    tagged = pom.advance_stage(pom.add_stage(uploaded(), 'tag', 'ZZ t', ART), 1, 'approved',
                               'consume')
    with pytest.raises(Blocked):
        pom.advance_stage(tagged, 1, 'consumed', 'acknowledge', ev(1), 'document-500')


def test_outcome_progression_to_sources_tagged():
    record = pom.add_stage(uploaded(), 'tag', 'ZZ t', ART)
    assert pom.outcome(record) == 'source_attached'
    record = pom.advance_stage(record, 1, 'approved', 'consume')
    record = pom.advance_stage(record, 1, 'consumed', 'acknowledge', ev('t1'))
    assert pom.outcome(record) == 'source_attached'
    record = pom.advance_stage(record, 1, 'acknowledged', 'verify', ev('t2'))
    assert pom.outcome(record) == 'sources_tagged'
    record = pom.add_stage(record, 'fact_cite', 'ZZ cite', ART)
    assert pom.outcome(record) == 'sources_tagged'  # citations never count as done
    record = pom.add_stage(record, 'source_upload', 'ZZ second', ART2)
    assert pom.outcome(record) == 'profile_created_source_pending'


# Validation and isolation

@pytest.mark.parametrize('mutate', [
    lambda r: r.update(extra=1), lambda r: r.update(production_enabled=True),
    lambda r: r.update(schema_version=2), lambda r: r.update(mode='live'),
    lambda r: r['profile'].update(created_id='profile-0'),
    lambda r: r['profile'].update(url=URL),
    lambda r: r['profile'].update(url_state='verified'),
    lambda r: r['profile'].update(name='ZZ Name'),
    lambda r: r['stages'][0].update(evidence_refs=[]),
    lambda r: r['stages'][0].update(object_id=None),
    lambda r: r['stages'][0].update(phase='approved'),
    lambda r: r['stages'].append(deepcopy(r['stages'][0])),
])
def test_validate_rejects_drift(mutate):
    record = uploaded()
    mutate(record)
    with pytest.raises(Blocked):
        pom.validate(record)


def test_inputs_and_outputs_are_copies():
    record = verified_record()
    before = deepcopy(record)
    result = pom.add_stage(record, 'source_upload', 'ZZ a', ART)
    assert record == before
    result['stages'][0]['phase'] = 'verified'
    again = pom.add_stage(record, 'source_upload', 'ZZ a', ART)
    assert again['stages'][0]['phase'] == 'approved'


def test_record_holds_no_names_or_payload():
    record = pom.add_stage(pom.record_profile_url(uploaded(), URL, URL), 'tag', 'ZZ t', ART)
    flat = repr(record)
    # Approval texts all start with 'ZZ'; only the synthetic URL path may carry it.
    assert 'ZZ' not in flat.replace('ZZ-Example', '')
