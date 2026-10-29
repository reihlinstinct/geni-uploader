"""Synthetic protected-report regression for source readiness."""
import argparse
import copy
import json
from unittest.mock import patch

import pytest

import geni_upload as g
import plan_report

MANIFEST = {'targets': [{'profile_id': '991234567890', 'expect_name': 'ZZFirst ZZLast',
                        'documents': [{'title': 'ZZSource', 'source_url': 'https://example.invalid/zz',
                                       'description_en': 'ZZDescription'}]}]}


def test_recorded_name_fallback_keeps_strict_identity_guard():
    profile = {'id': '991234567890', 'first_name': 'ZZFirst', 'last_name': 'ZZLast'}
    with patch.object(g, 'execute', return_value=profile):
        assert g.verify_profile('ZZTOKEN', '991234567890', 'ZZFirst ZZLast') == (
            '991234567890', 'ZZFirst ZZLast')
        with pytest.raises(g.ApiError):
            g.verify_profile('ZZTOKEN', '991234567890', 'ZZOther ZZName')
    guid = {**profile, 'id': '9912345', 'guid': '991234567890'}
    with patch.object(g, 'execute', side_effect=[{'results': []}, guid]):
        assert g.verify_profile('ZZTOKEN', '991234567890', 'ZZFirst ZZLast') == (
            '9912345', 'ZZFirst ZZLast')


@pytest.mark.parametrize('listing,record,ready,verdict', [
    ([], {}, True, 'NEW absent'),
    ([g.anchor(MANIFEST['targets'][0]['documents'][0], 'documents')], {}, True, 'SKIP already present'),
    (None, {}, False, 'UNKNOWN duplicate/completion'),
    ([], {'status': 'uncertain'}, False, 'BLOCKED journal'),
    ([], {'status': 'pending'}, False, 'BLOCKED journal'),
    ([], {'status': 'unexpected'}, False, 'BLOCKED journal'),
    ([], {'create_intent': True}, False, 'BLOCKED journal'),
    ([], {'status': 'uploaded'}, False, 'BLOCKED recorded done'),
    (None, {'status': 'uploaded'}, False, 'UNKNOWN duplicate/completion'),
    ([g.anchor(MANIFEST['targets'][0]['documents'][0], 'documents')], {'status': 'uploaded'}, True, 'SKIP already present'),
])
def test_each_source_guard_and_value_free_public_report(tmp_path, capsys, listing, record,
                                                        ready, verdict):
    path = tmp_path / 'upload-manifest.yaml'
    path.write_text('unused')
    key = '991234567890:documents:ZZSource'
    output = tmp_path / 'report.json'
    with patch.dict('os.environ', {'GENI_PLAN_REPORT': str(output)}), \
            patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'get_token', return_value='ZZTOKEN'), \
            patch.object(g, 'verify_profile', return_value=('991234567890', 'ZZFirst ZZLast')), \
            patch.object(g, 'load_status', return_value={'items': {key: record}}), \
            patch.object(g, 'list_tagged', return_value=listing) as read:
        assert g.cmd_plan(argparse.Namespace(manifest=str(path))) == (0 if ready else 1)
    text = capsys.readouterr().out
    assert 'OK (ZZFirst ZZLast)' in text
    assert 'schema/file=pass; target=pass' in text
    assert verdict in text
    assert 'photos: no proposed sources; listing not required' in text
    assert read.call_count == 1
    public = plan_report.render(json.loads(output.read_text()))
    assert ('Safe to run: yes' in public) == ready
    assert 'ZZ' not in public


@pytest.mark.parametrize('local', ['pending', 'uncertain', 'uploaded'])
def test_local_journal_is_read_only_and_blocks_unconfirmed_sources(tmp_path, capsys, local):
    path = tmp_path / 'upload-manifest.yaml'
    state_path = tmp_path / 'state.json'
    key = '991234567890:documents:ZZSource'
    state = {'uploaded': []}
    state[local] = {key: {'status': 'pending'}} if local == 'pending' else [key]
    original = json.dumps(state)
    state_path.write_text(original)
    with patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'get_token', return_value='ZZTOKEN'), \
            patch.object(g, 'verify_profile', return_value=('991234567890', 'ZZFirst ZZLast')), \
            patch.object(g, 'list_tagged', return_value=[]), \
            patch.object(g, 'execute') as request:
        assert g.cmd_plan(argparse.Namespace(manifest=str(path), state=str(state_path))) == 1
    assert 'BLOCKED' in capsys.readouterr().out
    assert state_path.read_text() == original
    request.assert_not_called()
    assert not (tmp_path / g.STATUS_NAME).exists()


def test_plan_rejects_malformed_status(tmp_path):
    path = tmp_path / 'upload-manifest.yaml'
    (tmp_path / g.STATUS_NAME).write_text('items: []')
    with patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'execute') as request, \
            pytest.raises(g.ApiError, match='invalid structure'):
        g.cmd_plan(argparse.Namespace(manifest=str(path)))
    request.assert_not_called()


@pytest.mark.parametrize('kind', ['state', 'status'])
def test_unreadable_journal_has_clean_review_error(tmp_path, kind):
    path = tmp_path / 'upload-manifest.yaml'
    state = tmp_path / 'state.json'
    if kind == 'state':
        state.write_text('{broken')
    else:
        (tmp_path / g.STATUS_NAME).write_text('items: [broken')
    with patch.object(g, 'load_manifest', return_value=copy.deepcopy(MANIFEST)), \
            patch.object(g, 'execute') as request, \
            pytest.raises(g.ApiError, match='cannot be read; manual review required'):
        g.cmd_plan(argparse.Namespace(manifest=str(path), state=str(state)))
    request.assert_not_called()
