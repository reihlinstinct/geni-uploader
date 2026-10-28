import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from people_core import Blocked
from workflow_content_contract import LIMIT, RESPONSE_LIMIT, descriptor, verify


def fixture():
    raw = b'name: ZZ-synthetic\njobs: {}\n'
    sha = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    pins = {'owner': 'ZZ-owner', 'repo': 'ZZ-repo', 'commit': 'a'*40,
            'filename': 'ZZ-human.yml', 'workflow_sha256': hashlib.sha256(raw).hexdigest()}
    data = [{'sha': 'a'*40, 'tree': {'sha': 'b'*40}},
            {'sha': 'b'*40, 'truncated': False, 'tree': [
                {'path': '.github', 'mode': '040000', 'type': 'tree', 'sha': 'c'*40}]},
            {'sha': 'c'*40, 'truncated': False, 'tree': [
                {'path': 'workflows', 'mode': '040000', 'type': 'tree', 'sha': 'd'*40}]},
            {'sha': 'd'*40, 'truncated': False, 'tree': [
                {'path': 'ZZ-human.yml', 'mode': '100644', 'type': 'blob', 'sha': sha}]},
            {'sha': sha, 'encoding': 'base64', 'size': len(raw),
             'content': base64.b64encode(raw).decode()}]
    routes = [descriptor(pins, 'commits')] + [descriptor(pins, 'trees', c*40) for c in 'bcd']
    routes += [descriptor(pins, 'blobs', sha)]
    return pins, data, routes


def envelopes(data, routes):
    return [{'request': route, 'status': 200, 'redirected': False, 'link': None,
             'raw': json.dumps(value).encode()} for value, route in zip(data, routes)]


def test_bytes_match_never_proves_authority():
    pins, data, routes = fixture()
    result = verify(pins, envelopes(data, routes))
    assert result == {'phase': 'synthetic_workflow_bytes_match',
                      'workflow_sha256': pins['workflow_sha256'], 'blob_sha': data[4]['sha'],
                      'production_enabled': False, 'provenance_verified': False,
                      'workflow_semantics_verified': False, 'owner_approval_verified': False,
                      'job_review_correlation_verified': False}
    data[4]['content'] += '\n'
    assert verify(pins, envelopes(data, routes)) == result


def paths(value, prefix=()):
    if isinstance(value, dict):
        for key, leaf in value.items():
            yield from paths(leaf, prefix+(key,))
    elif isinstance(value, list):
        for key, leaf in enumerate(value):
            yield from paths(leaf, prefix+(key,))
    else:
        yield prefix


DATA_PATHS = list(paths(fixture()[1]))


@pytest.mark.parametrize('path', DATA_PATHS)
@pytest.mark.parametrize('bad', [None, True, False, 0, -1, [], {}, 'ZZ-wrong'])
def test_every_binding_leaf_rejected(path, bad):
    p, data, routes = fixture()
    target = data
    for key in path[:-1]:
        target = target[key]
    if type(target[path[-1]]) is type(bad) and target[path[-1]] == bad:
        return
    target[path[-1]] = bad
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('path', DATA_PATHS)
def test_every_missing_binding_leaf_rejected(path):
    p, data, routes = fixture()
    target = data
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('field', list(fixture()[0]))
@pytest.mark.parametrize('bad', [None, True, False, '../ZZ', 'https://ZZ', 'ZZ?x=ZZ', [], {}, 'A'*40])
def test_pins_never_accept_url_or_branch_ref(field, bad):
    p, _, _ = fixture()
    # Uppercase valid owner/repo/filename still have legal syntax, unlike SHA pins.
    if bad == 'A'*40 and field in ('owner', 'repo'):
        return
    p[field] = bad
    with pytest.raises(Blocked):
        descriptor(p, 'commits')


@pytest.mark.parametrize('index', range(5))
@pytest.mark.parametrize('field,bad', [('status', 302), ('status', True), ('redirected', True),
                                     ('link', 'ZZ-next'), ('request', {}), ('raw', b'NaN'),
                                     ('raw', b'{"x":1,"x":2}'), ('raw', b'\xff'),
                                     ('raw', b'x'*(RESPONSE_LIMIT+1))])
def test_transport_metadata_and_raw_bounds(index, field, bad):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[index][field] = bad
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('index', [1, 2, 3])
@pytest.mark.parametrize('change', ['duplicate', 'missing', 'symlink', 'executable', 'submodule'])
def test_path_modes_and_ambiguity(index, change):
    p, data, routes = fixture()
    tree = data[index]['tree']
    if change == 'duplicate':
        tree.append(copy.deepcopy(tree[0]))
    elif change == 'missing':
        tree.clear()
    else:
        tree[0]['mode'], tree[0]['type'] = {
            'symlink': ('120000', 'blob'), 'executable': ('100755', 'blob'),
            'submodule': ('160000', 'commit')}[change]
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('bad', ['AA==', 'Zh==', 'ZA===', ' ZA==', 'ZA==\r\n', 'x'*(2*LIMIT+1)])
def test_base64_not_canonical_or_wrong_bytes(bad):
    p, data, routes = fixture()
    data[4]['content'] = bad
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_doc_pin():
    text = (Path(__file__).resolve().parents[1]/'docs/workflow-content-contract.md').read_text()
    assert hashlib.sha256(' '.join(text.split()).encode()).hexdigest() == '1e5442746448762ea66136e2d2314cdc728e649a9dc7a854c49e50ac890a437f'
