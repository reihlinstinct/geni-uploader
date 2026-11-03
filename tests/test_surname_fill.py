"""Synthetic current-surname-fill contracts (#718). No network or real names."""
import copy

import pytest

import geni_uploader.runners.bounded_profile_name_update as core
from geni_uploader.core.people import Blocked
from tests.test_profile_name_update import IO, OWNER, TARGET, Store, plan

SPOUSE = 'profile-303'


def fill_plan(with_maiden=True):
    c = plan()
    del c['expected']['last_name']
    for fields in c['expected']['names'].values():
        del fields['last_name']
    if with_maiden:
        c['expected']['maiden_name'] = 'ZZ Birth'
        c['expected']['names']['en-US']['maiden_name'] = 'ZZ Birth'
        c['expected']['names']['he']['maiden_name'] = 'ZZ Family'
    c['set'] = {'last_name': 'ZZ Married', 'names': {
        'en-US': {'last_name': 'ZZ Married'}, 'he': {'last_name': 'ZZ Married'}}}
    c['spouse'] = SPOUSE
    return c


class FillIO(IO):
    def __init__(self, c, anomaly=None):
        super().__init__(c, anomaly)
        self.edges[SPOUSE] = {'edges': {'union-303': {'rel': 'partner'}}}

    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        self.value['last_name'] = body['last_name']
        for locale, fields in body['names'].items():
            self.value['names'][locale].update(fields)
        return {'id': TARGET if self.anomaly != 'wrong_id' else 'profile-999'}


def run(c, anomaly=None, read_only=False):
    io, store = FillIO(c, anomaly), Store()
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=read_only)
    return r, io, store


@pytest.mark.parametrize('read_only', [False, True])
def test_fill_verified_preserves_maiden_and_edges(read_only):
    c = fill_plan()
    r, io, store = run(c, read_only=read_only)
    assert r['phase'] == ('READ_ONLY_NAME_VERIFIED' if read_only else 'VERIFIED')
    assert len(io.posts) == (not read_only)
    assert store.receipts == ([] if read_only else ['before', 'ack', 'final'])
    if not read_only:
        target, body = io.posts[0]
        assert target == TARGET
        assert set(body) == {'last_name', 'names'}
        assert set(body['names']) == {'en-US', 'he'}
        assert all(set(f) == {'last_name'} for f in body['names'].values())
        assert io.value['last_name'] == 'ZZ Married'
        assert io.value['names']['he']['last_name'] == 'ZZ Married'
    assert io.value.get('maiden_name') == 'ZZ Birth'
    assert io.value['names']['he'].get('maiden_name') == 'ZZ Family'
    assert io.value['first_name'] == 'ZZ First' and io.value['public'] is False


@pytest.mark.parametrize('where', ['main', 'en-US', 'he'])
def test_any_existing_surname_blocks_even_same_value(where):
    c = fill_plan()
    target = c['expected'] if where == 'main' else c['expected']['names'][where]
    target['last_name'] = 'ZZ Married'
    with pytest.raises(Blocked):
        core.plan(c)


def test_present_surname_equal_to_birth_name_blocks():
    c = fill_plan()
    c['expected']['last_name'] = c['expected']['maiden_name']
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('anomaly', ['missing_spouse_node', 'no_partner_union', 'child_rel'])
def test_spouse_not_verified_in_union_read_blocks(anomaly):
    c = fill_plan()
    io = FillIO(c)
    if anomaly == 'missing_spouse_node':
        del io.edges[SPOUSE]
    elif anomaly == 'no_partner_union':
        io.edges[TARGET]['edges'] = {'union-303': {'rel': 'child'}}
    else:
        io.edges[SPOUSE]['edges']['union-303'] = {'rel': 'child'}
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_missing_spouse_field_blocks():
    c = fill_plan()
    del c['spouse']
    with pytest.raises(Blocked):
        core.plan(c)


def test_spouse_equal_to_owner_or_target_blocks():
    for bad in (OWNER, TARGET):
        c = fill_plan()
        c['spouse'] = bad
        with pytest.raises(Blocked):
            core.plan(c)


@pytest.mark.parametrize('locale', ['en-US', 'he'])
def test_locale_mismatch_with_main_blocks(locale):
    c = fill_plan()
    c['set']['names'][locale]['last_name'] = 'ZZ Other'
    with pytest.raises(Blocked):
        core.plan(c)


@pytest.mark.parametrize('extra', ['first_name', 'maiden_name', 'gender'])
def test_extra_set_field_blocks(extra):
    c = fill_plan()
    c['set'][extra] = 'ZZ Extra'
    with pytest.raises(Blocked):
        core.plan(c)


def test_unknown_locale_blocks():
    c = fill_plan()
    c['set']['names']['fr'] = {'last_name': 'ZZ Married'}
    with pytest.raises(Blocked):
        core.plan(c)


def test_maidenless_target_fills():
    c = fill_plan(with_maiden=False)
    r, io, _ = run(c)
    assert r['phase'] == 'VERIFIED'
    assert 'maiden_name' not in io.value


def test_stale_union_graph_after_send_blocks():
    c = fill_plan()
    r, _io, _ = run(c, anomaly='graph')
    assert r['phase'] == 'STOPPED' and r['retry_allowed'] is False


def test_failed_post_is_terminal():
    c = fill_plan()
    r, io, store = run(c, anomaly='lost')
    assert r['phase'] == 'STOPPED' and r['retry_allowed'] is False
    assert len(io.posts) == 1 and store.receipts == ['before']


def test_spouse_pins_consumption_marker():
    a, b = fill_plan(), fill_plan()
    b['spouse'] = 'profile-404'
    assert core.marker(core.plan(a)) != core.marker(core.plan(b))


@pytest.mark.parametrize('locale', ['en-US', 'he'])
@pytest.mark.parametrize('extra', ['maiden_name', 'first_name'])
def test_locale_level_extra_fields_in_set_names_block(locale, extra):
    c = fill_plan()
    c['set']['names'][locale][extra] = 'ZZ Extra'
    with pytest.raises(Blocked):
        core.plan(c)


def test_live_preflight_absence_recheck_blocks():
    # The plan asserts no current surname; the live preflight read shows one.
    c = fill_plan()
    io = FillIO(c)
    io.value['last_name'] = 'ZZ Appeared'
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts
