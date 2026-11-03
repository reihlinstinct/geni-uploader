"""Synthetic fixed-slot bridge, no actual credential reads or writes."""
import base64
import copy
import json
from pathlib import Path

import pytest
import yaml

import geni_uploader.runners.source_slot_bridge as p


def fixture():
    env = {'GITHUB_REPOSITORY': p.source.REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
           'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
           'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_SHA': 'a' * 40, 'BRIDGE_EXECUTOR_SHA': 'a' * 40,
           'GITHUB_RUN_ID': '99101', 'BRIDGE_CONFIRM': 'COPY_SECONDARY_TO_SOURCE_ENV',
           'BRIDGE_SOURCE_UPDATED_AT': '2026-11-02T13:58:33Z', 'BRIDGE_SOURCE_VALUE': 'ZZ-source'}
    replies = {'actions/runs/99101': {'head_sha': 'a' * 40, 'run_attempt': 1,
        'path': p.WORKFLOW, 'head_branch': 'master', 'event': 'workflow_dispatch',
        'actor': {'login': 'reihlinstinct'}, 'triggering_actor': {'login': 'reihlinstinct'}},
        p.ENV: {'can_admins_bypass': False, 'protection_rules': [
            {'type': 'required_reviewers', 'prevent_self_review': True,
             'reviewers': [{'reviewer': {'login': 'reihl'}}]}, {'type': 'branch_policy'}]},
        p.ENV + '/deployment-branch-policies': {'total_count': 1,
            'branch_policies': [{'name': 'master', 'type': 'branch'}]},
        p.ENV + '/secrets?per_page=100': {'total_count': 0, 'secrets': []},
        p.SRC: {'name': 'GENI_SECONDARY_ACCESS_TOKEN', 'updated_at': env['BRIDGE_SOURCE_UPDATED_AT']},
        p.ENV + '/secrets/public-key': {'key': base64.b64encode(b'Z' * 32).decode(), 'key_id': '991'},
        p.DEST: {'name': 'GENI_ACCESS_TOKEN', 'updated_at': '2026-11-02T14:00:00Z'}}
    return env, replies


def execute(env, replies):
    calls = []; seals = []; written = []
    def request(method, path, body=None):
        calls.append((method, path, body))
        if method == 'PUT': written.append(True); return None
        actual = copy.deepcopy(replies[path])
        if path == p.DEST and written: actual['updated_at'] = '2026-11-02T14:01:00Z'
        return actual
    def seal(value, public):
        seals.append((value, public)); return base64.b64encode(b'Z' * (len(value.encode()) + 48)).decode()
    return p.execute(env, request, seal), calls, seals


def test_one_fixed_destination_put_with_sealed_value_only():
    e, data = fixture(); ok, calls, seals = execute(e, data)
    assert ok and len(seals) == 1 and seals[0][0] == 'ZZ-source'
    puts = [x for x in calls if x[0] == 'PUT']; assert len(puts) == 1 and puts[0][1] == p.DEST
    assert 'ZZ-source' not in json.dumps(puts)
    assert set(puts[0][2]) == {'encrypted_value', 'key_id'}
    assert len([x for x in calls if x[1] == p.SRC]) == 2


