"""Shipped closed contract. No caller-controlled proof can enable production."""
import json
from importlib.resources import files

from geni_uploader.core import proof_requirements
from geni_uploader.core.people import Blocked, exact, require

PROOFS = proof_requirements.PROOFS

CONTRACT = files('geni_uploader').joinpath('resources/human-parent-release-gates.json')


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
