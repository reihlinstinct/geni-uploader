"""Separately approved GET-only setup diagnostic. No create or remote persistence."""
import base64
import http.client
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from geni_uploader.core.parent_contract import payload
from geni_uploader.core.people import Blocked, exact, require
from one_time_parent_pilot import HTTPS, TransportStop, canonical, decode, preflight, sha
from parent_probe import encrypt

STAGES = frozenset(('setup', 'encryption', 'github_credential', 'private_repository',
                    'private_source', 'manifest', 'secondary_credential', 'vendor_reads', 'complete'))
ERRORS = (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
          http.client.HTTPException, subprocess.SubprocessError)


def configuration(c):
    exact(c, ('schema', 'mode', 'data_repo', 'data_sha', 'data_path', 'owner',
              'expect_name', 'recipient', 'allow_unknown_merge', 'expires_at',
              *(('created_id', 'union_id') if c.get('mode') == 'get_only_verify' else ())))
    require(type(c['schema']) is int and c['schema'] == 1 and c['mode'] in (
        'get_only_diagnostic', 'get_only_reconcile', 'get_only_verify'))
    if c['mode'] == 'get_only_verify':
        require(type(c['created_id']) is str and re.fullmatch(r'profile-[0-9]{1,30}', c['created_id'])
                and c['created_id'] != c['owner'])
        require(type(c['union_id']) is str and re.fullmatch(r'union-[0-9]{1,30}', c['union_id']))
    require(type(c['data_repo']) is str and re.fullmatch(
        r'[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_-]{1,100}', c['data_repo']))
    require(type(c['data_sha']) is str and re.fullmatch(r'[a-f0-9]{40}', c['data_sha']))
    require(type(c['data_path']) is str and re.fullmatch(
        r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.json', c['data_path'])
        and '..' not in c['data_path'])
    require(type(c['owner']) is str and re.fullmatch(r'profile-[0-9]{1,30}', c['owner']))
    require(type(c['expect_name']) is str and 2 <= len(c['expect_name'].split()) <= 8)
    require(type(c['recipient']) is str and re.fullmatch(r'age1[0-9a-z]{58}', c['recipient']))
    require(type(c['allow_unknown_merge']) is bool)
    require(type(c['expires_at']) is int and 0 < c['expires_at'] < 2**40)
    return c


class GetOnly:
    """Checks method and exact per-run route allowlist BEFORE transport construction."""
    def __init__(self, host, token, routes, *, factory=HTTPS):
        require(host in ('api.github.com', 'www.geni.com'))
        self.host, self.token, self.routes, self.factory = host, token, frozenset(routes), factory
        self.transport = None
        self.seen = set()

    def request(self, method, route, body=None):
        require(method == 'GET' and body is None and route in self.routes and route not in self.seen)
        self.seen.add(route)  # consume before construction; no retry even on failure
        if self.transport is None:
            options = {'github': self.host == 'api.github.com'}
            if self.factory is HTTPS:
                options['capture_failure'] = True
            self.transport = self.factory(self.host, self.token, **options)
        return self.transport.request('GET', route)


def routes(c):
    prefix = '/repos/' + c['data_repo']
    source = prefix + '/contents/' + urllib.parse.quote(c['data_path'], safe='/') + '?ref=' + c['data_sha']
    # Reuse the same fixed field list as the reviewed read preflight, not create/receipt logic.
    from one_time_parent_pilot import FIELDS
    if c['mode'] == 'get_only_verify':
        return prefix, source, ['/api/' + c['created_id'] + '?fields=' + FIELDS + '&only_ids=true',
                                '/api/' + c['union_id'] + '?only_ids=true']
    vendor = ['/api/' + x + '?fields=' + FIELDS + '&only_ids=true'
              for x in ('profile', c['owner'])]
    vendor.append('/api/' + c['owner'] + '/immediate-family?only_ids=true')
    return prefix, source, vendor


def diagnose(c, github, vendor, save, clock=time.time):
    """Every network dependency must already be wrapped in GetOnly."""
    require(type(github) is GetOnly and type(vendor) is GetOnly)
    c = configuration(c)
    report = {'schema': 1, 'mode': c['mode'], 'phase': 'STOPPED',
              'stage': 'private_repository', 'data_sha': c['data_sha'],
              'data_path': c['data_path'], 'owner': c['owner'], 'create_enabled': False}
    prefix, source, _ = routes(c)
    try:
        require(clock() < c['expires_at'])
        repo = github.request('GET', prefix)
        require(repo.get('private') is True and repo.get('full_name') == c['data_repo'])
        report['stage'] = 'private_source'
        require(clock() < c['expires_at'])
        r = github.request('GET', source)
        require(r.get('type') == 'file' and r.get('encoding') == 'base64'
                and type(r.get('size')) is int and 0 < r['size'] <= 65536)
        raw = base64.b64decode(''.join(r['content'].split()), validate=True)
        require(len(raw) == r['size'])
        report['stage'] = 'manifest'
        manifest = decode(raw)
        exact(manifest, ('kind', 'target', 'creation_enabled', 'payload'))
        require(manifest['kind'] == 'offline_father_only_data_proposal'
                and manifest['creation_enabled'] is False and manifest['target'] == c['owner'])
        approved = payload(manifest['payload'])
        require(approved['is_alive'] is True and approved['gender'] == 'male')
        report['payload_sha256'] = sha(canonical(approved))
        report['stage'] = 'vendor_reads'
        require(clock() < c['expires_at'])
        if c['mode'] == 'get_only_verify':
            verify_read_only(vendor, c, approved, report, save, clock)
        elif c['mode'] == 'get_only_reconcile':
            reconcile(vendor, c, approved, report, clock)
        else:
            report['preflight'] = preflight(vendor, c)
        require(clock() < c['expires_at'])
        report['phase'], report['stage'] = 'READ_ONLY_COMPLETE', 'complete'
    except ERRORS as exc:
        report['failure_code'] = exc.code if isinstance(exc, TransportStop) else 'validation_or_setup'
        if isinstance(exc, TransportStop) and exc.evidence:
            report['http_failure'] = exc.evidence
    save(report)
    return report


def verify_read_only(vendor, c, approved, report, save, clock):
    """Capture each parsed response durably before applying unchanged checks."""
    import copy

    from one_time_parent_pilot import FIELDS, merge_clear, vendor_payload
    report['verification'] = {'responses': {}, 'checks': {}, 'verified': False}
    evidence = report['verification']
    for label, route in (
        ('profile', '/api/' + c['created_id'] + '?fields=' + FIELDS + '&only_ids=true'),
        ('union', '/api/' + c['union_id'] + '?only_ids=true'),
    ):
        require(clock() < c['expires_at'])
        evidence['responses'][label] = vendor.request('GET', route)
        save(copy.deepcopy(report))  # failure here forbids the next read
    actual, union = evidence['responses']['profile'], evidence['responses']['union']

    def check(label, test):
        try:
            evidence['checks'][label] = bool(test())
        except ERRORS:
            evidence['checks'][label] = False

    check('profile_id', lambda: actual.get('id') == c['created_id'])
    def merge():
        merge_clear(actual, c['allow_unknown_merge'])
        return True
    check('merge', merge)
    check('private', lambda: actual.get('public') is False)
    check('alive', lambda: actual.get('is_alive') is True)
    check('gender', lambda: actual.get('gender') == 'male')
    for key, val in vendor_payload(approved).items():
        check('field_' + key, lambda key=key, val=val: actual.get(key) == val)
    check('profile_union', lambda: actual.get('unions') == [c['union_id']])
    check('union_id', lambda: union.get('id') == c['union_id'])
    check('union_partners', lambda: union.get('partners') == [c['created_id']])
    check('union_children', lambda: union.get('children') == [c['owner']])
    def url():
        value = actual.get('profile_url')
        if value is None:
            return True
        require(type(value) is str)
        parsed = urllib.parse.urlsplit(value)
        return parsed.scheme == 'https' and parsed.netloc == 'www.geni.com' and not parsed.fragment
    check('profile_url', url)
    evidence['verified'] = all(evidence['checks'].values())
    save(copy.deepcopy(report))
    require(evidence['verified'])


def reconcile(vendor, c, approved, report, clock):
    """Bounded immediate-family observations, not creation/completeness proof."""
    from one_time_parent_pilot import FIELDS, get_profile
    from parent_probe import profile
    owner = c['owner']
    def locale_keys(value):
        names = value.get('names', {})
        require(type(names) is dict and len(names) <= 20)
        require(all(type(k) is str and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{2,4})?', k)
                    for k in names))
        return sorted(names)
    report['root_name_locales'] = []
    for route in ('profile', owner):
        require(clock() < c['expires_at'])
        root = profile(get_profile(vendor, route), owner, c['expect_name'],
                       allow_unknown_merge=c['allow_unknown_merge'])
        report['root_name_locales'].append(locale_keys(root))
    require(clock() < c['expires_at'])
    family = vendor.request('GET', '/api/' + owner + '/immediate-family?only_ids=true')
    require(type(family) is dict and set(family) <= {'focus', 'nodes'})
    profile(family.get('focus'), owner, c['expect_name'],
            allow_unknown_merge=c['allow_unknown_merge'])
    nodes = family.get('nodes')
    require(type(nodes) is dict and len(nodes) <= 20)
    for key, value in nodes.items():
        require(type(key) is str and re.fullmatch(r'(?:profile|union)-[0-9]{1,30}', key)
                and type(value) is dict and value.get('id') == key)
    ids = sorted(key for key in nodes if key.startswith('profile-') and key != owner)
    report['reconciliation'] = {'observed_profile_ids': ids, 'checked': [],
        'completeness': 'UNPROVED', 'parenthood': 'UNPROVED'}
    require(len(ids) <= 8)  # no graph traversal or pagination
    def name(value):
        require(type(value) is dict)
        parts = [value.get(k, '') for k in ('first_name', 'middle_name', 'last_name')]
        require(all(type(v) is str and len(v) <= 256 for v in parts))
        return ' '.join(' '.join(parts).split()).casefold()
    expected = {name(approved)}
    expected.update(name(v) for v in approved.get('names', {}).values())
    for node in ids:
        route = '/api/' + node + '?fields=' + FIELDS + '&only_ids=true'
        vendor.routes = vendor.routes | {route}  # only validated immediate-family IDs
        require(clock() < c['expires_at'])
        actual = vendor.request('GET', route)
        require(type(actual) is dict and actual.get('id') == node and 'error' not in actual
                and not any(k in actual for k in ('next_page', 'paging', 'pagination')))
        # A name match is only a candidate, never proof of this write or relationship.
        report['reconciliation']['checked'].append({'id': node,
            'name_match': name(actual) in expected, 'name_locales': locale_keys(actual)})


