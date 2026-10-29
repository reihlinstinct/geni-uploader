"""Offline deterministic package builder. Never installs or dispatches a workflow."""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path


def _need(value):
    if not value:
        raise ValueError('father release package blocked')


def _exact(value, keys):
    _need(type(value) is dict and set(value) == set(keys))


def _hex(value, length):
    _need(type(value) is str and re.fullmatch(rf'[a-f0-9]{{{length}}}', value))


def validate_manifest(m, source_sha):
    _exact(m, ['schema_version', 'phase', 'source_sha', 'free_only', 'max_cost_usd',
               'activate_workflows', 'dispatch', 'geni_calls', 'service', 'issuer', 'actions'])
    _need(type(m['schema_version']) is int and m['schema_version'] == 1 and m['source_sha'] == source_sha)
    _need(m['free_only'] is True and type(m['max_cost_usd']) is int and m['max_cost_usd'] == 0)
    _need(m['activate_workflows'] is False and m['dispatch'] is False and type(m['geni_calls']) is int and m['geni_calls'] == 0)
    _need(m['phase'] in ['closed_provisioning', 'verified_release_candidate'])
    s, i = m['service'], m['issuer']
    _exact(s, ['new_worker_name', 'new_namespace_class', 'namespace_id', 'bundle_sha256'])
    _need(type(s['new_worker_name']) is str and
          re.fullmatch(r'[a-z][a-z0-9-]{2,62}', s['new_worker_name']))
    _need(s['new_namespace_class'] == 'FatherOwnerIntent')
    _hex(s['bundle_sha256'], 64)
    _exact(i, ['private_repository', 'repository_id', 'workflow_path', 'workflow_sha',
               'key_purpose', 'key_id', 'public_spki_base64', 'key_creation'])
    _need(type(i['private_repository']) is str and
          re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', i['private_repository']))
    _need(i['workflow_path'] == '.github/workflows/father-release-issuer.yml')
    _hex(i['workflow_sha'], 40)
    _need(i['key_purpose'] == 'exclusive_exact_father_policy')
    if m['phase'] == 'closed_provisioning':
        _need(s['namespace_id'] is None and i['repository_id'] is None and
              i['key_id'] is None and i['public_spki_base64'] is None)
        _need(i['key_creation'] == 'generate_ed25519_into_private_secret_after_approval')
        _need(m['actions'] == ['create_closed_worker', 'create_new_sqlite_namespace',
                               'create_private_issuer_repository', 'generate_exclusive_key'])
    else:
        import base64
        _hex(s['namespace_id'], 32)
        _need(type(i['repository_id']) is str and
              re.fullmatch(r'[1-9][0-9]{0,19}', i['repository_id']))
        _need(i['key_creation'] == 'already_provisioned_verified')
        _hex(i['key_id'], 64)
        _need(type(i['public_spki_base64']) is str)
        der = base64.b64decode(i['public_spki_base64'], validate=True)
        _need(len(der) == 44 and der[:12] == bytes.fromhex('302a300506032b6570032100'))
        _need(base64.b64encode(der).decode() == i['public_spki_base64'])
        _need(hashlib.sha256(der).hexdigest() == i['key_id'])
        _need(m['actions'] == ['inspect_verified_release_candidate'])


def package_release(root: Path, manifest: dict, output: Path, worker_bundle: Path):
    """Create one exclusive local tar. Manifest consistency is NOT user authority."""
    root = root.resolve()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    _hex(head, 40)
    validate_manifest(manifest, head)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).split(b'\0')
    paths = []
    for raw in tracked:
        if not raw:
            continue
        path = raw.decode()
        p = Path(path)
        selected = (len(p.parts) == 1 and p.suffix == '.py') or (
            len(p.parts) >= 3 and p.parts[:2] == ('src', 'geni_uploader') and
            p.suffix == '.py') or path in [
            'pyproject.toml', 'oauth-bootstrap/package.json', 'oauth-bootstrap/package-lock.json',
            'docs/father-run-workflow-draft.yml'] or (
            len(p.parts) == 2 and p.parts[0] == 'oauth-bootstrap' and p.suffix == '.mjs' and
            not p.name.startswith('ZZ-') and not p.name.endswith('.test.mjs') and
            p.name not in ['test.mjs', 'runtime.test.mjs', 'runtime-fixture.mjs'])
        if selected:
            _need(not p.is_absolute() and '..' not in p.parts)
            f = root / p
            _need(not any(part.is_symlink() for part in [f, *f.parents] if part != root)
                  and f.is_file() and f.stat().st_size <= 2097152)
            paths.append(path)
    _need(all(p in paths for p in ['oauth-bootstrap/father-intent-service.mjs',
          'oauth-bootstrap/private-release-issuer.mjs', 'oauth-bootstrap/no-write-workload-probe-cli.mjs',
          'oauth-bootstrap/protected-job-cli.mjs', 'oauth-bootstrap/package-lock.json']))
    # Reject dirty included content, including a modified index. No invented source pin.
    subprocess.run(['git', 'diff', '--exit-code', head, '--', *paths], cwd=root,
                   check=True, stdout=subprocess.DEVNULL)
    files = {p: (root / p).read_bytes() for p in sorted(paths)}
    _need(not worker_bundle.is_symlink() and worker_bundle.is_file() and
          worker_bundle.stat().st_size <= 2097152)
    bundle = worker_bundle.read_bytes()
    _need(hashlib.sha256(bundle).hexdigest() == manifest['service']['bundle_sha256'])
    files['worker-bundle.mjs'] = bundle
    files['release-manifest.json'] = json.dumps(manifest, sort_keys=True,
                                               separators=(',', ':')).encode()
    inventory = {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}
    files['sha256-inventory.json'] = json.dumps(inventory, sort_keys=True,
                                               separators=(',', ':')).encode()
    _need(sum(map(len, files.values())) <= 16777216)
    with output.open('xb') as target, tarfile.open(
            fileobj=target, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for path, data in sorted(files.items()):
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.mtime = len(data), 0o600, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
    return {'phase': 'offline_release_package_created',
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'file_count': len(files),
            'installed': False, 'post_permitted': False}


def inspect_package(path: Path):
    """Read and hash without extracting; no archive member becomes a filesystem path."""
    _need(path.stat().st_size <= 20000000)
    with tarfile.open(path, 'r:') as archive:
        members = archive.getmembers()
        _need(len(members) <= 500 and len({m.name for m in members}) == len(members))
        files = {}
        for m in members:
            _need(m.isfile() and not Path(m.name).is_absolute() and
                  '..' not in Path(m.name).parts and m.size <= 2097152)
            files[m.name] = archive.extractfile(m).read()
    _need(all(p in files for p in ['sha256-inventory.json', 'release-manifest.json',
                                  'worker-bundle.mjs']))
    inventory = json.loads(files.pop('sha256-inventory.json'))
    _need(inventory == {p: hashlib.sha256(b).hexdigest() for p, b in files.items()})
    manifest = json.loads(files['release-manifest.json'])
    validate_manifest(manifest, manifest['source_sha'])
    _need(hashlib.sha256(files['worker-bundle.mjs']).hexdigest() ==
          manifest['service']['bundle_sha256'])
    return {'phase': 'offline_package_inventory_consistent', 'installed': False,
            'post_permitted': False}
