"""All identities and URLs are invented fixtures, not observed live profiles."""
from copy import deepcopy

import pytest

from people_core import Blocked
from profile_result import PHASES, validate


def fixture():
    return {'schema_version': 1, 'mode': 'offline_profile_result',
            'pins': {'owner': 'profile-999001', 'payload_hash': '1'*64,
                     'run_hash': '2'*64, 'artifact_hash': '3'*64, 'approval_hash': '4'*64},
            'profile_id': 'profile-999002',
            'profile_url': 'https://www.geni.com/people/ZZ-Invented/999003',
            'acknowledgment_ref': 'a'*64, 'readback_ref': None,
            'source_refs': [], 'phase': 'created_unverified',
            'production_enabled': False, 'provenance_authenticated': False}


def test_valid_stages_and_copy_isolation():
    for phase in PHASES:
        value = fixture()
        value['phase'] = phase
        if phase != PHASES[0]:
            value['readback_ref'] = 'b'*64
        if phase in PHASES[2:]:
            value['source_refs'] = ['c'*64]
        original = deepcopy(value)
        result = validate(value, value['pins'])
        result['pins']['owner'] = 'profile-999004'
        result['source_refs'].append('d'*64)
        assert value == original
        value['pins']['owner'] = 'profile-999005'
        assert result['pins']['owner'] == 'profile-999004'


@pytest.mark.parametrize('key', ['owner', 'payload_hash', 'run_hash', 'artifact_hash',
                                'approval_hash'])
def test_every_expected_pin_is_bound(key):
    value = fixture()
    expected = deepcopy(value['pins'])
    expected[key] = 'profile-999005' if key == 'owner' else 'f'*64
    with pytest.raises(Blocked):
        validate(value, expected)


@pytest.mark.parametrize('url', [
    'http://www.geni.com/people/ZZ/999003',
    'https://www.geni.com.evil.invalid/people/ZZ/999003',
    'https://user@www.geni.com/people/ZZ/999003',
    'https://www.geni.com:443/people/ZZ/999003',
    'https://www.geni.com/people/ZZ/999003?token=ZZ',
    'https://www.geni.com/people/ZZ/999003#ZZ',
    'https://www.geni.com/people/ZZ/0',
    'https://www.geni.com/people/ZZ/profile-999003',
    'https://www.geni.com/people/ZZ/999003/',
    'https://www.geni.com/people/ZZ/999003\n',
    'https://www.geni.com/people/ZZ%2fother/999003',
    'https://[bad/people/ZZ/999003',
    'https://www.geni.com/people/ZZ%252fother/999003',
    'https://www.geni.com/people/ZZ%xx/999003',
    'https://www.geni.com/people/ZZ%ff/999003',
    None, 1, '',
])
def test_unsafe_or_noncanonical_url_rejected(url):
    value = fixture()
    value['profile_url'] = url
    with pytest.raises(Blocked):
        validate(value, fixture()['pins'])


@pytest.mark.parametrize('key,value', [
    ('schema_version', True), ('production_enabled', 0),
    ('production_enabled', True), ('provenance_authenticated', 0),
    ('provenance_authenticated', True), ('mode', 'live'),
    ('profile_id', 'profile-999001'), ('profile_id', 'profile-self'),
    ('acknowledgment_ref', 'ZZplaintext'), ('phase', 'success'),
    ('readback_ref', 'b'*64), ('source_refs', ['c'*64]),
])
def test_strict_shape_and_unverified_stage(key, value):
    record = fixture()
    record[key] = value
    with pytest.raises(Blocked):
        validate(record, fixture()['pins'])


@pytest.mark.parametrize('phase', PHASES[1:])
def test_verified_stages_need_distinct_readback(phase):
    for readback in (None, 'a'*64, 'ZZplaintext'):
        value = fixture()
        value.update(phase=phase, readback_ref=readback)
        if phase in PHASES[2:]:
            value['source_refs'] = ['c'*64]
        with pytest.raises(Blocked):
            validate(value, fixture()['pins'])


@pytest.mark.parametrize('refs', [[], ['c'*64]*2, ['ZZplaintext'], ['c'*64]*101, ()])
def test_sources_attached_requires_bounded_distinct_ciphertext_refs(refs):
    value = fixture()
    value.update(phase=PHASES[2], readback_ref='b'*64, source_refs=refs)
    with pytest.raises(Blocked):
        validate(value, fixture()['pins'])


@pytest.mark.parametrize('key', ['pins', 'source_refs', 'profile_url'])
def test_unknown_and_missing_fields_rejected(key):
    value = fixture()
    del value[key]
    with pytest.raises(Blocked):
        validate(value, fixture()['pins'])
    value = fixture()
    value['ZZ-extra'] = True
    with pytest.raises(Blocked):
        validate(value, fixture()['pins'])


def test_encoded_hebrew_name_segment_allowed_without_decoding_into_new_url():
    value = fixture()
    value['profile_url'] = 'https://www.geni.com/people/%D7%90%D7%91/999003'
    assert validate(value, value['pins'])['profile_url'] == value['profile_url']


@pytest.mark.parametrize('version', [0, 2, -1, '1', None])
def test_schema_version_exact_one(version):
    value = fixture()
    value['schema_version'] = version
    with pytest.raises(Blocked):
        validate(value, fixture()['pins'])


def test_source_cap_isolated_with_distinct_refs():
    value = fixture()
    value.update(phase=PHASES[2], readback_ref='b'*64,
                 source_refs=[f'{n:064x}' for n in range(100)])
    assert len(validate(value, value['pins'])['source_refs']) == 100
    value['source_refs'].append(f'{100:064x}')
    with pytest.raises(Blocked):
        validate(value, value['pins'])


@pytest.mark.parametrize('url', ['https://www.geni.com/foo/ZZ/1',
                                'https://www.geni.com/peoplex/ZZ/1'])
def test_people_path_prefix_required(url):
    value = fixture()
    value['profile_url'] = url
    with pytest.raises(Blocked):
        validate(value, value['pins'])


@pytest.mark.parametrize('key,bad', [('owner', 'profile-self'), ('owner', 'profile-0'),
                                   ('owner', 123), ('payload_hash', 'ZZ'),
                                   ('run_hash', 'A'*64), ('artifact_hash', 1),
                                   ('approval_hash', 'a'*63)])
def test_equal_expected_and_supplied_malformed_pins_rejected(key, bad):
    value = fixture()
    value['pins'][key] = bad
    with pytest.raises(Blocked):
        validate(value, deepcopy(value['pins']))
