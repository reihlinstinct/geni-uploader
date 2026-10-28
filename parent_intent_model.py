"""Pure offline create-intent state model. No durable store or release authority.

A caller must never use this model or its output as execution authorization.
A reviewed shared backend must enforce atomic CAS and authenticated callers.
"""
from copy import deepcopy

from people_core import Blocked, digest, exact, require

BINDINGS = ('owner', 'connection_id', 'operation', 'plan_hash', 'payload_hash',
            'artifact_hash', 'policy_hash')
PHASES = ('consumed', 'acknowledged', 'uncertain', 'verified')


def _hash(value):
    require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _id(value, prefix):
    require(type(value) is str and value.startswith(prefix)
            and 0 < len(value[len(prefix):]) <= 30
            and value[len(prefix):].isascii() and value[len(prefix):].isdigit()
            and value[len(prefix):][0] != '0')


def binding_hash(binding):
    """Content binding, never authentication, authority or proof of freshness."""
    exact(binding, BINDINGS)
    _id(binding['owner'], 'profile-')
    require(type(binding['connection_id']) is str
            and 0 < len(binding['connection_id']) <= 100
            and binding['connection_id'].isascii()
            and all(c.isalnum() or c in '-_' for c in binding['connection_id']))
    require(binding['operation'] == 'single_father_add_parent')
    for key in ('plan_hash', 'payload_hash', 'artifact_hash', 'policy_hash'):
        _hash(binding[key])
    return digest(binding)


def _version(value):
    require(type(value) is int and 0 <= value <= 2**31 - 1)


def validate(state):
    """Reject state drift. Returns a copy, without contacting any store."""
    exact(state, ('schema_version', 'mode', 'binding', 'binding_hash', 'version',
                  'phase', 'created_id', 'evidence_refs', 'production_enabled'))
    require(type(state['schema_version']) is int and state['schema_version'] == 1)
    require(state['mode'] == 'offline_intent_model')
    require(state['production_enabled'] is False)
    require(state['binding_hash'] == binding_hash(state['binding']))
    _version(state['version'])
    require(1 <= state['version'] <= 4 and type(state['phase']) is str
            and state['phase'] in PHASES)
    ident = state['created_id']
    if ident is not None:
        _id(ident, 'profile-')
        require(ident != state['binding']['owner'])
    refs = state['evidence_refs']
    require(type(refs) is list and len(refs) <= 3)
    for ref in refs:
        _hash(ref)
    require(len(set(refs)) == len(refs))
    if state['phase'] == 'consumed':
        require(state['version'] == 1 and ident is None and not refs)
    elif state['phase'] == 'acknowledged':
        require(state['version'] == 2 and ident is not None and len(refs) == 1)
    elif state['phase'] == 'uncertain':
        require(state['version'] in (2, 3) and len(refs) == state['version'] - 1)
        require((state['version'] == 2 and ident is None)
                or (state['version'] == 3 and ident is not None))
    else:
        require(state['version'] in (3, 4) and ident is not None
                and len(refs) == state['version'] - 1)
    return deepcopy(state)


def consume(binding, expected_version):
    """Propose empty-owner 0->1. NOT an atomic CAS or permission to POST.

    The eventual backend must atomically reject any pre-existing record under
    the canonical owner namespace, across ALL connection/plan/payload variants.
    """
    _version(expected_version)
    require(expected_version == 0)
    value = {'schema_version': 1, 'mode': 'offline_intent_model',
             'binding': deepcopy(binding), 'binding_hash': binding_hash(binding),
             'version': 1, 'phase': 'consumed', 'created_id': None,
             'evidence_refs': [], 'production_enabled': False}
    return validate(value)


def advance(state, expected_version, event, evidence_ref, created_id=None):
    """Propose one monotonic transition; output is never execution authority.

    evidence_ref is an opaque ciphertext SHA256 descriptor, not a URL or proof
    that ciphertext actually exists. The future backend must independently
    validate encrypted durable storage and authorized evidence provenance.
    """
    result = validate(state)
    _version(expected_version)
    require(expected_version == result['version'])
    _hash(evidence_ref)
    require(evidence_ref not in result['evidence_refs'])
    phase = result['phase']
    allowed = {'consumed': ('acknowledge', 'uncertain'),
               'acknowledged': ('uncertain', 'verify'),
               'uncertain': ('reconcile_verified',), 'verified': ()}
    require(type(event) is str and event in allowed[phase])
    if event in ('acknowledge', 'reconcile_verified'):
        _id(created_id, 'profile-')
        require(result['created_id'] in (None, created_id))
        result['created_id'] = created_id
    else:
        require(created_id is None)
    result['phase'] = {'acknowledge': 'acknowledged', 'uncertain': 'uncertain',
                       'verify': 'verified', 'reconcile_verified': 'verified'}[event]
    result['version'] += 1
    result['evidence_refs'].append(evidence_ref)
    try:
        return validate(result)
    except (KeyError, TypeError, ValueError) as exc:
        raise Blocked('offline intent transition blocked') from exc
