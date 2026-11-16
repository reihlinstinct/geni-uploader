import contextlib
import importlib.util
import io
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'probe', Path(__file__).parents[1] / 'tools/token-probe/check.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
TOKEN = 'ZZ_SYNTHETIC_TOKEN_ONLY'


class Response:
    status = 200
    def __init__(self, raw):
        self.raw = raw
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.raw[:size]


class Opener:
    def __init__(self, raw=b'{"name":"ZZ_SYNTHETIC_NAME","account_type":"basic"}', error=None):
        self.calls = []
        self.raw, self.error = raw, error
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return Response(self.raw)


class Tests(unittest.TestCase):
    def test_one_get_fixed_url_no_body(self):
        o = Opener()
        verdict, code = probe.check(TOKEN, o)
        self.assertEqual(code, 0)
        self.assertIn('OWNER_NOT_VERIFIED', verdict)
        self.assertEqual(len(o.calls), 1)
        request, timeout = o.calls[0]
        self.assertEqual((request.full_url, request.method, request.data, timeout),
                         (probe.URL, 'GET', None, 20))
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + TOKEN)
    def test_bad_input_no_request(self):
        for token in ('', 'ZZ\nTOKEN', 'ZZ TOKEN', 'https://zz.invalid',
                      'access_token=ZZ', 'x' * 8193, 'טוקן'):
            with self.subTest(token=token[:20]):
                o = Opener()
                self.assertEqual(probe.check(token, o)[1], 1)
                self.assertEqual(o.calls, [])
    def test_unknown_or_error_shapes_stop(self):
        for raw in (b'{}', b'[]', b'null', b'not json', b'{"error":"private"}',
                    b'{"id":123}', b'{"guid":""}', b'{"id":" "}',
                    b'{"id":"ZZ","id":"YY"}', b'\xff', b'x' * 65537):
            self.assertEqual(probe.check(TOKEN, Opener(raw))[1], 1)
    def test_documented_user_response_without_profile_ids(self):
        for account_type in ('basic', 'plus', 'pro'):
            raw = ('{"name":"ZZ_SYNTHETIC_NAME","account_type":"'
                   + account_type + '"}').encode()
            self.assertEqual(probe.check(TOKEN, Opener(raw))[1], 0)

    def test_profile_only_and_bad_user_shapes_stop(self):
        for raw in (b'{"id":"ZZ"}', b'{"guid":"ZZ"}',
                    b'{"name":"ZZ"}', b'{"account_type":"basic"}',
                    b'{"name":null,"account_type":"basic"}',
                    b'{"name":123,"account_type":"basic"}',
                    b'{"name":" ","account_type":"basic"}',
                    b'{"name":"ZZ","account_type":null}',
                    b'{"name":"ZZ","account_type":123}',
                    b'{"name":"ZZ","account_type":"unknown"}',
                    b'{"name":"ZZ","account_type":"Basic"}',
                    b'{"name":"ZZ","account_type":["basic"]}',
                    b'{"name":"ZZ","account_type":"pro","error":"ZZ"}',
                    b'{"name":"ZZ","name":"YY","account_type":"pro"}'):
            verdict, code = probe.check(TOKEN, Opener(raw))
            self.assertEqual(code, 1)
            self.assertNotIn('ZZ', verdict)

    def test_user_fields_never_printed(self):
        with patch.dict(os.environ, {'TOKEN_PROBE_CREDENTIAL': TOKEN}), patch.object(
                probe.urllib.request, 'build_opener', return_value=Opener()):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main(), 0)
            self.assertEqual(output.getvalue(),
                             'TOKEN_CONTEXT_RESPONSE_OK_OWNER_NOT_VERIFIED\n'
                             'GENI_WRITES=0; OWNER_IDENTITY=NOT_VERIFIED\n')
            self.assertNotIn('ZZ_SYNTHETIC_NAME', output.getvalue())
    def test_failures_never_retry_or_disclose(self):
        for code in (301, 302, 307, 401, 403, 429, 500, 503):
            error = urllib.error.HTTPError(probe.URL, code, TOKEN, {}, io.BytesIO(TOKEN.encode()))
            o = Opener(error=error)
            verdict, result = probe.check(TOKEN, o)
            self.assertEqual(result, 1)
            self.assertEqual(len(o.calls), 1)
            self.assertNotIn(TOKEN, verdict)
        o = Opener(error=TimeoutError(TOKEN))
        self.assertEqual(probe.check(TOKEN, o)[1], 1)
        self.assertEqual(len(o.calls), 1)
    def test_redirect_handler(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://zz.invalid'))
    def test_no_proxy_and_redirect_handler(self):
        with patch.object(probe.urllib.request, 'build_opener', return_value=Opener()) as build:
            probe.check(TOKEN)
            self.assertEqual(build.call_args.args[0].proxies, {})
            self.assertIsInstance(build.call_args.args[1], probe.NoRedirect)
    def test_fixed_stdout_and_env_removed(self):
        with patch.dict(os.environ, {'TOKEN_PROBE_CREDENTIAL': TOKEN}), patch.object(probe, 'check', return_value=('TOKEN_CONTEXT_RESPONSE_OK_OWNER_NOT_VERIFIED', 0)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(probe.main(), 0)
            self.assertNotIn('TOKEN_PROBE_CREDENTIAL', os.environ)
            self.assertNotIn(TOKEN, output.getvalue())
            self.assertIn('GENI_WRITES=0', output.getvalue())
    def test_workflow_isolated(self):
        root = Path(__file__).parents[1]
        workflow = (root / '.github/workflows/token-probe.yml').read_text()
        self.assertIn('github.actor == \'reihl\'', workflow)
        self.assertIn('github.triggering_actor == \'reihl\'', workflow)
        self.assertIn('secrets.TOKEN_PROBE_CREDENTIAL', workflow)
        self.assertNotIn('secrets.GENI_ACCESS_TOKEN', workflow)
        for forbidden in ('upload-artifact', 'schedule:', 'pull_request:', 'repository_dispatch:', 'git push', 'curl '):
            self.assertNotIn(forbidden, workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn("github.ref == 'refs/heads/master'", workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn("inputs.confirm == 'TEST'", workflow)
        self.assertIn("github.repository == 'reihlinstinct/geni-uploader'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn('  workflow_dispatch:', workflow)
        self.assertIn('3d3c42e5aac5ba805825da76410c181273ba90b1', workflow)
        self.assertIn('environment: token-probe', workflow)
        self.assertIn('run: python3 -I tools/token-probe/check.py', workflow)
        self.assertEqual(workflow.count('secrets.TOKEN_PROBE_CREDENTIAL'), 1)
        secret_step = workflow.split('      - name: One read-only request;', 1)[1]
        self.assertIn('TOKEN_PROBE_CREDENTIAL: ${{ secrets.TOKEN_PROBE_CREDENTIAL }}', secret_step)
        self.assertNotIn('secrets.', workflow.split('      - name: One read-only request;', 1)[0])
        owners = (root / '.github/CODEOWNERS').read_text()
        self.assertIn('/.github/ @reihl', owners)
        self.assertIn('/tools/token-probe/ @reihl', owners)


if __name__ == '__main__':
    unittest.main()
