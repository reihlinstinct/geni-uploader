"""Local-only synthetic consumption ledger, not production or global exclusion."""
import os
import sqlite3
import stat
from pathlib import Path

from parent_envelope import review
from people_core import Blocked, require


class LocalSyntheticLedger:
    """One canonical path must be shared by all cooperating local simulations.

    Copying/replacing the ledger or choosing another path evades local exclusion.
    No remote runner, refresh consumer or real write may rely on this prototype.
    No reset, release or production execution interface exists.
    """
    def __init__(self, directory):
        self.db = None
        directory = Path(directory)
        try:
            require(directory.is_absolute())
            # Refuse symlink components, not merely the last component.
            for part in (directory, *directory.parents):
                info = part.lstat()
                require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode))
            info = directory.stat()
            require(info.st_uid == os.getuid() and not info.st_mode & 0o077)
            path = directory/'synthetic-consumption.sqlite3'
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                        and info.st_nlink == 1 and not info.st_mode & 0o077)
            finally:
                os.close(fd)
            self.db = sqlite3.connect(path, isolation_level=None, timeout=2)
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.executescript('''
              CREATE TABLE IF NOT EXISTS consumed(
                plan_id TEXT PRIMARY KEY, envelope_hash TEXT NOT NULL,
                owner TEXT NOT NULL UNIQUE, connection_id TEXT NOT NULL,
                prior_version INTEGER NOT NULL, version INTEGER NOT NULL,
                phase TEXT NOT NULL CHECK(phase='consumed_no_execution'));
              CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON consumed
                BEGIN SELECT RAISE(ABORT,'immutable consumption'); END;
              CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON consumed
                BEGIN SELECT RAISE(ABORT,'immutable consumption'); END;
            ''')
        except (OSError, sqlite3.DatabaseError, Blocked) as exc:
            if self.db is not None:
                self.db.close()
            raise Blocked('local synthetic ledger unavailable; preserve durable state') from exc

    def close(self):
        self.db.close()

    def consume(self, envelope, proposal, expected, now):
        result = review(envelope, proposal, expected, now)
        bind = envelope['binding']
        # This first simulation models only an empty owner's version0->1.
        require(bind['journal_version'] == 0)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('INSERT INTO consumed VALUES(?,?,?,?,?,?,?)',
                            (bind['plan_id'], result['envelope_hash'], bind['owner'],
                             bind['connection_id'], 0, 1, 'consumed_no_execution'))
            self.db.execute('COMMIT')
            return {'mode': 'local_synthetic_only', 'phase': 'consumed_no_execution',
                    'version': 1, 'global_exclusion': False, 'production_enabled': False}
        except sqlite3.DatabaseError as exc:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise Blocked('local synthetic consumption stopped; inspect durable state') from exc

    def inspect(self):
        try:
            count = self.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0]
            return {'mode': 'local_synthetic_only', 'consumed_count': count,
                    'recovery_action': 'inspection_only', 'production_enabled': False}
        except sqlite3.DatabaseError as exc:
            raise Blocked('local synthetic ledger unreadable; preserve durable state') from exc
