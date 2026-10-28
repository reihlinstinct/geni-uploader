"""Pure offline per-profile outcome model (#244). No store, network or authority.

Tracks what is known after a profile create, separately from the create intent:
the canonical created ID, an optional vendor-returned profile URL confirmed by
readback, and separately approved source-upload / tag / fact-citation stages.
Nothing here permits a request. A verified stage proves only that the caller
reported readback evidence; evidence refs are opaque ciphertext SHA256
descriptors, never URLs, plaintext or names. Records hold IDs, a URL and hashes
only and must never be written to upload-status.yaml or any public artifact.
"""
import re
from copy import deepcopy

from parent_intent_model import validate as validate_intent
from people_core import Blocked, digest, exact, require

KINDS = ('source_upload', 'tag', 'fact_cite')
STAGE_PHASES = ('approved', 'consumed', 'acknowledged', 'uncertain', 'verified', 'unsupported')
URL_STATES = ('pending', 'not_in_response', 'verified')
RECORD_KEYS = ('schema_version', 'mode', 'production_enabled', 'intent_binding_hash',
               'profile', 'stages')
PROFILE_KEYS = ('created_id', 'phase', 'url', 'url_state')
STAGE_KEYS = ('kind', 'approval_ref', 'artifact_hash', 'target', 'phase', 'object_id',
              'evidence_refs')
_ALLOWED = {'approved': ('consume',), 'consumed': ('acknowledge', 'uncertain'),
            'acknowledged': ('verify', 'uncertain'), 'uncertain': ('reconcile_verified',),
            'verified': (), 'unsupported': ()}
_NEXT = {'consume': 'consumed', 'acknowledge': 'acknowledged', 'uncertain': 'uncertain',
         'verify': 'verified', 'reconcile_verified': 'verified'}


def _hash(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)


def _profile_id(value):
    require(type(value) is str and re.fullmatch(r'profile-[1-9][0-9]{0,29}', value) is not None)


def _object_id(value):
    require(type(value) is str
            and re.fullmatch(r'(?:document|photo)-[1-9][0-9]{0,29}', value) is not None)


def _url(value):
    require(type(value) is str and 0 < len(value) <= 300 and value.isascii()
            and value.startswith('https://') and not any(c.isspace() for c in value))


def approval_ref(approval_text):
    """SHA256 of the exact approval text, same canonical digest as intent bindings."""
    require(type(approval_text) is str and 0 < len(approval_text.strip()) <= 4000)
    return digest(approval_text)


def _validate_stage(stage, created_id):
    exact(stage, STAGE_KEYS)
    require(stage['kind'] in KINDS and stage['phase'] in STAGE_PHASES)
    _hash(stage['approval_ref'])
    _hash(stage['artifact_hash'])
    require(stage['target'] == created_id)
    refs = stage['evidence_refs']
    require(type(refs) is list and len(refs) <= 3)
    for ref in refs:
        _hash(ref)
    phase, kind, obj = stage['phase'], stage['kind'], stage['object_id']
    if kind == 'fact_cite':
        # No citation contract exists; never simulate one (docs/source-details-design.md).
        require(phase == 'unsupported' and obj is None and not refs)
        return
    require(phase != 'unsupported')
    if kind == 'tag':
        require(obj is None)
    elif obj is not None:
        _object_id(obj)
    count = {'approved': 0, 'consumed': 0, 'acknowledged': 1}.get(phase)
    if count is not None:
        require(len(refs) == count)
    elif phase == 'uncertain':
        require(len(refs) in (1, 2))
    else:
        require(len(refs) in (2, 3))
    if kind == 'source_upload':
        if phase in ('approved', 'consumed'):
            require(obj is None)
        elif phase in ('acknowledged', 'verified'):
            require(obj is not None)


def validate(record):
    """Reject drift. Returns a copy; contacts no store."""
    exact(record, RECORD_KEYS)
    require(type(record['schema_version']) is int and record['schema_version'] == 1)
    require(record['mode'] == 'offline_outcome_model')
    require(record['production_enabled'] is False)
    _hash(record['intent_binding_hash'])
    profile = record['profile']
    exact(profile, PROFILE_KEYS)
    _profile_id(profile['created_id'])
    require(profile['phase'] in ('acknowledged', 'verified'))
    require(profile['url_state'] in URL_STATES)
    if profile['url_state'] == 'verified':
        _url(profile['url'])
        require(profile['phase'] == 'verified')
    else:
        require(profile['url'] is None)
    stages = record['stages']
    require(type(stages) is list and len(stages) <= 50)
    keys, refs = set(), []
    for stage in stages:
        _validate_stage(stage, profile['created_id'])
        require(profile['phase'] == 'verified')
        key = (stage['kind'], stage['artifact_hash'], stage['target'])
        require(key not in keys)
        keys.add(key)
        refs += stage['evidence_refs']
    require(len(set(refs)) == len(refs))
    return deepcopy(record)


