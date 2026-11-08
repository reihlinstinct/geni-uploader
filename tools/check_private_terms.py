"""Keyed private-term scanner core: HMAC-SHA256, value-free (#733).

Design: docs/keyed-public-terms-design.md. This is the public scanner core
only: it holds algorithm and schema versions, never a term, key or real
digest. A private policy (a JSON digest file) and an HMAC key are supplied at
run time by a trusted context; candidate files are read as bytes, never
imported or executed, and the candidate's git metadata is never used.

Matching contract (normalization version 1), applied to policy terms when
digests are authored and to candidate text when scanned:
  1. Unicode NFC;
  2. remove Hebrew points and cantillation marks (U+0591-U+05BD, U+05BF,
     U+05C1, U+05C2, U+05C4, U+05C5, U+05C7);
  3. full case folding, then NFC again;
  4. map Hebrew final letters to their base letters (U+05DA->U+05DB,
     U+05DD->U+05DE, U+05DF->U+05E0, U+05E3->U+05E4, U+05E5->U+05E6).
Tokens are maximal runs of Unicode letters and digits (underscore and every
other character is a boundary); invalid UTF-8 bytes are boundaries. A term is
a sequence of 1..MAX_SEQUENCE tokens and matches only whole consecutive
tokens of one file's token stream (line breaks and punctuation are plain
boundaries); there is no substring matching and no transliteration. The
relative path of each file is scanned as its own stream (reported as line 0).

Digest: HMAC-SHA256(key, DOMAIN NUL "n1" NUL policy_version NUL str(len) NUL
tokens joined by U+001F, UTF-8), so a digest is bound to the normalization
version, the policy version and the token-sequence length. Equality is
decided only by hmac.compare_digest over the full 32 bytes.

Key: the environment variable PRIVATE_TERMS_KEY (at least 32 bytes UTF-8),
never a command argument. Policy file (--policy, JSON, duplicate keys and
unknown fields rejected):
  {"schema": 1, "algorithm": "hmac-sha256", "normalization": 1,
   "policy_version": "<label>",
   "entries": [{"length": N, "digest": "<64 lowercase hex>"}, ...],
   "exceptions": [{"path": "<rel path>", "line": L, "token": T,
                   "length": N, "binding": "<64 lowercase hex>",
                   "reason": "<text>", "expires": "YYYY-MM-DD"}, ...]}
"exceptions" is optional. An exception suppresses exactly one finding at its
position while its keyed binding matches the current file content and its
expiry date has not passed (UTC).

Usage:
  python tools/check_private_terms.py --policy FILE [--root DIR]
      [--expect-tree OID] [--findings]
--expect-tree binds the result to an exact git tree id (40 hex SHA-1 or 64
hex SHA-256), recomputed from the scanned files. --findings also prints each
finding as PATH:LINE:TOKEN: private-term (a file whose own path matches is
shown as <file #N>, its 1-based position in sorted path order); without it a
match prints only the fixed result line. Output never contains a term, normalized token, digest or
key. Exit 0 clean, 1 blocked, 2 not evaluated (missing or short key, missing
or invalid policy, unsupported version, cap exceeded, unreadable file,
symlink or special file, tree mismatch). Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import unicodedata

SCANNER_VERSION = 1
SCHEMA_VERSION = 1
NORMALIZATION_VERSION = 1
ALGORITHM = 'hmac-sha256'
KEY_ENV = 'PRIVATE_TERMS_KEY'
DOMAIN = b'geni-uploader/private-terms/v1'
EXCEPTION_DOMAIN = b'geni-uploader/private-terms-exception/v1'
CATEGORY = 'private-term'

MIN_KEY_BYTES = 32
MAX_SEQUENCE = 8
MAX_ENTRIES = 4096
MAX_EXCEPTIONS = 256
MAX_POLICY_BYTES = 4 * 1024 * 1024
MAX_FILES = 20000
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TOKENS = 8_000_000
MAX_REASON_CHARS = 200

TOKEN = re.compile(r'[^\W_]+')
HEX64 = re.compile(r'[0-9a-f]{64}')
TREE_OID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
POLICY_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')

HEBREW_MARKS = frozenset(
    list(range(0x0591, 0x05BE)) + [0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7])
HEBREW_FINALS = {0x05DA: '\u05db', 0x05DD: '\u05de', 0x05DF: '\u05e0',
                 0x05E3: '\u05e4', 0x05E5: '\u05e6'}
STRIP_MARKS = {cp: None for cp in HEBREW_MARKS}

POLICY_KEYS = {'schema', 'algorithm', 'normalization', 'policy_version', 'entries'}
POLICY_OPTIONAL = {'exceptions'}
ENTRY_KEYS = {'length', 'digest'}
EXCEPTION_KEYS = {'path', 'line', 'token', 'length', 'binding', 'reason', 'expires'}


class Stop(Exception):
    """The scan cannot be evaluated; the message is value-free."""


def normalize(text):
    """Normalization version 1 (see the module docstring)."""
    text = unicodedata.normalize('NFC', text)
    text = text.translate(STRIP_MARKS)
    text = unicodedata.normalize('NFC', text.casefold())
    return text.translate(HEBREW_FINALS)


def tokens(text):
    return TOKEN.findall(normalize(text))


def _message(policy_version, seq):
    return b'\0'.join([
        DOMAIN, b'n%d' % NORMALIZATION_VERSION, policy_version.encode('ascii'),
        str(len(seq)).encode('ascii'), '\x1f'.join(seq).encode('utf-8')])


def sequence_digest(key, policy_version, seq):
    """Keyed digest of an already-normalized token sequence."""
    return hmac.digest(key, _message(policy_version, seq), 'sha256')


def term_digest(key, policy_version, term):
    """Keyed digest of a raw term (authoring helper; returns bytes)."""
    seq = tokens(term)
    if not 1 <= len(seq) <= MAX_SEQUENCE:
        raise ValueError(f'term must normalize to 1..{MAX_SEQUENCE} tokens')
    return sequence_digest(key, policy_version, seq)


def exception_binding(key, policy_version, path, line, token, length, content):
    """Keyed binding of one exception to a position and exact file bytes."""
    msg = b'\0'.join([
        EXCEPTION_DOMAIN, policy_version.encode('ascii'),
        path.encode('utf-8', 'surrogateescape'),
        b'%d' % line, b'%d' % token, b'%d' % length,
        hashlib.sha256(content).digest()])
    return hmac.digest(key, msg, 'sha256')


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Stop('policy: duplicate JSON key')
        out[k] = v
    return out


def _reject_constant(_name):
    raise Stop('policy: non-finite number')


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _check_keys(obj, required, optional, where):
    if not isinstance(obj, dict):
        raise Stop(f'policy: {where} is not an object')
    keys = set(obj)
    if keys - required - optional:
        raise Stop(f'policy: unknown field in {where}')
    if required - keys:
        raise Stop(f'policy: missing field in {where}')


def load_policy(path):
    try:
        st = os.lstat(path)
    except OSError:
        raise Stop('policy file missing or unreadable') from None
    if not stat.S_ISREG(st.st_mode):
        raise Stop('policy file is not a regular file')
    if st.st_size > MAX_POLICY_BYTES:
        raise Stop('policy file over the byte cap')
    try:
        with open(path, 'rb') as fh:
            raw = fh.read(MAX_POLICY_BYTES + 1)
    except OSError:
        raise Stop('policy file missing or unreadable') from None
    if len(raw) > MAX_POLICY_BYTES:
        raise Stop('policy file over the byte cap')
    try:
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Stop('policy: not valid UTF-8 JSON') from None
    _check_keys(data, POLICY_KEYS, POLICY_OPTIONAL, 'policy')
    if not _is_int(data['schema']) or data['schema'] != SCHEMA_VERSION:
        raise Stop('policy: unsupported schema version')
    if data['algorithm'] != ALGORITHM:
        raise Stop('policy: unsupported algorithm')
    if not _is_int(data['normalization']) or data['normalization'] != NORMALIZATION_VERSION:
        raise Stop('policy: unsupported normalization version')
    version = data['policy_version']
    if not isinstance(version, str) or not POLICY_VERSION.fullmatch(version):
        raise Stop('policy: invalid policy_version')
    entries = data['entries']
    if not isinstance(entries, list) or not entries:
        raise Stop('policy: entries must be a non-empty list')
    if len(entries) > MAX_ENTRIES:
        raise Stop('policy: entry cap exceeded')
    index = {}
    seen = set()
    for entry in entries:
        _check_keys(entry, ENTRY_KEYS, set(), 'entry')
        length, digest = entry['length'], entry['digest']
        if not _is_int(length) or not 1 <= length <= MAX_SEQUENCE:
            raise Stop('policy: entry length out of range')
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise Stop('policy: entry digest is not 64 lowercase hex')
        value = bytes.fromhex(digest)
        if (length, value) in seen:
            raise Stop('policy: duplicate entry')
        seen.add((length, value))
        index.setdefault(length, {}).setdefault(value[:2], []).append(value)
    exceptions = {}
    raw_exceptions = data.get('exceptions', [])
    if not isinstance(raw_exceptions, list):
        raise Stop('policy: exceptions must be a list')
    if len(raw_exceptions) > MAX_EXCEPTIONS:
        raise Stop('policy: exception cap exceeded')
    for exc in raw_exceptions:
        _check_keys(exc, EXCEPTION_KEYS, set(), 'exception')
        if not isinstance(exc['path'], str) or not exc['path']:
            raise Stop('policy: exception path invalid')
        for field in ('line', 'token'):
            if not _is_int(exc[field]) or exc[field] < 0:
                raise Stop('policy: exception position invalid')
        if not _is_int(exc['length']) or not 1 <= exc['length'] <= MAX_SEQUENCE:
            raise Stop('policy: exception length out of range')
        if not isinstance(exc['binding'], str) or not HEX64.fullmatch(exc['binding']):
            raise Stop('policy: exception binding is not 64 lowercase hex')
        reason = exc['reason']
        if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
            raise Stop('policy: exception reason missing or too long')
        expires = exc['expires']
        try:
            if not isinstance(expires, str) or not DATE.fullmatch(expires):
                raise ValueError
            expiry = datetime.date.fromisoformat(expires)
        except ValueError:
            raise Stop('policy: exception expiry invalid') from None
        pos = (exc['path'], exc['line'], exc['token'], exc['length'])
        if pos in exceptions:
            raise Stop('policy: duplicate exception')
        exceptions[pos] = (bytes.fromhex(exc['binding']), expiry)
    return version, index, exceptions


def read_key():
    value = os.environ.get('PRIVATE_TERMS_KEY')
    if not value:
        raise Stop(f'key missing ({KEY_ENV} unset or empty)')
    key = value.encode('utf-8')
    if len(key) < MIN_KEY_BYTES:
        raise Stop(f'key shorter than {MIN_KEY_BYTES} bytes')
    return key


def walk(root):
    """Sorted (relative path, bytes, executable) for every regular file.

    The top-level .git entry is skipped and never read. Symlinks, special
    files and unreadable entries stop the scan; nothing is followed.
    """
    files = []
    total = 0

    def visit(rel_dir):
        nonlocal total
        abs_dir = os.path.join(root, rel_dir) if rel_dir else root
        try:
            with os.scandir(abs_dir) as it:
                names = sorted(e.name for e in it)
        except OSError:
            raise Stop('unreadable directory in candidate tree') from None
        for name in names:
            if not rel_dir and name == '.git':
                continue
            rel = rel_dir + '/' + name if rel_dir else name
            try:
                st = os.lstat(os.path.join(root, rel))
            except OSError:
                raise Stop('unreadable entry in candidate tree') from None
            if stat.S_ISDIR(st.st_mode):
                visit(rel)
            elif stat.S_ISREG(st.st_mode):
                if len(files) >= MAX_FILES:
                    raise Stop('file-count cap exceeded')
                if st.st_size > MAX_FILE_BYTES:
                    raise Stop('per-file byte cap exceeded')
                try:
                    with open(os.path.join(root, rel), 'rb') as fh:
                        data = fh.read(MAX_FILE_BYTES + 1)
                except OSError:
                    raise Stop('unreadable file in candidate tree') from None
                if len(data) > MAX_FILE_BYTES:
                    raise Stop('per-file byte cap exceeded')
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise Stop('total byte cap exceeded')
                files.append((rel, data, bool(st.st_mode & stat.S_IXUSR)))
            else:
                raise Stop('symlink or special file in candidate tree')

    if not os.path.isdir(root) or os.path.islink(root):
        raise Stop('root is not a directory')
    visit('')
    return sorted(files)


def git_tree_oid(files, algo):
    """Git tree id of the given files (blobs and trees only)."""
    tree = {}
    for rel, data, executable in files:
        node = tree
        parts = rel.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = (data, executable)

    def oid(kind, body):
        h = hashlib.new(algo)
        h.update(b'%s %d\0' % (kind, len(body)))
        h.update(body)
        return h.digest()

    def build(node):
        items = []
        for name, value in node.items():
            raw = name.encode('utf-8', 'surrogateescape')
            if isinstance(value, dict):
                items.append((raw + b'/', b'40000 ' + raw, oid(b'tree', build(value))))
            else:
                data, executable = value
                mode = b'100755 ' if executable else b'100644 '
                items.append((raw, mode + raw, oid(b'blob', data)))
        items.sort(key=lambda item: item[0])
        return b''.join(head + b'\0' + digest for _, head, digest in items)

    return oid(b'tree', build(tree)).hex()


def _today():
    return datetime.datetime.now(datetime.UTC).date()


def _stream(text, first_line):
    out = []
    for lineno, line in enumerate(text.split('\n'), first_line):
        for tok_no, tok in enumerate(tokens(line), 1):
            out.append((tok, lineno, tok_no))
    return out


def scan(key, policy_version, index, exceptions, files):
    """Sorted value-free findings: (path, line, token, length)."""
    findings = set()
    lengths = sorted(index)
    today = _today()
    budget = MAX_TOKENS
    for rel, data, _ in files:
        streams = [_stream(rel, 0), _stream(data.decode('utf-8', 'replace'), 1)]
        for stream in streams:
            budget -= len(stream)
            if budget < 0:
                raise Stop('token cap exceeded')
            words = [tok for tok, _, _ in stream]
            for length in lengths:
                buckets = index[length]
                for start in range(len(words) - length + 1):
                    digest = sequence_digest(key, policy_version, words[start:start + length])
                    matched = False
                    for candidate in buckets.get(digest[:2], ()):
                        matched |= hmac.compare_digest(digest, candidate)
                    if not matched:
                        continue
                    _, line, tok_no = stream[start]
                    pos = (rel, line, tok_no, length)
                    exc = exceptions.get(pos)
                    if exc is not None and exc[1] >= today and hmac.compare_digest(
                            exc[0], exception_binding(key, policy_version, *pos, data)):
                        continue
                    findings.add(pos)
    return sorted(findings)


def _safe_path(rel):
    return rel.encode('unicode_escape').decode('ascii')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Keyed private-term scan; value-free output (#733).')
    parser.add_argument('--policy', required=True,
                        help='private policy digest file (JSON)')
    parser.add_argument('--root', default='.', help='candidate tree (default: .)')
    parser.add_argument('--expect-tree', metavar='OID',
                        help='exact git tree id the scanned files must hash to')
    parser.add_argument('--findings', action='store_true',
                        help='also print PATH:LINE:TOKEN: private-term per finding')
    args = parser.parse_args(argv)
    try:
        key = read_key()
        if args.expect_tree is not None and not TREE_OID.fullmatch(args.expect_tree):
            raise Stop('--expect-tree is not a 40 or 64 lowercase hex tree id')
        policy_version, index, exceptions = load_policy(args.policy)
        files = walk(os.path.abspath(args.root))
        bound = ''
        if args.expect_tree is not None:
            algo = 'sha1' if len(args.expect_tree) == 40 else 'sha256'
            if not hmac.compare_digest(git_tree_oid(files, algo), args.expect_tree):
                raise Stop('candidate tree does not match --expect-tree')
            bound = ' tree=' + args.expect_tree
        findings = scan(key, policy_version, index, exceptions, files)
    except Stop as exc:
        print(f'private-terms: not evaluated: {exc}', file=sys.stderr)
        return 2
    if args.findings:
        order = {rel: number for number, (rel, _, _) in enumerate(files, 1)}
        named = {pos[0] for pos in findings if pos[1] == 0}
        for rel, line, tok_no in sorted({pos[:3] for pos in findings}):
            shown = f'<file #{order[rel]}>' if rel in named else _safe_path(rel)
            print(f'{shown}:{line}:{tok_no}: {CATEGORY}')
    result = 'blocked' if findings else 'clean'
    print(f'private-terms: {result} scanner={SCANNER_VERSION} policy={policy_version}{bound}')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
