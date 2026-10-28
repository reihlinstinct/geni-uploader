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
    assert hashlib.sha256(' '.join(text.split()).encode()).hexdigest() == '5e7dc389b6916024f2f718fbcc67d2166bb0b47f780f8c885e25488ff894baf5'


def set_blob(data, routes, pins, raw, *, update_pin=False):
    sha = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    data[3]['tree'][0]['sha'] = data[4]['sha'] = sha
    data[4]['size'], data[4]['content'] = len(raw), base64.b64encode(raw).decode()
    routes[4] = descriptor(pins, 'blobs', sha)
    if update_pin:
        pins['workflow_sha256'] = hashlib.sha256(raw).hexdigest()


def test_only_independently_pinned_sha256_rejects_changed_valid_blob():
    p, data, routes = fixture()
    set_blob(data, routes, p, b'ZZ-different exact workflow bytes')
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))
    p['workflow_sha256'] = hashlib.sha256(b'ZZ-different exact workflow bytes').hexdigest()
    assert verify(p, envelopes(data, routes))['production_enabled'] is False


def test_only_git_blob_header_and_content_hash_blocks_wrong_object_id():
    p, data, routes = fixture()
    raw = b'ZZ-replaced-content'
    p['workflow_sha256'] = hashlib.sha256(raw).hexdigest()
    data[4]['content'], data[4]['size'] = base64.b64encode(raw).decode(), len(raw)
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_only_reported_size_blocks_consistent_hashes():
    p, data, routes = fixture()
    data[4]['size'] += 1
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('path', ['ZZ/nested', 'ZZ\\nested', '..', '.', 'ZZ\x00'])
def test_invalid_sibling_path_is_not_ignored(path):
    p, data, routes = fixture()
    data[1]['tree'].append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': 'e'*40})
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_sibling_sha_shape_must_be_valid():
    p, data, routes = fixture()
    data[1]['tree'].append({'path': 'ZZ-other', 'mode': '100644', 'type': 'blob', 'sha': 'bad'})
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_tree_entry_cap_boundary():
    p, data, routes = fixture()
    data[1]['tree'] += [{'path': f'ZZ-{i}', 'mode': '100644', 'type': 'blob', 'sha': 'e'*40}
                        for i in range(4095)]
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
    data[1]['tree'].append({'path': 'ZZ-over', 'mode': '100644', 'type': 'blob', 'sha': 'e'*40})
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_content_cap_with_valid_sha_and_size_boundary():
    p, data, routes = fixture()
    set_blob(data, routes, p, b'Z'*LIMIT, update_pin=True)
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
    set_blob(data, routes, p, b'Z'*(LIMIT+1), update_pin=True)
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_response_cap_valid_json_with_padding():
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    raw = responses[0]['raw']
    responses[0]['raw'] = raw+b' '*(RESPONSE_LIMIT-len(raw))
    assert verify(p, responses)['production_enabled'] is False
    responses[0]['raw'] += b' '
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('count', [0, 1, 4, 6])
def test_exact_response_count(count):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    if count == 6:
        responses += [copy.deepcopy(responses[0])]
    else:
        responses = responses[:count]
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('index', range(5))
@pytest.mark.parametrize('bad', ['text', bytearray(b'{}')])
def test_raw_must_be_bytes_even_when_parseable(index, bad):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[index]['raw'] = responses[index]['raw'].decode() if bad == 'text' else bytearray(responses[index]['raw'])
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('index', range(5))
@pytest.mark.parametrize('raw', [b'[]', b'null', b'1', b'"ZZ"', b'true'])
def test_non_dict_json_top_level(index, raw):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[index]['raw'] = raw
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('suffix', ['\r', ' ', '!', '\t'])
def test_base64_ignored_characters_never_permitted(suffix):
    p, data, routes = fixture()
    data[4]['content'] += suffix
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_candidate_byte_caps_are_fixed_not_self_referential():
    assert LIMIT == 262144
    assert RESPONSE_LIMIT == 1048576


@pytest.mark.parametrize('mode,kind', [('100664', 'blob'), ('040000', 'blob'),
                                       ('100644', 'tree'), ('ZZ', 'tree')])
def test_invalid_sibling_mode_type_pair(mode, kind):
    p, data, routes = fixture()
    data[1]['tree'].append({'path': 'ZZ-other', 'mode': mode, 'type': kind, 'sha': 'e'*40})
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('index', range(5))
def test_duplicate_sha_in_otherwise_valid_json(index):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    raw = responses[index]['raw']
    responses[index]['raw'] = b'{"sha":"'+data[index]['sha'].encode()+b'",'+raw[1:]
    with pytest.raises(Blocked):
        verify(p, responses)


def test_extra_envelope_and_pin_keys_are_not_ignored():
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0]['extra'] = 'ZZ'
    with pytest.raises(Blocked):
        verify(p, responses)
    p['extra'] = 'ZZ'
    with pytest.raises(Blocked):
        descriptor(p, 'commits')


