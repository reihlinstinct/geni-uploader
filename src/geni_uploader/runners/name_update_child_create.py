"""Protected mixed-operation entrypoint. Existing name update must verify before create."""
import copy
import time

import geni_uploader.core.name_update_child_model as mixed
import geni_uploader.runners.geni_union_child_create as child_io
from geni_uploader.core.people import require


class ScopedVendor(child_io.ScopedVendor):
    def __init__(self, token, value):
        self.mixed = mixed.plan(value)
        super().__init__(token, self.mixed['create'])
        self.update_verified = False
        self.update_pending = False
        self.update_index = 0
        c = self.mixed
        profile = ('GET', '/api/' + c['target'] + '?fields=' + child_io.FIELDS + '&only_ids=true')
        anchor = ('GET', '/api/' + c['anchor'] + '/immediate-family?only_ids=true')
        reciprocal = ('GET', '/api/' + c['target'] + '/immediate-family?only_ids=true')
        union = ('GET', '/api/' + c['union'] + '?fields=id,partners,children,status&only_ids=true')
        self.update_sequence = [
            ('GET', '/api/profile?fields=' + child_io.FIELDS + '&only_ids=true'),
            profile, anchor, reciprocal, union,
            ('POST', '/api/' + c['target'] + '/update'), profile, anchor, reciprocal, union]
        self.budget += len(self.update_sequence)

    def admit_vendor(self, method, route):
        if self.update_verified:
            return super().admit_vendor(method, route)
        require(self.update_index < len(self.update_sequence)
                and (method, route) == self.update_sequence[self.update_index]
                and self.calls < self.budget and time.time() < self.mixed['expires_at'])
        if method == 'POST':
            require(not self.update_pending)
            self.update_pending = True
        self.update_index += 1; self.calls += 1  # consume before pacing/transport
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.mixed['expires_at'])
        self.last = time.monotonic()


class IO(child_io.IO):
    def __init__(self, client, *, debug=False, evidence=None):
        super().__init__(client, debug=debug, evidence=evidence)
        self.update_proofs = {}

    def get_profile(self, target):
        actual = super().get_profile(target)
        if self.client.update_pending and not self.client.update_verified:
            self.update_proofs['profile'] = copy.deepcopy(actual)
        return actual

    def get_family(self, target):
        actual = super().get_family(target)
        if self.client.update_pending and not self.client.update_verified:
            key = 'anchor' if target == self.client.mixed['anchor'] else 'reciprocal'
            self.update_proofs[key] = copy.deepcopy(actual)
        return actual

    def get_union(self, target):
        actual = super().get_union(target)
        if self.client.update_pending and not self.client.update_verified:
            self.update_proofs['union'] = copy.deepcopy(actual)
        return actual

    def update(self, target, body):
        c = self.client
        require(not c.update_pending and not c.update_verified
                and target == c.mixed['target'] and body == c.mixed['set']
                and self.evidence is not None)
        actual = self.request('POST', '/api/' + target + '/update', body)
        self.evidence({'phase': 'UPDATE_ACK_RAW', 'stage': 'update_ack_raw',
                       'value': copy.deepcopy(actual), 'retry_allowed': False})
        return actual

    def verified_update(self):
        c = self.client; p = self.update_proofs
        require(c.update_pending and not c.update_verified
                and c.update_index == len(c.update_sequence))
        mixed.proofs(c.mixed, p['profile'], p['anchor'], p['reciprocal'], p['union'], updated=True)
        c.update_verified = True

    def add(self, anchor, mode, body):
        require(self.client.update_verified)
        return super().add(anchor, mode, body)


# Reuse immutable config/source and encrypted storage mechanics, not effect authority.
import os
import re
from pathlib import Path

from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import exact
from geni_uploader.runners.one_time_parent_pilot import (
    HTTPS,
    PrivateGit,
    canonical,
    configuration,
    decode,
    sha,
)
from geni_uploader.runners.protected_family_additions import Store, setup_failure
from parent_probe import encrypt


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'anchor', 'target_union', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('plan_sha256', 'anchor', 'target_union')}
    profile_id(value['anchor'])
    require(value['target_union'] is None or mixed.child.shared.union_id(value['target_union']) is None)
    configuration(base)
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    debug = env.get('MIXED_CHILD_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('MIXED_CHILD_CONFIRM') == 'UPDATE_NAME_THEN_CREATE_CHILD')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('MIXED_CHILD_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('MIXED_CHILD_CONFIG_SHA256') == sha(raw)
            and env.get('MIXED_CHILD_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'household create encryption preflight')
    out = Path(env['MIXED_CHILD_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='name_update_then_child', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('MIXED_CHILD_TREE_PAT', ''), github=True,
                       capture_failure=True)
        stage = 'private_source'
        private = PrivateGit(github, c['data_repo'], c['data_sha'], c['owner'])
        approved = private.load(c['data_path'])
        stage = 'plan_hash'
        require(sha(canonical(approved)) == c['plan_sha256'])
        stage = 'plan_schema'
        approved = mixed.plan(approved)
        stage = 'plan_config_consistency'
        require(all(approved[key] == c[key] for key in
                    ('owner', 'anchor', 'expect_name', 'expires_at')))
        require(approved['union'] == c['target_union']
                and approved['create']['allow_unknown_merge'] == c['allow_unknown_merge'])
        stage = 'vendor_credential'
        vendor = ScopedVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved)
        stage = 'execute_or_storage'
        report = mixed.execute(approved, IO(vendor, debug=debug in ('1', 'true'), evidence=save), Store(private), save, time.time)
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
