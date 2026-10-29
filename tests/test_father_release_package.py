"""Synthetic offline package regressions, no provisioning or live keys."""
import copy
import hashlib
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

from father_release_package import inspect_package, package_release, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    return {'schema_version': 1, 'phase': 'closed_provisioning',
            'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                  cwd=ROOT, text=True).strip(),
            'free_only': True, 'max_cost_usd': 0, 'activate_workflows': False,
            'dispatch': False, 'geni_calls': 0,
            'service': {'new_worker_name': 'zz-father-closed',
                        'new_namespace_class': 'FatherOwnerIntent', 'namespace_id': None,
                        'bundle_sha256': 'a' * 64},
            'issuer': {'private_repository': 'ZZ-owner/ZZ-private', 'repository_id': None,
                       'workflow_path': '.github/workflows/father-release-issuer.yml',
                       'workflow_sha': 'b' * 40, 'key_purpose': 'exclusive_exact_father_policy',
                       'key_id': None, 'public_spki_base64': None,
                       'key_creation': 'generate_ed25519_into_private_secret_after_approval'},
            'actions': ['create_closed_worker', 'create_new_sqlite_namespace',
                        'create_private_issuer_repository', 'generate_exclusive_key']}


def test_repeatable_and_exclusive(tmp_path):
    m = manifest()
    a, b = tmp_path / 'a.tar', tmp_path / 'b.tar'
    bundle = tmp_path / 'worker.mjs'
    bundle.write_bytes(b'// ZZ synthetic closed bundle')
    m['service']['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    ra, rb = package_release(ROOT, m, a, bundle), package_release(ROOT, m, b, bundle)
    assert ra == rb
    assert a.read_bytes() == b.read_bytes()
    assert inspect_package(a)['post_permitted'] is False
    with pytest.raises(FileExistsError):
        package_release(ROOT, m, a, bundle)


@pytest.mark.parametrize('field,value', [('source_sha', 'f' * 40), ('free_only', False),
                         ('dispatch', True), ('activate_workflows', True), ('max_cost_usd', 1),
                         ('actions', ['create']), ('geni_calls', 1), ('geni_calls', False)])
def test_wrong_scope(field, value):
    m = manifest()
    head = m['source_sha']
    m[field] = value
    with pytest.raises(ValueError):
        validate_manifest(m, head)


def test_release_rejects_missing_ids_and_unresolved_key():
    m = manifest()
    m['phase'] = 'verified_release_candidate'
    with pytest.raises(ValueError):
        validate_manifest(m, m['source_sha'])


@pytest.mark.parametrize('name', ['../ZZescape', '/ZZabsolute'])
def test_unsafe_archive_member(tmp_path, name):
    path = tmp_path / 'bad.tar'
    with tarfile.open(path, 'w') as archive:
        info = tarfile.TarInfo(name)
        info.size = 1
        archive.addfile(info, io.BytesIO(b'x'))
    with pytest.raises(ValueError):
        inspect_package(path)


def test_inventory_tamper(tmp_path):
    path = tmp_path / 'bad.tar'
    import json
    files = {'release-manifest.json': json.dumps(manifest()).encode(), 'ZZdata': b'changed'}
    inventory = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
    inventory['ZZdata'] = '0' * 64
    files['sha256-inventory.json'] = json.dumps(inventory).encode()
    with tarfile.open(path, 'w') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError):
        inspect_package(path)


def test_exact_fields_no_placeholders():
    m = manifest()
    for section in ['service', 'issuer']:
        bad = copy.deepcopy(m)
        bad[section]['unexpected'] = 'ZZ'
        with pytest.raises(ValueError):
            validate_manifest(bad, m['source_sha'])


def test_supplied_bundle_digest_and_symlink_block(tmp_path):
    m = manifest()
    bundle = tmp_path / 'bundle.mjs'
    bundle.write_bytes(b'ZZ altered')
    with pytest.raises(ValueError):
        package_release(ROOT, m, tmp_path / 'bad.tar', bundle)
    link = tmp_path / 'link.mjs'
    link.symlink_to(bundle)
    m['service']['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        package_release(ROOT, m, tmp_path / 'symlink.tar', link)


def test_verified_manifest_has_exact_key_digest():
    import base64
    m = manifest()
    m['phase'] = 'verified_release_candidate'
    m['service']['namespace_id'] = 'a' * 32
    der = bytes.fromhex('302a300506032b6570032100') + b'Z' * 32
    m['issuer'].update(repository_id='999001', key_creation='already_provisioned_verified',
                       key_id=hashlib.sha256(der).hexdigest(),
                       public_spki_base64=base64.b64encode(der).decode())
    m['actions'] = ['inspect_verified_release_candidate']
    validate_manifest(m, m['source_sha'])
    m['issuer']['key_id'] = 'f' * 64
    with pytest.raises(ValueError):
        validate_manifest(m, m['source_sha'])



def test_top_level_unknown_field():
    m = manifest()
    m['unexpected'] = 'ZZ'
    with pytest.raises(ValueError):
        validate_manifest(m, m['source_sha'])


@pytest.mark.parametrize('missing', ['sha256-inventory.json', 'release-manifest.json',
                                     'worker-bundle.mjs'])
def test_missing_archive_members_value_error(tmp_path, missing):
    path = tmp_path / 'missing.tar'
    with tarfile.open(path, 'w') as archive:
        for name in ['sha256-inventory.json', 'release-manifest.json', 'worker-bundle.mjs']:
            if name != missing:
                info = tarfile.TarInfo(name)
                info.size = 2
                archive.addfile(info, io.BytesIO(b'{}'))
    with pytest.raises(ValueError, match='father release package blocked'):
        inspect_package(path)


def test_symlink_archive_member_rejected(tmp_path):
    path = tmp_path / 'symlink.tar'
    with tarfile.open(path, 'w') as archive:
        info = tarfile.TarInfo('ZZlink')
        info.type = tarfile.SYMTYPE
        info.linkname = 'ZZtarget'
        archive.addfile(info)
    with pytest.raises(ValueError):
        inspect_package(path)


def test_runtime_fixture_excluded(tmp_path):
    m = manifest()
    bundle = tmp_path / 'bundle.mjs'
    bundle.write_bytes(b'// ZZ synthetic bundle')
    m['service']['bundle_sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    path = tmp_path / 'package.tar'
    package_release(ROOT, m, path, bundle)
    with tarfile.open(path, 'r:') as archive:
        assert 'oauth-bootstrap/runtime-fixture.mjs' not in archive.getnames()
