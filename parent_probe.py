"""Human-started local GET-only probe. Never imported by MCP or uploader."""
import argparse
import http.client
import json
import os
import re
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from people_core import Blocked, exact, require, text

BASE = 'https://www.geni.com/api/'
LIMIT = 1024 * 1024
FIELDS = 'id,guid,first_name,middle_name,last_name,maiden_name,names,public,is_alive,merge_pending,merged_into,unions'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Blocked('probe stopped; redirect refused')


def protected_file(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o077 and info.st_size <= maximum)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            value = stream.read(maximum + 1)
        require(len(value) <= maximum)
        return value.decode('utf-8')
    finally:
        os.close(fd)


def connection(data):
    exact(data, ('schema_version', 'connection_id', 'owner_node', 'expect_name'))
    require(type(data['schema_version']) is int and data['schema_version'] == 1)
    require(type(data['connection_id']) is str
            and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', data['connection_id']) is not None)
    require(type(data['owner_node']) is str
            and re.fullmatch(r'profile-[0-9]{1,30}', data['owner_node']) is not None)
    text(data['expect_name'])
    require(len(data['expect_name'].split()) >= 2)
    return data


def profile(value, owner, expected, *, allow_unknown_merge=False):
    require(type(value) is dict and value.get('id') == owner
            and 'error' not in value and 'results' not in value
            and not any(k in value for k in ('next_page', 'paging', 'pagination')))
    require(type(allow_unknown_merge) is bool)
    unknown = ('merge_pending' not in value and 'merged_into' not in value)
    require((allow_unknown_merge and unknown) or
            (value.get('merged_into') is None and value.get('merge_pending') is False))
    # Exact expected root-name tokens, not names from relatives or a broad graph.
    names = [value.get(k, '') for k in ('first_name', 'middle_name', 'last_name', 'maiden_name')]
    require(all(type(n) is str for n in names))
    require(all(w.casefold() in ' '.join(names).casefold().split() for w in expected.split()))
    return value


class ReadOnly:
    def __init__(self, token):
        require(type(token) is str and re.fullmatch(r'[A-Za-z0-9._~-]{8,4096}', token) is not None)
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.calls = 0
        self.last = None

    def get(self, route):
        require(type(route) is str and (route == 'profile' or re.fullmatch(
            r'(?:profile-[0-9]{1,30}(?:/immediate-family)?|union-[0-9]{1,30})', route)))
        require(self.calls < 20)
        if self.last is not None:
            time.sleep(max(0, 10 - (time.monotonic() - self.last)))
        self.calls += 1
        self.last = time.monotonic()
        query = {'only_ids': 'true'}
        if route.startswith('profile') and not route.endswith('immediate-family'):
            query['fields'] = FIELDS
        req = urllib.request.Request(BASE + route + '?' + urllib.parse.urlencode(query),
                                     headers={'Authorization': 'Bearer ' + self.token}, method='GET')
        try:
            with self.opener.open(req, timeout=30) as response:
                require(response.status == 200 and response.geturl() == req.full_url)
                raw = response.read(LIMIT + 1)
                require(len(raw) <= LIMIT)
                result = json.loads(raw.decode('utf-8'))
                require(type(result) is dict and 'error' not in result)
                return result
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                http.client.HTTPException) as exc:
            raise Blocked('probe stopped; request or response unavailable') from exc