def test_noncanonical_padding_bits_for_exact_correct_bytes():
    p, data, routes = fixture()
    set_blob(data, routes, p, b'f', update_pin=True)
    assert data[4]['content'] == 'Zg=='
    data[4]['content'] = 'Zh=='
    assert base64.b64decode('Zh==') == b'f'
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('field,bad', [('status', 200.0), ('status', 201),
                                     ('redirected', 0), ('redirected', None),
                                     ('redirected', 'false')])
def test_transport_metadata_strict_types(field, bad):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0][field] = bad
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('bad', [True, False, 26.0, '26', None])
def test_blob_size_integer_only(bad):
    p, data, routes = fixture()
    data[4]['size'] = bad
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_envelopes_tuple_and_empty_blob_block_even_with_correct_hash():
    p, data, routes = fixture()
    with pytest.raises(Blocked):
        verify(p, tuple(envelopes(data, routes)))
    set_blob(data, routes, p, b'', update_pin=True)
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('path,allowed', [('Z'*254, True), ('Z'*255, True), ('Z'*256, False),
                                         ('', False), ('ZZ\x1f', False), ('ZZ ', True)])
def test_sibling_path_length_and_control_boundaries(path, allowed):
    p, data, routes = fixture()
    data[1]['tree'].append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': 'e'*40})
    if allowed:
        assert verify(p, envelopes(data, routes))['production_enabled'] is False
    else:
        with pytest.raises(Blocked):
            verify(p, envelopes(data, routes))


@pytest.mark.parametrize('field,bad', [('commit', 'a'*40+'ZZ'), ('workflow_sha256', 'a'*64+'ZZ'),
                                     ('filename', 'ZZ.yml.extra'), ('owner', 'Z'*101),
                                     ('repo', 'Z'*101)])
def test_pin_regex_fullmatch_and_max_lengths(field, bad):
    p, _, _ = fixture()
    p[field] = bad
    with pytest.raises(Blocked):
        descriptor(p, 'commits')


def test_owner_name_100_boundary_and_descriptor_literal_contract():
    p, _, _ = fixture()
    p['owner'] = 'Z'*100
    assert descriptor(p, 'commits') == {
        'method': 'GET', 'origin': 'https://api.github.com',
        'route': '/repos/'+'Z'*100+'/ZZ-repo/git/commits/'+'a'*40,
        'redirects_allowed': False, 'retries_allowed': False}
    assert descriptor(p, 'trees', 'b'*40)['route'] == '/repos/'+'Z'*100+'/ZZ-repo/git/trees/'+'b'*40
    assert descriptor(p, 'blobs', 'c'*40)['route'] == '/repos/'+'Z'*100+'/ZZ-repo/git/blobs/'+'c'*40
    with pytest.raises(Blocked):
        descriptor(p, 'commits', 'a'*40)
    for kind in ['ZZ', 'GET', None]:
        with pytest.raises(Blocked):
            descriptor(p, kind)


def test_invalid_utf8_in_ignored_field_must_not_be_replaced():
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0]['raw'] = responses[0]['raw'][:-1]+b',"ignored":"\xff"}'
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('constant', ['NaN', 'Infinity', '-Infinity'])
def test_non_json_constants_in_ignored_field_must_block(constant):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0]['raw'] = responses[0]['raw'][:-1]+b',"ignored":'+constant.encode()+b'}'
    with pytest.raises(Blocked):
        verify(p, responses)


def test_deep_json_returns_fixed_blocked_not_recursion_error():
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0]['raw'] = b'{"ZZ":'+b'['*2000+b'0'+b']'*2000+b'}'
    with pytest.raises(Blocked, match='^workflow content blocked; review protected inputs$'):
        verify(p, responses)


@pytest.mark.parametrize('kind', ['ZZ', 'GET', None, 1])
def test_descriptor_invalid_kind_with_otherwise_valid_sha(kind):
    p, _, _ = fixture()
    with pytest.raises(Blocked):
        descriptor(p, kind, 'a'*40)


@pytest.mark.parametrize('kind', ['trees', 'blobs'])
@pytest.mark.parametrize('sha', ['a'*40+'ZZ', 'A'*40, '../ZZ', None, True])
def test_descriptor_sha_shape_independent_of_response_matching(kind, sha):
    p, _, _ = fixture()
    with pytest.raises(Blocked):
        descriptor(p, kind, sha)


@pytest.mark.parametrize('index', range(5))
@pytest.mark.parametrize('field,value', [('method', 'POST'), ('origin', 'https://example.org'),
                                       ('route', '/repos/ZZ-other/ZZ-repo/git/blobs/'+'a'*40),
                                       ('redirects_allowed', True), ('retries_allowed', True)])
