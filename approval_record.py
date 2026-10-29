"""Pure offline approval-record content check (#256). Never authentication or permission.

Checks that a private approval record is internally well formed and that every
pin matches the exact expected pins the caller supplies, inside a bounded time
window and with the fixed approved exclusions. The result says only that the
content is consistent. It does not prove who created the record, that the owner
or reviewer really approved, that review settings were protected, or that any
request may be sent: external provenance, protected review settings and record
creation authority remain service release blockers (docs/intent-storage-decisions.md,
docs/intent-service-auth-design.md). No clock is read; the caller passes `now`.
"""
import re
from copy import deepcopy

from people_core import digest, exact, require

PIN_KEYS = ('owner', 'connection_id', 'operation', 'payload_hash', 'graph_hash', 'data_hash',
            'executor_sha', 'workflow_sha', 'artifact_hash', 'service_sha', 'policy_hash',
            'recipient', 'run_id', 'run_attempt', 'nonce', 'issued_at', 'expires_at')
RECORD_KEYS = ('schema_version', 'mode', 'production_enabled', 'pins', 'exclusions',
               'approvals')
APPROVAL_KEYS = ('role', 'approver_ref', 'evidence_ref')
ROLES = ('owner', 'human_reviewer')
# Every write other than the one father add-parent is excluded and stays excluded.
EXCLUDED_ACTIONS = ('add_child', 'add_mother', 'add_partner', 'delete', 'fact_cite', 'marriage',
                    'merge', 'profile_update', 'retry', 'source_upload', 'tag', 'union_update')
MAX_WINDOW_SECONDS = 900
_HEX64 = ('payload_hash', 'graph_hash', 'data_hash', 'artifact_hash', 'policy_hash',
          'recipient', 'nonce')
_SHA40 = ('executor_sha', 'workflow_sha', 'service_sha')
_TIME_MAX = 2**40


def _hex(value, size):
    require(type(value) is str and re.fullmatch(f'[0-9a-f]{{{size}}}', value) is not None)


def _time(value):
    require(type(value) is int and 0 < value < _TIME_MAX)


def _pins(pins):
    exact(pins, PIN_KEYS)
    require(type(pins['owner']) is str
            and re.fullmatch(r'profile-[1-9][0-9]{0,29}', pins['owner']) is not None)
    require(type(pins['connection_id']) is str and 0 < len(pins['connection_id']) <= 100
            and re.fullmatch(r'[A-Za-z0-9_-]+', pins['connection_id']) is not None)
    require(pins['operation'] == 'single_father_add_parent')
    for key in _HEX64:
        _hex(pins[key], 64)
    for key in _SHA40:
        _hex(pins[key], 40)
    require(type(pins['run_id']) is str
            and re.fullmatch(r'[1-9][0-9]{0,19}', pins['run_id']) is not None)
    require(type(pins['run_attempt']) is int and pins['run_attempt'] == 1)
    _time(pins['issued_at'])
    _time(pins['expires_at'])
    require(0 < pins['expires_at'] - pins['issued_at'] <= MAX_WINDOW_SECONDS)


def validate(record):
    """Shape only. Returns a copy; contacts nothing."""
    exact(record, RECORD_KEYS)
    require(type(record['schema_version']) is int and record['schema_version'] == 1)
    require(record['mode'] == 'offline_approval_record')
    require(record['production_enabled'] is False)
    _pins(record['pins'])
    require(type(record['exclusions']) is list
            and tuple(record['exclusions']) == EXCLUDED_ACTIONS)
    approvals = record['approvals']
    require(type(approvals) is list and len(approvals) == len(ROLES))
    for approval, role in zip(approvals, ROLES, strict=True):
        exact(approval, APPROVAL_KEYS)
        require(approval['role'] == role)
        _hex(approval['approver_ref'], 64)
        _hex(approval['evidence_ref'], 64)
    # No self-review and no shared evidence between the two roles.
    require(approvals[0]['approver_ref'] != approvals[1]['approver_ref'])
    require(approvals[0]['evidence_ref'] != approvals[1]['evidence_ref'])
    return deepcopy(record)


def check(record, expected_pins, expected_approvals, now):
    """Content consistency against exact expectations at caller time `now`.

    expected_approvals maps each role to its exact {approver_ref, evidence_ref}.
    Returns a fixed result that never grants authentication or permission to send.
    """
    result = validate(record)
    _pins(expected_pins)
    for key in PIN_KEYS:
        require(result['pins'][key] == expected_pins[key])
    exact(expected_approvals, ROLES)
    for approval in result['approvals']:
        want = expected_approvals[approval['role']]
        exact(want, ('approver_ref', 'evidence_ref'))
        require(approval['approver_ref'] == want['approver_ref'])
        require(approval['evidence_ref'] == want['evidence_ref'])
    _time(now)
    require(result['pins']['issued_at'] <= now < result['pins']['expires_at'])
    return {'mode': 'offline_approval_record', 'content_consistent': True,
            'authenticated': False, 'post_permitted': False, 'production_enabled': False,
            'record_hash': digest(result)}
