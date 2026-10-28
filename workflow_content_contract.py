"""Pure immutable workflow-content candidate (#260), no HTTP or execution."""
import base64
import hashlib
import json
import re

from people_core import Blocked, exact, require

LIMIT = 256 * 1024
RESPONSE_LIMIT = 1024 * 1024


def _sha(value, length=40):
    require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}', value) is not None)


def _pins(pins):
    exact(pins, ('owner', 'repo', 'commit', 'filename', 'workflow_sha256'))
    for key in ('owner', 'repo'):
        require(type(pins[key]) is str
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', pins[key]) is not None)
    require(type(pins['filename']) is str
            and re.fullmatch(r'[A-Za-z0-9_-]+\.ya?ml', pins['filename']) is not None)
    _sha(pins['commit'])
    _sha(pins['workflow_sha256'], 64)


def descriptor(pins, kind, sha=None):
    _pins(pins)
    require(type(kind) is str and kind in ('commits', 'trees', 'blobs'))
    if kind == 'commits':
        require(sha is None)
        sha = pins['commit']
    else:
        _sha(sha)
    return {'method': 'GET', 'origin': 'https://api.github.com',
            'route': f"/repos/{pins['owner']}/{pins['repo']}/git/{kind}/{sha}",
            'redirects_allowed': False, 'retries_allowed': False}


def _parse(envelope, expected):
    exact(envelope, ('request', 'status', 'redirected', 'link', 'raw'))
    require(envelope['request'] == expected and type(envelope['status']) is int
            and envelope['status'] == 200 and envelope['redirected'] is False
            and envelope['link'] is None)
    raw = envelope['raw']
    require(type(raw) is bytes and 0 < len(raw) <= RESPONSE_LIMIT)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                        parse_constant=lambda _: require(False))
    require(type(result) is dict)
    return result


def verify(pins, envelopes):
    """Five supplied snapshots: commit, root tree, .github tree, workflows tree, blob.

    Cannot authenticate envelopes or resolve GitHub review/job association.
    Hashing exact content proves byte equality only, never approval or semantics.
    """
    try:
        _pins(pins)
        require(type(envelopes) is list and len(envelopes) == 5)
        commit = _parse(envelopes[0], descriptor(pins, 'commits'))
        require(commit['sha'] == pins['commit'])
        sha = commit['tree']['sha']
        _sha(sha)
        for envelope, name, mode, kind in zip(
                envelopes[1:4], ('.github', 'workflows', pins['filename']),
                ('040000', '040000', '100644'), ('tree', 'tree', 'blob')):
            tree = _parse(envelope, descriptor(pins, 'trees', sha))
            require(tree['sha'] == sha and tree['truncated'] is False)
            entries = tree['tree']
            require(type(entries) is list and 0 < len(entries) <= 4096)
            seen, chosen = set(), None
            for entry in entries:
                path = entry['path']
                require(type(path) is str and 0 < len(path) <= 255
                        and path not in ('.', '..') and '/' not in path and '\\' not in path
                        and not any(ord(c) < 32 for c in path) and path not in seen)
                seen.add(path)
                _sha(entry['sha'])
                require((entry['mode'], entry['type']) in (
                    ('040000', 'tree'), ('100644', 'blob'), ('100755', 'blob'),
                    ('120000', 'blob'), ('160000', 'commit')))
                if path == name:
                    chosen = entry
            require(chosen is not None and chosen['mode'] == mode and chosen['type'] == kind)
            sha = chosen['sha']
        blob = _parse(envelopes[4], descriptor(pins, 'blobs', sha))
        require(blob['sha'] == sha and blob['encoding'] == 'base64'
                and type(blob['size']) is int and 0 < blob['size'] <= LIMIT
                and type(blob['content']) is str)
        encoded = blob['content']
        # GitHub wraps base64 with newlines; accept LF only, no arbitrary whitespace.
        # Bound LF padding independently of decoded size; CR is always refused.
        require(len(encoded) <= 2*LIMIT and '\r' not in encoded)
        encoded = encoded.replace('\n', '')
        raw = base64.b64decode(encoded, validate=True)
        require(base64.b64encode(raw).decode('ascii') == encoded and len(raw) == blob['size'])
        require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == sha)
        require(hashlib.sha256(raw).hexdigest() == pins['workflow_sha256'])
    except (Blocked, ValueError, KeyError, TypeError, UnicodeError, RecursionError, IndexError):
        raise Blocked('workflow content blocked; review protected inputs') from None
    return {'phase': 'synthetic_workflow_bytes_match', 'workflow_sha256': pins['workflow_sha256'],
            'blob_sha': sha, 'production_enabled': False, 'provenance_verified': False,
            'workflow_semantics_verified': False, 'owner_approval_verified': False,
            'job_review_correlation_verified': False}
