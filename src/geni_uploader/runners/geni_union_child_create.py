"""Separate protected entry point. No effects until exact private config/source admission."""
import copy
import os
import re
import time
from pathlib import Path

import geni_uploader.core.geni_union_child_model as core
from geni_uploader.client.probe import encrypt
from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.one_time_parent_pilot import (
    FIELDS,
    HTTPS,
    PrivateGit,
    canonical,
    configuration,
    decode,
    sha,
)
from geni_uploader.runners.protected_family_additions import IO as BaseIO
from geni_uploader.runners.protected_family_additions import Store, setup_failure

FIELDS = FIELDS + ',about_me,claimed'


class ScopedVendor(HTTPS):
    """Exact fixed routes. One consumed send per entry, proof latch before next."""
    def __init__(self, token, value):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = core.plan(value)
        self.profiles = {'profile', *value['profiles']}
        self.families = {value['anchor']}
        self.unions = set(value['family'])
        self.post_count = 0
        self.pending = False
        self.created = []
        self.graph = copy.deepcopy(value['family'])
        self.target = value['target_union']
        # Exact model request budget: initial identity/profiles/family/unions,
        # then family+union+POST+profile+anchor+reciprocal+union per entry.
        self.budget = 2 + len(value['profiles']) + len(value['family']) + 7 * len(value['entries'])

    def admit_vendor(self, method, route):
        c = self.plan
        require(self.calls < self.budget and time.time() < c['expires_at'])
        if method == 'GET':
            allowed = {'/api/' + x + '?fields=' + FIELDS + '&only_ids=true' for x in self.profiles}
            allowed |= {'/api/' + x + '?fields=id,partners,children,status&only_ids=true' for x in self.unions}
            allowed |= {'/api/' + x + '/immediate-family?only_ids=true' for x in self.families}
            require(route in allowed)
        else:
            require(method == 'POST' and route == '/api/' + c['target_union'] + '/add-child')
            require(not self.pending and self.post_count < len(c['entries']))
            self.pending = True
            self.post_count += 1
        self.calls += 1  # consume admission before possible timeout/wait/transport
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < c['expires_at'])
        self.last = time.monotonic()


class IO(BaseIO):
    def __init__(self, client, *, debug=False, evidence=None):
        super().__init__(client, debug=debug)
        self.proofs = {}
        self.evidence = evidence

    def get_profile(self, target):
        actual = self.request('GET', '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')
        if self.client.pending and target in self.client.created:
            self.proofs['profile'] = copy.deepcopy(actual)
        return actual

    def get_family(self, target):
        c = self.client
        actual = super().get_family(target)
        if self.evidence is not None:
            self.evidence({'phase': 'OBSERVED_BEFORE_PROOF', 'stage': 'family_raw',
                           'target': target, 'value': copy.deepcopy(actual), 'retry_allowed': False})
        if c.pending and c.created:
            if target == c.plan['anchor']:
                graph = copy.deepcopy(c.graph)
                created = c.created[-1]
                if c.plan['mode'] == 'partner':
                    require(type(actual) is dict and type(actual.get('nodes')) is dict
                            and len(actual['nodes']) <= 30)
                    added = {n for n in actual['nodes'] if re.fullmatch(r'union-[0-9]{1,30}', n)} - set(graph)
                    require(len(added) == 1)
                    c.target = next(iter(added))
                    graph[c.target] = {target: 'partner', created: 'partner'}
                else:
                    graph[c.target][created] = 'child'
                try:
                    core.shared.graph_check(actual, target, graph, external_edges=c.plan['external_edges'])
                except Blocked:
                    if self.evidence is not None:
                        nodes = actual.get('nodes') if type(actual) is dict else None
                        expected = set(graph) | {n for members in graph.values() for n in members}
                        self.evidence({'phase': 'STOPPED', 'stage': 'anchor_graph_proof',
                            'failure': 'exact_graph_mismatch', 'retry_allowed': False,
                            'node_set_equal': type(nodes) is dict and set(nodes) == expected,
                            'expected_graph': copy.deepcopy(graph),
                            'expected_external_edges': copy.deepcopy(c.plan['external_edges'])})
                    raise
                c.unions.add(c.target)  # only after exact anchor graph validated
                self.proofs['graph'] = graph
                self.proofs['anchor'] = copy.deepcopy(actual)
            elif target == c.created[-1]:
                self.proofs['reciprocal'] = copy.deepcopy(actual)
        return actual

    def get_union(self, target):
        actual = self.request('GET', '/api/' + target + '?fields=id,partners,children,status&only_ids=true')
        if self.client.pending:
            self.proofs['union'] = copy.deepcopy(actual)
        return actual

    def add(self, anchor, mode, body):
        c = self.client
        require(not c.pending and c.post_count < len(c.plan['entries'])
                and anchor == c.plan['anchor'] and mode == c.plan['mode'])
        expected = c.plan['entries'][c.post_count]['payload']
        require(body == core.vendor_payload(expected))
        self.proofs = {}
        # Consume transport latch before send; save decoded ACK before any ID/body
        # interpretation. A union-shaped ACK is evidence, never a new-ID source.
        require(self.evidence is not None)
        actual = self.request('POST', '/api/' + c.plan['target_union'] + '/add-child', body)
        self.evidence({'phase': 'ACK_RAW_UNINTERPRETED', 'stage': 'ack_raw',
                       'value': copy.deepcopy(actual), 'retry_allowed': False})
        require(type(actual) is dict and 'error' not in actual)
        target = actual.get('id')
        profile_id(target)
        require(target not in c.profiles)
        c.created.append(target)
        c.profiles.add(target)
        c.families.add(target)
        return actual

    def verified(self, created, target, graph):
        c = self.client
        require(c.pending and c.created[-1] == created and c.target == target
                and self.proofs.get('graph') == graph)
        core.profile_check(self.proofs['profile'], c.plan['entries'][c.post_count - 1]['payload'],
                           created, c.plan['allow_unknown_merge'], created=True)
        core.shared.graph_check(self.proofs['anchor'], c.plan['anchor'], graph,
                                external_edges=c.plan['external_edges'])
        boundary = core.shared.boundary_edges(c.plan, target, graph[target])
        core.shared.graph_check(self.proofs['reciprocal'], created, {target: graph[target]},
                                external_edges=boundary)
        core.union_check(self.proofs['union'], target, graph[target],
                         c.plan['accept_omitted_union_fields'])
        c.graph = copy.deepcopy(graph)
        c.pending = False


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'anchor', 'target_union', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('plan_sha256', 'anchor', 'target_union')}
    profile_id(value['anchor'])
    require(value['target_union'] is None or core.shared.union_id(value['target_union']) is None)
    configuration(base)
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    debug = env.get('UNION_CHILD_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('UNION_CHILD_CONFIRM') == 'CREATE_ONE_UNION_CHILD')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('UNION_CHILD_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('UNION_CHILD_CONFIG_SHA256') == sha(raw)
            and env.get('UNION_CHILD_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'household create encryption preflight')
    out = Path(env['UNION_CHILD_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='geni_union_child_experiment', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('UNION_CHILD_TREE_PAT', ''), github=True,
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
                    ('owner', 'anchor', 'target_union', 'expect_name', 'allow_unknown_merge', 'expires_at')))
        stage = 'vendor_credential'
        vendor = ScopedVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved)
        stage = 'execute_or_storage'
        report = core.execute(approved, IO(vendor, debug=debug in ('1', 'true'), evidence=save), Store(private), save, time.time)
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
    print('single union child verification complete; encrypted evidence retained; no retry' if ok else
          'single union child stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
