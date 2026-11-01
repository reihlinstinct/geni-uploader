"""Separate protected entry point. No effects until exact private config/source admission."""
import copy
import os
import re
import time
from pathlib import Path

import bounded_relative_siblings as core
import protected_parent_addition as parent
from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require  # noqa: F401 - public boundary type
from one_time_parent_pilot import (
    FIELDS,
    HTTPS,
    PrivateGit,
    canonical,
    configuration,
    decode,
    sha,
)
from parent_probe import encrypt
from protected_family_additions import Store, setup_failure


class ScopedVendor(HTTPS):
    """Fixed approved sibling routes; finite reads, one send per approved entry."""
    def __init__(self, token, value):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = core.plan(value)
        self.profiles = {'profile', *value['profiles']}
        self.families = {value['anchor']}
        self.post_count = 0
        self.pending = False
        self.created = []

    def admit_vendor(self, method, route):
        c = self.plan
        require(self.calls < 40 and time.time() < c['expires_at'])
        if method == 'GET':
            allowed = {'/api/' + x + '?fields=' + FIELDS + '&only_ids=true' for x in self.profiles}
            allowed |= {'/api/' + c['parent_union'] + '?only_ids=true'}
            allowed |= {'/api/' + x + '/immediate-family?only_ids=true' for x in self.families}
            require(route in allowed)
        else:
            require(method == 'POST' and route == '/api/' + c['anchor'] + '/add-sibling')
            require(not self.pending and self.post_count < len(c['entries']))
            self.pending = True
            self.post_count += 1  # Consume before a possibly uncertain send.
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < c['expires_at'])
        self.calls += 1
        self.last = time.monotonic()


class IO(parent.IO):
    def __init__(self, client, *, debug=False):
        super().__init__(client, debug=debug)
        self.anchor_after = None
        self.reciprocal_after = None

    def expected_graph(self):
        graph = copy.deepcopy(self.client.plan['family'])
        for node in self.client.created:
            graph[self.client.plan['parent_union']][node] = 'child'
        return graph

    def get_family(self, target):
        c = self.client
        actual = self.request('GET', '/api/' + target + '/immediate-family?only_ids=true')
        if c.pending and c.created:
            if target == c.plan['anchor']:
                self.anchor_after = copy.deepcopy(actual)
            elif target == c.created[-1]:
                self.reciprocal_after = copy.deepcopy(actual)
        return actual

    def get_union(self, target):
        c = self.client
        require(target == c.plan['parent_union'])
        graph = self.expected_graph()
        if c.pending:
            require(c.created and self.anchor_after is not None and self.reciprocal_after is not None)
            core.parent.graph_check(self.anchor_after, c.plan['anchor'], graph)
            core.parent.graph_check(self.reciprocal_after, c.created[-1], {target: graph[target]},
                                    external_edges=core.parent.boundary_edges(c.plan, target, graph[target]))
        actual = self.request('GET', '/api/' + target + '?only_ids=true')
        core.parent.direct_union_check(actual, target, graph[target])
        if c.pending:
            c.pending = False
        return actual

    def add_sibling(self, anchor, body):
        c = self.client
        require(not c.pending and c.post_count < len(c.plan['entries']) and anchor == c.plan['anchor'])
        expected = c.plan['entries'][c.post_count]['payload']
        require(body == core.parent.vendor_parent_payload(expected))
        self.anchor_after = self.reciprocal_after = None
        actual = self.request('POST', '/api/' + anchor + '/add-sibling', body)
        require(type(actual) is dict and 'error' not in actual)
        target = actual.get('id')
        profile_id(target)
        require(target not in c.profiles)
        c.created.append(target)
        c.profiles.add(target)
        c.families.add(target)
        return actual


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'anchor', 'parent_union', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('plan_sha256', 'anchor', 'parent_union')}
    profile_id(value['anchor'])
    core.parent.union_id(value['parent_union'])
    require(value['anchor'] != value['owner'])
    configuration(base)
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    debug = env.get('RELATIVE_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('RELATIVE_CONFIRM') == 'CREATE_APPROVED_RELATIVE_SIBLINGS')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('RELATIVE_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('RELATIVE_CONFIG_SHA256') == sha(raw)
            and env.get('RELATIVE_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'relative sibling encryption preflight')
    out = Path(env['RELATIVE_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='protected_relative_siblings', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('RELATIVE_TREE_PAT', ''), github=True,
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
                    ('owner', 'anchor', 'parent_union', 'expect_name', 'allow_unknown_merge', 'expires_at')))
        stage = 'vendor_credential'
        vendor = ScopedVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved)
        stage = 'execute_or_storage'
        report = core.execute(approved, IO(vendor, debug=debug in ('1', 'true')), Store(private), save, time.time)
        return report['phase'] == 'VERIFIED'
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
    print('relative siblings verification complete; encrypted evidence retained; no retry' if ok else
          'relative siblings stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