def test_each_request_descriptor_field_bound_independently(index, field, value):
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[index]['request'] = {**responses[index]['request'], field: value}
    with pytest.raises(Blocked):
        verify(p, responses)


def test_float_size_equal_to_actual_bytes_is_not_integer():
    p, data, routes = fixture()
    data[4]['size'] = float(data[4]['size'])
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_github_lf_wrapped_base64_and_encoded_length_boundary():
    p, data, routes = fixture()
    set_blob(data, routes, p, b'ZZ-content '*15, update_pin=True)
    encoded = data[4]['content']
    data[4]['content'] = '\n'.join(encoded[i:i+60] for i in range(0, len(encoded), 60))+'\n'
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
    data[4]['content'] = encoded+'\n'*(2*262144-len(encoded))
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
    data[4]['content'] += '\n'
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_encoded_length_bound_is_independent_with_small_candidate_limit(monkeypatch):
    import workflow_content_contract as contract
    monkeypatch.setattr(contract, 'LIMIT', 64)
    p, data, routes = fixture()
    encoded = data[4]['content']
    data[4]['content'] = encoded+'\n'*(128-len(encoded))
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
    data[4]['content'] += '\n'
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def changed_last(value):
    return value[:-1]+('0' if value[-1] != '0' else '1')


@pytest.mark.parametrize('index', range(5))
def test_full_sha_comparison_including_last_nibble(index):
    p, data, routes = fixture()
    data[index]['sha'] = changed_last(data[index]['sha'])
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_last_nibble_of_git_blob_digest_and_sha256_pin():
    p, data, routes = fixture()
    wrong = changed_last(data[4]['sha'])
    data[3]['tree'][0]['sha'] = data[4]['sha'] = wrong
    routes[4] = descriptor(p, 'blobs', wrong)
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))
    p, data, routes = fixture()
    p['workflow_sha256'] = changed_last(p['workflow_sha256'])
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('field,value', [('owner', '_ZZ'), ('repo', '_ZZ'), ('owner', 'ZZ.name'),
                                       ('repo', 'ZZ.name'), ('filename', 'ZZ.name.yml'),
                                       ('filename', '.yml')])
def test_disallowed_names_no_silent_regex_widening(field, value):
    p, _, _ = fixture()
    p[field] = value
    with pytest.raises(Blocked):
        descriptor(p, 'commits')


def test_yaml_extension_supported_tags_descriptor_not_supported():
    p, _, _ = fixture()
    p['filename'] = 'ZZ-human.yaml'
    assert descriptor(p, 'commits')['method'] == 'GET'
    with pytest.raises(Blocked):
        descriptor(p, 'tags', 'a'*40)


def test_link_empty_string_and_utf8_bom_are_not_accepted():
    p, data, routes = fixture()
    responses = envelopes(data, routes)
    responses[0]['link'] = ''
    with pytest.raises(Blocked):
        verify(p, responses)
    responses = envelopes(data, routes)
    responses[0]['raw'] = b'\xef\xbb\xbf'+responses[0]['raw']
    with pytest.raises(Blocked):
        verify(p, responses)


@pytest.mark.parametrize('mode,kind', [('100755', 'blob'), ('120000', 'blob'), ('160000', 'commit')])
def test_valid_unselected_sibling_modes_are_supported(mode, kind):
    p, data, routes = fixture()
    data[1]['tree'].append({'path': 'ZZ-other', 'mode': mode, 'type': kind, 'sha': 'e'*40})
    assert verify(p, envelopes(data, routes))['production_enabled'] is False


@pytest.mark.parametrize('mode,kind', [('160000', 'tree'), ('100755', 'tree'),
                                     ('120000', 'tree'), ('040000', 'commit')])
def test_unselected_sibling_cross_pairs_rejected(mode, kind):
    p, data, routes = fixture()
    data[1]['tree'].append({'path': 'ZZ-other', 'mode': mode, 'type': kind, 'sha': 'e'*40})
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


@pytest.mark.parametrize('index', [1, 2, 3])
def test_selected_names_are_case_sensitive(index):
    p, data, routes = fixture()
    data[index]['tree'][0]['path'] = data[index]['tree'][0]['path'].upper()
    with pytest.raises(Blocked):
        verify(p, envelopes(data, routes))


def test_case_distinct_sibling_git_paths_are_not_duplicates():
    p, data, routes = fixture()
    data[1]['tree'].append({'path': '.GITHUB', 'mode': '040000', 'type': 'tree', 'sha': 'e'*40})
    assert verify(p, envelopes(data, routes))['production_enabled'] is False


def test_del_character_not_below_control_boundary():
    p, data, routes = fixture()
    data[1]['tree'].append({'path': 'ZZ\x7f', 'mode': '100644', 'type': 'blob', 'sha': 'e'*40})
    assert verify(p, envelopes(data, routes))['production_enabled'] is False
