"""Synthetic offline tests for approval_record (#256). No network, keys or real data."""
from copy import deepcopy

import pytest

import approval_record as ar
from people_core import Blocked, digest

T0 = 1_800_000_000


def h(tag):
    return digest({'synthetic': f'ZZ-{tag}'})


def pins():
    return {'owner': 'profile-999001', 'connection_id': 'ZZ-secondary',
            'operation': 'single_father_add_parent', 'payload_hash': h('payload'),
            'graph_hash': h('graph'), 'data_hash': h('data'), 'executor_sha': 'a' * 40,
            'workflow_sha': 'b' * 40, 'artifact_hash': h('artifact'), 'service_sha': 'c' * 40,
            'policy_hash': h('policy'), 'recipient': h('recipient'), 'run_id': '1234567890',
            'run_attempt': 1, 'nonce': h('nonce'), 'issued_at': T0, 'expires_at': T0 + 600}


APPROVERS = {'owner': {'approver_ref': h('owner-approver'), 'evidence_ref': h('owner-evidence')},
             'human_reviewer': {'approver_ref': h('reviewer-approver'),
                                'evidence_ref': h('reviewer-evidence')}}


def approvers():
    return deepcopy(APPROVERS)


def record():
    return {'schema_version': 1, 'mode': 'offline_approval_record', 'production_enabled': False,
            'pins': pins(), 'exclusions': list(ar.EXCLUDED_ACTIONS),
            'approvals': [{'role': role, **APPROVERS[role]} for role in ar.ROLES]}


def approvers_default():
    return deepcopy(APPROVERS)


def run(rec=None, expected=None, approvers=None, now=T0 + 60):
    return ar.check(rec if rec is not None else record(),
                    expected if expected is not None else pins(),
                    approvers if approvers is not None else approvers_default(), now)


def test_consistent_result_is_exact_and_grants_nothing():
    rec = record()
    assert run(rec) == {'mode': 'offline_approval_record', 'content_consistent': True,
                        'authenticated': False, 'post_permitted': False,
                        'production_enabled': False, 'record_hash': digest(rec)}


def test_inputs_not_mutated():
    rec, exp, appr = record(), pins(), approvers()
    before = deepcopy((rec, exp, appr))
    run(rec, exp, appr)
    assert (rec, exp, appr) == before


# Each pin, altered on the record alone, on the expectation alone, or both, blocks.

def altered(key, value):
    if key in ('issued_at', 'expires_at'):
        return value + 1
    if key == 'run_attempt':
        return 2
    if key == 'run_id':
        return '1234567891'
    if key == 'owner':
        return 'profile-999009'
    if key == 'connection_id':
        return 'ZZ-other'
    if key == 'operation':
        return 'single_mother_add_parent'
    return value[:-1] + ('0' if value[-1] != '0' else '1')


@pytest.mark.parametrize('key', ar.PIN_KEYS)
@pytest.mark.parametrize('where', ['record', 'expected', 'both'])
def test_each_pin_mismatch_blocks(key, where):
    rec, exp = record(), pins()
    new = altered(key, exp[key])
    if where in ('record', 'both'):
        rec['pins'][key] = new
    if where in ('expected', 'both'):
        exp[key] = new
    if where == 'both' and key not in ('run_attempt', 'operation'):
        # Same change on both sides is consistent content: still never a permission.
        assert run(rec, exp)['post_permitted'] is False
        return
    with pytest.raises(Blocked):
        run(rec, exp)


@pytest.mark.parametrize('key', ar.PIN_KEYS)
def test_each_pin_wrong_type_blocks(key):
    rec = record()
    rec['pins'][key] = True if key not in ('run_attempt',) else '1'
    with pytest.raises(Blocked):
        run(rec)


