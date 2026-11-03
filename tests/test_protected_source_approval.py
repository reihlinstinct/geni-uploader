"""Synthetic protected source approval contract and mutation-sensitive gates."""
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import geni_uploader.runners.protected_source_approval as p


def fixture(mode='plan'):
    c = {'schema': 1, 'private_repo_url': 'https://github.com/ZZ-owner/ZZ-data.git',
         'private_ref': 'ZZ-source', 'private_expect_sha': 'a' * 40,
         'manifest_path': 'ZZ/ZZ-manifest.yaml', 'recipient': 'age1' + 'a' * 58}
    digest = hashlib.sha256(p.canonical(c)).hexdigest()
    e = {'GITHUB_REPOSITORY': p.REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
         'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
         'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_RUN_ATTEMPT': '1',
         'GITHUB_SHA': 'b' * 40, 'GITHUB_RUN_ID': '99002', 'SOURCE_EXECUTOR_SHA': 'b' * 40,
         'SOURCE_CONFIG_SHA256': digest, 'SOURCE_PACKAGE_JSON': p.canonical(c).decode(),
         'SOURCE_MODE': mode, 'SOURCE_CONFIRM': 'PLAN_SOURCES' if mode == 'plan' else 'UPLOAD_SOURCES',
         'SOURCE_PLAN_RUN_ID': '' if mode == 'plan' else '99001',
         'SOURCE_TREE_PAT': 'ZZ-tree-secret', 'GENI_ACCESS_TOKEN': 'ZZ-geni-secret'}
    run = {'head_sha': 'b' * 40, 'event': 'workflow_dispatch', 'run_attempt': 1,
           'actor': {'login': 'reihlinstinct'}, 'triggering_actor': {'login': 'reihlinstinct'},
           'path': p.WORKFLOW, 'head_branch': 'master', 'workflow_id': 999,
           'display_title': p.title(mode, digest, 'b' * 40, e['SOURCE_PLAN_RUN_ID'])}
    prior = dict(copy.deepcopy(run), status='completed', conclusion='success',
                 created_at='1970-01-01T00:01:00Z', updated_at='1970-01-01T00:01:40Z', display_title=p.title('plan', digest, 'b' * 40))
    data = {'actions/runs/99002': run, 'actions/runs/99001': prior,
            'environments/father-create': {'can_admins_bypass': False,
                'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
                'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                                     'reviewers': [{'reviewer': {'login': 'reihl'}}]}]},
            'environments/father-create/deployment-branch-policies': {
                'total_count': 1, 'branch_policies': [{'name': 'master', 'type': 'branch'}]}}
    data['actions/workflows/protected-source-approval.yml/runs?event=workflow_dispatch&per_page=100&created=%3E%3D1970-01-01T00:01:00Z'] = {'total_count': 1, 'workflow_runs': [dict(run, id=99002)]}
    return c, e, data


@pytest.mark.parametrize('mode', ['plan', 'run'])
def test_valid_separate_plan_or_run(mode):
    c, e, data = fixture(mode)
    assert p.validate(e, data.__getitem__, lambda: 200) == (c, mode)


@pytest.mark.parametrize('key,value', [('GITHUB_ACTOR', 'ZZ-other'),
    ('GITHUB_TRIGGERING_ACTOR', 'ZZ-other'), ('GITHUB_REF', 'refs/heads/ZZ-other'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'ZZ/ZZ'),
    ('GITHUB_SHA', 'c' * 40), ('SOURCE_EXECUTOR_SHA', 'bad'), ('SOURCE_CONFIG_SHA256', 'c' * 64),
    ('SOURCE_MODE', 'details-repair'), ('SOURCE_CONFIRM', 'UPLOAD_SOURCES'),
    ('SOURCE_PLAN_RUN_ID', '99001'), ('GITHUB_RUN_ID', '../ZZ')])
def test_dispatch_envelope_gates(key, value):
    _, e, data = fixture(); e[key] = value
    with pytest.raises((p.Blocked, KeyError)): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('key,value', [('schema', True), ('private_repo_url', 'https://ZZ.invalid/ZZ.git'),
    ('private_ref', '../ZZ'), ('private_ref', '-ZZ'), ('private_expect_sha', 'bad'),
    ('manifest_path', '../ZZ.yaml'), ('manifest_path', 'ZZ;ZZ.yaml'), ('recipient', 'ZZ')])
def test_package_values_rejected_even_with_correct_hash(key, value):
    c, _, _ = fixture(); c[key] = value; raw = p.canonical(c)
    with pytest.raises(p.Blocked): p.configuration(raw, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('key,value', [('status', 'in_progress'), ('conclusion', 'failure'),
    ('event', 'push'), ('run_attempt', 2), ('actor', {'login': 'ZZ-other'}),
    ('triggering_actor', {'login': 'ZZ-other'}), ('head_sha', 'c' * 40), ('head_branch', 'ZZ-other'),
    ('path', '.github/workflows/ZZ-other.yml'), ('workflow_id', 123),
    ('display_title', 'ZZ-wrong-package'), ('updated_at', '1970-01-03T00:00:00Z')])
def test_prior_plan_bound_to_exact_successful_package(key, value):
    _, e, data = fixture('run'); data['actions/runs/99001'][key] = value
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('clock', [99, 86501])
def test_prior_plan_not_future_or_expired(clock):
    _, e, data = fixture('run')
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: clock)


@pytest.mark.parametrize('prior_id', ['', '99002', '../ZZ'])
def test_run_requires_distinct_plan_id(prior_id):
    _, e, data = fixture('run'); e['SOURCE_PLAN_RUN_ID'] = prior_id
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('key,value', [('head_sha', 'c' * 40), ('event', 'push'), ('run_attempt', 2),
    ('actor', {'login': 'ZZ-other'}), ('triggering_actor', {'login': 'ZZ-other'}),
    ('path', 'ZZ-other'), ('head_branch', 'ZZ-other'), ('display_title', 'ZZ-other')])
def test_current_run_independently_bound(key, value):
    _, e, data = fixture(); data['actions/runs/99002'][key] = value
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('change', ['bypass', 'self', 'reviewer', 'branch', 'branchcount', 'policy'])
def test_human_environment_protection_required(change):
    _, e, data = fixture(); env = data['environments/father-create']; branches = data['environments/father-create/deployment-branch-policies']
    if change == 'bypass': env['can_admins_bypass'] = True
    if change == 'self': env['protection_rules'][0]['prevent_self_review'] = False
    if change == 'reviewer': env['protection_rules'][0]['reviewers'][0]['reviewer']['login'] = 'ZZ-other'
    if change == 'branch': branches['branch_policies'][0]['name'] = 'ZZ-other'
    if change == 'branchcount': branches['total_count'] = 2
    if change == 'policy': env['deployment_branch_policy']['protected_branches'] = True
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('mode,status', [('plan', 0), ('run', 0), ('run', 1)])
def test_real_envelope_to_container_boundary_encrypted_output(tmp_path, mode, status):
    c, e, data = fixture(mode); e['SOURCE_TEMP'] = str(tmp_path / 'ZZ-out'); calls = []
    def call(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == 'docker':
            kwargs['stdout'].write(b'ZZ-private output')
            if mode == 'plan': (tmp_path / 'ZZ-out/plan/report.json').write_text('{"ZZ":true}')
        return SimpleNamespace(returncode=status if args[0] == 'docker' else 0)
    if status:
        with pytest.raises(p.Blocked): p.execute(e, data.__getitem__, lambda: 200, call)
    else: assert p.execute(e, data.__getitem__, lambda: 200, call)
    assert calls[0][0][0] == 'age'
    docker = next(args for args, _ in calls if args[0] == 'docker')
    assert p.IMAGE in docker and '--token-file' in docker and '--manifest' in docker
    assert c['private_expect_sha'] in ' '.join(docker)
    assert not any('ZZ-tree-secret' in x or 'ZZ-geni-secret' in x for x in docker)
    assert ('YES' in docker) == (mode == 'run')
    assert any(args[0] == 'age' and 'source-output.age' in ' '.join(args) for args, _ in calls)
    assert any('source-plan.age' in ' '.join(args) for args, _ in calls) == (mode == 'plan')


def test_failed_encryption_preflight_prevents_container(tmp_path):
    _, e, data = fixture(); e['SOURCE_TEMP'] = str(tmp_path / 'ZZ-out'); calls = []
    def call(args, **kwargs):
        calls.append(args); raise subprocess.CalledProcessError(1, args)
    with pytest.raises(subprocess.CalledProcessError): p.execute(e, data.__getitem__, lambda: 200, call)
    assert len(calls) == 1 and calls[0][0] == 'age'


def test_main_never_prints_external_exception(monkeypatch, capsys):
    monkeypatch.setattr(p, 'execute', lambda *_: (_ for _ in ()).throw(ValueError('ZZ-secret-data')))
    assert p.main() == 1
    assert 'ZZ-secret-data' not in capsys.readouterr().out


def test_workflow_gate_and_original_route_unchanged():
    root = Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root / '.github/workflows/geni-upload.yml').read_bytes()).hexdigest() == '7759137b504cfbf20fd8e868cbb612ffae4a510a57cd47bf32142eebc16592bf'
    s = (root / p.WORKFLOW).read_text()
    for gate in ['environment: father-create', 'github.sha == inputs.executor_sha',
                 'github.run_attempt == 1', 'github.actor == \'reihlinstinct\'',
                 'github.triggering_actor == \'reihlinstinct\'', 'PLAN_SOURCES', 'UPLOAD_SOURCES',
                 'PROTECTED_SOURCE_PACKAGE_JSON', 'group: geni-upload', 'cancel-in-progress: false',
                 'persist-credentials: false', 'retention-days: 1', 'if: always()']:
        assert gate in s
    assert 'workflow_dispatch:' in s and 'schedule:' not in s and 'pull_request:' not in s


