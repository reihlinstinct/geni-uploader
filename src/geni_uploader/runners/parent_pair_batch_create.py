"""Protected entry point candidate. No live effect without exact approved package."""
import copy
import os
import re
import time
from pathlib import Path

from geni_uploader.client.probe import encrypt
from geni_uploader.core import bounded_parent_pair_batch as core
from geni_uploader.core.people import require
from geni_uploader.runners.one_time_parent_pilot import HTTPS, PrivateGit, canonical, decode, sha
from geni_uploader.runners.protected_family_additions import Store, setup_failure
from geni_uploader.runners.protected_parent_pair_batch import IO, ScopedVendor, admit_source, config


def run(env):
    debug = env.get('PAIR_DEBUG')
    require(debug in ('1', 'true'))
    require(env.get('PAIR_CONFIRM') == 'CREATE_APPROVED_PARENT_PAIR_BATCH')
    for key, expected in (
        ('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'), ('GITHUB_REF', 'refs/heads/master'),
        ('GITHUB_ACTOR', 'reihlinstinct'), ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'),
    ):
        require(env.get(key) == expected)
    raw = env.get('PAIR_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('PAIR_CONFIG_SHA256') == sha(raw)
            and env.get('PAIR_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < c['expires_at'])
    encrypt(c['recipient'], b'batch encryption preflight')
    out = Path(env['PAIR_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    snapshots = 0

    def save(report):
        nonlocal snapshots
        report = dict(copy.deepcopy(report), mode='protected_parent_pair_batch', production_enabled=True,
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
        github = HTTPS('api.github.com', env.get('PAIR_TREE_PAT', ''), github=True,
                       capture_failure=True)
        stage = 'private_source'
        private = PrivateGit(github, c['data_repo'], c['data_sha'], c['owner'])
        approved = admit_source(c, private)
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
    print('batch verification complete; encrypted evidence retained; no retry' if ok else
          'batch stopped; inspect encrypted evidence; no retry or automatic repair')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
