"""Design fixtures cannot release either existing production entry."""
import json
from pathlib import Path

import pytest

import human_parent_gate
import parent_plan
import parent_runner
from people_core import Blocked

ROOT = Path(__file__).resolve().parents[1]


def test_single_father_design_is_closed_and_explicit():
    value = json.loads((ROOT / 'docs/single-father-risk-release-gates.json').read_text())
    assert value == {
        'schema_version': 1,
        'kind': 'offline_single_father_risk_release_design',
        'production_create_enabled': False,
        'executable_policy': False,
        'evidence_is_authenticated': False,
        'default_all_proofs_gate_unchanged': True,
        'unknown_is_pass': False,
        'max_post_count': 1,
        'proposed_relation': 'father',
        'shared_intent_backend_selected': False,
        'required_approvals': [
            'named_implementation_merge', 'separate_exact_release',
            'exact_private_payload_and_risks', 'exact_run', 'protected_human_environment',
        ],
        'excluded_operations': [
            'mother', 'partner', 'child', 'merge', 'delete', 'refresh', 'retry', 'edit',
        ],
    }


@pytest.mark.parametrize('entry', [parent_plan.apply, parent_runner.run_production])
def test_risk_design_cannot_enable_existing_entry(entry):
    value = json.loads((ROOT / 'docs/single-father-risk-release-gates.json').read_text())
    value.update(production_create_enabled=True, risk_accepted=True, all_proofs=True)
    with pytest.raises(Blocked, match='disabled'):
        entry(value)


def test_substituting_risk_fixture_for_default_gate_fails(monkeypatch):
    monkeypatch.setattr(human_parent_gate, 'CONTRACT',
                        ROOT / 'docs/single-father-risk-release-gates.json')
    with pytest.raises(Blocked, match='changed'):
        human_parent_gate.require_production_release()