@pytest.mark.parametrize('state', ['queued', 'in_progress', 'completed', 'waiting'])
def test_one_upload_per_plan_even_failed_or_rejected(state):
    _, e, data = fixture('run')
    history = next(v for k, v in data.items() if '/runs?' in k)
    history['workflow_runs'].append(dict(data['actions/runs/99002'], id=99003, status=state))
    history['total_count'] += 1
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('count', [99, 100])
def test_history_truncation_or_limit_blocks(count):
    _, e, data = fixture('run'); history = next(v for k, v in data.items() if '/runs?' in k)
    history['total_count'] = count
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('path', ['environments/father-create-x', 'environments/father-create/secrets',
                                  'actions/runs/1/other', 'actions/runs/../ZZ', 'ZZ'])
def test_github_path_allowlist_exact(path):
    with pytest.raises(p.Blocked): p.github_get('ZZ-token', path)


EXPECTED_GATE = """${{ github.repository == 'reihlinstinct/geni-uploader' && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/master' && github.sha == inputs.executor_sha && github.actor == 'reihlinstinct' && github.triggering_actor == 'reihlinstinct' && github.run_attempt == 1 && ((inputs.mode == 'plan' && inputs.confirm == 'PLAN_SOURCES' && inputs.plan_run_id == '') || (inputs.mode == 'run' && inputs.confirm == 'UPLOAD_SOURCES' && inputs.plan_run_id != '')) }}"""