def collect(config, client, *, allow_unknown_merge=False):
    """Minimal protected observations. No parent-completeness/readiness claim."""
    require(type(allow_unknown_merge) is bool)
    config = connection(config)
    owner, name = config['owner_node'], config['expect_name']
    self_profile = profile(client.get('profile'), owner, name, allow_unknown_merge=allow_unknown_merge)
    owner_profile = profile(client.get(owner), owner, name, allow_unknown_merge=allow_unknown_merge)
    family = client.get(owner + '/immediate-family')
    require(type(family.get('focus')) is dict and family['focus'].get('id') == owner
            and type(family.get('nodes')) is dict and len(family['nodes']) <= 100
            and set(family) <= {'focus', 'nodes'})
    profile(family['focus'], owner, name, allow_unknown_merge=allow_unknown_merge)
    # Extract bounded typed leaves, never copy nested provider objects.
    def edges(value):
        require(type(value) is list and len(value) <= 100)
        require(all(type(v) is str and re.fullmatch(
            r'(?:profile|union)-[0-9]{1,30}', v) for v in value))
        require(len(set(value)) == len(value))
        return list(value)

    def minimal(value):
        require(type(value) is dict)
        result = {}
        if 'id' in value:
            require(type(value['id']) is str and re.fullmatch(
                r'(?:profile|union)-[0-9]{1,30}', value['id']))
            result['id'] = value['id']
        if 'guid' in value:
            require(type(value['guid']) is str and re.fullmatch(r'[0-9]{1,30}', value['guid']))
            result['guid'] = value['guid']
        for key in ('public', 'is_alive', 'merge_pending'):
            if key in value:
                require(type(value[key]) is bool)
                result[key] = value[key]
        if 'merged_into' in value:
            require(value['merged_into'] is None)
            result['merged_into'] = None
        name_fields = {'first_name', 'middle_name', 'last_name', 'maiden_name'}
        for key in name_fields:
            if key in value:
                text(value[key])
                result[key] = value[key]
        if 'names' in value:
            names = value['names']
            require(type(names) is dict and len(names) <= 10)
            result['names'] = {}
            for locale, fields in names.items():
                require(type(locale) is str and re.fullmatch(r'[a-z]{2}', locale)
                        and type(fields) is dict and 1 <= len(fields) <= 4
                        and set(fields) <= name_fields)
                for leaf in fields.values():
                    text(leaf)
                result['names'][locale] = dict(fields)
        for key in ('unions', 'partners', 'children', 'adopted_children', 'foster_children'):
            if key in value:
                result[key] = edges(value[key])
                kind = 'union-' if key == 'unions' else 'profile-'
                require(all(v.startswith(kind) for v in result[key]))
        return result
    nodes = {}
    union_ids = set()
    for key, value in family['nodes'].items():
        require(type(key) is str and re.fullmatch(r'(profile|union)-[0-9]{1,30}', key)
                and type(value) is dict and value.get('id') == key)
        nodes[key] = minimal(value)
        if key.startswith('union-'):
            union_ids.add(key)
    require(len(union_ids) <= 10)
    unions = []
    for uid in sorted(union_ids):
        union = client.get(uid)
        require(union.get('id') == uid)
        for field in ('partners', 'children'):
            require(type(union.get(field)) is list and len(union[field]) <= 100
                    and all(type(v) is str and re.fullmatch(r'profile-[0-9]{1,30}', v)
                            for v in union[field]))
        unions.append(minimal(union))
    return {'schema_version': 1, 'connection_id': config['connection_id'],
            'collected_at_unix': int(time.time()), 'mode': 'human_read_only_probe',
            'self': minimal(self_profile), 'owner': minimal(owner_profile),
            'family': {'focus': minimal(family['focus']), 'nodes': nodes}, 'unions': unions,
            'create_enabled': False, 'hidden_parent_completeness': 'unproved',
            'slot_semantics': 'unproved', 'privacy_create_behavior': 'unproved'}


def encrypt(recipient, value):
    require(type(recipient) is str and re.fullmatch(r'age1[0-9a-z]{58}', recipient) is not None)
    result = subprocess.run(['age', '-r', recipient], input=value, capture_output=True,
                            timeout=30, check=False)
    require(result.returncode == 0 and result.stdout.startswith(b'age-encryption.org/v1\n'))
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description='Human-started local read-only parent evidence probe')
    parser.add_argument('--connection-file', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--recipient', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--confirm-read-only', choices=['YES'], required=True)
    args = parser.parse_args(argv)
    try:
        config = connection(json.loads(protected_file(args.connection_file, 8192)))
        token = protected_file(args.token_file, 4096).strip()
        require(not Path(args.output_dir).exists())
        encrypt(args.recipient, b'preflight')  # fail before network if age/recipient unavailable
        os.mkdir(args.output_dir, 0o700)
        result = collect(config, ReadOnly(token))
        ciphertext = encrypt(args.recipient, json.dumps(result, ensure_ascii=False).encode())
        fd = os.open(Path(args.output_dir) / 'parent-evidence.age',
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(ciphertext)
            stream.flush()
            os.fsync(stream.fileno())
        print('parent-probe complete; encrypted evidence saved; creation disabled')
        return 0
    except (Blocked, OSError, ValueError, subprocess.SubprocessError,
            http.client.HTTPException):
        print('parent-probe blocked; inspect local configuration or request human review')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
