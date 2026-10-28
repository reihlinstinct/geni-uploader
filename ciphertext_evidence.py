"""Pure offline ciphertext evidence descriptors, byte caps and readback (#257).

Validates a strict descriptor for one encrypted evidence object, the supplied
local bytes against it, immutable per-operation byte accounting, and a remote
readback (bytes plus commit) supplied by the caller. Nothing here reads a
network, writes a repository or holds a key. A passing check does NOT prove the
bytes are real ciphertext, that the recipient can decrypt them, that the object
is privately retained, who uploaded it, or any authority. Header screening only
rejects obviously plaintext-shaped data. Caps are candidate values pending
reviewed real-schema/encryption-overhead validation (docs/intent-storage-decisions.md).

check_bytes and verify_readback do not compare stage, operation, run or
recipient with any expected value; the caller pins those. Under a uniform
random-bytes model the single-byte prefixes alone reject about 1.17 % of
objects; the other prefixes and the valid-UTF-8 branch add a further,
negligible share for objects of 32 bytes or more (docs/ciphertext-evidence.md).
Scalars are exact types: production_enabled must be the bool False (0, None
and other falsy values are rejected) and integer fields reject bool.
"""
import hashlib
import re
from copy import deepcopy

from people_core import exact, require

OBJECT_CAP = 1024 * 1024
OPERATION_CAP = 8 * 1024 * 1024
SCHEMA = 'geni-evidence-ciphertext-v1'
STAGES = ('pre_write', 'acknowledgment', 'readback', 'reconciliation')
DESCRIPTOR_KEYS = ('schema_version', 'mode', 'production_enabled', 'schema', 'stage',
                   'sha256', 'byte_length', 'recipient', 'operation_binding', 'run_id',
                   'run_attempt', 'blob_id', 'commit')
LEDGER_KEYS = ('mode', 'operation_binding', 'run_id', 'recipient', 'objects', 'total_bytes')
_PLAINTEXT_PREFIXES = (b'{', b'[', b'<', b'-----BEGIN', b'%PDF', b'PK\x03\x04', b'\xef\xbb\xbf')


def _hex(value, size):
    require(type(value) is str and re.fullmatch(f'[0-9a-f]{{{size}}}', value) is not None)


def validate_descriptor(descriptor):
    """Shape only; returns a copy."""
    exact(descriptor, DESCRIPTOR_KEYS)
    require(type(descriptor['schema_version']) is int and descriptor['schema_version'] == 1)
    require(descriptor['mode'] == 'offline_ciphertext_descriptor')
    require(descriptor['production_enabled'] is False)
    require(descriptor['schema'] == SCHEMA)
    require(type(descriptor['stage']) is str and descriptor['stage'] in STAGES)
    for key in ('sha256', 'recipient', 'operation_binding'):
        _hex(descriptor[key], 64)
    for key in ('blob_id', 'commit'):
        _hex(descriptor[key], 40)
    size = descriptor['byte_length']
    require(type(size) is int and 0 < size <= OBJECT_CAP)
    require(type(descriptor['run_id']) is str
            and re.fullmatch(r'[1-9][0-9]{0,19}', descriptor['run_id']) is not None)
    require(type(descriptor['run_attempt']) is int and descriptor['run_attempt'] == 1)
    return deepcopy(descriptor)


def git_blob_id(data):
    """Git's object id for a blob with these exact bytes (SHA-1 of header + bytes)."""
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data,
                        usedforsecurity=False).hexdigest()


def _plaintext_shaped(data):
    if data.startswith(_PLAINTEXT_PREFIXES):
        return True
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return False
    printable = sum(ch.isprintable() or ch in '\n\r\t' for ch in text)
    return printable >= 0.95 * len(text)


def check_bytes(descriptor, data):
    """Exact length, SHA256 and git blob id; reject empty, oversize or plaintext-shaped."""
    result = validate_descriptor(descriptor)
    require(type(data) is bytes and 0 < len(data) <= OBJECT_CAP)
    require(len(data) == result['byte_length'])
    require(hashlib.sha256(data).hexdigest() == result['sha256'])
    require(git_blob_id(data) == result['blob_id'])
    require(not _plaintext_shaped(data))
    return result


def new_ledger(operation_binding, run_id, recipient):
    """Empty immutable accounting for one exact operation/run/recipient."""
    ledger = {'mode': 'offline_ciphertext_ledger', 'operation_binding': operation_binding,
              'run_id': run_id, 'recipient': recipient, 'objects': [], 'total_bytes': 0}
    return validate_ledger(ledger)


def validate_ledger(ledger):
    exact(ledger, LEDGER_KEYS)
    require(ledger['mode'] == 'offline_ciphertext_ledger')
    _hex(ledger['operation_binding'], 64)
    _hex(ledger['recipient'], 64)
    require(type(ledger['run_id']) is str
            and re.fullmatch(r'[1-9][0-9]{0,19}', ledger['run_id']) is not None)
    objects = ledger['objects']
    require(type(objects) is list)
    seen_sha, seen_blob, total = set(), set(), 0
    for item in objects:
        validate_descriptor(item)
        require(item['operation_binding'] == ledger['operation_binding'])
        require(item['run_id'] == ledger['run_id'])
        require(item['recipient'] == ledger['recipient'])
        require(item['sha256'] not in seen_sha and item['blob_id'] not in seen_blob)
        seen_sha.add(item['sha256'])
        seen_blob.add(item['blob_id'])
        total += item['byte_length']
    require(type(ledger['total_bytes']) is int and ledger['total_bytes'] == total)
    require(total <= OPERATION_CAP)
    return deepcopy(ledger)


def account(ledger, descriptor, data):
    """Append one checked object. Returns a new ledger; never edits or removes entries."""
    result = validate_ledger(ledger)
    item = check_bytes(descriptor, data)
    require(item['operation_binding'] == result['operation_binding'])
    require(item['run_id'] == result['run_id'])
    require(item['recipient'] == result['recipient'])
    require(all(o['sha256'] != item['sha256'] and o['blob_id'] != item['blob_id']
                for o in result['objects']))
    require(result['total_bytes'] + item['byte_length'] <= OPERATION_CAP)
    result['objects'].append(item)
    result['total_bytes'] += item['byte_length']
    return validate_ledger(result)


def verify_readback(descriptor, remote_bytes, remote_commit):
    """Durable-evidence claim needs read-back bytes AND the exact private commit.

    Upload success, filenames or response metadata are not readback. A mismatch
    blocks; it never triggers retry, reset, delete or a plaintext fallback.
    """
    result = check_bytes(descriptor, remote_bytes)
    _hex(remote_commit, 40)
    require(remote_commit == result['commit'])
    return {'mode': 'offline_ciphertext_readback', 'content_consistent': True,
            'ciphertext_proved': False, 'retention_proved': False, 'authority': False,
            'production_enabled': False}