def from_intent(intent_state):
    """Open a record for a profile the intent model already knows. Not a create."""
    intent = validate_intent(intent_state)
    require(intent['phase'] in ('acknowledged', 'verified') and intent['created_id'] is not None)
    return validate({'schema_version': 1, 'mode': 'offline_outcome_model',
                     'production_enabled': False,
                     'intent_binding_hash': intent['binding_hash'],
                     'profile': {'created_id': intent['created_id'], 'phase': intent['phase'],
                                 'url': None, 'url_state': 'pending'},
                     'stages': []})


def sync_profile(record, intent_state):
    """Mirror a later verified intent. The created ID can never change."""
    result, intent = validate(record), validate_intent(intent_state)
    require(intent['binding_hash'] == result['intent_binding_hash'])
    require(intent['created_id'] == result['profile']['created_id'])
    require(intent['phase'] == 'verified')
    result['profile']['phase'] = 'verified'
    return validate(result)


def record_profile_url(record, response_url, readback_url):
    """Accept a URL only if the vendor response returned it and readback confirms it.

    No URL in the response is its own state; a URL is never built from the ID.
    Set once; a later different URL is blocked.
    """
    result = validate(record)
    profile = result['profile']
    require(profile['phase'] == 'verified' and profile['url_state'] == 'pending')
    if response_url is None:
        require(readback_url is None)
        profile['url_state'] = 'not_in_response'
    else:
        _url(response_url)
        require(readback_url == response_url)
        profile['url'], profile['url_state'] = response_url, 'verified'
    return validate(result)


def add_stage(record, kind, approval_text, artifact_hash):
    """Record one separately approved stage for this record's own profile only."""
    result = validate(record)
    require(kind in KINDS)
    require(result['profile']['phase'] == 'verified')
    _hash(artifact_hash)
    if kind == 'tag':
        require(any(s['kind'] == 'source_upload' and s['artifact_hash'] == artifact_hash
                    and s['phase'] == 'verified' for s in result['stages']))
    ref = approval_ref(approval_text)
    require(all(s['approval_ref'] != ref for s in result['stages']))
    result['stages'].append({'kind': kind, 'approval_ref': ref, 'artifact_hash': artifact_hash,
                             'target': result['profile']['created_id'],
                             'phase': 'unsupported' if kind == 'fact_cite' else 'approved',
                             'object_id': None, 'evidence_refs': []})
    try:
        return validate(result)
    except (KeyError, TypeError, ValueError) as exc:
        raise Blocked('offline outcome stage blocked') from exc


def advance_stage(record, index, expected_phase, event, evidence_ref=None, object_id=None):
    """One monotonic stage transition. Uncertain finishes only via GET reconciliation."""
    result = validate(record)
    stages = result['stages']
    require(type(index) is int and 0 <= index < len(stages))
    stage = stages[index]
    require(stage['phase'] == expected_phase)
    require(type(event) is str and event in _ALLOWED[stage['phase']])
    if event == 'consume':
        require(evidence_ref is None and object_id is None)
    else:
        _hash(evidence_ref)
        stage['evidence_refs'].append(evidence_ref)
    if event in ('acknowledge', 'reconcile_verified') and stage['kind'] == 'source_upload':
        _object_id(object_id)
        require(stage['object_id'] in (None, object_id))
        stage['object_id'] = object_id
    else:
        require(object_id is None)
    stage['phase'] = _NEXT[event]
    try:
        return validate(result)
    except (KeyError, TypeError, ValueError) as exc:
        raise Blocked('offline outcome transition blocked') from exc


def outcome(record):
    """Derived summary. Never complete from a create alone; citations are unsupported."""
    result = validate(record)
    if result['profile']['phase'] != 'verified':
        return 'profile_unverified'
    stages = [s for s in result['stages'] if s['kind'] != 'fact_cite']
    if any(s['phase'] == 'uncertain' for s in stages):
        return 'partial_uncertain'
    uploads = [s for s in stages if s['kind'] == 'source_upload']
    tags = [s for s in stages if s['kind'] == 'tag']
    if not uploads or any(s['phase'] != 'verified' for s in uploads):
        return 'profile_created_source_pending'
    if not tags or any(s['phase'] != 'verified' for s in tags):
        return 'source_attached'
    return 'sources_tagged'
