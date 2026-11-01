"""Separate protected entry point. No effects until exact private config/source admission."""
import copy
import os
import re
import time
from pathlib import Path

import bounded_parent_addition as core
from geni_uploader.core.people import Blocked, exact, require  # noqa: F401 - public boundary type
from one_time_parent_pilot import (
    FIELDS,
    HTTPS,
    PrivateGit,
    canonical,
    decode,
    sha,
)
from parent_probe import encrypt
from protected_family_additions import setup_failure
from protected_parent_addition import config as parent_config


class ReadOnlyVendor(HTTPS):
    """A fixed plan/config-derived GET allowlist; no mutation route is ever admitted."""
    def __init__(self, token, approved, created, union):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.expires = approved['expires_at']
        self.routes = {'/api/' + x + '?fields=' + FIELDS + '&only_ids=true'
                       for x in {'profile', *approved['profiles'], created}}
        self.routes |= {'/api/' + x + '/immediate-family?only_ids=true'
                        for x in (approved['anchor'], created)}
        self.routes.add('/api/' + union + '?only_ids=true')
        self.seen = set()

    def admit_vendor(self, method, route):
        require(method == 'GET' and route in self.routes and route not in self.seen
                and self.calls < 20 and time.time() < self.expires)
        self.seen.add(route)
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.expires)
        self.calls += 1
        self.last = time.monotonic()


class ReadOnlyIO:
    def __init__(self, client):
        self.client = client

    def get_profile(self, target):
        return self.client.request('GET', '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')

    def get_family(self, target):
        return self.client.request('GET', '/api/' + target + '/immediate-family?only_ids=true')

    def get_union(self, target):
        return self.client.request('GET', '/api/' + target + '?only_ids=true')


def reconcile(c, io, created, target, save, clock):
    r = {'phase': 'STOPPED', 'retry_allowed': False, 'create_enabled': False,
         'responses': [], 'stage': 'preflight', 'created_id': created, 'union_id': target}

    def read(kind, node):
        require(clock() < c['expires_at'])
        r['stage'] = 'read_' + kind
        actual = getattr(io, 'get_' + kind)(node)
        r['responses'].append({'kind': kind, 'target': node, 'value': actual})
        save(copy.deepcopy(r))
        return actual
    try:
        owner = read('profile', 'profile')
        name = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in name.casefold().split() for w in c['expect_name'].split()))
        for node, body in c['profiles'].items():
            actual = owner if node == c['owner'] else read('profile', node)
            core.profile_check(actual, body, node, c['allow_unknown_merge'])
        core.profile_check(read('profile', created), c['entry']['payload'], created,
                           c['allow_unknown_merge'], new_parent=True)
        union, members = core.parent_union_after(read('family', c['anchor']), c, created)
        require(union == target)
        core.graph_check(read('family', created), created, {target: members},
                         external_edges=core.boundary_edges(c, target, members))
        core.direct_union_check(read('union', target), target, members)
        require(clock() < c['expires_at'])
        r.update(phase='READ_ONLY_VERIFIED', stage='complete')
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        save(copy.deepcopy(r))
    return r


def config(value):
    require(type(value) is dict)
    base = {k: v for k, v in value.items() if k not in ('created_id', 'union_id')}
    parent_config(base)
    require(set(value) == set(base) | {'created_id', 'union_id'})
    core.profile_id(value['created_id'])
    core.union_id(value['union_id'])
    require(value['created_id'] not in (value['owner'], value['anchor']))
    return value


def run(env):
    debug = env.get('RECONCILE_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('RECONCILE_CONFIRM') == 'READ_ONLY_EXISTING_PARENT')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('RECONCILE_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('RECONCILE_CONFIG_SHA256') == sha(raw)
            and env.get('RECONCILE_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'parent encryption preflight')
    out = Path(env['RECONCILE_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='read_only_parent_reconciliation', production_enabled=False,
                      executor_sha=env['GITHUB_SHA'],
                      run_id=env['GITHUB_RUN_ID'], recorded_at=int(time.time()))
        cipher = encrypt(c['recipient'], canonical(report))
        fd = os.open(out / ('evidence-' + str(snapshots) + '.age'),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        snapshots += 1
        with os.fdopen(fd, 'wb') as f:
            f.write(cipher)
            f.flush()
            os.fsync(f.fileno())
        return cipher

    stage = 'github_credential'
    try:
        github = HTTPS('api.github.com', env.get('RECONCILE_TREE_PAT', ''), github=True,
                       capture_failure=True)
        stage = 'private_source'
        private = PrivateGit(github, c['data_repo'], c['data_sha'], c['owner'])
        approved = private.load(c['data_path'])
        stage = 'plan_hash'
        require(sha(canonical(approved)) == c['plan_sha256'])
        stage = 'plan_schema'
        approved = core.plan(approved)
        stage = 'plan_config_consistency'
        require(all(approved[key] == c[key] for key in
                    ('owner', 'anchor', 'expect_name', 'allow_unknown_merge', 'expires_at')))
        # Omission behavior for unknown life status is not established for live use.
        require(type(approved['entry']['payload']['is_alive']) is bool)
        require(c['created_id'] not in approved['profiles'])
        stage = 'consumed_ack_refs'
        marker = core.marker(approved)
        for suffix in ('', '-ack'):
            ref = private.get('/git/ref/tags/' + marker + suffix)
            obj = ref.get('object', {})
            if suffix == '':
                require(obj.get('sha') == c['data_sha'])
            else:
                tag_sha = obj.get('sha')
                require(type(tag_sha) is str and re.fullmatch(r'[a-f0-9]{40}', tag_sha))
                tag = private.get('/git/tags/' + tag_sha)
                require(tag.get('object', {}).get('sha') == c['data_sha']
                        and tag.get('tag') == marker + suffix)
        stage = 'vendor_credential'
        vendor = ReadOnlyVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved,
                                c['created_id'], c['union_id'])
        stage = 'reconcile'
        report = reconcile(approved, ReadOnlyIO(vendor), c['created_id'], c['union_id'], save, time.time)
        return report['phase'] == 'READ_ONLY_VERIFIED'
    except Exception as exc:  # noqa: BLE001 - terminal boundary, no external text
        save({'phase': 'STOPPED', 'retry_allowed': False, 'stage': 'setup_or_storage',
              'failure': setup_failure(stage, exc)})
        return False


def main():
    try:
        ok = run(os.environ)
    except Exception as exc:  # noqa: BLE001 - terminal boundary, no external text
        _ = type(exc)  # fixed log only
        ok = False
    print('existing parent read-only verification complete; encrypted evidence retained; no retry' if ok else
          'parent read-only verification stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
