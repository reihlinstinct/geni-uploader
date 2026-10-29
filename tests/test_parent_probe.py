import copy
import io
import json
import urllib.error

import pytest

import parent_probe as p
from people_core import Blocked

C = {'schema_version': 1, 'connection_id': 'ZZisolated',
     'owner_node': 'profile-99123', 'expect_name': 'ZZRoot ZZPerson'}
PROFILE = {'id': 'profile-99123', 'first_name': 'ZZRoot', 'last_name': 'ZZPerson',
           'merge_pending': False, 'public': False, 'is_alive': True}
FAMILY = {'focus': PROFILE, 'nodes': {'profile-99123': PROFILE,
          'union-99111': {'id': 'union-99111'}}}
UNION = {'id': 'union-99111', 'partners': ['profile-99123'], 'children': [],
         'adopted_children': [], 'foster_children': []}


class Client:
    def __init__(self):
        self.calls = []
        self.responses = {'profile': PROFILE, C['owner_node']: PROFILE,
                          C['owner_node']+'/immediate-family': FAMILY,
                          'union-99111': UNION}

    def get(self, route):
        self.calls.append(route)
        return copy.deepcopy(self.responses[route])


def test_collect_minimal_isolated_read_evidence():
    client = Client()
    client.responses['profile'] = {**PROFILE, 'email': 'ZZprivate', 'about_me': 'ZZinjection'}
    result = p.collect(C, client)
    assert client.calls == ['profile', 'profile-99123', 'profile-99123/immediate-family', 'union-99111']
    assert result['create_enabled'] is False and result['hidden_parent_completeness'] == 'unproved'
    assert 'ZZprivate' not in str(result) and 'ZZinjection' not in str(result)


@pytest.mark.parametrize('where', ['profile', 'profile-99123'])
def test_wrong_owner_or_name_stops_before_family(where):
    client = Client()
    client.responses[where] = {**PROFILE, 'id': 'profile-99555'}
    with pytest.raises(Blocked): p.collect(C, client)
    assert not any('immediate-family' in x for x in client.calls)


@pytest.mark.parametrize('change', ['merged', 'name', 'pagination', 'familyfocus', 'nodes', 'union'])
def test_bad_response_stops_without_guess(change):
    client = Client()
    if change == 'merged': client.responses['profile'] = {**PROFILE, 'merge_pending': True}
    if change == 'name': client.responses['profile'] = {**PROFILE, 'last_name': 'ZZOther'}
    if change == 'pagination': client.responses['profile'] = {**PROFILE, 'next_page': 'ZZremote'}
    if change == 'familyfocus': client.responses[C['owner_node']+'/immediate-family'] = {'focus': {}, 'nodes': {}}
    if change == 'nodes': client.responses[C['owner_node']+'/immediate-family'] = {'focus': PROFILE, 'nodes': {'ZZurl': {}}}
    if change == 'union': client.responses['union-99111'] = {**UNION, 'partners': ['https://ZZ.invalid']}
    with pytest.raises(Blocked): p.collect(C, client)


def test_protected_inputs_refuse_shared_file_and_symlink(tmp_path):
    file = tmp_path/'token'
    file.write_text('ZZsentinel')
    file.chmod(0o600)
    assert p.protected_file(file, 100) == 'ZZsentinel'
    file.chmod(0o644)
    with pytest.raises(Blocked): p.protected_file(file, 100)
    file.chmod(0o600)
    with pytest.raises(Blocked): p.protected_file(file, 1)
    link = tmp_path/'link'
    link.symlink_to(file)
    with pytest.raises(OSError): p.protected_file(link, 100)


@pytest.mark.parametrize('route', ['https://ZZ.invalid', 'profile/refresh', 'profile-1/add-parent',
                                  '../profile', 'profile-1?access_token=ZZ', 'union-1/delete'])
def test_transport_exact_get_allowlist(route):
    client = p.ReadOnly('ZZsyntheticToken')
    with pytest.raises(Blocked): client.get(route)
    assert client.calls == 0


class Response(io.BytesIO):
    status = 200
    def __init__(self, raw, url):
        super().__init__(raw)
        self.url = url
    def geturl(self): return self.url


class Opener:
    def __init__(self, response=None, error=None):
        self.requests = []
        self.response, self.error = response, error
    def open(self, req, timeout):
        self.requests.append(req)
        if self.error: raise self.error
        return Response(self.response, req.full_url)


