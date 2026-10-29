"""Version2 content-only single-human assurance. No source authentication or grant."""
import re
from copy import deepcopy

from approval_record import EXCLUDED_ACTIONS, _pins, _time
from people_core import digest, exact, require

ASSURANCE = 'single_human_owner_agent_dispatch_independent_agent_review'
SOURCE_KEYS = ('kind', 'principal_id', 'source_ref', 'content_hash')
SOURCE_KINDS = {'owner_grant': 'protected_environment_exact_payload_approval',
                'protected_review': 'protected_environment_human_action',
                'dispatch': 'designated_agent_workflow_dispatch',
                'code_review': 'independent_agent_exact_head_review'}


def _id(value):
    require(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,19}', value) is not None)


def _hash(value):
    require(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) is not None)


def validate(record):
    exact(record, ('schema_version', 'mode', 'assurance', 'human_count',
                   'production_enabled', 'pins', 'exclusions', 'risk_hash',
                   'sources', 'reviewed_executor_sha', 'revocation_epoch'))
    require(type(record['schema_version']) is int and record['schema_version'] == 2)
    require(record['mode'] == 'single_human_approval_content')
    require(record['assurance'] == ASSURANCE and type(record['human_count']) is int
            and record['human_count'] == 1 and record['production_enabled'] is False)
    _pins(record['pins'])
    require(type(record['exclusions']) is list and tuple(record['exclusions']) == EXCLUDED_ACTIONS)
    _hash(record['risk_hash'])
    require(type(record['revocation_epoch']) is int and 0 <= record['revocation_epoch'] < 2**40)
    require(record['reviewed_executor_sha'] == record['pins']['executor_sha'])
    exact(record['sources'], SOURCE_KINDS)
    for role, kind in SOURCE_KINDS.items():
        source = record['sources'][role]
        exact(source, SOURCE_KEYS)
        require(source['kind'] == kind)
        _id(source['principal_id'])
        _hash(source['source_ref'])
        _hash(source['content_hash'])
    s = record['sources']
    # Same sole HUMAN approves exact payload/risk through the SAME protected job approval action. Dispatcher/reviewer-agent are explicitly not extra humans.
    require(s['owner_grant']['principal_id'] == s['protected_review']['principal_id'])
    require(s['dispatch']['principal_id'] != s['owner_grant']['principal_id'])
    require(s['code_review']['principal_id'] != s['dispatch']['principal_id'])
    require(s['code_review']['principal_id'] != s['owner_grant']['principal_id'])
    require(s['owner_grant']['source_ref'] == s['protected_review']['source_ref'])
    require(s['owner_grant']['content_hash'] == s['protected_review']['content_hash'])
    require(len({s[role]['source_ref'] for role in ('owner_grant', 'dispatch', 'code_review')}) == 3)
    return deepcopy(record)


def check(record, expected_record, now):
    """Exact content, not trusted-channel authorship or actual human gate action.

    Expected values MUST come from the future module-owned release config and
    authenticated source capture. Caller-supplied copies cannot supply authority.
    Revocation epoch equality only checks supplied expectations; no revocation
    service/source is queried. No implicit inheritance from version1 approvals.
    """
    value, expected = validate(record), validate(expected_record)
    require(value == expected)
    _time(now)
    require(value['pins']['issued_at'] <= now < value['pins']['expires_at'])
    return {'phase': 'single_human_content_consistent_only', 'schema_version': 2,
            'assurance': ASSURANCE, 'human_count': 1, 'two_humans_verified': False,
            'content_consistent': True, 'record_hash': digest(value),
            'owner_approval_verified': False, 'protected_human_action_verified': False,
            'dispatch_provenance_verified': False, 'independent_review_verified': False,
            'revocation_verified': False, 'post_permitted': False, 'production_enabled': False}
