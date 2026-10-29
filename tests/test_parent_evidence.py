import copy
import socket

import pytest

import parent_evidence as p

OWNER = 'profile-99123'
PROFILE = {'id': OWNER, 'merge_pending': False}
DATA = {'self': PROFILE, 'owner': PROFILE,
        'family': {'focus': PROFILE, 'nodes': {}}, 'unions': []}


def test_empty_graph_is_never_absence_or_ready(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket, 'socket', deny)
    result = p.review(DATA, OWNER)
    assert result['observed_parent_count'] == 0
    assert result['create_enabled'] is False
    assert result['hidden_parent_completeness'] == 'unproved'
    with pytest.raises(p.Blocked): p.collect('ZZsecret')


def parents():
    data = copy.deepcopy(DATA)
    data['family']['nodes'] = {'profile-99222': {'id': 'profile-99222',
                                              'public': False, 'is_alive': True}}
    data['unions'] = [{'id': 'union-99111', 'children': [OWNER],
                       'partners': ['profile-99222']}]
    return data


def test_observed_parent_is_not_slot_or_completeness_proof():
    result = p.review(parents(), OWNER)
    assert result['observed_parent_count'] == 1
    assert result['explicit_private_life_readback_count'] == 1
    assert result['add_parent_slot_semantics'] == 'unproved'


@pytest.mark.parametrize('field,value', [('public', None), ('public', True),
                                       ('public', 0), ('is_alive', 1), ('is_alive', None)])
def test_missing_or_wrong_type_privacy_never_defaults_false(field, value):
    data = parents()
    data['family']['nodes']['profile-99222'][field] = value
    assert p.review(data, OWNER)['explicit_private_life_readback_count'] == 0


@pytest.mark.parametrize('change', ['wrong_owner', 'merged', 'missing_parent',
                                  'extra', 'duplicate', 'bad_node', 'unbounded'])
def test_reject_malformed_or_inconsistent_evidence(change):
    data = parents()
    if change == 'wrong_owner': data['self'] = {'id': 'profile-99555'}
    if change == 'merged': data['self'] = {**PROFILE, 'merge_pending': True}
    if change == 'missing_parent': data['family']['nodes'] = {}
    if change == 'extra': data['next_page'] = 'ZZunexpected'
    if change == 'duplicate': data['unions'][0]['partners'] *= 2
    if change == 'bad_node': data['unions'][0]['partners'] = ['ZZunknown']
    if change == 'unbounded': data['unions'] *= 11
    with pytest.raises(p.Blocked): p.review(data, OWNER)


def test_private_sentinels_never_in_summary_or_error():
    data = parents()
    data['family']['nodes']['profile-99222']['name'] = 'ZZPrivateSentinel'
    result = str(p.review(data, OWNER))
    assert 'ZZPrivateSentinel' not in result and OWNER not in result and '99222' not in result
    data['self'] = {'id': 'ZZPrivateSentinel'}
    with pytest.raises(p.Blocked) as error: p.review(data, OWNER)
    assert 'ZZPrivateSentinel' not in str(error.value)


def test_duplicate_union_id_rejected():
    data = parents()
    data['unions'] *= 2
    with pytest.raises(p.Blocked): p.review(data, OWNER)


@pytest.mark.parametrize('field', ['nodes', 'children', 'partners'])
def test_hundred_record_bounds(field):
    data = copy.deepcopy(DATA)
    if field == 'nodes':
        data['family']['nodes'] = {f'profile-{i}': {'id': f'profile-{i}'} for i in range(100)}
    else:
        data['unions'] = [{'id': 'union-99111', 'children': [], 'partners': []}]
        data['unions'][0][field] = [f'profile-{i}' for i in range(100)]
    assert p.review(data, OWNER)['create_enabled'] is False
    if field == 'nodes':
        data['family']['nodes']['profile-100'] = {'id': 'profile-100'}
    else:
        data['unions'][0][field].append('profile-100')
    with pytest.raises(p.Blocked): p.review(data, OWNER)