def test_transport_get_only_bearer_header_and_pacing(monkeypatch):
    client = p.ReadOnly('ZZsentinelToken')
    opener = Opener(b'{"id":"profile-99123"}')
    client.opener = opener
    sleeps = []
    monkeypatch.setattr(p.time, 'sleep', sleeps.append)
    client.get('profile'); client.get('profile-99123')
    assert len(sleeps) == 1 and 0 <= sleeps[0] <= 10
    for req in opener.requests:
        assert req.method == 'GET' and req.data is None
        assert req.get_header('Authorization') == 'Bearer ZZsentinelToken'
        assert 'ZZsentinelToken' not in req.full_url
        assert req.full_url.startswith(p.BASE)


@pytest.mark.parametrize('code', [401, 429, 500])
def test_http_stop_no_retry_no_error_leak(code):
    client = p.ReadOnly('ZZsentinelToken')
    opener = Opener(error=urllib.error.HTTPError('ZZurl', code, 'ZZprivate', {}, None))
    client.opener = opener
    with pytest.raises(Blocked) as error: client.get('profile')
    assert len(opener.requests) == 1 and 'ZZ' not in str(error.value)


@pytest.mark.parametrize('raw', [b'notjson', b'[]', b'{"error":"ZZprivate"}', b'x'*(p.LIMIT+1)])
def test_bad_or_large_response_blocked(raw):
    client = p.ReadOnly('ZZsentinelToken')
    client.opener = Opener(raw)
    with pytest.raises(Blocked): client.get('profile')


def test_redirect_and_budget_blocked():
    with pytest.raises(Blocked): p.NoRedirect().redirect_request(None,None,302,'ZZ',{},'https://ZZ.invalid')
    client = p.ReadOnly('ZZsentinelToken')
    client.calls = 20
    with pytest.raises(Blocked): client.get('profile')


def test_main_encryption_preflight_before_network_and_fixed_failure(tmp_path, monkeypatch, capsys):
    config = tmp_path/'connection'
    config.write_text(json.dumps(C)); config.chmod(0o600)
    token = tmp_path/'token'
    token.write_text('ZZsentinelToken'); token.chmod(0o600)
    def deny(*args): raise Blocked('ZZprivate internal')
    monkeypatch.setattr(p, 'encrypt', deny)
    assert p.main(['--connection-file',str(config),'--token-file',str(token),
                   '--recipient','ZZrecipient','--output-dir',str(tmp_path/'out'),
                   '--confirm-read-only','YES']) == 1
    assert 'ZZ' not in capsys.readouterr().out
    assert not (tmp_path/'out').exists()


def test_main_writes_only_ciphertext_private_directory(tmp_path, monkeypatch, capsys):
    config = tmp_path/'connection'
    config.write_text(json.dumps(C)); config.chmod(0o600)
    token = tmp_path/'token'
    token.write_text('ZZsentinelToken'); token.chmod(0o600)
    monkeypatch.setattr(p, 'ReadOnly', lambda token: Client())
    monkeypatch.setattr(p, 'encrypt', lambda recipient, value: b'age-encryption.org/v1\nZZciphertext')
    out = tmp_path/'out'
    assert p.main(['--connection-file',str(config),'--token-file',str(token),
                   '--recipient','age1'+'a'*58,'--output-dir',str(out),
                   '--confirm-read-only','YES']) == 0
    assert (out/'parent-evidence.age').read_bytes() == b'age-encryption.org/v1\nZZciphertext'
    assert out.stat().st_mode & 0o777 == 0o700
    assert (out/'parent-evidence.age').stat().st_mode & 0o777 == 0o600
    assert 'ZZ' not in capsys.readouterr().out