def normalize_expression(value):
    # GitHub single-quoted strings escape a quote by doubling it. Tokenize
    # strings intact, then discard whitespace only between those tokens.
    tokens = re.findall(r"'(?:[^']|'')*'|[^']+", value)
    return ''.join(token if token.startswith("'") else re.sub(r'\s+', '', token)
                   for token in tokens)


def check_workflow_contract(workflow):
    job = workflow['jobs']['source']
    # Exact token expression, allowing whitespace only. A redundant true OR,
    # weakened operator, changed operand or grouping cannot keep this contract.
    assert normalize_expression(job['if']) == normalize_expression(EXPECTED_GATE)
    assert job['environment'] == 'father-create'
    artifacts = [step for candidate in workflow['jobs'].values()
                 for step in candidate['steps']
                 if step.get('uses', '').lower().startswith('actions/upload-artifact@')]
    assert len(artifacts) == 1
    assert [step['with']['path'] for step in artifacts] == [
        '${{ runner.temp }}/protected-source/encrypted/*.age']
    for name, value in workflow['jobs'].items():
        if 'secrets.' in json.dumps(value): assert name == 'source' and value['environment'] == 'father-create'
    step = next(x for x in job['steps'] if 'SOURCE_PACKAGE_JSON' in x.get('env', {}))
    assert step['env']['SOURCE_PACKAGE_JSON'] == '${{ secrets.PROTECTED_SOURCE_PACKAGE_JSON }}'
    assert step['env']['SOURCE_TREE_PAT'] == '${{ secrets.FAMILY_TREE_PAT }}'
    assert step['env']['GENI_ACCESS_TOKEN'] == '${{ secrets.GENI_ACCESS_TOKEN }}'


def workflow_fixture():
    import yaml
    return yaml.safe_load((Path(__file__).resolve().parents[1] / p.WORKFLOW).read_text())


def test_parsed_workflow_exact_dispatch_expression_and_all_artifacts():
    check_workflow_contract(workflow_fixture())


@pytest.mark.parametrize('mutation', ['true_or', 'and_to_or', 'or_to_and', 'ungroup',
    'repository', 'event', 'ref', 'executor', 'actor', 'triggering_actor', 'attempt',
    'plan_mode', 'plan_confirm', 'empty_plan_id', 'run_mode', 'run_confirm', 'required_plan_id'])
