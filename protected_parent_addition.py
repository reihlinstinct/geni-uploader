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
    TransportStop,
    canonical,
    configuration,
    decode,
    sha,
)
from parent_probe import encrypt
from protected_family_additions import Store, read_error_structure, setup_failure


class ScopedVendor(HTTPS):
    """Old pilot admission is unchanged. Exact plan-bound routes and a finite budget."""
    def __init__(self, token, value):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = core.plan(value)
        self.profiles = {'profile', *value['profiles']}
        self.families = {value['anchor']}
        self.unions = set()  # No union read until the post-create graph is validated.
        self.created = None
        self.post_count = 0
        self.unknown_send = False

    def admit_vendor(self, method, route):
        c = self.plan
        require(self.calls < 24 and time.time() < c['expires_at'])
        if method == 'GET':
            allowed = {'/api/' + x + '?fields=' + FIELDS + '&only_ids=true' for x in self.profiles}
            allowed |= {'/api/' + x + '?only_ids=true' for x in self.unions}
            allowed |= {'/api/' + x + '/immediate-family?only_ids=true' for x in self.families}
            require(route in allowed)
        else:
            require(method == 'POST' and route == '/api/' + c['anchor'] + '/add-parent')
            require(not self.unknown_send and self.post_count == 0)
            self.unknown_send = True
            self.post_count += 1
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < c['expires_at'])
        self.calls += 1
        self.last = time.monotonic()


class IO:
    def __init__(self, client, *, debug=False):
        require(type(debug) is bool)
        self.client, self.debug = client, debug
        self.anchor_after = None

    def request(self, method, route, body=None):
        try:
            return self.client.request(method, route, body)
        except TransportStop as exc:
            status = exc.evidence.get('http_status')
            evidence = {'host': 'www.geni.com', 'error_type': exc.code}
            if type(status) is int and 100 <= status <= 599:
                evidence['status_class'] = str(status // 100) + 'xx'
                if method == 'GET':
                    evidence['http_status'] = status
            if self.debug and method == 'GET':
                evidence['debug'] = read_error_structure(exc.evidence)
            raise TransportStop(exc.code, evidence=evidence) from None
        except Exception as exc:
            raise TransportStop('transport_unavailable', evidence={
                'host': 'www.geni.com', 'error_type': 'seam_failure'}) from exc

    def get_profile(self, target):
        return self.request('GET', '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')

    def get_union(self, target):
        c = self.client
        require(c.created is not None and self.anchor_after is not None)
        validated, _ = core.parent_union_after(self.anchor_after, c.plan, c.created)
        require(target == validated)
        c.unions.add(validated)
        return self.request('GET', '/api/' + target + '?only_ids=true')

    def get_family(self, target):
        actual = self.request('GET', '/api/' + target + '/immediate-family?only_ids=true')
        if target == self.client.plan['anchor'] and self.client.created is not None:
            self.anchor_after = copy.deepcopy(actual)
        return actual

    def add_parent(self, anchor, body):
        c = self.client
        require(c.post_count == 0 and anchor == c.plan['anchor'])
        require(body == core.vendor_parent_payload(c.plan['entry']['payload']))
        actual = self.request('POST', '/api/' + anchor + '/add-parent', body)
        require(type(actual) is dict and 'error' not in actual)
        target = actual.get('id')
        core.profile_id(target)
        require(target not in c.profiles)
        c.created = target
        c.profiles.add(target)
        c.families.add(target)
        return actual


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'anchor', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('plan_sha256', 'anchor')}
    core.profile_id(value['anchor'])
    require(value['anchor'] != value['owner'])
    configuration(base)
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    debug = env.get('PARENT_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('PARENT_CONFIRM') == 'CREATE_APPROVED_ONE_PARENT')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('PARENT_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('PARENT_CONFIG_SHA256') == sha(raw)
            and env.get('PARENT_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'parent encryption preflight')
    out = Path(env['PARENT_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='protected_one_parent', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('PARENT_TREE_PAT', ''), github=True,
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
    print('parent verification complete; encrypted evidence retained; no retry' if ok else
          'parent stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
