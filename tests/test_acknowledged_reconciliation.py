"""Opt-in GET-only proof never replays attempted operations."""
import copy
from unittest.mock import patch

import pytest
from test_durable_resume import harness

import geni_upload as g


def blocked(tmp_path):
    run, state, status, item = harness(tmp_path)
    with patch.object(g, 'execute', return_value={'id': '999'}), \
            patch.object(g, 'verify_linkage', side_effect=g.ApiError('ZZ')), \
            pytest.raises(g.UncertainWrite):
        run()
    rec = next(iter(status['items'].values()))
    assert rec['blocked'] and rec['tags']['123']['phase'] == 'acknowledged'
    return run, state, status, item, rec


def test_proven_primary_reconciles_then_only_untouched_extra_posts(tmp_path):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    with patch.object(g, 'verify_linkage', return_value=True), \
            patch.object(g, 'verify_profile', return_value=('456', 'ZZ Extra')), \
            patch.object(g, 'execute', return_value={}) as call:
        run({'uploaded': []}, status)
    assert call.call_count == 1
    assert call.call_args.args[2].endswith('/document-999/tag/profile-456')
    assert rec['status'] == 'uploaded' and 'blocked' not in rec
    assert 'reconcile_readback' not in rec and rec['object_id'] == '999'


@pytest.mark.parametrize('change', [
    {'reconcile_readback': False}, {'reconcile_readback': 'true'}, {'reason': '429'},
    {'create_intent': False}, {'object_id': None}, {'object_id': 'ZZ'},
    {'tags': {}}, {'tags': {'123': {'node': '123', 'phase': 'intent'}}},
    {'tags': {'789': {'node': '789', 'phase': 'acknowledged'}}},
])
def test_unsafe_records_never_reconcile(tmp_path, change):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    rec.update(change)
    with patch.object(g, 'execute') as call, pytest.raises(g.UncertainWrite):
        run({'uploaded': []}, status)
    call.assert_not_called()
    assert rec['blocked']


def test_failed_proof_preserves_all_phases_and_block(tmp_path):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    before = copy.deepcopy(rec)
    with patch.object(g, 'execute') as call, patch.object(g, 'verify_linkage', return_value=False), \
            pytest.raises(g.VerificationError):
        run({'uploaded': []}, status)
    call.assert_not_called()
    assert rec == before


def test_proof_throttle_preserves_block(tmp_path):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    with patch.object(g, 'execute') as call, \
            patch.object(g, 'verify_linkage', side_effect=g.ThrottledError('429')), \
            pytest.raises(g.ThrottledError):
        run({'uploaded': []}, status)
    call.assert_not_called()
    assert rec['blocked']


def test_reconciled_checkpoint_failure_prevents_untouched_extra(tmp_path):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    with patch.object(g, 'execute') as call, patch.object(g, 'verify_linkage', return_value=True), \
            patch.object(g, 'repo_sync', return_value=False), pytest.raises(g.ApiError):
        run({'uploaded': []}, status, sync=True)
    call.assert_not_called()


def test_changed_identity_cannot_unblock(tmp_path):
    run, _, status, _, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    rec['tags']['123']['node'] = '777'
    with patch.object(g, 'execute') as call, pytest.raises(g.UncertainWrite):
        run({'uploaded': []}, status)
    call.assert_not_called()
    assert rec['blocked']


def test_changed_binding_cannot_unblock(tmp_path):
    run, _, status, item, rec = blocked(tmp_path)
    rec['reconcile_readback'] = True
    item['description'] = 'ZZ changed'
    with patch.object(g, 'execute') as call, pytest.raises(g.ApiError):
        run({'uploaded': []}, status)
    call.assert_not_called()
    assert rec['blocked']
