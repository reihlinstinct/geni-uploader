import copy
import socket

import pytest

from parent_snapshot import parse
from people_core import Blocked

OWNER = 'profile-99123'
PROFILE = {'id': OWNER, 'merge_pending': False}
BASE = {'self': dict(PROFILE), 'owner': dict(PROFILE),
        'family': {'focus': dict(PROFILE), 'nodes': {OWNER: dict(PROFILE)}}, 'unions': []}


def test_empty_graph_never_proves_absence_or_authority(monkeypatch):
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network forbidden'))
    value = parse(BASE, OWNER)
    assert value['observed_parent_count'] == 0
    assert value['graph_status'] == 'observed_consistent_not_complete'
    assert value['hidden_parent_completeness'] == 'unknown'
    assert value['create_enabled'] is False and value['evidence_authenticated'] is False
    assert OWNER not in str(value)


@pytest.mark.parametrize('field', ['self', 'owner', 'focus'])
@pytest.mark.parametrize('flag,status', [(None, 'unknown'), (False, 'explicit_clear'),
                                       (True, 'blocked'), ('false', 'unknown'), (0, 'unknown')])
def test_unknown_merge_never_coerced(field, flag, status):
    data = copy.deepcopy(BASE)
    value = data['family']['focus'] if field == 'focus' else data[field]
    value.pop('merge_pending')
    if flag is not None: value['merge_pending'] = flag
    assert parse(data, OWNER)['merge_status'] == status
    assert parse(data, OWNER)['create_enabled'] is False


@pytest.mark.parametrize('change', ['absent', 'null', 'wrapper', 'pagination', 'hidden',
                                  'redacted', 'partial', 'missing-union'])
def test_unprovable_graph_is_unknown(change):
    data = copy.deepcopy(BASE)
    if change == 'absent': data['family'] = {}
    if change == 'null': data['family'] = None
    if change == 'wrapper': data['family'] = {'results': [BASE['family']]}
    if change == 'pagination': data['family']['next_page'] = 'https://ZZ.invalid'
    if change in ('hidden', 'redacted', 'partial'):
        data['family']['nodes'][OWNER][change] = True
    if change == 'missing-union': data['family']['nodes'][OWNER]['unions'] = ['union-99555']
    result = parse(data, OWNER)
    assert result['graph_status'] == 'unknown' and result['observed_parent_count'] is None
    assert result['create_enabled'] is False


@pytest.mark.parametrize('where', ['self', 'owner', 'focus'])
def test_mismatched_owner_blocks_without_values(where):
    data = copy.deepcopy(BASE)
    value = data['family']['focus'] if where == 'focus' else data[where]
    value['id'] = 'profile-99555'
    with pytest.raises(Blocked) as error: parse(data, OWNER)
    assert '99555' not in str(error.value)


def test_wrapped_owner_and_custody_bundle_are_not_snapshot():
    for bad in [{'results': BASE}, {**BASE, 'credential_storage_only': True}]:
        with pytest.raises(Blocked): parse(bad, OWNER)


def test_observed_parent_count_is_not_completeness():
    data = copy.deepcopy(BASE)
    parent, uid = 'profile-99222', 'union-99111'
    union = {'id': uid, 'partners': [parent], 'children': [OWNER],
             'adopted_children': [], 'foster_children': []}
    data['family']['nodes'].update({parent: {'id': parent}, uid: union})
    data['unions'] = [union]
    result = parse(data, OWNER)
    assert result['observed_parent_count'] == 1 and result['hidden_parent_completeness'] == 'unknown'
    data['family']['nodes'][uid] = {**union, 'partners': []}
    assert parse(data, OWNER)['graph_status'] == 'unknown'


@pytest.mark.parametrize('target', ['owner-node', 'parent-node', 'focus-no-id', 'unknown-self',
                                  'unknown-owner', 'missing-focus-id'])
def test_all_graph_merge_signals_and_unknown_fields_preserved(target):
    data = copy.deepcopy(BASE)
    if target == 'owner-node':
        data['family']['nodes'][OWNER]['merged_into'] = 'profile-99555'
    if target == 'parent-node':
        data['family']['nodes']['profile-99222'] = {
            'id': 'profile-99222', 'merged_into': 'profile-99555'}
    if target in ('focus-no-id', 'missing-focus-id'):
        data['family']['focus'].pop('id')
        if target == 'focus-no-id': data['family']['focus']['merge_pending'] = True
    if target.startswith('unknown-'):
        data[target.split('-')[1]]['ZZunknown'] = True
    result = parse(data, OWNER)
    expected = 'blocked' if target in ('owner-node', 'parent-node', 'focus-no-id') else 'unknown'
    assert result['merge_status'] == expected and result['create_enabled'] is False


@pytest.mark.parametrize('unions', [[[1]], [None], ['ZZinvalid']])
def test_non_object_union_is_value_free_blocked(unions):
    data = copy.deepcopy(BASE)
    data['unions'] = unions
    with pytest.raises(Blocked): parse(data, OWNER)


def test_total_input_budget_is_bounded():
    data = copy.deepcopy(BASE)
    data['family']['nodes'] = {f'profile-{99123+i}': {'id': f'profile-{99123+i}',
                              'names': {'en': {'first_name': 'ZZPerson'}}}
                              for i in range(101)}
    with pytest.raises(Blocked): parse(data, OWNER)
    # Small per-container limits still cannot multiply into an unbounded tree.
    data = copy.deepcopy(BASE)
    data['family']['ZZnested'] = [['ZZleaf']*100 for _ in range(100)]
    with pytest.raises(Blocked): parse(data, OWNER)


def test_counted_parent_merge_target_is_still_blocked():
    data = copy.deepcopy(BASE)
    parent, uid = 'profile-99222', 'union-99111'
    union = {'id': uid, 'partners': [parent], 'children': [OWNER],
             'adopted_children': [], 'foster_children': [], 'merge_pending': False}
    data['family']['nodes'].update({parent: {'id': parent, 'merged_into': 'profile-99555'},
                                  uid: {k: v for k, v in union.items() if k != 'merge_pending'}})
    data['unions'] = [{k: v for k, v in union.items() if k != 'merge_pending'}]
    result = parse(data, OWNER)
    assert result['observed_parent_count'] == 1
    assert result['merge_status'] == 'blocked' and result['create_enabled'] is False


@pytest.mark.parametrize('nested', [[[1]], [{}], [None], [1], ['ZZinvalid']])
def test_nested_union_reference_unknown_not_typeerror(nested):
    data = copy.deepcopy(BASE)
    data['family']['nodes'][OWNER]['unions'] = nested
    result = parse(data, OWNER)
    assert result['graph_status'] == 'unknown' and result['create_enabled'] is False


@pytest.mark.parametrize('change', ['partial', 'hidden', 'redacted', 'ZZunknown',
                                  'missing-id', 'noncanonical-key', 'mismatched-id'])
def test_unknown_or_invalid_graph_node_never_explicit_clear(change):
    data = copy.deepcopy(BASE)
    value = data['family']['nodes'][OWNER]
    if change == 'missing-id': value.pop('id')
    elif change == 'noncanonical-key':
        data['family']['nodes']['ZZkey'] = data['family']['nodes'].pop(OWNER)
    elif change == 'mismatched-id': value['id'] = 'profile-99555'
    else: value[change] = True
    result = parse(data, OWNER)
    assert result['merge_status'] == 'unknown' and result['graph_status'] == 'unknown'
    assert result['create_enabled'] is False
