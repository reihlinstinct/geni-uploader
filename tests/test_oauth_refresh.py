import io
import json
import urllib.parse
from unittest.mock import patch

import pytest

import oauth_refresh as m

B = {'schema': 1, 'client_id': 'ZZCLIENT', 'client_secret': 'ZZSECRET',
     'redirect_uri': 'https://example.invalid/callback', 'refresh_token': 'ZZREFRESH'}
R = {'access_token': 'ZZACCESS', 'refresh_token': 'ZZROTATED', 'expires_in': 86400}
REPO = 'reihlinstinct/geni-uploader'


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return m.ENDPOINT


def transport(req, timeout):
    assert req.full_url == m.ENDPOINT and req.method == 'POST' and timeout == 30
    fields = urllib.parse.parse_qs(req.data.decode())
    assert fields['grant_type'] == ['refresh_token']
    assert 'ZZSECRET' not in req.full_url
    return Response(json.dumps(R).encode())


def test_happy_rotation_order():
    calls = []
    def call(args, value=None):
        calls.append((args, value))
    assert m.run(json.dumps(B), REPO, call, transport) == 'renewal_saved'
    assert calls[0][0][0] == 'api'
    assert calls[1][0][2] == m.BUNDLE_SECRET
    assert json.loads(calls[1][1])['refresh_token'] == 'ZZROTATED'
    assert json.loads(calls[1][1])['pending_access_token'] == 'ZZACCESS'
    assert calls[2][0][2] == m.ACCESS_SECRET
    assert 'pending_access_token' not in json.loads(calls[3][1])


@pytest.mark.parametrize('raw', ['', '{}', '[]', '{', json.dumps(B | {'schema': 2}),
                                  json.dumps(B | {'client_secret': 'bad\nsecret'})])
def test_bad_bundle(raw):
    with pytest.raises(m.RenewalError):
        m.load_bundle(raw)


@pytest.mark.parametrize('uri', ['http://example.invalid/cb', 'https://u:p@example.invalid/cb',
                                'https://example.invalid/cb#x', 'https://example.invalid:42/cb',
                                'https://example.invalid/cb?x=y'])
def test_bad_redirect(uri):
    with pytest.raises(m.RenewalError):
        m.load_bundle(json.dumps(B | {'redirect_uri': uri}))


@pytest.mark.parametrize('data', [[], {}, R | {'error': 'SECRET'},
                                 R | {'expires_in': True}, R | {'expires_in': 0},
                                 R | {'refresh_token': ''}, R | {'access_token': 'x y'}])
def test_response_rejected(data):
    with pytest.raises(m.RenewalError):
        m.refresh(B, lambda *a, **kw: Response(json.dumps(data).encode()))


def test_no_redirect():
    with pytest.raises(m.RenewalError):
        m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid')


def test_repo_refused_before_network():
    with pytest.raises(m.RenewalError, match='repository_refused'):
        m.run(json.dumps(B), 'ZZOTHER/repo', lambda *a: pytest.fail('network'))


def test_persist_failure_no_access_update():
    calls = []
    def call(args, value=None):
        calls.append(args)
        if args[0] == 'secret':
            raise RuntimeError('ZZSECRET')
    with pytest.raises(m.RenewalError, match='rotation_persist_failed'):
        m.run(json.dumps(B), REPO, call, transport)
    assert len(calls) == 2


def test_recovery_never_calls_oauth():
    calls = []
    def call(args, value=None):
        calls.append((args, value))
    b = B | {'pending_access_token': 'ZZPENDING', 'pending_expires_at': 9999999999}
    assert m.run(json.dumps(b), REPO, call,
                 lambda *a, **k: pytest.fail('OAuth called')) == 'recovered_previous_rotation'
    assert calls[1][1] == 'ZZPENDING'


def test_failure_logs_are_fixed(capsys):
    with (
        patch.dict('os.environ', {'OAUTH_BUNDLE': json.dumps(B), 'GITHUB_REPOSITORY': REPO}),
        patch.object(m, 'run', side_effect=RuntimeError('ZZSECRET')),
    ):
        assert m.main() == 1
    out = capsys.readouterr()
    assert out.out == 'STOP: renewal_failed\n' and out.err == ''


def test_workflow_is_human_only():
    from pathlib import Path

    import yaml
    text = Path('.github/workflows/oauth-refresh.yml').read_text()
    d = yaml.safe_load(text)
    assert d[True] == {'workflow_dispatch': None}
    gate = d['jobs']['renew']['if']
    for check in ["github.actor == 'reihl'", "github.triggering_actor == 'reihl'",
                  "github.ref == 'refs/heads/master'", "github.event_name == 'workflow_dispatch'"]:
        assert check in gate
    assert d['jobs']['renew']['environment'] == 'oauth-refresh'
    assert 'schedule:' not in text


@pytest.mark.parametrize('expiry', [None, 0, 100, True, '9999999999'])
def test_stale_pending_refreshes_instead_of_restoring(expiry):
    calls = []
    def call(args, value=None):
        calls.append((args, value))
    b = B | {'pending_access_token': 'ZZSTALE', 'pending_expires_at': expiry}
    assert m.run(json.dumps(b), REPO, call, transport, clock=lambda: 200) == 'renewal_saved'
    assert calls[2][1] == 'ZZACCESS'
    assert json.loads(calls[1][1])['pending_expires_at'] == 86600
    assert 'pending_expires_at' not in json.loads(calls[3][1])
