"""Separate protected entry point for title/gender/photo (#715). No effects until exact private config/source admission."""
import base64
import copy
import os
import re
import time
from pathlib import Path

import geni_uploader.runners.bounded_profile_tgp as core
import geni_uploader.runners.protected_parent_addition as parent
from geni_uploader.client.probe import encrypt
from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require  # noqa: F401 - public boundary type
from geni_uploader.runners.one_time_parent_pilot import (
    HTTPS,
    PrivateGit,
    canonical,
    configuration,
    decode,
    sha,
)
from geni_uploader.runners.protected_family_additions import Store, setup_failure

NAME_FIELDS = (parent.FIELDS + ',claimed,mugshot_urls')


class ScopedVendor(HTTPS):
    """Title/gender: three reads, one update, two readbacks. Photo: three reads, one upload, three readbacks."""
    def __init__(self, token, value, *, read_only):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.plan = core.plan(value)
        self.read_only = read_only
        self.post_count = 0
        target = value['target']
        fields = '?fields=' + NAME_FIELDS + '&only_ids=true'
        self.sequence = [('GET', '/api/profile' + fields),
                         ('GET', '/api/' + target + fields),
                         ('GET', '/api/' + target + '/immediate-family?only_ids=true')]
        if not read_only:
            if value['capability'] == 'photo':
                self.sequence += [('POST', '/api/' + target + '/add-photo'),
                                  ('GET', '/api/photo-PHOTO_ID'),
                                  self.sequence[1], self.sequence[2]]
            else:
                self.sequence += [('POST', '/api/' + target + '/update'),
                                  self.sequence[1], self.sequence[2]]

    def admit_vendor(self, method, route):
        require(self.calls < len(self.sequence) and time.time() < self.plan['expires_at'])
        expected_method, expected_route = self.sequence[self.calls]
        require(method == expected_method)
        if expected_route == '/api/photo-PHOTO_ID':
            require(re.fullmatch(r'/api/photo-[0-9]{1,30}', route))
        else:
            require(route == expected_route)
        if method == 'POST':
            require(not self.read_only and self.post_count == 0)
            self.post_count += 1
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.plan['expires_at'])
        self.calls += 1
        self.last = time.monotonic()


class IO(parent.IO):
    def get_profile(self, target):
        return self.request('GET', '/api/' + target + '?fields=' + NAME_FIELDS + '&only_ids=true')

    def get_family(self, target):
        require(target == self.client.plan['target'])
        return self.request('GET', '/api/' + target + '/immediate-family?only_ids=true')

    def get_photo(self, photo_id):
        return self.request('GET', '/api/' + photo_id)

    def update(self, target, body):
        require(target == self.client.plan['target'] and body == self.client.plan['set'])
        return self.request('POST', '/api/' + target + '/update', body)

    def add_photo(self, target, body):
        require(target == self.client.plan['target'] and body == self.client.plan['set'])
        require(self.image_b64 is not None)
        return self.request('POST', '/api/' + target + '/add-photo',
                            {'title': body['title'], 'file': self.image_b64})


class PhotoStore(Store):
    """Adds duplicate-hash blocking over VERIFIED photo receipts."""
    def photo_hashes(self, target):
        raise NotImplementedError  # wired to the private receipt ledger at admission

    def record_photo_hash(self, target, image_sha256):
        raise NotImplementedError  # recorded with the VERIFIED receipt


def config(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'target', 'expires_at', 'plan_sha256'))
    base = {k: v for k, v in value.items() if k not in ('plan_sha256', 'target')}
    base.update(allow_unknown_merge=False, accept_hidden_parent_risk=True,
                accept_private_create_risk=True)
    configuration(base)
    profile_id(value['target'])
    require(value['target'] != value['owner'])
    require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))
    return value


def run(env):
    debug = env.get('TGP_DEBUG')
    require(debug in ('1', 'true'))
    mode = env.get('TGP_MODE')
    require(mode in ('plan', 'update'))
    require(env.get('TGP_CONFIRM') == ('READ_ONLY_TGP' if mode == 'plan' else 'UPDATE_APPROVED_TGP'))
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('TGP_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('TGP_CONFIG_SHA256') == sha(raw)
            and env.get('TGP_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'profile tgp encryption preflight')
    out = Path(env['TGP_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='protected_profile_tgp', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('TGP_TREE_PAT', ''), github=True,
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
                    ('owner', 'target', 'expect_name', 'expires_at')))
        stage = 'vendor_credential'
        vendor = ScopedVendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), approved,
                              read_only=mode == 'plan')
        stage = 'execute_or_storage'
        io = IO(vendor, debug=debug in ('1', 'true'))
        io.image_b64 = None
        if approved['capability'] == 'photo':
            image = private.load(c['data_path'] + '.image')
            require(type(image) is dict and type(image.get('file_b64')) is str)
            require(sha(base64.b64decode(image['file_b64'])) == approved['image_sha256'])
            io.image_b64 = image['file_b64']
        report = core.execute(approved, io, PhotoStore(private), save, time.time,
                              read_only=mode == 'plan')
        return report['phase'] == ('READ_ONLY_TGP_VERIFIED' if mode == 'plan' else 'VERIFIED')
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
    print('profile tgp verification complete; encrypted evidence retained; no retry' if ok else
          'profile tgp stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
