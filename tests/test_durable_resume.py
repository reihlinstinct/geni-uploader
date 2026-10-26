"""Synthetic offline write-ahead and restart regression cases."""
import copy
from unittest.mock import Mock, patch

import pytest

import geni_upload as g


def harness(tmp_path):
    manifest = str(tmp_path / 'manifest.yaml')
    item = {'title': 'ZZ source', 'source_url': 'https://example.invalid/source',
            'also_tag': ['456']}
    state = {'uploaded': []}
    status = {'items': {}}
    log = Mock()
    targets = {'456': {'expect_name': 'ZZ Extra'}}

    def run(st=state, ss=status, sync=False):
        return g.durable_upload(item, 'documents', 'document', 'document_add',
                                'document_tag', '123', '123', 'ZZtoken',
                                '123:documents:ZZ source', st, str(tmp_path / 'state.json'),
                                ss, manifest, log, sync, targets)
    return run, state, status, item


def test_ack_id_and_tag_durable_before_readback_fresh_restart(tmp_path):
    run, _state, _status, _ = harness(tmp_path)
    posts = []

    def execute(method, kind, url, token, data):
        posts.append(kind)
        return {'id': '999'} if kind == 'document_add' else {}

    def lag(*args):
        on_disk = g.load_status(str(tmp_path / 'manifest.yaml'))
        rec = next(iter(on_disk['items'].values()))
        assert rec['object_id'] == '999'
        assert rec['tags']['123']['phase'] == 'acknowledged'
        return False

    with patch.object(g, 'execute', execute), patch.object(g, 'verify_linkage', lag), \
            pytest.raises(g.VerificationError):
        run()
    assert posts == ['document_add', 'document_tag']
    # Disposable container state lost; only repo journal remains.
    fresh = g.load_status(str(tmp_path / 'manifest.yaml'))
    with patch.object(g, 'execute', execute), patch.object(g, 'verify_linkage', return_value=True), \
            patch.object(g, 'verify_profile', return_value=('456', 'ZZ Extra')):
        run({'uploaded': []}, fresh)
    assert posts == ['document_add', 'document_tag', 'document_tag']
    assert next(iter(fresh['items'].values()))['also_tagged'] == ['456']


def test_sync_failure_prevents_mutation(tmp_path):
    run, *_ = harness(tmp_path)
    with patch.object(g, 'repo_sync', return_value=False), patch.object(g, 'execute') as call:
        with pytest.raises(g.ApiError, match='push failed'):
            run(sync=True)
        call.assert_not_called()


def test_lost_create_response_fresh_restart_never_replays(tmp_path):
    run, *_ = harness(tmp_path)
    with patch.object(g, 'execute', side_effect=g.UncertainWrite('ZZ response lost')) as call:
        with pytest.raises(g.UncertainWrite):
            run()
        fresh = g.load_status(str(tmp_path / 'manifest.yaml'))
        with pytest.raises(g.UncertainWrite):
            run({'uploaded': []}, fresh)
        assert call.call_count == 1


def test_precondition_change_stops_without_post(tmp_path):
    run, _, status, item = harness(tmp_path)
    with patch.object(g, 'execute', return_value={'id': '999'}), \
            patch.object(g, 'verify_linkage', return_value=False), \
            pytest.raises(g.VerificationError):
        run()
    item['description'] = 'ZZ changed'
    with patch.object(g, 'execute') as call:
        with pytest.raises(g.ApiError, match='precondition changed'):
            run({'uploaded': []}, copy.deepcopy(status))
        call.assert_not_called()


def test_readback_window_and_throttle_stop():
    with patch.object(g, 'list_tagged', return_value=set()) as call, \
            patch.object(g, '_sleep') as sleep:
        assert not g.verify_linkage('ZZtoken', '123', 'documents', ('ZZ', None), Mock())
        assert call.call_count == 13
        assert sleep.call_count == 12
        sleep.assert_called_with(30)
    with patch.object(g, 'execute', side_effect=g.ThrottledError('ZZ429')) as call:
        with pytest.raises(g.ThrottledError):
            g.list_tagged('ZZtoken', '123', 'photos')
        assert call.call_count == 1


def test_remote_journal_survives_container_loss(tmp_path):
    import subprocess

    def git(*args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                              text=True).stdout

    remote = tmp_path / 'remote.git'
    work = tmp_path / 'work'
    git('init', '--bare', str(remote))
    git('clone', str(remote), str(work))
    git('checkout', '-b', 'main', cwd=work)
    (work / 'manifest.yaml').write_text('targets: []\n')
    git('add', '.', cwd=work)
    git('-c', 'user.name=ZZ', '-c', 'user.email=zz@example.invalid',
        'commit', '-m', 'ZZ initial', cwd=work)
    git('push', '-u', 'origin', 'main', cwd=work)
    run, *_ = harness(work)
    posts = []

    def execute(method, kind, url, token, data):
        posts.append(kind)
        return {'id': '999'} if kind == 'document_add' else {}

    with patch.object(g, 'execute', execute), patch.object(g, 'verify_linkage', return_value=False), \
            pytest.raises(g.VerificationError):
        run(sync=True)
    fresh = tmp_path / 'fresh'
    git('clone', '-b', 'main', str(remote), str(fresh))
    new_run, *_ = harness(fresh)
    journal = g.load_status(str(fresh / 'manifest.yaml'))
    with patch.object(g, 'execute', execute), patch.object(g, 'verify_linkage', return_value=True), \
            patch.object(g, 'verify_profile', return_value=('456', 'ZZ Extra')):
        new_run({'uploaded': []}, journal, sync=True)
    assert posts == ['document_add', 'document_tag', 'document_tag']
    assert 'uploaded' in git('--git-dir', str(remote), 'show', 'main:upload-status.yaml')
