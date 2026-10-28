"""Offline exact Plan binding contract. No signer, verifier, replay service or permit."""
import copy
import re

from human_parent_gate import PROOFS
from parent_plan import verify_proposal
from people_core import digest, exact, require, text

BINDING_KEYS = ('owner', 'connection_id', 'operator', 'consent_refs', 'manifest_hash',
                'payload_hashes', 'graph_hash', 'proof_refs', 'data_sha', 'executor_sha',
                'image_digest', 'journal_version', 'plan_id', 'created', 'expires', 'count')


def pattern(value, expression):
    require(type(value) is str and re.fullmatch(expression, value) is not None)


def binding(value):
    exact(value, BINDING_KEYS)
    pattern(value['owner'], r'profile-[0-9]{1,30}')
    pattern(value['connection_id'], r'[A-Za-z0-9_-]{1,64}')
    text(value['operator'])
    require(type(value['consent_refs']) is list and 1 <= len(value['consent_refs']) <= 10)
    for ref in value['consent_refs']:
        pattern(ref, r'[A-Za-z0-9:_-]{1,160}')
    require(len(set(value['consent_refs'])) == len(value['consent_refs']))
    for key in ('manifest_hash', 'graph_hash'):
        pattern(value[key], r'[a-f0-9]{64}')
    for key in ('data_sha', 'executor_sha'):
        pattern(value[key], r'[a-f0-9]{40}')
    pattern(value['image_digest'], r'sha256:[a-f0-9]{64}')
    pattern(value['plan_id'], r'[a-f0-9]{64}')
    require(type(value['journal_version']) is int and value['journal_version'] >= 0)
    require(type(value['count']) is int and 1 <= value['count'] <= 2)
    require(type(value['payload_hashes']) is list
            and len(value['payload_hashes']) == value['count'])
    for item in value['payload_hashes']:
        pattern(item, r'[a-f0-9]{64}')
    require(type(value['created']) is int and type(value['expires']) is int
            and 0 <= value['created'] < value['expires'] <= value['created'] + 900)
    exact(value['proof_refs'], PROOFS)
    # Scope binds each reference but cannot authenticate it or establish its truth.
    for proof in value['proof_refs'].values():
        exact(proof, ('content_hash', 'owner', 'connection_id', 'manifest_hash'))
        pattern(proof['content_hash'], r'[a-f0-9]{64}')
        for key in ('owner', 'connection_id', 'manifest_hash'):
            require(proof[key] == value[key])
    return value


def draft(proposal, supplied_binding):
    """Return a detached draft. Never creates a signed live Plan or approval."""
    verify_proposal(proposal)
    value = copy.deepcopy(binding(supplied_binding))
    require(value['owner'] == 'profile-' + proposal['owner']['node'])
    require(value['operator'] == proposal['operator'])
    require(value['manifest_hash'] == proposal['manifest_hash'])
    require(value['count'] == len(proposal['entries']))
    require(value['payload_hashes'] == [entry['payload_hash'] for entry in proposal['entries']])
    require(value['data_sha'] == proposal['pins']['data_sha']
            and value['executor_sha'] == proposal['pins']['workflow_sha']
            and value['image_digest'] == proposal['pins']['image_digest'])
    basis = {'schema_version': 1, 'kind': 'offline_unsigned_parent_plan_envelope',
             'binding': value, 'signature_verified': False, 'source_authenticated': False,
             'replay_enforced': False, 'creation_enabled': False}
    return {**basis, 'envelope_hash': digest(basis)}


def review(envelope, proposal, expected_binding, now):
    """Compare exact supplied expectations; not an independent trusted authority.

    An attacker controlling both candidate and expected input can make matching
    drafts. That never grants authority: output is always unsigned and disabled.
    """
    exact(envelope, ('schema_version', 'kind', 'binding', 'signature_verified',
                     'source_authenticated', 'replay_enforced', 'creation_enabled', 'envelope_hash'))
    require(type(envelope['schema_version']) is int and envelope['schema_version'] == 1)
    for key in ('signature_verified', 'source_authenticated', 'replay_enforced', 'creation_enabled'):
        require(envelope[key] is False)
    require(type(now) is int)
    binding(envelope['binding'])
    basis = {key: value for key, value in envelope.items() if key != 'envelope_hash'}
    require(envelope['envelope_hash'] == digest(basis))
    expected = draft(proposal, expected_binding)
    require(digest(envelope) == digest(expected))
    require(expected['binding']['created'] <= now < expected['binding']['expires'])
    return {'status': 'offline_binding_matches_only', 'envelope_hash': expected['envelope_hash'],
            'signature_verified': False, 'source_authenticated': False,
            'replay_enforced': False, 'creation_enabled': False}
