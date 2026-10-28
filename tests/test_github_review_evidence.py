import copy
import hashlib
import json
from pathlib import Path

import pytest

from github_review_evidence import LIMIT, inspect, requests
from people_core import Blocked


def fixture():
    pins = {'owner': 'ZZ-owner', 'repo': 'ZZ-repo', 'repository_id': 41, 'run_id': 42, 'attempt': 1,
                'environment': 'ZZ-human', 'environment_id': 43, 'sha': 'a'*40, 'branch': 'ZZ-main',
                'workflow': '.github/workflows/ZZ-human.yml', 'actor_id': 44, 'reviewer_id': 45}
    repo = {'id': 41, 'full_name': 'ZZ-owner/ZZ-repo'}
    run = {'id': 42, 'run_attempt': 1, 'head_sha': 'a'*40, 'head_branch': 'ZZ-main',
               'path': pins['workflow'], 'event': 'workflow_dispatch', 'actor': {'id': 44},
               'triggering_actor': {'id': 44}, 'repository': repo, 'head_repository': copy.deepcopy(repo)}
    env = {'id': 43, 'name': 'ZZ-human', 'can_admins_bypass': False, 'protection_rules': [
        {'type': 'required_reviewers', 'prevent_self_review': True,
         'reviewers': [{'type': 'User', 'reviewer': {'id': 45}}]}, {'type': 'branch_policy'}],
        'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}
    approvals = [{'state': 'approved', 'user': {'id': 45, 'type': 'User'},
                  'environments': [{'id': 43, 'name': 'ZZ-human'}], 'comment': 'ZZ ignored'}]
    branches = {'total_count': 1, 'branch_policies': [{'name': 'ZZ-main', 'type': 'branch'}]}
    data = [run, env, approvals, branches]
    return pins, data


def envelopes(pins, data):
    return [{'request': d, 'status': 200, 'redirected': False, 'link': None,
                 'raw': json.dumps(value).encode()} for d, value in zip(requests(pins), data)]


def test_consistent_snapshot_is_never_authority():
    p, data = fixture()
    result = inspect(p, envelopes(p, data))
    assert result == {'phase': 'synthetic_review_snapshot_consistent', 'production_enabled': False,
                         'provenance_verified': False, 'owner_approval_verified': False,
                         'payload_approval_verified': False, 'job_review_correlation_verified': False,
                         'retry_allowed': False}
    data[2][0]['comment'] = 'ZZ arbitrary approval-looking content ignored'
    assert inspect(p, envelopes(p, data)) == result


def paths(value, prefix=()):
    if isinstance(value, dict):
        for key, leaf in value.items():
            yield from paths(leaf, prefix+(key,))
    elif isinstance(value, list):
        for key, leaf in enumerate(value):
            yield from paths(leaf, prefix+(key,))
    else:
        yield prefix


DATA_PATHS = [path for path in paths(fixture()[1]) if path != (2, 0, 'comment')]


@pytest.mark.parametrize('path', DATA_PATHS)
@pytest.mark.parametrize('bad', [None, True, False, 0, -1, 'ZZ-wrong', [], {}])
def test_every_binding_leaf_fails_closed(path, bad):
    p, data = fixture()
    target = data
    for key in path[:-1]:
        target = target[key]
    original = target[path[-1]]
    if type(original) is type(bad) and original == bad:
        return
    target[path[-1]] = bad
    with pytest.raises(Blocked, match='^GitHub evidence blocked; review protected inputs$'):
        inspect(p, envelopes(p, data))


@pytest.mark.parametrize('path', DATA_PATHS)
def test_missing_binding_leaf_blocks(path):
    p, data = fixture()
    target = data
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    with pytest.raises(Blocked):
        inspect(p, envelopes(p, data))


@pytest.mark.parametrize('field', list(fixture()[0]))
@pytest.mark.parametrize('bad', [None, True, False, 0, -1, '../ZZ', 'https://ZZ', 'ZZ?token=ZZ', [], {}])
def test_untrusted_pin_shapes_never_create_routes(field, bad):
    p, _ = fixture()
    p[field] = bad
    with pytest.raises(Blocked):
        requests(p)


@pytest.mark.parametrize('index', range(4))
@pytest.mark.parametrize('field,bad', [('status', 302), ('status', True), ('redirected', True),
                                     ('link', '<https://ZZ>; rel=next'), ('raw', b''),
                                     ('raw', b'{"x":1,"x":2}'), ('raw', b'\xff'),
                                     ('raw', b'[]'*600), ('raw', b'x'*(LIMIT+1)),
                                     ('raw', b'NaN'), ('request', {})])
def test_transport_envelopes_are_strict(index, field, bad):
    p, data = fixture()
    responses = envelopes(p, data)
    responses[index][field] = bad
    with pytest.raises(Blocked):
        inspect(p, responses)


@pytest.mark.parametrize('index,key', [(1, 'protection_rules'), (2, None), (3, 'branch_policies')])
def test_ambiguous_multiple_records_rejected(index, key):
    p, data = fixture()
    array = data[index] if key is None else data[index][key]
    array.append(copy.deepcopy(array[0]))
    with pytest.raises(Blocked):
        inspect(p, envelopes(p, data))


def test_attempt_replay_self_review_unknown_pins_and_route_injection():
    for field, bad in [('attempt', 2), ('reviewer_id', 44), ('environment', 'ZZ/name'),
                       ('sha', 'A'*40), ('workflow', '.github/workflows/../ZZ.yml'),
                       ('unknown', 'ZZ')]:
        p, _ = fixture()
        p[field] = bad
        with pytest.raises(Blocked):
            requests(p)


def test_document_contract_pin():
    text = (Path(__file__).resolve().parents[1]/'docs/github-review-evidence.md').read_text()
    assert hashlib.sha256(' '.join(text.split()).encode()).hexdigest() == '52979dea5783a8556d4b05f998424ea984be2573d888625c36875068da560862'
