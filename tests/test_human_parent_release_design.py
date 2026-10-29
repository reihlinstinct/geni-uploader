"""Offline guard for the closed human-runner release contract, not vendor proof."""
import json
from pathlib import Path

import pytest

import parent_plan
from people_core import Blocked

ROOT = Path(__file__).resolve().parents[1]


def test_human_parent_design_is_closed_and_names_all_proof_gates():
    value = json.loads((ROOT / 'docs/human-parent-release-gates.json').read_text())
    assert value['production_create_enabled'] is False
    assert value['evidence_is_authenticated'] is False
    assert value['unknown_is_pass'] is False
    assert value['custody_attestation_is_create_permission'] is False
    assert value['agent_live_calls_allowed'] is False
    assert len(value['required_proofs']) == len(set(value['required_proofs'])) == 10
    assert 'complete_visible_and_hidden_parent_graph' in value['required_proofs']
    assert 'human_executor_release' in value['required_proofs']
    with pytest.raises(Blocked):
        parent_plan.apply(value)


def test_design_cites_vendor_contract_and_distinguishes_unknowns():
    text = ' '.join((ROOT / 'docs/human-parent-runner-release.md').read_text().split())
    for endpoint in ['profile/add-parent', 'profile/immediate-family', 'union', 'profile']:
        assert ('https://www.geni.com/platform/developer/help/api?path=' + endpoint) in text.split()
    for guard in ['UNCERTAIN', 'Production creation remains', 'No real family profile',
                  'Unknown merge', 'No firm live-create', 'not cryptographic proof']:
        assert guard in text
