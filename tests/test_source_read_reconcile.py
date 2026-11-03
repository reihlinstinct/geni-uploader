"""Synthetic ZZ source read reconciliation. No service calls."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import geni_uploader.runners.source_read_reconcile as p


def config():
    return {'schema': 1, 'owner_id': 'profile-991', 'target_id': 'profile-992',
            'target_guid': '9993', 'expect_name': 'ZZ Source',
            'recipient': 'age1' + 'a' * 58, 'expires_at': 1000,
            'sources': [{'source_url': 'https://zz.invalid/source', 'title': 'ZZ Source',
                         'description_sha256': hashlib.sha256(b'ZZ description').hexdigest()}]}


def fixture():
    c = config(); sha = 'a' * 40
    env = {'GITHUB_REPOSITORY': p.gate.REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
           'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
           'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_SHA': sha, 'GITHUB_RUN_ID': '99', 'RECONCILE_EXECUTOR_SHA': sha,
           'RECONCILE_CONFIRM': 'READ_ONLY_SOURCE_RECONCILE',
           'RECONCILE_CONFIG_JSON': json.dumps(c),
           'RECONCILE_CONFIG_SHA256': hashlib.sha256(p.gate.canonical(c)).hexdigest(),
           'GENI_ACCESS_TOKEN': 'ZZ-token'}
    meta = {'actions/runs/99': {'head_sha': sha, 'run_attempt': 1, 'path': p.WORKFLOW,
            'head_branch': 'master', 'event': 'workflow_dispatch',
            'actor': {'login': 'reihlinstinct'}, 'triggering_actor': {'login': 'reihlinstinct'}},
            'environments/father-create': {'can_admins_bypass': False, 'protection_rules': [
                {'type': 'required_reviewers', 'prevent_self_review': True,
                 'reviewers': [{'reviewer': {'login': 'reihl'}}]}, {'type': 'branch_policy'}]},
            'environments/father-create/deployment-branch-policies': {'total_count': 1,
                'branch_policies': [{'name': 'master', 'type': 'branch'}]}}
    obj = {'id': 'document-994', 'title': 'ZZ Source', 'source_url': 'https://zz.invalid/source',
           'description': 'ZZ description', 'tags': []}
    responses = {'/api/profile?fields=id': {'id': 'profile-991'},
                 '/api/profile-g9993?fields=' + p.FIELDS: {'id': 'profile-992', 'guid': '9993', 'name': 'ZZ Source'},
                 '/api/profile-992/documents?page=1&per_page=50': {'page': 1, 'results': []},
                 '/api/user/uploaded-documents?page=1&per_page=50': {'page': 1, 'results': [copy.deepcopy(obj)]},
                 '/api/document-994?fields=' + p.DOC_FIELDS: obj}
    return c, env, meta, responses


class Fake:
    def __init__(self, responses):
        self.responses = responses; self.calls = []; self.candidates = []
    def request(self, method, path):
        assert method == 'GET'; self.calls.append(path)
        value = self.responses[path]
        if isinstance(value, Exception): raise value
        return copy.deepcopy(value)
    def admit_document(self, oid):
        self.candidates.append(oid)


def report():
    return {'phase': 'UNKNOWN', 'responses': [], 'sources': [], 'recreate_allowed': False}


def test_orphan_create_found_in_account_uploads_without_target_tag():
    c, _, _, replies = fixture(); fake = Fake(replies); result = p.reconcile(c, fake, report())
    assert result['phase'] == 'READ_ONLY_COMPLETE'
    assert result['sources'][0]['state'] == 'EXACT_UNTAGGED'
    assert result['sources'][0]['recreate_allowed'] is False
    assert fake.candidates == ['document-994']


def test_tagged_match_full_url_normalization_only_for_tag_id():
    c, _, _, replies = fixture(); replies['/api/document-994?fields=' + p.DOC_FIELDS]['tags'] = ['https://www.geni.com/api/profile-992']
    assert p.reconcile(c, Fake(replies), report())['sources'][0]['state'] == 'EXACT_TAGGED'


@pytest.mark.parametrize('change', ['url', 'title', 'description', 'tags', 'duplicate', 'no_match'])
def test_ambiguity_never_grants_recreate(change):
    c, _, _, replies = fixture(); obj = replies['/api/document-994?fields=' + p.DOC_FIELDS]
    if change == 'url': obj['source_url'] += '/'
    if change == 'title': obj['title'] = 'ZZ other'
    if change == 'description': obj['description'] += ' changed'
    if change == 'tags': obj['tags'] = [{'id': 'profile-992'}]
    if change == 'duplicate':
        second = dict(obj, id='document-995'); replies['/api/user/uploaded-documents?page=1&per_page=50']['results'].append(second)
        replies['/api/document-995?fields=' + p.DOC_FIELDS] = second
    if change == 'no_match': replies['/api/user/uploaded-documents?page=1&per_page=50']['results'] = []
    result = report()
    if change == 'url':
        with pytest.raises(p.gate.Blocked): p.reconcile(c, Fake(replies), result)
    else:
        result = p.reconcile(c, Fake(replies), result)
        assert result['sources'][0]['state'] in ('UNKNOWN', 'NOT_OBSERVED_IN_COMPLETE_LISTS')
        assert result['sources'][0]['recreate_allowed'] is False


@pytest.mark.parametrize('kind', ['owner', 'target_id', 'guid', 'name'])
def test_wrong_identity_stops_before_document_access(kind):
    c, _, _, replies = fixture()
    if kind == 'owner': replies['/api/profile?fields=id']['id'] = 'profile-999'
    else: replies['/api/profile-g9993?fields=' + p.FIELDS][{'target_id': 'id', 'guid': 'guid', 'name': 'name'}[kind]] = 'ZZ wrong'
    fake = Fake(replies)
    with pytest.raises(p.gate.Blocked): p.reconcile(c, fake, report())
    assert not any('/documents' in x or 'uploaded-documents' in x for x in fake.calls)


@pytest.mark.parametrize('next_page', ['https://zz.invalid/api/user/uploaded-documents?page=2',
    'https://www.geni.com/api/profile-99/documents?page=2', '?page=1', '?page=3', '?page=2&page=2',
    '?page=2&token=ZZ', '?page=2#ZZ', 2])
def test_hostile_or_ambiguous_pagination_stops(next_page):
    _, _, _, replies = fixture(); prefix = '/api/user/uploaded-documents'
    replies[prefix + '?page=1&per_page=50']['next_page'] = next_page
    fake = Fake(replies)
    with pytest.raises((p.gate.Blocked, ValueError)): p.listing(fake, prefix, lambda *_: None)
    assert len(fake.calls) == 1


def test_pagination_complete_and_page_cap_unknown():
    prefix = '/api/user/uploaded-documents'; replies = {}
    for page in range(1, p.MAX_PAGES + 1):
        replies[prefix + f'?page={page}&per_page=50'] = {'page': page,
            'results': [{'id': f'document-{page}', 'title': 'ZZ', 'source_url': 'https://zz.invalid'}],
            'next_page': f'?page={page + 1}'}
    with pytest.raises(p.gate.Blocked): p.listing(Fake(replies), prefix, lambda *_: None)
    replies[prefix + f'?page={p.MAX_PAGES}&per_page=50']['next_page'] = None
    assert len(p.listing(Fake(replies), prefix, lambda *_: None)) == p.MAX_PAGES


@pytest.mark.parametrize('change', ['error', 'missing_page', 'wrong_page', 'rows', 'oversize', 'row_id', 'row_url', 'duplicate'])
def test_malformed_or_incomplete_listing_is_unknown(change):
    _, _, _, replies = fixture(); prefix = '/api/user/uploaded-documents'; value = replies[prefix + '?page=1&per_page=50']
    if change == 'error': value['error'] = 'ZZ'
    if change == 'missing_page': del value['page']
    if change == 'wrong_page': value['page'] = 2
    if change == 'rows': value['results'] = {}
    if change == 'oversize': value['results'] *= 51
    if change == 'row_id': value['results'][0]['id'] = '../ZZ'
    if change == 'row_url': del value['results'][0]['source_url']
    if change == 'duplicate': value['results'] *= 2
    with pytest.raises(p.gate.Blocked): p.listing(Fake(replies), prefix, lambda *_: None)


@pytest.mark.parametrize('method,path', [('POST', '/api/document/add'), ('DELETE', '/api/document-994'),
    ('GET', 'https://zz.invalid'), ('GET', '/api/profile-991/immediate-family'),
    ('GET', '/api/document-994?fields=' + p.DOC_FIELDS)])
def test_transport_denies_before_network(method, path):
    c = config(); opener = SimpleNamespace(open=lambda *_a, **_k: pytest.fail('network constructed'))
    reader = p.Reader(c, 'ZZ-token', opener=opener, wallclock=lambda: 100)
    with pytest.raises(p.gate.Blocked): reader.request(method, path)


def test_reader_budget_size_and_no_retries():
    c = config(); calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'{"id":"profile-991"}'
    def opened(req, **_):
        calls.append(req); return Response()
    reader = p.Reader(c, 'ZZ-token', opener=SimpleNamespace(open=opened), wallclock=lambda: 100)
    assert reader.request('GET', '/api/profile?fields=id')['id'] == 'profile-991'
    with pytest.raises(p.gate.Blocked): reader.request('GET', '/api/profile?fields=id')
    assert len(calls) == 1
    assert calls[0].method == 'GET' and calls[0].full_url == 'https://www.geni.com/api/profile?fields=id'
    reader.seen = set(map(str, range(p.MAX_CALLS)))
    with pytest.raises(p.gate.Blocked): reader.request('GET', '/api/profile?fields=id')


@pytest.mark.parametrize('key,value', [('schema', True), ('owner_id', 'ZZ'), ('target_guid', '../99'),
    ('recipient', 'ZZ'), ('expires_at', 99), ('sources', []), ('extra', 'ZZ')])
def test_config_negative(key, value):
    c = config(); c[key] = value; raw = json.dumps(c)
    with pytest.raises(p.gate.Blocked): p.config(raw, hashlib.sha256(p.gate.canonical(c)).hexdigest(), lambda: 100)


def test_config_hash_and_expiry():
    c = config(); digest = hashlib.sha256(p.gate.canonical(c)).hexdigest()
    assert p.config(json.dumps(c), digest, lambda: 100) == c
    with pytest.raises(p.gate.Blocked): p.config(json.dumps(c), 'b' * 64, lambda: 100)


@pytest.mark.parametrize('key,value', [('GITHUB_ACTOR', 'ZZ'), ('GITHUB_RUN_ATTEMPT', '2'),
    ('GITHUB_SHA', 'b' * 40), ('GITHUB_REF', 'refs/heads/ZZ'), ('RECONCILE_CONFIRM', 'ZZ')])
def test_envelope_wrong_execution(key, value):
    _, env, meta, _ = fixture(); env[key] = value
    with pytest.raises(p.gate.Blocked): p.envelope(env, meta.__getitem__)


@pytest.mark.parametrize('kind', ['path', 'attempt', 'reviewer', 'bypass', 'branch', 'extra_rule'])
def test_envelope_metadata_negative(kind):
    _, env, meta, _ = fixture()
    if kind == 'path': meta['actions/runs/99']['path'] = 'ZZ'
    if kind == 'attempt': meta['actions/runs/99']['run_attempt'] = 2
    if kind == 'reviewer': meta['environments/father-create']['protection_rules'][0]['reviewers'].append({'reviewer': {'login': 'ZZ'}})
    if kind == 'bypass': meta['environments/father-create']['can_admins_bypass'] = True
    if kind == 'branch': meta['environments/father-create/deployment-branch-policies']['branch_policies'][0]['name'] = 'ZZ'
    if kind == 'extra_rule': meta['environments/father-create']['protection_rules'].append({'type': 'wait_timer'})
    with pytest.raises(p.gate.Blocked): p.envelope(env, meta.__getitem__)


def test_preflight_before_reads_and_partial_evidence_on_failure(tmp_path):
    _, env, meta, replies = fixture(); env['RECONCILE_OUTPUT_DIR'] = str(tmp_path / 'out'); events = []
    replies['/api/user/uploaded-documents?page=1&per_page=50'] = OSError('ZZ private')
    def seal(_recipient, value, path): events.append((path.name, copy.deepcopy(value)))
    with pytest.raises(OSError): p.execute(env, meta.__getitem__, clock=lambda: 100,
                                         factory=lambda *_: Fake(replies), seal=seal)
    assert events[0][0] == 'preflight.age' and events[-1][0] == 'source-reconcile.age'
    assert events[-1][1]['phase'] == 'UNKNOWN' and len(events[-1][1]['responses']) == 3
    env['RECONCILE_OUTPUT_DIR'] = str(tmp_path / 'preflight-fail')
    with pytest.raises(OSError): p.execute(env, meta.__getitem__, clock=lambda: 100,
        factory=lambda *_: pytest.fail('vendor read'), seal=lambda *_: (_ for _ in ()).throw(OSError()))


def test_age_child_path_only_and_fixed_public_output(monkeypatch, capsys):
    seen = []; monkeypatch.setenv('GENI_ACCESS_TOKEN', 'ZZ-secret')
    monkeypatch.setattr(p.subprocess, 'run', lambda *a, **k: seen.append(k))
    p.encrypt(config()['recipient'], {'ZZ': True}, Path('/tmp/ZZ.age'))
    assert set(seen[0]['env']) == {'PATH'} and seen[0]['check'] is True
    monkeypatch.setattr(p, 'execute', lambda *_: (_ for _ in ()).throw(ValueError('ZZ-secret')))
    assert p.main() == 1 and 'ZZ-secret' not in capsys.readouterr().out


def test_workflow_no_write_or_plaintext_artifact_steps():
    root = Path(__file__).resolve().parents[1]; flow = yaml.safe_load((root / p.WORKFLOW).read_text())
    assert set(flow['jobs']) == {'source'}; job = flow['jobs']['source']
    assert job['environment'] == 'father-create' and 'github.run_attempt == 1' in job['if']
    assert "inputs.confirm == 'READ_ONLY_SOURCE_RECONCILE'" in job['if']
    env = next(x['env'] for x in job['steps'] if x.get('name') == 'GET-only source reconciliation')
    assert env['GENI_ACCESS_TOKEN'] == '${{ secrets.GENI_ACCESS_TOKEN }}'
    assert env['RECONCILE_CONFIG_JSON'] == '${{ secrets.SOURCE_RECONCILE_JSON }}'
    artifact = next(x for x in job['steps'] if x.get('uses', '').startswith('actions/upload-artifact@'))
    assert artifact['with']['path'] == '${{ runner.temp }}/source-reconcile/*.age'
    assert artifact['if'] == 'always()'
    assert all('secrets.' not in x.get('run', '') for x in job['steps'])


def test_full_terminal_page_does_not_prove_completeness():
    prefix = '/api/user/uploaded-documents'
    value = {'page': 1, 'results': [{'id': f'document-{n}', 'title': 'ZZ',
                                   'source_url': 'https://zz.invalid'} for n in range(1, 51)]}
    with pytest.raises(p.gate.Blocked): p.listing(Fake({prefix + '?page=1&per_page=50': value}), prefix, lambda *_: None)


def test_no_redirect_handler_and_no_retry_on_network_failure():
    reader = p.Reader(config(), 'ZZ', wallclock=lambda: 100)
    redirect = next(x for x in reader.opener.handlers if isinstance(x, p.urllib.request.HTTPRedirectHandler))
    with pytest.raises(p.gate.Blocked): redirect.redirect_request(None, None, None, None, None, None)
    calls = []
    def fail(*_a, **_k):
        calls.append(True); raise OSError('ZZ')
    reader = p.Reader(config(), 'ZZ', opener=SimpleNamespace(open=fail), wallclock=lambda: 100)
    with pytest.raises(OSError): reader.request('GET', '/api/profile?fields=id')
    with pytest.raises(p.gate.Blocked): reader.request('GET', '/api/profile?fields=id')
    assert calls == [True]


def test_reader_response_size_pacing_and_candidate_cap():
    clock = [0]; waits = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'{}'
    reader = p.Reader(config(), 'ZZ', opener=SimpleNamespace(open=lambda *_a, **_k: Response()),
                      clock=lambda: clock[0], sleep=waits.append, wallclock=lambda: 100)
    reader.request('GET', '/api/profile?fields=id'); clock[0] = 3
    reader.request('GET', '/api/profile-g9993?fields=' + p.FIELDS)
    assert waits == [7]
    for n in range(1, p.MAX_CANDIDATES + 1): reader.admit_document(f'document-{n}')
    with pytest.raises(p.gate.Blocked): reader.admit_document('document-999')
    with pytest.raises(p.gate.Blocked): reader.admit_document('../ZZ')
    Response.read = lambda *_: b'Z' * 2_000_001
    with pytest.raises(p.gate.Blocked): reader.request('GET', '/api/document-1?fields=' + p.DOC_FIELDS)


def test_success_and_expiry_failure_evidence(tmp_path):
    _, env, meta, replies = fixture(); saved = []
    env['RECONCILE_OUTPUT_DIR'] = str(tmp_path / 'complete')
    assert p.execute(env, meta.__getitem__, clock=lambda: 100,
                     factory=lambda *_: Fake(replies), seal=lambda _r, v, _p: saved.append(copy.deepcopy(v)))
    assert saved[-1]['phase'] == 'READ_ONLY_COMPLETE' and saved[-1]['writes'] == 0
    env['RECONCILE_OUTPUT_DIR'] = str(tmp_path / 'expired'); times = iter([100, 100, 1001])
    with pytest.raises(p.gate.Blocked): p.execute(env, meta.__getitem__, clock=lambda: next(times),
        factory=lambda *_: Fake(replies), seal=lambda _r, v, _p: saved.append(copy.deepcopy(v)))
    assert saved[-1]['phase'] == 'UNKNOWN'


def test_exact_metadata_free_empty_first_page_live_shape():
    c, _, _, replies = fixture()
    replies['/api/profile-992/documents?page=1&per_page=50'] = {'results': []}
    result = p.reconcile(c, Fake(replies), report())
    assert result['target_listing_complete'] is True
    assert result['sources'][0]['state'] == 'EXACT_UNTAGGED'
    assert result['sources'][0]['recreate_allowed'] is False


@pytest.mark.parametrize('extra', ['next', 'next_page', 'prev_page', 'error', 'page', 'ZZ'])
def test_empty_missing_page_with_any_extra_key_remains_unknown(extra):
    prefix = '/api/user/uploaded-documents'
    value = {'results': [], extra: None}
    with pytest.raises(p.gate.Blocked):
        p.listing(Fake({prefix + '?page=1&per_page=50': value}), prefix, lambda *_: None)


def test_missing_page_on_later_empty_page_remains_unknown():
    prefix = '/api/user/uploaded-documents'
    values = {prefix + '?page=1&per_page=50': {'page': 1, 'results': [
        {'id': 'document-991', 'source_url': 'https://zz.invalid', 'title': 'ZZ'}], 'next_page': '?page=2'},
        prefix + '?page=2&per_page=50': {'results': []}}
    with pytest.raises(p.gate.Blocked): p.listing(Fake(values), prefix, lambda *_: None)
