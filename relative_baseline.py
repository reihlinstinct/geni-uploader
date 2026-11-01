"""Separately gated, read-only pinned relative baseline. No create or traversal."""
import copy
import os
import re
import time
from pathlib import Path

import bounded_parent_addition as core
from geni_uploader.core.people import Blocked, exact, require
from one_time_parent_pilot import FIELDS, HTTPS, PrivateGit, TransportStop, canonical, decode, sha
from parent_probe import encrypt
from pilot_get_diagnostics import GetOnly, configuration
from protected_family_additions import read_error_structure, setup_failure


def plan(value):
    exact(value, ('schema', 'kind', 'owner', 'anchor', 'expect_name', 'profiles', 'family',
                  'external_edges', 'allow_unknown_merge', 'expires_at'))
    require(type(value['schema']) is int and value['schema'] == 1
            and value['kind'] == 'read_only_relative_baseline')
    core.profile_id(value['owner'])
    core.profile_id(value['anchor'])
    require(value['owner'] != value['anchor'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['allow_unknown_merge']) is bool)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    family = core.graph_spec(value['family'])
    profiles = value['profiles']
    require(type(profiles) is dict and 2 <= len(profiles) <= 12
            and set(profiles) == {p for m in family.values() for p in m})
    require(value['owner'] in profiles and value['anchor'] in profiles)
    require(sum(m.get(value['owner']) == 'child' and m.get(value['anchor']) == 'partner'
                for m in family.values()) == 1)
    for target, body in profiles.items():
        core.profile_id(target)
        core.existing_payload(body)
    boundary = value['external_edges']
    require(type(boundary) is dict and set(boundary) <= set(profiles))
    for target, edges in boundary.items():
        require(type(edges) is dict and 1 <= len(edges) <= 2)
        for union, role in edges.items():
            core.union_id(union)
            require(union not in family and role in ('partner', 'child'))
    return copy.deepcopy(value)


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'anchor',
                  'expect_name', 'recipient', 'allow_unknown_merge', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('anchor', 'plan_sha256')}
    configuration(dict(base, mode='get_only_diagnostic'))
    core.profile_id(value['anchor'])
    require(value['anchor'] != value['owner'])
    require(type(value['plan_sha256']) is str
            and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return copy.deepcopy(value)


def routes(approved):
    return {'/api/' + p + '?fields=' + FIELDS + '&only_ids=true'
            for p in {'profile', *approved['profiles']}} | {
                '/api/' + approved['anchor'] + '/immediate-family?only_ids=true'} | {
                    '/api/' + u + '?only_ids=true' for u in approved['family']}


class ReadOnlyVendor(HTTPS):
    def __init__(self, token, approved):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = plan(approved)
        self.routes = routes(self.plan)
        require(len(self.routes) <= 16)
        self.seen = set()

    def admit_vendor(self, method, route):
        require(method == 'GET' and route in self.routes and route not in self.seen
                and self.calls < len(self.routes) and time.time() < self.plan['expires_at'])
        self.seen.add(route)  # consumed before any wait or possible transport failure
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.plan['expires_at'])
        self.calls += 1
        self.last = time.monotonic()


def observe(approved, client, save, clock):
    c = plan(approved)
    result = {'phase': 'STOPPED', 'stage': 'identity', 'create_enabled': False,
              'retry_allowed': False, 'responses': []}

    def read(kind, target, route):
        require(clock() < c['expires_at'])
        result['stage'] = 'read_' + kind
        value = client.request('GET', route)
        require(len(canonical(value)) <= 262144)
        result['responses'].append({'kind': kind, 'target': target, 'value': value})
        save(copy.deepcopy(result))
        return value

    try:
        owner = read('profile', 'profile', '/api/profile?fields=' + FIELDS + '&only_ids=true')
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        core.profile_check(owner, c['profiles'][c['owner']], c['owner'], c['allow_unknown_merge'])
        for target, expected in c['profiles'].items():
            actual = owner if target == c['owner'] else read(
                'profile', target, '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')
            core.profile_check(actual, expected, target, c['allow_unknown_merge'])
        family = read('family', c['anchor'], '/api/' + c['anchor'] + '/immediate-family?only_ids=true')
        core.graph_check(family, c['anchor'], c['family'], external_edges=c['external_edges'])
        for union, members in c['family'].items():
            core.direct_union_check(read('union', union, '/api/' + union + '?only_ids=true'),
                                    union, members)
        require(clock() < c['expires_at'])
        result.update(phase='READ_ONLY_BASELINE_VERIFIED', stage='complete')
        save(copy.deepcopy(result))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        result['failure_code'] = exc.code if isinstance(exc, TransportStop) else 'validation_or_storage'
        if isinstance(exc, TransportStop):
            evidence = read_error_structure(exc.evidence)
            status = exc.evidence.get('http_status')
            if type(status) is int and 100 <= status <= 599:
                evidence['http_status'] = status
            for key in ('location_present', 'link_present'):
                if type(exc.evidence.get(key)) is bool:
                    evidence[key] = exc.evidence[key]
            result['http_failure'] = evidence
        save(copy.deepcopy(result))
    return result


def run(env):
    require(env.get('BASELINE_CONFIRM') == 'READ_ONLY_RELATIVE_BASELINE')
    for key, expected in (('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                          ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'),
                          ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_ACTOR', 'reihlinstinct'),
                          ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct')):
        require(env.get(key) == expected)
    raw = env.get('BASELINE_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('BASELINE_CONFIG_SHA256') == sha(raw)
            and env.get('BASELINE_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'read-only baseline encryption preflight')
    out = Path(env['BASELINE_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(result):
        nonlocal snapshots
        report = dict(copy.deepcopy(result), mode='read_only_relative_baseline',
                      executor_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'],
                      recorded_at=int(time.time()), production_enabled=False)
        cipher = encrypt(c['recipient'], canonical(report))
        fd = os.open(out / ('evidence-' + str(snapshots) + '.age'),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        snapshots += 1
        with os.fdopen(fd, 'wb') as f:
            f.write(cipher)
            f.flush()
            os.fsync(f.fileno())

    stage = 'private_source'
    try:
        prefix = '/repos/' + c['data_repo']
        import urllib.parse
        source = prefix + '/contents/' + urllib.parse.quote(c['data_path'], safe='/') + '?ref=' + c['data_sha']
        github = GetOnly('api.github.com', env.get('BASELINE_TREE_PAT', ''), [prefix, source])
        approved = PrivateGit(github, c['data_repo'], c['data_sha'], c['owner']).load(c['data_path'])
        stage = 'plan_hash'
        require(sha(canonical(approved)) == c['plan_sha256'])
        approved = plan(approved)
        stage = 'plan_config_consistency'
        require(all(approved[k] == c[k] for k in
                    ('owner', 'anchor', 'expect_name', 'allow_unknown_merge', 'expires_at')))
        require(time.time() < c['expires_at'])
        stage = 'vendor_reads'
        vendor = ReadOnlyVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved)
        return observe(approved, vendor, save, time.time)['phase'] == 'READ_ONLY_BASELINE_VERIFIED'
    except Exception as exc:  # noqa: BLE001 - terminal boundary, no external text
        save({'phase': 'STOPPED', 'retry_allowed': False, 'create_enabled': False,
              'stage': 'setup_or_storage', 'failure': setup_failure(stage, exc)})
        return False


def main():
    try:
        ok = run(os.environ)
    except Exception:  # noqa: BLE001 - fixed log, never external text
        ok = False
    print('read-only baseline complete; encrypted evidence retained' if ok else
          'read-only baseline stopped; inspect encrypted evidence; no retry')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
