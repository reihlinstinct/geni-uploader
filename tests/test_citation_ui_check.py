"""Synthetic shape tests, not a representation of verified live DOM."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from geni_uploader.client import citation_ui_check as c


def fixture():
    return {'schema': 1, 'profile_url': 'https://www.geni.com/people/ZZ-Test/111',
            'document_guid': '222', 'sources_tab': True, 'add_source_count': 1,
            'citation_dialog': True, 'profile_edit': False, 'login': False,
            'challenge': False, 'restricted': False,
            'rows': [{'label': 'Death Date', 'value_controls': 1, 'note_controls': 1,
                      'enabled': True, 'readonly': False}]}


class CitationUICheckTest(unittest.TestCase):
    def test_form_is_only_observed_not_saved_or_authorized(self):
        r = c.check(fixture(), '111', '222')
        self.assertEqual(r['status'], 'controls_observed')
        self.assertFalse(r['save_allowed']); self.assertFalse(r['citation_verified'])
        self.assertEqual(r['writes'], 0)

    def test_stop_conditions(self):
        for field, status in [('login', 'login_required'), ('challenge', 'challenge'),
                              ('restricted', 'restricted'), ('profile_edit', 'unsupported_layout')]:
            with self.subTest(field=field):
                o = fixture(); o[field] = True
                self.assertEqual(c.check(o, '111', '222')['status'], status)

    def test_identity(self):
        for url in ['https://[bad/people/ZZ-Test/111', 'https://evil.invalid/people/ZZ-Test/111',
                    'https://www.geni.com.evil.invalid/people/ZZ-Test/111',
                    'http://www.geni.com/people/ZZ-Test/111',
                    'https://www.geni.com/people/ZZ-Test/112',
                    'https://user@www.geni.com/people/ZZ-Test/111',
                    'https://www.geni.com/people/ZZ-Test/111?extra=1',
                    'https://www.geni.com/people/ZZ-Test/111#/tab/overview']:
            o = fixture(); o['profile_url'] = url
            self.assertFalse(c.check(o, '111', '222')['controls_observed'])
        o = fixture(); o['document_guid'] = '223'
        self.assertEqual(c.check(o, '111', '222')['status'], 'identity_mismatch')

    def test_ambiguous_disabled_unknown_layout(self):
        for key, val in [('label', 'Death Place'), ('label', 'תאריך פטירה'),
                         ('value_controls', 2), ('note_controls', 0),
                         ('enabled', False), ('readonly', True)]:
            o = fixture(); o['rows'][0][key] = val
            self.assertFalse(c.check(o, '111', '222')['controls_observed'])
        o = fixture(); o['rows'] *= 2
        self.assertEqual(c.check(o, '111', '222')['status'], 'unsupported_layout')
        for key, val in [('sources_tab', False), ('citation_dialog', False),
                         ('add_source_count', 2), ('rows', [])]:
            o = fixture(); o[key] = val
            self.assertFalse(c.check(o, '111', '222')['controls_observed'])

    def test_schema_rejects_values_and_secrets(self):
        for key, val in [('schema', True), ('rows', 'bad'), ('unknown', 'ZZ-secret'),
                         ('profile_url', None), ('add_source_count', True)]:
            o = fixture(); o[key] = val
            self.assertFalse(c.check(o, '111', '222')['controls_observed'])
        o = fixture(); o['rows'][0]['value'] = 'ZZ-sensitive'
        self.assertEqual(c.check(o, '111', '222')['status'], 'invalid_observation')
        self.assertNotIn('ZZ-sensitive', json.dumps(c.check(o, '111', '222')))
        self.assertFalse(c.check({}, '111', '222')['controls_observed'])
        self.assertFalse(c.check(fixture(), 'not-id', '222')['controls_observed'])

    def test_cli_private_quiet_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'in.json'; dest = Path(td) / 'out.json'
            src.write_text(json.dumps(fixture()))
            args = ['--observation', str(src), '--expected-profile', '111',
                    '--expected-document', '222', '--output', str(dest)]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(c.main(args), 0)
            self.assertNotIn('diagnostic', out.getvalue())
            self.assertNotIn('111', out.getvalue())
            self.assertEqual(os.stat(dest).st_mode & 0o777, 0o600)
            before = dest.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(c.main(args), 2)
            self.assertEqual(dest.read_bytes(), before)
            dest.unlink()
            with contextlib.redirect_stdout(io.StringIO()) as out: self.assertEqual(c.main(args + ['--debug']), 0)
            self.assertIn('offline shape analysis only', out.getvalue())

    def test_no_network_driver(self):
        code = Path(c.__file__).read_text()
        for token in ('import requests', 'urlopen(', 'fetch(', 'playwright', '.click(', '.fill('):
            self.assertNotIn(token, code)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'in.json'; p.write_text('{"schema":1,"schema":1}')
            with self.assertRaises(ValueError): c.load(p)

    def test_mutation_free(self):
        o = fixture(); before = copy.deepcopy(o)
        c.check(o, '111', '222'); self.assertEqual(o, before)

    def test_mixed_valid_and_unsupported_extra_rows_stop(self):
        for extras in [
                [{'label': 'Birth Date', 'value_controls': 1, 'note_controls': 1,
                  'enabled': True, 'readonly': False}] * 2,
                [{'label': 'Unknown-layout', 'value_controls': 20, 'note_controls': 20,
                  'enabled': True, 'readonly': False}],
                [fixture()['rows'][0]]]:
            o = fixture(); o['rows'].extend(copy.deepcopy(extras))
            self.assertEqual(c.check(o, '111', '222')['status'], 'unsupported_layout')

    def test_argument_errors_never_echo_values_or_paths(self):
        for args in [[], ['--ZZ-secret'], ['--observation', 'ZZ-private-path'],
                     ['--debug=ZZ-secret']]:
            with (contextlib.redirect_stdout(io.StringIO()) as out,
                  contextlib.redirect_stderr(io.StringIO()) as err,
                  self.assertRaises(SystemExit) as raised):
                c.main(args)
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(err.getvalue(), 'citation checker: invalid arguments\n')

    def test_bounded_regular_file_input(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'in.json'
            p.write_bytes(b' ' * 100_001)
            with self.assertRaises(ValueError): c.load(p)
            alias = Path(td) / 'alias'; alias.symlink_to(p)
            with self.assertRaises(OSError): c.load(alias)
            fifo = Path(td) / 'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError): c.load(fifo)
            with self.assertRaises((OSError, ValueError)): c.load(td)

    def test_cosmetic_slug_and_sources_fragment(self):
        for slug in ['ZZ.Test', '%D7%A9%D7%A8%D7%94-ZZ', 'ZZ-Test']:
            for suffix in ['', '#/tab/sources']:
                o = fixture()
                o['profile_url'] = 'https://www.geni.com/people/' + slug + '/111' + suffix
                self.assertEqual(c.check(o, '111', '222')['status'], 'controls_observed')
        for slug in ['ZZ%2FTest', 'ZZ%5cTest', 'ZZ%00Test', 'ZZ%20Test', 'ZZ%7fTest']:
            o = fixture(); o['profile_url'] = 'https://www.geni.com/people/' + slug + '/111'
            self.assertEqual(c.check(o, '111', '222')['status'], 'identity_mismatch')