def test_workflow_gate_negative_mutations_killed(mutation):
    workflow = workflow_fixture(); gate = workflow['jobs']['source']['if']
    replacements = {
        'true_or': ('${{', '${{ true ||'), 'and_to_or': (' && ', ' || '),
        'or_to_and': (' || ', ' && '), 'ungroup': ("&& ((inputs.mode", "&& (inputs.mode"),
        'repository': ("github.repository == 'reihlinstinct/geni-uploader'", 'true'),
        'event': ("github.event_name == 'workflow_dispatch'", 'true'),
        'ref': ("github.ref == 'refs/heads/master'", 'true'),
        'executor': ('github.sha == inputs.executor_sha', 'true'),
        'actor': ("github.actor == 'reihlinstinct'", 'true'),
        'triggering_actor': ("github.triggering_actor == 'reihlinstinct'", 'true'),
        'attempt': ('github.run_attempt == 1', 'true'),
        'plan_mode': ("inputs.mode == 'plan'", 'true'),
        'plan_confirm': ("inputs.confirm == 'PLAN_SOURCES'", 'true'),
        'empty_plan_id': ("inputs.plan_run_id == ''", 'true'),
        'run_mode': ("inputs.mode == 'run'", 'true'),
        'run_confirm': ("inputs.confirm == 'UPLOAD_SOURCES'", 'true'),
        'required_plan_id': ("inputs.plan_run_id != ''", 'true')}
    before, after = replacements[mutation]; assert before in gate
    workflow['jobs']['source']['if'] = gate.replace(before, after, 1)
    with pytest.raises(AssertionError): check_workflow_contract(workflow)


@pytest.mark.parametrize('mutation', ['second_plaintext', 'second_encrypted', 'plaintext_path',
                                     'extra_plaintext_path', 'other_job_plaintext'])
def test_all_artifact_negative_mutations_killed(mutation):
    workflow = workflow_fixture(); steps = workflow['jobs']['source']['steps']
    artifact = next(step for step in steps if step.get('uses', '').lower().startswith('actions/upload-artifact@'))
    if mutation in ('second_plaintext', 'second_encrypted', 'other_job_plaintext'):
        extra = copy.deepcopy(artifact)
        if mutation != 'second_encrypted': extra['with']['path'] = '${{ runner.temp }}/protected-source/raw.log'
        if mutation == 'other_job_plaintext': workflow['jobs']['ZZ-other'] = {'steps': [extra]}
        else: steps.append(extra)
    elif mutation == 'plaintext_path': artifact['with']['path'] = '${{ runner.temp }}/protected-source/raw.log'
    else: artifact['with']['path'] += '\n${{ runner.temp }}/protected-source/raw.log'
    with pytest.raises(AssertionError): check_workflow_contract(workflow)


def test_full_history_page_blocks_even_when_length_matches():
    _, e, data = fixture('run'); history = next(v for k, v in data.items() if '/runs?' in k)
    history['total_count'] = 100
    history['workflow_runs'] = [{'id': n, 'display_title': 'ZZ-other-plan'} for n in range(100)]
    with pytest.raises(p.Blocked): p.validate(e, data.__getitem__, lambda: 200)


@pytest.mark.parametrize('before,after', [("'PLAN_SOURCES'", "' PLAN_SOURCES'"),
    ("'PLAN_SOURCES'", "'PLAN_SOURCES '"), ("''", "' '"),
    ("'refs/heads/master'", "'refs/heads/ master'"),
    ("'reihlinstinct/geni-uploader'", "'reihlinstinct/ geni-uploader'")])
def test_literal_whitespace_mutations_killed(before, after):
    workflow = workflow_fixture(); gate = workflow['jobs']['source']['if']
    assert before in gate; workflow['jobs']['source']['if'] = gate.replace(before, after, 1)
    with pytest.raises(AssertionError): check_workflow_contract(workflow)


def test_normalizer_preserves_escaped_quote_and_literal_spaces():
    assert normalize_expression("  x == ' ZZ it''s  here '  ") == "x==' ZZ it''s  here '"
    assert normalize_expression("x == 'a b'") != normalize_expression("x == 'ab'")
    workflow = workflow_fixture(); workflow['jobs']['source']['if'] = EXPECTED_GATE.replace(' && ', '  &&  \n')
    check_workflow_contract(workflow)


@pytest.mark.parametrize('action', ['Actions/Upload-Artifact@ZZ', 'ACTIONS/UPLOAD-ARTIFACT@ZZ',
                                   'actions/Upload-Artifact@ZZ'])
def test_mixed_case_second_plaintext_artifact_killed(action):
    workflow = workflow_fixture()
    workflow['jobs']['source']['steps'].append({'uses': action,
        'with': {'path': '${{ runner.temp }}/protected-source/raw.log'}})
    with pytest.raises(AssertionError): check_workflow_contract(workflow)
