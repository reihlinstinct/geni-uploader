"""Offline citation-form observation checker. No browser, network or write client."""
import argparse
import json
import os
import re
import stat
from urllib.parse import unquote, urlsplit

FIELDS = {'schema', 'profile_url', 'document_guid', 'sources_tab', 'add_source_count',
          'citation_dialog', 'profile_edit', 'login', 'challenge', 'restricted', 'rows'}
ROW_FIELDS = {'label', 'value_controls', 'note_controls', 'enabled', 'readonly'}
# First release admits only the single observed fact row, no inferred extra layout.
ALLOWED_LABELS = {'Death Date'}


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'citation checker: invalid arguments\n')



def profile_guid(url):
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    if (u.scheme != 'https' or u.netloc != 'www.geni.com' or u.query
            or u.fragment not in ('', '/tab/sources') or any(ord(c) < 33 for c in url)):
        return None
    match = re.fullmatch(r'/people/([^/]+)/([1-9][0-9]{0,29})', u.path)
    if not match:
        return None
    slug = unquote(match.group(1))
    if any(c in '/\\' or ord(c) < 33 or ord(c) == 127 for c in slug):
        return None
    return match.group(2)


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,29}', value) is not None


def check(observation, expected_profile, expected_document):
    """Untrusted observations cannot grant authority or establish a saved citation."""
    def result(status):
        return {'schema': 1, 'status': status, 'controls_observed': status == 'controls_observed',
                'save_allowed': False, 'citation_verified': False, 'writes': 0}
    o = observation
    if not identifier(expected_profile) or not identifier(expected_document):
        return result('invalid_observation')
    if not isinstance(o, dict) or set(o) != FIELDS or type(o['schema']) is not int or o['schema'] != 1:
        return result('invalid_observation')
    for key in ('sources_tab', 'citation_dialog', 'profile_edit', 'login', 'challenge', 'restricted'):
        if type(o[key]) is not bool:
            return result('invalid_observation')
    if (type(o['add_source_count']) is not int or not 0 <= o['add_source_count'] <= 20
            or not isinstance(o['rows'], list) or len(o['rows']) > 50):
        return result('invalid_observation')
    for row in o['rows']:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            return result('invalid_observation')
        if (not isinstance(row['label'], str) or len(row['label']) > 100
                or type(row['enabled']) is not bool or type(row['readonly']) is not bool
                or any(type(row[k]) is not int or not 0 <= row[k] <= 20
                       for k in ('value_controls', 'note_controls'))):
            return result('invalid_observation')
    for field, status in [('challenge', 'challenge'), ('login', 'login_required'),
                          ('restricted', 'restricted')]:
        if o[field]:
            return result(status)
    if (profile_guid(o['profile_url']) != expected_profile
            or o['document_guid'] != expected_document):
        return result('identity_mismatch')
    labels = [r['label'] for r in o['rows']]
    if any(label not in ALLOWED_LABELS for label in labels) or len(set(labels)) != len(labels):
        return result('unsupported_layout')
    death = [r for r in o['rows'] if r['label'] == 'Death Date']
    if (not o['sources_tab'] or o['add_source_count'] != 1 or not o['citation_dialog']
            or o['profile_edit'] or len(death) != 1 or not death[0]['enabled']
            or death[0]['readonly'] or death[0]['value_controls'] != 1
            or death[0]['note_controls'] != 1):
        return result('unsupported_layout')
    return result('controls_observed')


def load(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError()
        raw = stream.read(100_001)
    if len(raw) > 100_000:
        raise ValueError()
    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError()
            data[key] = value
        return data
    return json.loads(raw, object_pairs_hook=unique)


def main(argv=None):
    parser = QuietParser(description=__doc__)
    parser.add_argument('--observation', required=True)
    parser.add_argument('--expected-profile', required=True)
    parser.add_argument('--expected-document', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--debug', action='store_true', default=False)
    args = parser.parse_args(argv)
    try:
        report = check(load(args.observation), args.expected_profile, args.expected_document)
        # Never follow an existing output symlink or overwrite an existing file.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, sort_keys=True)
        if args.debug:
            print('citation checker diagnostic: offline shape analysis only')
        print('citation checker: ' + report['status'])
        return 0 if report['controls_observed'] else 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('citation checker: stopped')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