def test_recipient_not_a_command_or_key(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('no subprocess')
    monkeypatch.setattr(p.subprocess, 'run', deny)
    with pytest.raises(Blocked): p.encrypt('ZZ; command', b'ZZprivate')


@pytest.mark.parametrize('field,bad', [
    ('names', {'en': {'email': 'ZZsentinel'}}),
    ('names', {'en': {'first_name': {'access_token': 'ZZsentinel'}}}),
    ('names', {'en': {'first_name': ['ZZsentinel']}}),
    ('names', {'EN': {'first_name': 'ZZsentinel'}}),
    ('unions', [{'access_token': 'ZZsentinel'}]),
    ('unions', ['https://ZZsentinel.invalid']),
    ('public', 'ZZsentinel'), ('is_alive', 0), ('merge_pending', None),
    ('guid', {'email': 'ZZsentinel'}),
    ('first_name', ['ZZsentinel'])])
def test_profile_nested_leaf_schema_rejects_malformed(field, bad):
    client = Client()
    # Family node is checked even if the two identity responses are valid.
    family = copy.deepcopy(FAMILY)
    family['nodes']['profile-99123'][field] = bad
    client.responses[C['owner_node']+'/immediate-family'] = family
    with pytest.raises(Blocked) as error: p.collect(C, client)
    assert 'ZZsentinel' not in str(error.value)


@pytest.mark.parametrize('field', ['partners', 'children', 'adopted_children', 'foster_children'])
@pytest.mark.parametrize('bad', [[{'access_token': 'ZZsentinel'}], 'ZZsentinel',
                                ['profile-1']*101, ['profile-1', 'profile-1']])
def test_union_relationship_container_rejects_malformed(field, bad):
    client = Client()
    client.responses['union-99111'] = {**UNION, field: bad}
    with pytest.raises(Blocked) as error: p.collect(C, client)
    assert 'ZZsentinel' not in str(error.value)


@pytest.mark.parametrize('error_type', ['BadStatusLine', 'IncompleteRead'])
def test_http_protocol_failure_main_no_traceback_or_sentinel(tmp_path, monkeypatch, capsys, error_type):
    import http.client
    config = tmp_path/'connection'
    config.write_text(json.dumps(C)); config.chmod(0o600)
    token = tmp_path/'token'
    token.write_text('ZZsentinelToken'); token.chmod(0o600)
    error = (http.client.BadStatusLine('ZZproviderSentinel') if error_type == 'BadStatusLine'
             else http.client.IncompleteRead(b'ZZproviderSentinel'))
    client = p.ReadOnly('ZZsentinelToken')
    client.opener = Opener(error=error)
    monkeypatch.setattr(p, 'ReadOnly', lambda token: client)
    monkeypatch.setattr(p, 'encrypt', lambda recipient, value: b'age-encryption.org/v1\nZZcipher')
    assert p.main(['--connection-file',str(config),'--token-file',str(token),
                   '--recipient','age1'+'a'*58,'--output-dir',str(tmp_path/'out'),
                   '--confirm-read-only','YES']) == 1
    output = capsys.readouterr()
    assert 'ZZ' not in output.out + output.err and not output.err
    assert len(client.opener.requests) == 1


def test_valid_bounded_locale_and_edges_preserved_without_extras():
    client = Client()
    family = copy.deepcopy(FAMILY)
    family['nodes']['profile-99123'].update(
        names={'en': {'first_name': 'ZZRoot'}, 'he': {'first_name': 'ZZHebrew'}},
        unions=['union-99111'], email={'access_token': 'ZZsentinel'})
    client.responses[C['owner_node']+'/immediate-family'] = family
    result = p.collect(C, client)
    node = result['family']['nodes']['profile-99123']
    assert node['names']['he']['first_name'] == 'ZZHebrew'
    assert node['unions'] == ['union-99111'] and 'ZZsentinel' not in str(result)


@pytest.mark.parametrize('field,bad', [('names', {f'a{n}': {'first_name': 'ZZ'} for n in range(11)}),
                                    ('names', {'en': {'first_name': 'ZZ'*81}}),
                                    ('unions', ['union-1']*101)])
def test_nested_collection_and_leaf_bounds(field, bad):
    client = Client()
    family = copy.deepcopy(FAMILY)
    family['nodes']['profile-99123'][field] = bad
    client.responses[C['owner_node']+'/immediate-family'] = family
    with pytest.raises(Blocked): p.collect(C, client)


@pytest.mark.parametrize('opt_in', [False, True])
def test_unknown_merge_requires_explicit_readonly_choice(opt_in):
    client = Client()
    for route in ('profile', C['owner_node']):
        client.responses[route].pop('merge_pending', None)
    client.responses[C['owner_node']+'/immediate-family']['focus'].pop('merge_pending', None)
    if not opt_in:
        with pytest.raises(Blocked): p.collect(C, client)
    else:
        result = p.collect(C, client, allow_unknown_merge=True)
        assert result['create_enabled'] is False
        assert 'merge_pending' not in result['self']


@pytest.mark.parametrize('flag', [True, None, 'false', 0])
def test_readonly_unknown_optin_never_allows_invalid_explicit_flags(flag):
    client = Client()
    client.responses['profile'] = {**PROFILE, 'merge_pending': flag}
    with pytest.raises(Blocked): p.collect(C, client, allow_unknown_merge=True)
