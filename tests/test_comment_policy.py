"""Owner comment commands are exact, read-only and confined to one issue."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('command_gate', ROOT / '.github/geni_command_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
POLICY = json.loads((ROOT / '.github/geni-command-policy.json').read_text())
EVENT = {'repository': {'full_name': 'reihlinstinct/geni-uploader'}, 'action': 'created',
         'issue': {'number': 119}, 'sender': {'login': 'reihl'},
         'comment': {'performed_via_github_app': None, 'body': '/geni plan', 'user': {'login': 'reihl', 'type': 'User'},
                     'created_at': 'ZZtimestamp', 'updated_at': 'ZZtimestamp'}}


def mode(event=None, policy=None, **kwargs):
    return gate.select_mode(event or EVENT, policy or POLICY,
                            kwargs.get('event_name', 'issue_comment'),
                            kwargs.get('actor', 'reihl'), kwargs.get('triggering_actor', 'reihl'))


@pytest.mark.parametrize('command', ['/geni plan', '/geni details-plan'])
def test_exact_commands(command):
    event = copy.deepcopy(EVENT)
    event['comment']['body'] = command
    assert mode(event) == command.split()[-1]


@pytest.mark.parametrize('command', ['/geni run', '/geni details-repair', '/geni plan YES',
    '/geni plan\n', ' /geni plan', '/geni plan ', '```/geni plan```',
    '/geni plan; echo ZZsecret', '/geni plan$(id)', '/geni plan\n/geni run',
    '/GENI plan', '/geni\tplan', '/geni  plan'])
def test_reject_extra_text_and_write_modes(command):
    event = copy.deepcopy(EVENT)
    event['comment']['body'] = command
    assert mode(event) is None


@pytest.mark.parametrize('field,value', [('action', 'edited'), ('action', 'deleted'),
    ('repository', {'full_name': 'ZZfork/repo'}), ('issue', {'number': 120}),
    ('issue', {'number': 119, 'pull_request': {}}), ('sender', {'login': 'ZZother'})])
def test_reject_context(field, value):
    event = copy.deepcopy(EVENT)
    event[field] = value
    assert mode(event) is None


@pytest.mark.parametrize('field,value', [('user', {'login': 'reihlinstinct', 'type': 'User'}),
    ('user', {'login': 'reihl', 'type': 'Bot'}), ('updated_at', 'ZZedited'),
    ('created_at', None)])
def test_reject_comment_identity_and_edits(field, value):
    event = copy.deepcopy(EVENT)
    event['comment'][field] = value
    assert mode(event) is None


@pytest.mark.parametrize('kwargs', [{'actor': 'ZZother'}, {'triggering_actor': 'ZZother'},
    {'event_name': 'pull_request'}, {'event_name': 'push'}, {'event_name': 'repository_dispatch'}])
def test_reject_actor_and_event(kwargs):
    assert mode(**kwargs) is None


def test_policy_cannot_expand_commands_or_contain_private_selections():
    for extra in ('run', 'private_ref', 'manifest', 'expect_sha'):
        policy = copy.deepcopy(POLICY)
        policy[extra] = 'ZZPrivate'
        assert mode(policy=policy) is None
    policy = copy.deepcopy(POLICY)
    policy['commands']['/geni run'] = 'run'
    assert mode(policy=policy) is None


def test_manual_modes_remain_supported_but_comment_cannot_claim_dispatch():
    event = copy.deepcopy(EVENT)
    event['inputs'] = {'mode': 'details-repair'}
    assert mode(event) == 'plan'
    assert mode(event, event_name='workflow_dispatch') == 'details-repair'


def test_workflow_default_branch_policy_and_no_comment_shell_interpolation():
    text = (ROOT / '.github/workflows/geni-upload.yml').read_text()
    data = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(data['on']) == {'workflow_dispatch', 'issue_comment'}
    assert data['on']['issue_comment']['types'] == ['created']
    policy = data['jobs']['command-policy']
    assert policy['permissions'] == {'contents': 'read'}
    assert policy['steps'][0]['with']['ref'] == '${{ github.sha }}'
    assert policy['steps'][0]['with']['persist-credentials'] == 'false'
    assert data['jobs']['upload']['needs'] == 'command-policy'
    assert 'needs.command-policy.outputs.allowed' in data['jobs']['upload']['if']
    assert 'fromJSON' in data['jobs']['upload']['if']
    assert 'github.event.comment.body' not in text
    assert 'github.event.issue' not in text
    assert 'CONFIRM: ${{ inputs.confirm }}' in text
    assert 'MODE: ${{ needs.command-policy.outputs.mode }}' in text
    assert 'Agents never post' in (ROOT / 'WORKING.md').read_text()


def test_issue_number_requires_integer_and_timestamp_nonempty():
    event = copy.deepcopy(EVENT)
    event['issue']['number'] = '119'
    assert mode(event) is None
    event = copy.deepcopy(EVENT)
    event['comment']['created_at'] = event['comment']['updated_at'] = ''
    assert mode(event) is None


@pytest.mark.parametrize('app', [{'slug': 'ZZagent'}, {}, 'ZZunexpected', False, 0])
def test_app_mediated_commands_are_rejected(app):
    event = copy.deepcopy(EVENT)
    event['comment']['performed_via_github_app'] = app
    assert mode(event) is None


def test_explicit_no_app_owner_comment_is_accepted():
    event = copy.deepcopy(EVENT)
    event['comment']['performed_via_github_app'] = None
    assert mode(event) == 'plan'


def test_unrelated_comments_never_enter_source_concurrency():
    data = yaml.load((ROOT / '.github/workflows/geni-upload.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'concurrency' not in data
    assert 'concurrency' not in data['jobs']['command-policy']
    upload = data['jobs']['upload']
    assert upload['concurrency'] == {'group': 'geni-upload', 'cancel-in-progress': 'false'}
    assert "needs.command-policy.outputs.allowed == 'true'" in upload['if']
    event = copy.deepcopy(EVENT)
    event['comment']['body'] = 'ZZunrelated owner comment'
    assert mode(event) is None
    event['issue']['number'] = 121
    assert mode(event) is None


def test_missing_app_attribution_is_rejected():
    event = copy.deepcopy(EVENT)
    del event['comment']['performed_via_github_app']
    assert mode(event) is None


def test_queue_limit_warning_stays_documented():
    text = (ROOT / 'WORKING.md').read_text()
    assert 'Do not post plan commands while a write run is queued.' in text
    assert 'one pending job' in text
