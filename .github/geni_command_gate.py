"""Exact owner-only read-only command gate; never execute comment content."""
import json
import os
from pathlib import Path


def select_mode(event, policy, event_name, actor, triggering_actor):
    if (set(policy) != {'schema_version', 'repository', 'owner', 'issue_number', 'commands'}
            or policy['schema_version'] != 1 or type(policy['issue_number']) is not int
            or policy['issue_number'] <= 0
            or policy['commands'] != {'/geni plan': 'plan',
                                      '/geni details-plan': 'details-plan'}
            or policy['owner'] != 'reihl'
            or policy['repository'] != 'reihlinstinct/geni-uploader'):
        return None
    if (event.get('repository', {}).get('full_name') != policy['repository']
            or actor != policy['owner'] or triggering_actor != policy['owner']):
        return None
    if event_name == 'workflow_dispatch':
        return event.get('inputs', {}).get('mode')
    issue, comment = event.get('issue', {}), event.get('comment', {})
    if (event_name != 'issue_comment' or event.get('action') != 'created'
            or 'pull_request' in issue or type(issue.get('number')) is not int
            or issue.get('number') != policy['issue_number']
            or comment.get('user', {}).get('login') != policy['owner']
            or event.get('sender', {}).get('login') != policy['owner']
            or comment.get('user', {}).get('type') != 'User'
            or 'performed_via_github_app' not in comment
            or comment['performed_via_github_app'] is not None
            or comment.get('created_at') != comment.get('updated_at')
            or not isinstance(comment.get('created_at'), str)
            or not comment['created_at']):
        return None
    return policy['commands'].get(comment.get('body'))


def main():
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        policy = json.loads(Path('.github/geni-command-policy.json').read_text())
        mode = select_mode(event, policy, os.environ['GITHUB_EVENT_NAME'],
                           os.environ['GITHUB_ACTOR'], os.environ['GITHUB_TRIGGERING_ACTOR'])
        # Fixed allowlist for outputs, even on manual events.
        if mode not in {'plan', 'details-plan', 'run', 'details-repair', 'selftest',
                        'whoami', 'contrast', 'guidmap', 'pguid', 'listing-shape'}:
            mode = None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        mode = None
    with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
        out.write('allowed=' + ('true' if mode else 'false') + '\n')
        if mode:
            out.write('mode=' + mode + '\n')


if __name__ == '__main__':
    main()
