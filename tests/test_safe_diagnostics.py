"""Offline diagnostics must not echo any input or exception value."""
import copy
import hashlib
import json
import sys
from unittest.mock import patch

import pytest
from test_source_details import ITEM, Fake

import source_details as s


@pytest.mark.parametrize('failure,stage,category', [
    ('object', 'object_identity', 'api'),
    ('anchor', 'preconditions', 'api'),
    ('hash', 'preconditions', 'api'),
    ('identity', 'target_identity', 'api'),
    ('deceased', 'target_deceased', 'api'),
    ('throttled', 'object_identity', 'throttled'),
])
def test_main_fixed_failure_output(tmp_path, capsys, failure, stage, category):
    item = copy.deepcopy(ITEM)
    item['key'] = 'ZZDO_NOT_PRINT_KEY'
    item['expect']['description_sha256'] = hashlib.sha256(b'ZZ old').hexdigest()
    item['expect']['title'] = 'ZZ existing'
    fake = Fake(alive=failure == 'deceased')
    if failure == 'anchor':
        fake.obj['title'] = 'ZZDO_NOT_PRINT_OBSERVED_TITLE'
    if failure == 'hash':
        fake.obj['description'] = 'ZZDO_NOT_PRINT_OBSERVED_DESCRIPTION'
    manifest = tmp_path / 'ZZDO_NOT_PRINT_PATH'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [item]}))
    def execute(method, kind, url, token=None, data=None):
        assert method == 'GET'
        if failure in {'object', 'throttled'}:
            error = s.api.ThrottledError if failure == 'throttled' else s.api.ApiError
            raise error('ZZDO_NOT_PRINT_EXCEPTION https://example.invalid/secret')
        return fake(method, kind, url, token, data)
    def profile(*args):
        if failure == 'identity':
            raise s.api.ApiError('ZZDO_NOT_PRINT_NAME')
        return '201', 'ZZDO_NOT_PRINT_NAME'
    with patch.object(sys, 'argv', ['source_details', 'plan', '--manifest', str(manifest)]), \
            patch.object(s.api, 'get_token', return_value='ZZDO_NOT_PRINT_TOKEN'), \
            patch.object(s.api, 'verify_profile', profile), patch.object(s.api, 'execute', execute):
        assert s.main() == 1
    output = capsys.readouterr().out
    assert f'stage={stage}' in output
    assert f'stopped category={category}' in output
    assert 'ZZ' not in output and 'https://' not in output
    assert item['expect']['description_sha256'] not in output
    assert 'plan_checked' not in output
    if failure == 'hash':
        assert 'stage=description_present result=true' in output
        assert 'stage=description_hash result=false' in output
        assert 'stage=description_desired result=false' in output
    if failure == 'anchor':
        assert 'stage=title result=false' in output


def test_main_success_ordinals_not_identifiers(tmp_path, capsys):
    manifest = tmp_path / 'input.json'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [ITEM]}))
    fake = Fake()
    with patch.object(sys, 'argv', ['source_details', 'plan', '--manifest', str(manifest)]), \
            patch.object(s.api, 'get_token', return_value='ZZTOKEN'), \
            patch.object(s.api, 'execute', fake):
        assert s.main() == 0
    out = capsys.readouterr().out
    assert 'item=1 target=1 stage=target_deceased result=pass' in out
    assert 'stage=plan_checked result=pass' in out
    assert not any(value in out for value in ('ZZ', '101', '201', 'https://'))
    assert all(call[0] == 'GET' for call in fake.calls)


@pytest.mark.parametrize('stage,result,item,target', [
    ('ZZINJECT', 'pass', 1, 1), ('schema', 'ZZINJECT', 1, 1),
    ('schema', 'pass', 'ZZINJECT', 1), ('schema', 'pass', 1, 'ZZINJECT'),
    ('schema', 'pass', True, 0), ('schema', 'pass', -1, 0),
])
def test_diagnostic_rejects_dynamic_values(capsys, stage, result, item, target):
    with pytest.raises(ValueError):
        s.diagnostic(stage, result, item, target)
    assert capsys.readouterr().out == ''


def test_unknown_expectation_fails_closed():
    item = copy.deepcopy(ITEM)
    item['expect']['ZZUNKNOWN'] = 'ZZVALUE'
    with pytest.raises(s.api.ApiError, match='unsupported expectation'):
        s.expectation_checks({}, item)


def test_desired_text_with_old_hash_mismatch_is_idempotent(capsys):
    item = copy.deepcopy(ITEM)
    item['expect']['description_sha256'] = hashlib.sha256(b'ZZ old').hexdigest()
    fake = Fake()
    fake.obj['description'] = s.api.render_description(item['set'])
    with patch.object(s.api, 'execute', fake):
        assert len(s.checked_plan([item], 'ZZTOKEN')) == 1
    output = capsys.readouterr().out
    assert 'stage=description_hash result=false' in output
    assert 'stage=description_desired result=true' in output
    assert 'stage=preconditions result=pass' in output
    assert all(call[0] == 'GET' for call in fake.calls)


@pytest.mark.parametrize('error_type,category', [
    ('UncertainWrite', 'uncertain_write'),
    ('VerificationError', 'verification'),
    (OSError, 'filesystem'),
    (s.subprocess.SubprocessError, 'subprocess'),
    (ValueError, 'input'), (TypeError, 'input'),
])
def test_repair_error_categories_no_echo(tmp_path, capsys, error_type, category):
    if isinstance(error_type, str):
        error_type = getattr(s.api, error_type)
    manifest = tmp_path / 'ZZPATH'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [ITEM]}))
    fake = Fake()
    with patch.object(sys, 'argv', ['source_details', 'repair', '--manifest', str(manifest),
                                   '--confirm', 'YES', '--state', str(tmp_path / 'ZZSTATE')]), \
            patch.object(s.api, 'get_token', return_value='ZZTOKEN'), \
            patch.object(s.api, 'execute', fake), \
            patch.object(s, 'apply_plan', side_effect=error_type('ZZSECRET https://example.invalid')):
        assert s.main() == 1
    out = capsys.readouterr().out
    assert f'stopped category={category}' in out
    assert 'stage=repair result=start' in out
    assert 'stage=repair result=pass' not in out
    assert 'ZZ' not in out and 'https://' not in out
    assert all(call[0] == 'GET' for call in fake.calls)


def test_invalid_json_has_input_category_and_no_network(tmp_path, capsys):
    manifest = tmp_path / 'ZZPATH'
    manifest.write_text('{ZZSECRET')
    with patch.object(sys, 'argv', ['source_details', 'plan', '--manifest', str(manifest)]), \
            patch.object(s.api, 'execute') as execute:
        assert s.main() == 1
        execute.assert_not_called()
    out = capsys.readouterr().out
    assert 'stopped category=input' in out
    assert 'ZZ' not in out


@pytest.mark.parametrize('mode', ['repair', 'snapshot'])
def test_completed_operation_has_pass_marker(tmp_path, capsys, mode):
    manifest = tmp_path / 'input.json'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [ITEM]}))
    fake = Fake()
    argv = ['source_details', mode, '--manifest', str(manifest), '--confirm', 'YES',
            '--state', str(tmp_path / 'state'), '--output', str(tmp_path / 'out')]
    with patch.object(sys, 'argv', argv), \
            patch.object(s.api, 'get_token', return_value='ZZTOKEN'), \
            patch.object(s.api, 'execute', fake), patch.object(s, 'apply_plan'), \
            patch.object(s, 'snapshot'):
        assert s.main() == 0
    assert f'stage={mode} result=pass' in capsys.readouterr().out
