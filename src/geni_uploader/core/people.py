"""Offline parent-only validation and safety journal. No production Geni adapter."""
import datetime
import hashlib
import json
import re
import sqlite3
import unicodedata


class Blocked(ValueError):
    """Fixed, value-free validation failure."""


def require(condition):
    if not condition:
        raise Blocked('parent creation blocked; review inputs and journal')


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def text(value, limit=160):
    require(type(value) is str and 0 < len(value.strip()) <= limit
            and unicodedata.normalize('NFC', value) == value
            and not any(unicodedata.category(c).startswith('C') for c in value))


def digest(value):
    # Bound recursion before JSON serialization. Preserve existing canonical bytes.
    def depth(item, level=0):
        require(level <= 32)
        if type(item) is dict:
            for key, leaf in item.items():
                require(type(key) is str)
                depth(leaf, level + 1)
        elif type(item) in (list, tuple):
            for leaf in item:
                depth(leaf, level + 1)
    try:
        depth(value)
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False).encode()).hexdigest()
    except (TypeError, ValueError, RecursionError) as exc:
        raise Blocked('offline parent hash blocked; unsupported or overdeep input') from exc


def validate(data):
    exact(data, ('schema_version', 'owner', 'operator', 'approval', 'parents'))
    require(type(data['schema_version']) is int and data['schema_version'] == 1)
    exact(data['owner'], ('node', 'expect_name'))
    require(type(data['owner']['node']) is str
            and re.fullmatch(r'[0-9]{1,30}', data['owner']['node']) is not None)
    text(data['owner']['expect_name'])
    require(len(data['owner']['expect_name'].split()) >= 2)
    text(data['operator'])
    exact(data['approval'], ('source', 'date', 'requested_by_owner', 'private_storage_approved'))
    text(data['approval']['source'])
    require(type(data['approval']['date']) is str
            and re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['approval']['date']) is not None)
    try:
        datetime.date.fromisoformat(data['approval']['date'])
    except ValueError as exc:
        raise Blocked('parent creation blocked; review inputs and journal') from exc
    require(data['approval']['requested_by_owner'] is True
            and data['approval']['private_storage_approved'] is True)
    require(type(data['parents']) is list and 1 <= len(data['parents']) <= 2)
    ids = set()
    for parent in data['parents']:
        exact(parent, ('local_id', 'relation', 'anchor', 'names', 'gender', 'is_alive', 'public'))
        text(parent['local_id'], 64)
        require(re.fullmatch(r'[A-Za-z0-9_-]+', parent['local_id']) is not None)
        require(parent['local_id'] not in ids)
        ids.add(parent['local_id'])
        require(parent['relation'] == 'parent' and parent['anchor'] == data['owner']['node'])
        require(type(parent['is_alive']) is bool and parent['public'] is False
                and parent['gender'] in ('male', 'female', 'unknown'))
        require(type(parent['names']) is dict and 1 <= len(parent['names']) <= 5)
        for locale, names in parent['names'].items():
            require(type(locale) is str and re.fullmatch(r'[a-z]{2}', locale) is not None)
            require(type(names) is dict and 'first_name' in names
                    and set(names) <= {'first_name', 'middle_name', 'last_name', 'maiden_name'})
            for value in names.values():
                text(value)
    return data


def warnings(data):
    validate(data)
    parents = data['parents']
    result = []
    if len(parents) == 2:
        if parents[0]['names'] == parents[1]['names']:
            result.append('duplicate parent names require review')
        if parents[0]['gender'] == parents[1]['gender'] != 'unknown':
            result.append('same-gender parents require slot semantics review')
    return result


RECEIPT_KEYS = ('manifest_hash', 'data_sha', 'owner', 'graph_hash', 'state_version',
                'workflow_sha', 'image_digest', 'job_workflow_ref', 'run_id',
                'run_attempt', 'created', 'expires', 'count')


def check_receipt(receipt, expected, now):
    """Caller authenticates OIDC/receipt envelope first. This is binding only."""
    exact(receipt, RECEIPT_KEYS)
    exact(expected, RECEIPT_KEYS)
    require(receipt == expected)
    require(type(now) in (int, float) and type(receipt['created']) is int
            and type(receipt['expires']) is int)
    require(receipt['created'] <= now < receipt['expires']
            and 0 < receipt['expires'] - receipt['created'] <= 900)
    require(type(receipt['count']) is int and 1 <= receipt['count'] <= 2)
    require(type(receipt['run_attempt']) is int and receipt['run_attempt'] >= 1)
    require(type(receipt['state_version']) is int and receipt['state_version'] >= 0)
    for field in ('manifest_hash', 'graph_hash'):
        require(type(receipt[field]) is str
                and re.fullmatch(r'[0-9a-f]{64}', receipt[field]) is not None)
    for field in ('data_sha', 'workflow_sha'):
        require(type(receipt[field]) is str
                and re.fullmatch(r'[0-9a-f]{40}', receipt[field]) is not None)
    require(type(receipt['image_digest']) is str
            and re.fullmatch(r'sha256:[0-9a-f]{64}', receipt['image_digest']) is not None)
    for field in ('owner', 'job_workflow_ref', 'run_id'):
        text(receipt[field], 256)
    return digest(receipt)


