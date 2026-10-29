import copy
import hashlib
import json
import os
import time
from io import BytesIO

import pytest

from people_core import Blocked
from protected_father_job import collect_from_environment, plan_fingerprint
from tests.test_github_review_evidence import fixture as review_fixture
from tests.test_single_human_approval_record import fixture as record_fixture


def setup(monkeypatch, mutate=lambda c: None, fault=None):
    pins, bodies = review_fixture()
    pins.update(branch='master', environment='father-create')
    bodies[0]['head_branch'] = 'master'
    bodies[1]['name'] = 'father-create'
    bodies[2][0]['environments'][0]['name'] = 'father-create'
    bodies[3]['branch_policies'][0]['name'] = 'master'
    record = record_fixture()
    now = int(time.time())
    record['pins'].update(run_id=str(pins['run_id']), executor_sha=pins['sha'],
                         workflow_sha=pins['sha'], issued_at=now-1, expires_at=now+300)
    for role in ('owner_grant', 'protected_review'):
        record['sources'][role]['principal_id'] = str(pins['reviewer_id'])
    record['sources']['dispatch']['principal_id'] = str(pins['actor_id'])
    record['reviewed_executor_sha'] = pins['sha']
    name = f"Approve plan {plan_fingerprint(record)} risk {record['risk_hash']} run {pins['run_id']} attempt 1"
    config = {'mode': 'unreleased_protected_job_capture', 'production_enabled': False,
              'review_pins': pins, 'record': record, 'job_name': name,
              'plan_fingerprint': plan_fingerprint(record)}
    mutate(config)
    raw = json.dumps(config, separators=(',', ':'), ensure_ascii=False).encode()
    values = {'FATHER_JOB_RELEASE_JSON': raw.decode(),
              'FATHER_JOB_RELEASE_SHA256': hashlib.sha256(raw).hexdigest(),
              'FATHER_JOB_READ_TOKEN': 'ZZtest', 'GITHUB_RUN_ID': str(pins['run_id']),
              'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': pins['sha'],
              'GITHUB_REF': 'refs/heads/master', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
              'GITHUB_REPOSITORY': f"{pins['owner']}/{pins['repo']}",
              'GITHUB_ACTOR_ID': str(pins['actor_id'])}
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    root = 'https://api.github.com/repos/ZZ-owner/ZZ-repo'
    run = root+'/actions/runs/42'
    env = root+'/environments/father-create'
    job = {'id': 46, 'name': name, 'run_id': 42, 'run_attempt': 1,
           'head_sha': pins['sha'], 'status': 'in_progress', 'conclusion': None}
    urls = [run, env, run+'/approvals', env+'/deployment-branch-policies',
            run+'/attempts/1/jobs?per_page=100', env, env+'/deployment-branch-policies']
    data = [*bodies, {'total_count': 1, 'jobs': [job]}, bodies[1], bodies[3]]
    calls = []

    class Response(BytesIO):
        status = 200

        def __init__(self, url, value):
            super().__init__(json.dumps(value).encode())
            self.url = url
            self.headers = {}

        def geturl(self):
            return self.url

    class Opener:
        def open(self, request, timeout):
            n = len(calls)
            calls.append(request.full_url)
            assert request.full_url == urls[n]
            assert request.get_method() == 'GET'
            assert 0 < timeout <= 5
            value = copy.deepcopy(data[n])
            if fault:
                value = fault(n, value)
            return Response(request.full_url, value)

    monkeypatch.setattr('urllib.request.build_opener', lambda _: Opener())
    return calls


def test_actual_fixed_get_collector_writes_one_v2_receipt(monkeypatch, tmp_path):
    calls = setup(monkeypatch)
    path = tmp_path/'ZZ-receipt.json'
    result = collect_from_environment(path)
    assert len(calls) == 7
    assert result['post_permitted'] is False
    receipt = json.loads(path.read_text())
    assert receipt['schema_version'] == 2
    assert result['capture']['job_id'] == 46
    assert receipt['sources']['owner_grant']['source_ref'] == receipt['sources']['protected_review']['source_ref']
    assert receipt['sources']['owner_grant']['source_ref'] != '1'*64
    assert os.stat(path).st_mode & 0o777 == 0o600
    with pytest.raises(Blocked):
        collect_from_environment(path)


@pytest.mark.parametrize('key,value', [('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_SHA', '0'*40),
    ('GITHUB_ACTOR_ID', '45'), ('GITHUB_REF', 'refs/heads/ZZ-other')])
def test_wrong_runtime_before_any_network(monkeypatch, tmp_path, key, value):
    calls = setup(monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(Blocked):
        collect_from_environment(tmp_path/'ZZ.json')
    assert calls == []


@pytest.mark.parametrize('fault', [
    lambda n, v: {**v, 'total_count': 2} if n == 4 else v,
    lambda n, v: {**v, 'can_admins_bypass': True} if n == 5 else v,
    lambda n, v: [] if n == 2 else v,
    lambda n, v: {**v, 'head_sha': '0'*40} if n == 0 else v,
])
def test_bad_current_evidence_never_writes(monkeypatch, tmp_path, fault):
    setup(monkeypatch, fault=fault)
    path = tmp_path/'ZZ.json'
    with pytest.raises(Blocked):
        collect_from_environment(path)
    assert not path.exists()


@pytest.mark.parametrize('field,value', [('run_id', 43), ('run_attempt', 2),
    ('head_sha', '0'*40), ('name', 'ZZ-other'), ('status', 'completed'),
    ('conclusion', 'success'), ('id', True)])
def test_job_pins_cannot_be_substituted(monkeypatch, tmp_path, field, value):
    def fault(n, body):
        if n == 4:
            body['jobs'][0][field] = value
        return body
    setup(monkeypatch, fault=fault)
    with pytest.raises(Blocked):
        collect_from_environment(tmp_path/'ZZ.json')


def test_release_hash_is_not_silent_recomputed(monkeypatch, tmp_path):
    calls = setup(monkeypatch)
    monkeypatch.setenv('FATHER_JOB_RELEASE_SHA256', '0'*64)
    with pytest.raises(Blocked):
        collect_from_environment(tmp_path/'ZZ.json')
    assert not calls


def test_redirects_disabled_in_actual_opener():
    from protected_father_job import _NoRedirect
    assert _NoRedirect().redirect_request(None, None, 302, 'ZZ', {}, 'https://ZZ.invalid') is None


def test_plan_fingerprint_excludes_only_dynamic_capture():
    r = record_fixture()
    original = plan_fingerprint(r)
    r['pins'].update(run_id='999099', issued_at=200, expires_at=600)
    for role in ('owner_grant', 'protected_review'):
        r['sources'][role]['source_ref'] = 'e'*64
        r['sources'][role]['content_hash'] = 'f'*64
    assert plan_fingerprint(r) == original
    r['pins']['payload_hash'] = '0'*64
    assert plan_fingerprint(r) != original



def test_capture_decision_binds_actual_job_run_and_static_plan(monkeypatch, tmp_path):
    from people_core import digest
    setup(monkeypatch)
    path = tmp_path/'ZZ.json'
    result = collect_from_environment(path)
    record = json.loads(path.read_text())
    decision = result['decision']
    assert decision['job_id'] == '46'
    assert decision['run_id'] == '42'
    assert decision['run_attempt'] == 1
    assert decision['plan_fingerprint'] == plan_fingerprint(record)
    for role in ('owner_grant', 'protected_review'):
        assert record['sources'][role]['source_ref'] == digest(decision)
        assert record['sources'][role]['content_hash'] == decision['review_content_hash']
