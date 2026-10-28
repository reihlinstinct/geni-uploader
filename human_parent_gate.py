"""Shipped closed contract. No caller-controlled proof can enable production."""
import json
from pathlib import Path

from people_core import Blocked, exact, require

CONTRACT = Path(__file__).resolve().parent / 'docs/human-parent-release-gates.json'
PROOFS = (
    'exact_owner_identity', 'owner_create_scope', 'complete_visible_and_hidden_parent_graph',
    'add_parent_slot_semantics', 'private_create_and_readback', 'hebrew_and_english_default_locale',
    'signed_exact_live_plan', 'immutable_executor_and_data_pins',
    'shared_owner_lock_and_durable_intent', 'human_executor_release',
)


def require_production_release():
    """Read the packaged contract, reject drift, then block even a matching fixture.

    Future release logic needs a separate reviewed change, not a JSON toggle.
    Nothing supplied by a Plan, peer, caller or credential is trusted here.
    """
    try:
        gate = json.loads(CONTRACT.read_text(encoding='utf-8'))
        exact(gate, ('schema_version', 'kind', 'production_create_enabled',
                     'evidence_is_authenticated', 'required_proofs', 'unknown_is_pass',
                     'custody_attestation_is_create_permission', 'agent_live_calls_allowed'))
        require(type(gate['schema_version']) is int and gate['schema_version'] == 1)
        require(gate['kind'] == 'offline_release_gate_contract')
        require(gate['required_proofs'] == list(PROOFS))
        for key in ('production_create_enabled', 'evidence_is_authenticated', 'unknown_is_pass',
                    'custody_attestation_is_create_permission', 'agent_live_calls_allowed'):
            require(gate[key] is False)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise Blocked('production parent gate unavailable or changed; release blocked') from exc
    raise Blocked('production parent creation disabled; authenticated release proofs required')
