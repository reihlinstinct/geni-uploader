import copy
import multiprocessing
import os

import pytest

from parent_consumption import LocalSyntheticLedger
from parent_envelope import draft
from people_core import Blocked
from tests.test_parent_envelope import fixture


def private(tmp_path):
    path = tmp_path/'private'
    path.mkdir(mode=0o700)
    return path


def attempt(path, plan, binding, queue):
    ledger = LocalSyntheticLedger(path)
    try:
        ledger.consume(draft(plan, binding), plan, binding, 1100)
        queue.put('consumed')
    except Blocked:
        queue.put('blocked')
    finally:
        ledger.close()


def crash_after_commit(path, plan, binding):
    ledger = LocalSyntheticLedger(path)
    ledger.consume(draft(plan, binding), plan, binding, 1100)
    os._exit(17)


def test_replay_changed_connection_or_fresh_plan_cannot_hide_consumption(tmp_path):
    path = private(tmp_path)
    plan, value = fixture()
    ledger = LocalSyntheticLedger(path)
    assert ledger.consume(draft(plan, value), plan, value, 1100)['production_enabled'] is False
    ledger.close()
    ledger = LocalSyntheticLedger(path)
    for change in ('same', 'plan', 'connection'):
        binding = copy.deepcopy(value)
        if change == 'plan': binding['plan_id'] = 'a'*64
        if change == 'connection':
            binding['connection_id'] = 'ZZother'
            for ref in binding['proof_refs'].values(): ref['connection_id'] = 'ZZother'
        with pytest.raises(Blocked): ledger.consume(draft(plan, binding), plan, binding, 1100)
    assert ledger.inspect()['consumed_count'] == 1
    assert not hasattr(ledger, 'reset') and not hasattr(ledger, 'release')
    ledger.close()


def test_process_race_has_single_winner(tmp_path):
    path = private(tmp_path)
    plan, value = fixture()
    LocalSyntheticLedger(path).close()
    ctx = multiprocessing.get_context('fork')
    queue = ctx.Queue()
    children = [ctx.Process(target=attempt, args=(path, plan, value, queue)) for _ in range(2)]
    for child in children: child.start()
    for child in children:
        child.join(10)
        assert child.exitcode == 0
    assert sorted(queue.get(timeout=2) for _ in children) == ['blocked', 'consumed']


def test_committed_intent_survives_process_death(tmp_path):
    path = private(tmp_path)
    plan, value = fixture()
    ctx = multiprocessing.get_context('fork')
    child = ctx.Process(target=crash_after_commit, args=(path, plan, value))
    child.start()
    child.join(10)
    assert child.exitcode == 17
    ledger = LocalSyntheticLedger(path)
    with pytest.raises(Blocked): ledger.consume(draft(plan, value), plan, value, 1100)
    assert ledger.inspect()['recovery_action'] == 'inspection_only'
    ledger.close()


@pytest.mark.parametrize('bad', ['shared-dir', 'symlink-dir', 'symlink-db', 'hardlink-db',
                               'shared-db', 'relative'])
def test_unsafe_storage_refused(tmp_path, bad):
    path = private(tmp_path)
    db = path/'synthetic-consumption.sqlite3'
    if bad == 'shared-dir': path.chmod(0o755)
    if bad == 'symlink-dir':
        link = tmp_path/'link'
        link.symlink_to(path)
        path = link
    if bad in ('symlink-db', 'hardlink-db'):
        target = tmp_path/'ZZtarget'
        target.write_text('ZZprivate')
        target.chmod(0o600)
        if bad == 'symlink-db': db.symlink_to(target)
        else: os.link(target, db)
    if bad == 'shared-db': db.touch(mode=0o644)
    if bad == 'relative': path = 'ZZrelative'
    with pytest.raises(Blocked) as error: LocalSyntheticLedger(path)
    assert 'ZZ' not in str(error.value)
