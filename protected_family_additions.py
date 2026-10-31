"""Separate protected entry point. No effects until exact private config/source admission."""
import copy
import os
import re
import time
from pathlib import Path

import guarded_family_additions as core
from geni_uploader.core.people import Blocked, exact, require
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


class ScopedVendor(HTTPS):
    """Old pilot admission is unchanged. Exact plan-bound routes and a finite budget."""
    def __init__(self, token, value):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = core.plan(value)
        self.profiles = {'profile', value['owner'], *(x['id'] for x in value['parents'])}
        self.families = set()
        self.post_count = 0
        self.unknown_send = False

    def admit_vendor(self, method, route):
        c = self.plan
        require(self.calls < 40 and time.time() < c['expires_at'])
        if method == 'GET':
            allowed = {'/api/' + x + '?fields=' + FIELDS + '&only_ids=true' for x in self.profiles}
            allowed |= {'/api/' + c['union_id'] + '?only_ids=true'}
            allowed |= {'/api/' + x + '/immediate-family?only_ids=true' for x in self.families}
            require(route in allowed)
        else:
            operation = 'add-parent' if c['mode'] == 'mother' else 'add-sibling'
            require(method == 'POST' and route == '/api/' + c['owner'] + '/' + operation)
            require(not self.unknown_send and self.post_count < len(c['entries']))
            self.unknown_send = True
            self.post_count += 1
        if self.last is not None:
            time.sleep(max(0, 10 - (time.monotonic() - self.last)))
        self.calls += 1
        self.last = time.monotonic()


class IO:
    def __init__(self, client):
        self.client = client

    def request(self, method, route, body=None):
        try:
            return self.client.request(method, route, body)
        except TransportStop as exc:
            status = exc.evidence.get('http_status')
            evidence = {'host': 'www.geni.com', 'error_type': exc.code}
            if type(status) is int and 100 <= status <= 599:
                evidence['status_class'] = str(status // 100) + 'xx'
            raise TransportStop(exc.code, evidence=evidence) from None
        except Exception as exc:
            raise TransportStop('transport_unavailable', evidence={
                'host': 'www.geni.com', 'error_type': 'seam_failure'}) from exc

    def get_profile(self, target):
        return self.request('GET', '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')

    def get_union(self, target):
        return self.request('GET', '/api/' + target + '?only_ids=true')

    def get_family(self, target):
        return self.request('GET', '/api/' + target + '/immediate-family?only_ids=true')

    def add(self, owner, operation, body):
        c = self.client.plan
        index = self.client.post_count
        require(index < len(c['entries']) and owner == c['owner'])
        require(body == core.vendor_payload(c['entries'][index]['payload']))
        actual = self.request('POST', '/api/' + owner + '/' + operation, body)
        require(type(actual) is dict and 'error' not in actual)
        target = actual.get('id')
        core.profile_id(target)
        require(target not in self.client.profiles)
        self.client.profiles.add(target)
        self.client.families.add(target)
        self.client.unknown_send = False
        return actual


class Store:
    def __init__(self, private):
        self.private = private

    def consume(self, marker):
        self.private.marker = marker
        try:
            self.private.consume()
        except Exception as exc:
            raise Blocked() from exc

    def receipt(self, marker, stage, ciphertext):
        self.private.marker = marker
        try:
            self.private.receipt(stage, ciphertext)
        except Exception as exc:
            raise Blocked() from exc


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k != 'plan_sha256'}
    configuration(base)
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    require(env.get('FAMILY_CONFIRM') == 'CREATE_APPROVED_FAMILY_ADDITIONS')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('FAMILY_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('FAMILY_CONFIG_SHA256') == sha(raw)
            and env.get('FAMILY_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'family encryption preflight')
    out = Path(env['FAMILY_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), executor_sha=env['GITHUB_SHA'],
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

    try:
        github = HTTPS('api.github.com', env.get('FAMILY_TREE_PAT', ''), github=True,
                       capture_failure=True)
        private = PrivateGit(github, c['data_repo'], c['data_sha'], c['owner'])
        approved = private.load(c['data_path'])
        require(sha(canonical(approved)) == c['plan_sha256'])
        approved = core.plan(approved)
        require(all(approved[key] == c[key] for key in
                    ('owner', 'expect_name', 'allow_unknown_merge', 'expires_at')))
        vendor = ScopedVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved)
        report = core.execute(approved, IO(vendor), Store(private), save)
        return report['phase'] == 'VERIFIED'
    except Exception as exc:  # noqa: BLE001 - terminal boundary, no external text
        _ = type(exc)  # never print external exception contents
        save({'phase': 'STOPPED', 'retry_allowed': False, 'stage': 'setup_or_storage'})
        return False


def main():
    try:
        ok = run(os.environ)
    except Exception as exc:  # noqa: BLE001 - terminal boundary, no external text
        _ = type(exc)  # fixed log only
        ok = False
    print('family verification complete; encrypted evidence retained; no retry' if ok else
          'family stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