@pytest.mark.parametrize('key', ['payload_hash', 'recipient', 'nonce'])
@pytest.mark.parametrize('bad', ['A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, 'a' * 63 + '\n'])
def test_hash_shape(key, bad):
    rec, exp = record(), pins()
    rec['pins'][key] = exp[key] = bad
    with pytest.raises(Blocked):
        run(rec, exp)


@pytest.mark.parametrize('key', ['executor_sha', 'workflow_sha', 'service_sha'])
def test_sha_pins_are_exact_40_hex(key):
    rec, exp = record(), pins()
    rec['pins'][key] = exp[key] = 'a' * 64
    with pytest.raises(Blocked):
        run(rec, exp)


def test_missing_or_extra_pin_blocks():
    for mutate in (lambda p: p.pop('nonce'), lambda p: p.update(extra='x')):
        rec = record()
        mutate(rec['pins'])
        with pytest.raises(Blocked):
            run(rec)
        exp = pins()
        mutate(exp)
        with pytest.raises(Blocked):
            run(expected=exp)


# Approval roles

@pytest.mark.parametrize('role_index', [0, 1])
@pytest.mark.parametrize('field', ['approver_ref', 'evidence_ref', 'role'])
def test_each_approval_field_altered_blocks(role_index, field):
    rec = record()
    approval = rec['approvals'][role_index]
    approval[field] = 'operator' if field == 'role' else h(f'other-{field}')
    with pytest.raises(Blocked):
        run(rec)


@pytest.mark.parametrize('role', ar.ROLES)
@pytest.mark.parametrize('field', ['approver_ref', 'evidence_ref'])
def test_expected_approval_mismatch_blocks(role, field):
    appr = approvers()
    appr[role][field] = h('someone-else')
    with pytest.raises(Blocked):
        run(approvers=appr)


@pytest.mark.parametrize('role', ar.ROLES)
def test_expected_approval_entry_exact_keys(role):
    appr = approvers()
    appr[role]['extra'] = 'x'
    with pytest.raises(Blocked):
        run(approvers=appr)


def test_self_review_blocks():
    rec = record()
    rec['approvals'][1]['approver_ref'] = APPROVERS['owner']['approver_ref']
    appr = approvers()
    appr['human_reviewer']['approver_ref'] = APPROVERS['owner']['approver_ref']
    with pytest.raises(Blocked):
        run(rec, approvers=appr)


def test_shared_evidence_blocks():
    rec = record()
    rec['approvals'][1]['evidence_ref'] = rec['approvals'][0]['evidence_ref']
    appr = approvers()
    appr['human_reviewer']['evidence_ref'] = APPROVERS['owner']['evidence_ref']
    with pytest.raises(Blocked):
        run(rec, approvers=appr)


@pytest.mark.parametrize('mutate', [
    lambda a: a.pop(),  # missing reviewer
    lambda a: a.append(deepcopy(a[1])),  # extra approval
    lambda a: a.reverse(),  # roles out of order
    lambda a: a[0].update(extra='x'),
    lambda a: a[0].pop('evidence_ref'),
])
def test_approval_list_shape(mutate):
    rec = record()
    mutate(rec['approvals'])
    with pytest.raises(Blocked):
        run(rec)


def test_expected_approvers_exact_keys():
    for appr in ({'owner': APPROVERS['owner']}, {**APPROVERS, 'operator': APPROVERS['owner']}):
        with pytest.raises(Blocked):
            run(approvers=appr)


# Timing

@pytest.mark.parametrize('now,ok', [(T0, True), (T0 + 599, True), (T0 + 600, False),
                                    (T0 - 1, False), (T0 + 10_000, False)])
def test_time_window_edges(now, ok):
    if ok:
        assert run(now=now)['content_consistent'] is True
    else:
        with pytest.raises(Blocked):
            run(now=now)


@pytest.mark.parametrize('window,ok', [(1, True), (900, True), (901, False), (0, False),
                                       (-5, False)])
def test_window_length_bounded(window, ok):
    rec, exp = record(), pins()
    rec['pins']['expires_at'] = exp['expires_at'] = T0 + window
    if ok:
        assert run(rec, exp, now=T0)['content_consistent'] is True
    else:
        with pytest.raises(Blocked):
            run(rec, exp, now=T0)


@pytest.mark.parametrize('now', [True, float(T0 + 1), str(T0 + 1), 0, 2**40, None])
def test_now_must_be_bounded_int(now):
    with pytest.raises(Blocked):
        run(now=now)


# Exclusions and envelope

@pytest.mark.parametrize('mutate', [
    lambda e: e.pop(), lambda e: e.append('add_father'), lambda e: e.reverse(),
    lambda e: e.__setitem__(0, 'add_child '), lambda e: e.clear(),
])
def test_exclusions_exact(mutate):
    rec = record()
    mutate(rec['exclusions'])
    with pytest.raises(Blocked):
        run(rec)


def test_exclusions_tuple_not_list_blocks():
    rec = record()
    rec['exclusions'] = tuple(rec['exclusions'])
    with pytest.raises(Blocked):
        run(rec)


@pytest.mark.parametrize('key,value', [('schema_version', 2), ('schema_version', True),
                                       ('mode', 'live'), ('production_enabled', True),
                                       ('production_enabled', 0)])
def test_envelope_exact(key, value):
    rec = record()
    rec[key] = value
    with pytest.raises(Blocked):
        run(rec)


def test_extra_or_missing_record_key_blocks():
    for mutate in (lambda r: r.update(approved=True), lambda r: r.pop('exclusions')):
        rec = record()
        mutate(rec)
        with pytest.raises(Blocked):
            run(rec)


@pytest.mark.parametrize('window', [0, -5])
def test_validate_alone_rejects_empty_window(window):
    rec = record()
    rec['pins']['expires_at'] = T0 + window
    with pytest.raises(Blocked):
        ar.validate(rec)


# Review follow-ups (#261): the same invalid value on BOTH record and expectation,
# so only the shape guard can block, plus validate-alone checks.

def both(key, value):
    rec, exp = record(), pins()
    rec['pins'][key] = exp[key] = value
    return rec, exp


@pytest.mark.parametrize('key,value', [
    ('owner', 'person-999001'), ('owner', 'profile-0'), ('owner', '../profile-1'),
    ('connection_id', '../path'), ('connection_id', 'ZZ secondary'), ('connection_id', ''),
    ('connection_id', 'x' * 101),
    ('run_id', '0'), ('run_id', '01'), ('run_id', '1' * 21), ('run_id', '-1'),
])
def test_identity_syntax_guards_with_matching_expectation(key, value):
    rec, exp = both(key, value)
    with pytest.raises(Blocked):
        run(rec, exp)
    with pytest.raises(Blocked):
        ar.validate(rec)


@pytest.mark.parametrize('issued,expires', [(0, 600), (-600, 0), (2**40 - 600, 2**40),
                                            (2**40, 2**40 + 600)])
def test_time_bounds_with_matching_expectation(issued, expires):
    rec, exp = record(), pins()
    for target in (rec['pins'], exp):
        target['issued_at'], target['expires_at'] = issued, expires
    with pytest.raises(Blocked):
        run(rec, exp, now=max(issued, 1))
    with pytest.raises(Blocked):
        ar.validate(rec)


@pytest.mark.parametrize('role', ar.ROLES)
@pytest.mark.parametrize('field', ['approver_ref', 'evidence_ref'])
def test_approval_hash_shape_with_matching_expectation(role, field):
    rec, appr = record(), approvers()
    index = ar.ROLES.index(role)
    rec['approvals'][index][field] = appr[role][field] = 'ZZ-not-a-hash'
    with pytest.raises(Blocked):
        run(rec, approvers=appr)
    with pytest.raises(Blocked):
        ar.validate(rec)