@pytest.mark.parametrize('key,value', [('GITHUB_REPOSITORY', 'ZZ/ZZ'), ('GITHUB_EVENT_NAME', 'push'),
    ('GITHUB_REF', 'refs/heads/ZZ'), ('GITHUB_ACTOR', 'ZZ'), ('GITHUB_TRIGGERING_ACTOR', 'ZZ'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_SHA', 'b' * 40), ('BRIDGE_EXECUTOR_SHA', 'bad'),
    ('GITHUB_RUN_ID', '../ZZ'), ('BRIDGE_CONFIRM', 'ZZ'), ('BRIDGE_SOURCE_UPDATED_AT', 'ZZ'),
    ('BRIDGE_SOURCE_VALUE', '')])
def test_envelope_negative_gates(key, value):
    e, data = fixture(); e[key] = value
    with pytest.raises(p.source.Blocked): execute(e, data)


@pytest.mark.parametrize('kind', ['bypass', 'review', 'self', 'branch', 'override', 'timestamp', 'pubkey', 'run'])
def test_read_evidence_gates_before_put(kind):
    e, data = fixture()
    if kind == 'bypass': data[p.ENV]['can_admins_bypass'] = True
    if kind == 'review': data[p.ENV]['protection_rules'][0]['reviewers'][0]['reviewer']['login'] = 'ZZ'
    if kind == 'self': data[p.ENV]['protection_rules'][0]['prevent_self_review'] = False
    if kind == 'branch': data[p.ENV + '/deployment-branch-policies']['branch_policies'][0]['name'] = 'ZZ'
    if kind == 'override': data[p.ENV + '/secrets?per_page=100'] = {'total_count': 1, 'secrets': [{'name': 'GENI_SECONDARY_ACCESS_TOKEN'}]}
    if kind == 'timestamp': data[p.SRC]['updated_at'] = '2026-11-02T12:00:00Z'
    if kind == 'pubkey': data[p.ENV + '/secrets/public-key']['key'] = 'ZZ'
    if kind == 'run': data['actions/runs/99101']['head_branch'] = 'ZZ'
    with pytest.raises((p.source.Blocked, ValueError)): execute(e, data)


def test_source_drift_or_unknown_put_never_retries():
    e, data = fixture(); calls = []; reads = []
    def request(method, path, body=None):
        calls.append((method, path))
        if path == p.SRC:
            reads.append(None)
            if len(reads) == 2: return dict(data[path], updated_at='ZZ-drift')
        return data[path]
    with pytest.raises(p.source.Blocked): p.execute(e, request, lambda *_: base64.b64encode(b'Z' * 57).decode())
    assert not any(method == 'PUT' for method, _ in calls)
    calls.clear()
    def uncertain(method, path, body=None):
        calls.append((method, path))
        if method == 'PUT': raise OSError('ZZ-uncertain')
        return data[path]
    with pytest.raises(OSError): p.execute(e, uncertain, lambda *_: base64.b64encode(b'Z' * 57).decode())
    assert sum(method == 'PUT' for method, _ in calls) == 1


@pytest.mark.parametrize('method,path', [('POST', p.DEST), ('PUT', p.SRC),
    ('PUT', 'actions/secrets/GENI_ACCESS_TOKEN'), ('GET', p.ENV + '-ZZ'),
    ('GET', 'actions/secrets/ZZ'), ('GET', 'https://ZZ.invalid')])
def test_transport_exact_paths_before_network(method, path):
    with pytest.raises(p.source.Blocked): p.transport('ZZ', method, path)


def test_main_fixed_output_no_exception_or_value(monkeypatch, capsys):
    monkeypatch.setattr(p, 'execute', lambda *_: (_ for _ in ()).throw(ValueError('ZZ-secret')))
    assert p.main() == 1 and 'ZZ-secret' not in capsys.readouterr().out


def test_workflow_exact_gate_all_steps_secret_scope():
    root = Path(__file__).resolve().parents[1]; flow = yaml.safe_load((root / p.WORKFLOW).read_text())
    assert set(flow['jobs']) == {'bridge'}; job = flow['jobs']['bridge']
    assert job['environment'] == 'father-create'
    expected = "${{ github.repository == 'reihlinstinct/geni-uploader' && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/master' && github.sha == inputs.executor_sha && github.actor == 'reihlinstinct' && github.triggering_actor == 'reihlinstinct' && github.run_attempt == 1 && inputs.confirm == 'COPY_SECONDARY_TO_SOURCE_ENV' }}"
    assert job['if'] == expected
    for step in job['steps']:
        assert 'upload-artifact' not in step.get('uses', '').lower()
        assert 'secrets.' not in step.get('run', '')
        assert 'echo' not in step.get('run', '') and 'printenv' not in step.get('run', '')
    env = job['steps'][-1]['env']
    assert env['BRIDGE_SOURCE_VALUE'] == '${{ secrets.GENI_SECONDARY_ACCESS_TOKEN }}'
    assert env['BRIDGE_WRITER'] == '${{ secrets.SOURCE_BRIDGE_WRITER }}'
    assert flow['concurrency'] == {'group': 'geni-upload', 'cancel-in-progress': False}


def test_seal_child_receives_no_credentials(monkeypatch):
    from types import SimpleNamespace
    seen = []
    monkeypatch.setenv('BRIDGE_WRITER', 'ZZ-writer')
    monkeypatch.setenv('BRIDGE_SOURCE_VALUE', 'ZZ-source')
    monkeypatch.setenv('GITHUB_TOKEN', 'ZZ-github')
    def run(args, **kwargs):
        seen.append(kwargs); return SimpleNamespace(stdout=b'ZZ-cipher')
    monkeypatch.setattr(p.subprocess, 'run', run)
    assert p.seal('ZZ-source', 'ZZ-public') == 'ZZ-cipher'
    assert set(seen[0]['env']) == {'PATH'}
    assert all(not key.startswith('BRIDGE_') for key in seen[0]['env'])


@pytest.mark.parametrize('kind', ['meta_path', 'meta_attempt', 'extra_reviewer', 'secret_length',
                                  'cipher_length', 'cipher_overlong', 'after_name', 'unchanged_time', 'wait_timer'])
def test_independent_negative_checks_before_or_after_one_put(kind):
    e, data = fixture(); puts = []; reads = []
    if kind == 'meta_path': data['actions/runs/99101']['path'] = 'ZZ-other'
    if kind == 'meta_attempt': data['actions/runs/99101']['run_attempt'] = 2
    if kind == 'extra_reviewer': data[p.ENV]['protection_rules'][0]['reviewers'].append({'reviewer': {'login': 'reihl'}})
    if kind == 'secret_length': data[p.ENV + '/secrets?per_page=100']['total_count'] = 1
    if kind == 'wait_timer': data[p.ENV]['protection_rules'].append({'type': 'wait_timer'})
    def request(method, path, body=None):
        if method == 'PUT': puts.append(body); return None
        value = copy.deepcopy(data[path])
        if path == p.DEST:
            reads.append(True)
            if len(reads) == 2:
                if kind == 'after_name': value['name'] = 'ZZ-wrong'
                if kind != 'unchanged_time': value['updated_at'] = '2026-11-02T14:01:00Z'
        return value
    cipher = base64.b64encode(b'Z' * (56 if kind == 'cipher_length' else 58 if kind == 'cipher_overlong' else 57)).decode()
    with pytest.raises(p.source.Blocked): p.execute(e, request, lambda *_: cipher)
    assert len(puts) == (1 if kind in ('after_name', 'unchanged_time') else 0)


def test_node_and_package_runner_versions_pinned():
    root = Path(__file__).resolve().parents[1]; flow = yaml.safe_load((root / p.WORKFLOW).read_text())
    steps = flow['jobs']['bridge']['steps']; setup = next(x for x in steps if x.get('uses', '').startswith('actions/setup-node@'))
    assert setup['uses'] == 'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020'
    assert setup['with']['node-version'] == '22.23.0'
    install = next(x for x in steps if x.get('name') == 'Install exact reviewed sealed-box dependency')
    assert '10.9.8' in install['run'] and '--ignore-scripts' in install['run']