def bind(data, receipt, expected, now):
    validated = validate(data)
    exact(receipt, RECEIPT_KEYS)
    require(receipt.get('manifest_hash') == digest(validated))
    require(receipt.get('count') == len(validated['parents'])
            and receipt.get('owner') == validated['owner']['node'])
    return check_receipt(receipt, expected, now)


class Journal:
    """Local synthetic CAS prototype, not the deployed service or an auth layer.

    One in-flight operation per owner. Durable intents survive expiry/crashes.
    New manifest hashes never hide old intents. No reset or delete interface.
    """
    def __init__(self, path):
        try:
            self.db = sqlite3.connect(path, isolation_level=None)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA busy_timeout=2000')
            self.db.executescript('''
              CREATE TABLE IF NOT EXISTS owners(owner TEXT PRIMARY KEY, version INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS events(
                owner TEXT NOT NULL, version INTEGER NOT NULL, operation TEXT NOT NULL,
                manifest TEXT NOT NULL, payload TEXT NOT NULL, phase TEXT NOT NULL,
                object_id TEXT, receipt TEXT NOT NULL, run_id TEXT NOT NULL,
                attempt INTEGER NOT NULL, anchor TEXT NOT NULL, PRIMARY KEY(owner,version));
              CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT,'immutable journal'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT,'immutable journal'); END;
            ''')
        except sqlite3.DatabaseError as exc:
            if hasattr(self, 'db'):
                self.db.close()
            raise Blocked('journal unavailable; review durable state') from exc

    def close(self):
        self.db.close()

    def transition(self, owner, expected_version, operation, manifest, payload, phase,
                   object_id=None, *, binding):
        exact(binding, ('receipt', 'run_id', 'attempt', 'anchor'))
        require(type(binding['receipt']) is str
                and re.fullmatch(r'[0-9a-f]{64}', binding['receipt']) is not None)
        text(binding['run_id'])
        require(type(binding['attempt']) is int and binding['attempt'] >= 1)
        require(binding['anchor'] == owner)
        text(owner)
        text(operation, 64)
        require(type(expected_version) is int and expected_version >= 0)
        require(all(type(h) is str and re.fullmatch(r'[0-9a-f]{64}', h)
                    for h in (manifest, payload)))
        require(phase in {'intent', 'acknowledged', 'verified', 'blocked'})
        require(object_id is None or (type(object_id) is str
                                      and re.fullmatch(r'[0-9]{1,30}', object_id)))
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT version FROM owners WHERE owner=?', (owner,)).fetchone()
            version = row[0] if row else 0
            maximum = self.db.execute('SELECT COALESCE(MAX(version),0) FROM events '
                                      'WHERE owner=?', (owner,)).fetchone()[0]
            require(version == expected_version == maximum)
            events = self.db.execute(
                'SELECT operation,manifest,payload,phase,object_id,receipt,run_id,attempt,anchor FROM events '
                'WHERE owner=? ORDER BY version', (owner,)).fetchall()
            previous = next((e for e in reversed(events) if e[0] == operation), None)
            active = {}
            for event in events:
                active[event[0]] = event[3]
            if phase == 'intent':
                require(previous is None and object_id is None
                        and not any(e[1:3] == (manifest, payload) for e in events)
                        and all(p == 'verified' for p in active.values()))
            else:
                require(previous is not None and previous[1:3] == (manifest, payload))
                require(previous[5:] == (binding['receipt'], binding['run_id'],
                                          binding['attempt'], binding['anchor']))
                old_phase, old_id = previous[3:5]
                if phase == 'acknowledged':
                    require(old_phase == 'intent' and object_id is not None)
                elif phase == 'verified':
                    require(old_phase == 'acknowledged' and object_id == old_id)
                else:
                    require(old_phase in {'intent', 'acknowledged'} and object_id == old_id)
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (owner, version + 1, operation, manifest, payload, phase, object_id,
                             binding['receipt'], binding['run_id'], binding['attempt'], binding['anchor']))
            self.db.execute('INSERT INTO owners VALUES(?,?) ON CONFLICT(owner) '
                            'DO UPDATE SET version=excluded.version', (owner, version + 1))
            self.db.execute('COMMIT')
            return version + 1
        except sqlite3.DatabaseError as exc:
            try:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
            except sqlite3.DatabaseError:
                pass
            raise Blocked('journal unavailable; review durable state') from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def resume(self, owner, operation):
        try:
            row = self.db.execute('SELECT phase,object_id FROM events WHERE owner=? AND operation=? '
                                  'ORDER BY version DESC LIMIT 1', (owner, operation)).fetchone()
            require(row is not None and row[0] in {'acknowledged', 'verified'})
            return {'action': 'get_only', 'object_id': row[1]}
        except sqlite3.DatabaseError as exc:
            raise Blocked('journal unavailable; review durable state') from exc


def production_adapter(*args, **kwargs):
    raise Blocked('production parent creation disabled; vendor proof and release required')
