"""Offline GitHub evidence-contract candidate. No HTTP, credentials or authority."""
import json
import re

from people_core import Blocked, exact, require

LIMIT = 1024 * 1024


def _id(value):
    require(type(value) is int and 0 < value <= 2**63 - 1)


def _string(value, pattern):
    require(type(value) is str and re.fullmatch(pattern, value) is not None)


def _pins(pins):
    exact(pins, ('owner', 'repo', 'repository_id', 'run_id', 'attempt', 'environment',
                 'environment_id', 'sha', 'branch', 'workflow', 'actor_id', 'reviewer_id'))
    for field in ('repository_id', 'run_id', 'environment_id', 'actor_id', 'reviewer_id'):
        _id(pins[field])
    for field in ('owner', 'repo', 'environment', 'branch'):
        _string(pins[field], r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}')
    _string(pins['workflow'], r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml')
    _string(pins['sha'], r'[0-9a-f]{40}')
    require(type(pins['attempt']) is int and pins['attempt'] == 1)
    require(pins['actor_id'] != pins['reviewer_id'])


def requests(pins):
    """Fixed GET descriptors, not requests to any external service."""
    _pins(pins)
    root = f"/repos/{pins['owner']}/{pins['repo']}"
    run = f"{root}/actions/runs/{pins['run_id']}"
    env = f"{root}/environments/{pins['environment']}"
    return [{'method': 'GET', 'origin': 'https://api.github.com', 'route': route,
             'redirects_allowed': False, 'retries_allowed': False}
            for route in (run, env, run + '/approvals', env + '/deployment-branch-policies')]


def _parse(response, descriptor):
    exact(response, ('request', 'status', 'redirected', 'link', 'raw'))
    require(response['request'] == descriptor and type(response['status']) is int
            and response['status'] == 200 and response['redirected'] is False
            and response['link'] is None)
    raw = response['raw']
    require(type(raw) is bytes and 0 < len(raw) <= LIMIT)

    def unique(pairs):
        value = {}
        for key, leaf in pairs:
            require(key not in value)
            value[key] = leaf
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: require(False))


def inspect(pins, responses):
    """Validate supplied synthetic snapshots. Forged envelopes do NOT prove provenance.

    Real response provenance, freshness, TOCTOU and job/attempt-level review
    correlation are not implemented here. This cannot authorize any execution.
    """
    try:
        descriptors = requests(pins)
        require(type(responses) is list and len(responses) == len(descriptors))
        run, env, approvals, branches = [_parse(r, d) for r, d in zip(responses, descriptors)]
        require(type(run) is dict and type(env) is dict and type(approvals) is list
                and type(branches) is dict)
        require(type(run['id']) is int and run['id'] == pins['run_id']
                and type(run['run_attempt']) is int and run['run_attempt'] == 1
                and run['head_sha'] == pins['sha'] and run['head_branch'] == pins['branch']
                and run['path'] == pins['workflow'] and run['event'] == 'workflow_dispatch'
                and type(run['actor']['id']) is int
                and run['actor']['id'] == pins['actor_id']
                and type(run['triggering_actor']['id']) is int
                and run['triggering_actor']['id'] == pins['actor_id'])
        for repository in (run['repository'], run['head_repository']):
            require(type(repository['id']) is int and repository['id'] == pins['repository_id']
                    and repository['full_name'] == f"{pins['owner']}/{pins['repo']}")
        require(type(env['id']) is int and env['id'] == pins['environment_id']
                and env['name'] == pins['environment'] and env['can_admins_bypass'] is False)
        rules = env['protection_rules']
        require(type(rules) is list and len(rules) == 2)
        by_type = {rule['type']: rule for rule in rules}
        require(set(by_type) == {'required_reviewers', 'branch_policy'})
        review = by_type['required_reviewers']
        require(review['prevent_self_review'] is True)
        reviewers = review['reviewers']
        require(type(reviewers) is list and len(reviewers) == 1
                and reviewers[0]['type'] == 'User'
                and type(reviewers[0]['reviewer']['id']) is int
                and reviewers[0]['reviewer']['id'] == pins['reviewer_id'])
        policy = env['deployment_branch_policy']
        exact(policy, ('protected_branches', 'custom_branch_policies'))
        require(policy['protected_branches'] is False and policy['custom_branch_policies'] is True)
        require(type(branches['total_count']) is int and branches['total_count'] == 1)
        policies = branches['branch_policies']
        require(type(policies) is list and len(policies) == 1
                and policies[0]['name'] == pins['branch'] and policies[0]['type'] == 'branch')
        # No ordering or latest-decision inference: accept exactly one record.
        require(len(approvals) == 1 and approvals[0]['state'] == 'approved'
                and approvals[0]['user']['type'] == 'User'
                and type(approvals[0]['user']['id']) is int
                and approvals[0]['user']['id'] == pins['reviewer_id'])
        environments = approvals[0]['environments']
        require(type(environments) is list and len(environments) == 1
                and type(environments[0]['id']) is int
                and environments[0]['id'] == pins['environment_id']
                and environments[0]['name'] == pins['environment'])
    except (Blocked, KeyError, TypeError, ValueError, UnicodeError, RecursionError, IndexError):
        raise Blocked('GitHub evidence blocked; review protected inputs') from None
    return {'phase': 'synthetic_review_snapshot_consistent', 'production_enabled': False,
            'provenance_verified': False, 'owner_approval_verified': False,
            'payload_approval_verified': False, 'job_review_correlation_verified': False,
            'retry_allowed': False}
