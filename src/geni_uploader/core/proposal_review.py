"""Complete offline proposal closure. No I/O, authority or live execution."""
import copy
import re

from geni_uploader.core.people import digest, exact, require, validate, warnings


def payloads(data):
    """Deterministic approved-name payload proposal, not verified API encoding."""
    validate(data)
    result = []
    for parent in data['parents']:
        require('en' in parent['names'])
        # English main-name encoding is a proposal until vendor proofs are reviewed.
        result.append({'names': copy.deepcopy(parent['names']),
                       **copy.deepcopy(parent['names']['en']),
                       'gender': parent['gender'], 'is_alive': parent['is_alive'],
                       'public': False})
    return result


BLOCKERS = ('owner_connection_identity_not_verified', 'exact_owner_create_approval_not_verified',
            'hidden_parent_completeness_unproved', 'add_parent_slot_semantics_unproved',
            'private_and_default_locale_create_readback_unproved',
            'production_human_runner_not_implemented')


def proposal(data, pins):
    """A draft, not an authenticated remote plan receipt. No live state read."""
    data = copy.deepcopy(validate(data))
    exact(pins, ('data_sha', 'workflow_sha', 'image_digest'))
    for key in ('data_sha', 'workflow_sha'):
        require(type(pins[key]) is str and re.fullmatch(r'[a-f0-9]{40}', pins[key]))
    require(type(pins['image_digest']) is str
            and re.fullmatch(r'sha256:[a-f0-9]{64}', pins['image_digest']))
    proposed = payloads(data)
    entries = []
    for parent, payload in zip(data['parents'], proposed, strict=True):
        require(parent['gender'] in ('male', 'female'))
        # A Hebrew input must retain Hebrew and English, with explicit review.
        require('he' in parent['names'] and 'en' in parent['names'])
        entries.append({'operation': parent['local_id'], 'action': 'create_parent',
                        'anchor': parent['anchor'], 'proposed_payload': payload,
                        'payload_hash': digest(payload),
                        'readiness': 'blocked', 'duplicate_status': 'not_checked'})
    basis = {'schema_version': 1, 'kind': 'offline_parent_proposal',
             'owner': data['owner'], 'operator': data['operator'],
             'approval_as_supplied_not_authenticated': data['approval'],
             'manifest_hash': digest(data), 'pins': copy.deepcopy(pins),
             'entries': entries, 'blockers': list(BLOCKERS), 'warnings': warnings(data),
             'creation_enabled': False, 'live_checks_performed': False,
             'approval_grants_write': False}
    return {**basis, 'proposal_hash': digest(basis)}


def verify_proposal(value):
    exact(value, ('schema_version', 'kind', 'owner', 'operator',
                  'approval_as_supplied_not_authenticated', 'manifest_hash', 'pins', 'entries',
                  'blockers', 'warnings', 'creation_enabled', 'live_checks_performed',
                  'approval_grants_write', 'proposal_hash'))
    expected = value['proposal_hash']
    basis = {k: v for k, v in value.items() if k != 'proposal_hash'}
    require(type(expected) is str and expected == digest(basis))
    require(value.get('creation_enabled') is False and value.get('live_checks_performed') is False
            and value.get('approval_grants_write') is False and value.get('blockers') == list(BLOCKERS))
    require(type(value.get('entries')) is list and 1 <= len(value['entries']) <= 2)
    for entry in value['entries']:
        exact(entry, ('operation', 'action', 'anchor', 'proposed_payload', 'payload_hash',
                      'readiness', 'duplicate_status'))
        require(entry['action'] == 'create_parent' and entry['readiness'] == 'blocked'
                and entry['duplicate_status'] == 'not_checked')
        require(entry['anchor'] == value['owner']['node'])
        require(entry['payload_hash'] == digest(entry['proposed_payload']))
    # Rebuild the canonical proposal, rather than trusting a self-recomputed hash.
    reconstructed = {'schema_version': 1, 'owner': value['owner'], 'operator': value['operator'],
                     'approval': value['approval_as_supplied_not_authenticated'], 'parents': []}
    for entry in value['entries']:
        payload = entry['proposed_payload']
        require(type(payload) is dict and type(payload.get('names')) is dict
                and type(payload['names'].get('en')) is dict)
        exact(payload, ('names', *payload['names']['en'],
                        'gender', 'is_alive', 'public'))
        reconstructed['parents'].append({'local_id': entry['operation'], 'relation': 'parent',
                                         'anchor': entry['anchor'], 'names': payload['names'],
                                         'gender': payload['gender'], 'is_alive': payload['is_alive'],
                                         'public': payload['public']})
    require(digest(proposal(reconstructed, value['pins'])) == digest(value))
    return expected


