"""Synthetic birth-surname-only contracts. No network or real names."""
import copy

import pytest

import geni_uploader.runners.bounded_profile_name_update as core
import geni_uploader.runners.protected_profile_name_update as protected
from geni_uploader.core.people import Blocked
from tests.test_profile_name_update import IO, TARGET, Store, environment, plan


def birth_plan(current=False):
    c = plan()
    if not current:
        del c['expected']['last_name']
        for fields in c['expected']['names'].values():
            del fields['last_name']
    c['set'] = {'maiden_name': 'ZZ Birth', 'names': {
        'en-US': {'maiden_name': 'ZZ Birth'}, 'he': {'maiden_name': 'ZZ Family'}}}
    return c


class BirthIO(IO):
    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        self.value['maiden_name'] = body['maiden_name']
        for locale, fields in body['names'].items():
            self.value['names'][locale].update(fields)
        return {'id': TARGET}


@pytest.mark.parametrize('current', [False, True])
@pytest.mark.parametrize('read_only', [False, True])
def test_exact_birth_only_preserves_presence_and_current_values(current, read_only):
    c = birth_plan(current)
    io, store = BirthIO(c), Store()
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=read_only)
    assert r['phase'] == ('READ_ONLY_NAME_VERIFIED' if read_only else 'VERIFIED')
    assert len(io.posts) == (not read_only)
    assert store.receipts == ([] if read_only else ['before', 'ack', 'final'])
    assert ('last_name' in io.value) is current
    for locale in ('en-US', 'he'):
        assert ('last_name' in io.value['names'][locale]) is current
        if current:
            assert io.value['names'][locale]['last_name'] == c['expected']['names'][locale]['last_name']


@pytest.mark.parametrize('where', ['main', 'en-US', 'he'])
def test_any_existing_birth_surname_blocks_even_same_value(where):
    c = birth_plan()
    target = c['expected'] if where == 'main' else c['expected']['names'][where]
    target['maiden_name'] = 'ZZ Birth'
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('key,value', [('last_name', 'ZZ New'), ('public', True),
                                     ('first_name', 'ZZ Other'), ('email', 'zz@example.invalid')])
def test_unapproved_main_change_blocked(key, value):
    c = birth_plan()
    c['set'][key] = value
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('key', ['last_name', 'first_name', 'public'])
def test_locale_extra_field_blocked(key):
    c = birth_plan()
    c['set']['names']['he'][key] = 'ZZ Wrong'
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('mutation', ['main_surname_added', 'locale_surname_added', 'first_name',
                                    'claimed', 'graph', 'wrong_birth_surname', 'locale_lost'])
def test_postwrite_drift_stops_no_final_receipt(mutation):
    c = birth_plan()
    io, store = BirthIO(c), Store()
    original = io.update

    def update(*args):
        response = original(*args)
        if mutation == 'main_surname_added':
            io.value['last_name'] = 'ZZ Unexpected'
        elif mutation == 'locale_surname_added':
            io.value['names']['he']['last_name'] = 'ZZ Unexpected'
        elif mutation == 'first_name':
            io.value['first_name'] = 'ZZ Unexpected'
        elif mutation == 'claimed':
            io.value['claimed'] = True
        elif mutation == 'graph':
            io.edges[TARGET]['edges']['union-404'] = {'rel': 'partner'}
        elif mutation == 'wrong_birth_surname':
            io.value['maiden_name'] = 'ZZ Wrong'
        else:
            del io.value['names']['he']
        return response

    io.update = update
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1
    assert 'final' not in store.receipts


def test_birth_only_io_sends_no_current_surname(monkeypatch):
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    c = birth_plan()
    v = protected.ScopedVendor('ZZ-token', c, read_only=False)
    calls = []
    v.request = lambda *args: calls.append(args) or {'id': TARGET}
    protected.IO(v).update(TARGET, c['set'])
    assert calls == [('POST', '/api/' + TARGET + '/update', c['set'])]
    assert 'last_name' not in calls[0][2]
    for fields in calls[0][2]['names'].values():
        assert set(fields) == {'maiden_name'}


def test_marker_stable_and_consumed_not_rearmed():
    c = birth_plan()
    marker = core.marker(core.plan(c))
    c['expires_at'] += 10
    assert core.marker(core.plan(c)) == marker
    io, store = BirthIO(c), Store()
    store.consume(marker)
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and io.posts == []


@pytest.mark.parametrize('mode', ['plan', 'update'])
def test_real_entrypoint_birth_only(tmp_path, monkeypatch, mode):
    c = birth_plan()
    io, store = BirthIO(c), Store()

    class Private:
        def __init__(self, *_):
            pass

        def load(self, _):
            return protected.decode(protected.canonical(c))

    monkeypatch.setattr(protected, 'PrivateGit', Private)
    monkeypatch.setattr(protected, 'Store', lambda _: store)
    monkeypatch.setattr(protected, 'IO', lambda *a, **k: io)
    monkeypatch.setattr(protected.time, 'time', lambda: 200)
    monkeypatch.setattr(protected, 'encrypt', lambda *_: b'age-encryption.org/v1\nZZ')
    assert protected.run(environment(c, tmp_path, mode)) is True
    assert len(io.posts) == (mode == 'update')


def test_main_birth_surname_must_match_english_locale():
    c = birth_plan()
    c['set']['maiden_name'] = 'ZZ Different'
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('mutation', ['missing', 'unexpected'])
def test_birth_only_requested_locales_are_exact(mutation):
    c = birth_plan()
    if mutation == 'missing':
        del c['set']['names']['he']
    else:
        c['set']['names']['fr'] = {'maiden_name': 'ZZ Family'}
    with pytest.raises(Blocked):
        core.plan(c)