def run(env, progress):
    def stage(name):
        require(name in STAGES)
        progress['stage'] = name
    stage('setup')
    require(env.get('DIAGNOSTIC_CONFIRM') == 'READ_ONLY_NO_CREATE')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == 'reihlinstinct/geni-uploader'
            and env.get('GITHUB_REF') == 'refs/heads/master'
            and env.get('GITHUB_ACTOR') == 'reihlinstinct'
            and env.get('GITHUB_TRIGGERING_ACTOR') == 'reihlinstinct')
    raw = env.get('DIAGNOSTIC_CONFIG_JSON', '').encode()
    c = configuration(decode(raw))
    require(c['mode'] == env.get('DIAGNOSTIC_MODE', 'get_only_diagnostic'))
    require(env.get('DIAGNOSTIC_CONFIG_SHA256') == sha(raw)
            and env.get('DIAGNOSTIC_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    stage('encryption')
    encrypt(c['recipient'], b'diagnostic preflight')
    output = Path(env['DIAGNOSTIC_OUTPUT_DIR'])
    require(output.is_absolute() and not output.exists())
    output.mkdir(mode=0o700)
    save_count = 0
    def save(report):
        nonlocal save_count
        report = dict(report, executor_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'],
                      recorded_at=int(time.time()))
        ciphertext = encrypt(c['recipient'], canonical(report))
        filename = ('diagnostic-' + str(save_count) + '.age'
                    if c['mode'] == 'get_only_verify' else 'diagnostic.age')
        save_count += 1
        fd = os.open(output / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(ciphertext)
            f.flush()
            os.fsync(f.fileno())
    prefix, source, vendor_routes = routes(c)
    try:
        stage('github_credential')
        require(type(env.get('FAMILY_TREE_PAT')) is str and re.fullmatch(
            r'[A-Za-z0-9._~-]{8,4096}', env['FAMILY_TREE_PAT']))
        github = GetOnly('api.github.com', env.get('FAMILY_TREE_PAT', ''), [prefix, source])
        stage('secondary_credential')
        require(type(env.get('GENI_SECONDARY_ACCESS_TOKEN')) is str and re.fullmatch(
            r'[A-Za-z0-9._~-]{8,4096}', env['GENI_SECONDARY_ACCESS_TOKEN']))
        vendor = GetOnly('www.geni.com', env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), vendor_routes)
        report = diagnose(c, github, vendor, save)
        stage(report['stage'])
        return report['phase'] == 'READ_ONLY_COMPLETE'
    except ERRORS as exc:
        save({'schema': 1, 'mode': c['mode'], 'phase': 'STOPPED',
              'stage': progress['stage'], 'create_enabled': False,
              'failure_code': exc.code if isinstance(exc, TransportStop) else 'validation_or_setup',
              **({'http_failure': exc.evidence} if isinstance(exc, TransportStop)
                 and exc.evidence else {})})
        raise


def main():
    progress = {'stage': 'setup'}
    try:
        ok = run(os.environ, progress)
        print('GET-only diagnostic stage=' + progress['stage'] + '; encrypted evidence; no creation')
        return 0 if ok else 1
    except ERRORS:
        print('GET-only diagnostic stopped at ' + progress['stage'] + '; no creation or retry')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
