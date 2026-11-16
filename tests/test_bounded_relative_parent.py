"""Synthetic pure-model regressions. No service, credentials or network."""
import copy

import pytest

from geni_uploader.runners import bounded_parent_addition as legacy
from geni_uploader.runners import bounded_relative_parent as model
from tests import test_bounded_parent_addition as fixture
from tests.test_guarded_family_additions import Store

OWNER, ANCHOR, SPOUSE, NEW, OLD = (fixture.OWNER, fixture.ANCHOR, fixture.SPOUSE,
                                  fixture.NEW, fixture.OLD)
FAMILY, PARENTS = fixture.FAMILY, fixture.PARENTS


def plan(existing=False, spouse=False):
    c = fixture.plan(existing)
    c['external_edges'] = {}
    if spouse:
        c['family'][FAMILY] = {OWNER: 'partner', ANCHOR: 'partner', SPOUSE: 'child'}
    c['profiles'] = {p: dict(legacy.existing_payload(v), claimed=False)
                     for p, v in c['profiles'].items()}
    c['path'] = [OWNER, ANCHOR]
    c['path_unions'] = [FAMILY]
    c['path_union_members'] = {FAMILY: copy.deepcopy(c['family'][FAMILY])}
    c['path_families'] = {p: {'family': copy.deepcopy(c['family']), 'external_edges': {}}
                          for p in c['path']}
    # Owner's immediate family does not include the anchor's parent union.
    if existing:
        del c['path_families'][OWNER]['family'][PARENTS]
        c['path_families'][OWNER]['external_edges'] = {ANCHOR: {PARENTS: 'child'}}
    return c


class IO:
    def __init__(self, c):
        self.c, self.reads, self.posts = copy.deepcopy(c), [], []
        self.profiles = {p: dict(v, id=p) for p, v in c['profiles'].items()}
        self.spec = copy.deepcopy(c['family'])

    def get_profile(self, node):
        self.reads.append(('profile', node))
        return copy.deepcopy(self.profiles[OWNER if node == 'profile' else node])

    def get_family(self, node):
        self.reads.append(('family', node))
        if self.posts and node == ANCHOR:
            spec, boundary = self.spec, self.c['external_edges']
        elif node == NEW:
            spec = {PARENTS: self.spec[PARENTS]}
            boundary = legacy.boundary_edges(self.c, PARENTS, self.spec[PARENTS])
        else:
            b = self.c['path_families'][node]
            spec, boundary = b['family'], b['external_edges']
        value = fixture.family(node, spec)
        for p, edges in boundary.items():
            if p in value['nodes']:
                value['nodes'][p]['edges'].update({u: {'rel': role} for u, role in edges.items()})
        return value

    def get_union(self, union):
        self.reads.append(('union', union))
        members = self.spec[union]
        return {'id': union, 'partners': [p for p, r in members.items() if r == 'partner'],
                'children': [p for p, r in members.items() if r == 'child']}

    def add_parent(self, anchor, fields):
        assert anchor == ANCHOR
        self.posts.append((anchor, fields))
        self.profiles[NEW] = dict(fields, id=NEW, claimed=False)
        self.spec.setdefault(PARENTS, {ANCHOR: 'child'})[NEW] = 'partner'
        return {'id': NEW}


def execute(c=None, io=None, store=None, save=None):
    c = c or plan()
    io, store, snapshots = io or IO(c), store or Store(), []

    def capture(value):
        snapshots.append(copy.deepcopy(value))
        return b'ZZ-cipher'

    r = model.execute(c, io, store, save or capture, lambda: 200)
    return r, io, store, snapshots


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('spouse', [False, True])
@pytest.mark.parametrize('alive', [False, True])
def test_first_second_parent_and_spouse_anchor(existing, spouse, alive):
    c = plan(existing, spouse)
    c['entry']['payload']['is_alive'] = alive
    r, io, st, snapshots = execute(c)
    assert r['phase'] == 'VERIFIED'
    assert len(io.posts) == 1 and len(st.consumed) == 1
    assert st.events == ['before', 'consume', 'ack', 'final']
    assert len(io.reads) + len(io.posts) == model.request_budget(c) <= 27
    assert snapshots[-1] == r and not r['production_enabled']
    assert any(s['item'] and s['item'].get('create_response') == {'id': NEW}
               and 'id' not in s['item'] for s in snapshots)


def test_existing_public_claimed_context_is_read_only():
    c = plan(spouse=True)
    c['profiles'][OWNER]['public'] = True
    c['profiles'][ANCHOR]['claimed'] = True
    r, io, _, _ = execute(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert io.posts[0][1]['public'] is False


@pytest.mark.parametrize('key,value', [('path', [OWNER, OWNER]), ('path', [ANCHOR, OWNER]),
    ('path_unions', []), ('path_union_members', {}), ('accept_hidden_duplicate_risk', False),
    ('accept_private_create_risk', False), ('accept_union_selection_risk', False),
    ('expires_at', True), ('allow_unknown_merge', 'yes')])
def test_invalid_schema_rejected_without_reads(key, value):
    c = plan()
    c[key] = value
    io = IO(plan())
    with pytest.raises(model.Blocked):
        execute(c, io)
    assert not io.reads and not io.posts


@pytest.mark.parametrize('field', ['claimed', 'public', 'is_alive', 'gender'])
def test_missing_existing_safety_field_blocks(field):
    c = plan()
    del c['profiles'][ANCHOR][field]
    with pytest.raises(model.Blocked):
        model.plan(c)


def test_unknown_new_life_status_rejected():
    c = plan()
    c['entry']['payload']['is_alive'] = None
    with pytest.raises(model.Blocked):
        model.plan(c)


def test_disconnected_union_or_role_mismatch_rejected():
    c = plan()
    c['path_families'][OWNER]['family'][FAMILY][ANCHOR] = 'child'
    with pytest.raises(model.Blocked):
        model.plan(c)


@pytest.mark.parametrize('stage,count', [('before', 0), ('ack', 1), ('final', 1)])
def test_storage_failure_terminal(stage, count):
    r, io, _, _ = execute(store=Store(stage))
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


def test_legacy_marker_compatible_and_never_reset():
    c = plan()
    assert model.marker(c) == legacy.marker(fixture.plan())
    _, _, store, _ = execute(c)
    c['expires_at'] += 1
    r, io, _, _ = execute(c, store=store)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('kind', ['profile', 'family', 'union'])
def test_preflight_mismatch_stops_before_consume(kind):
    c = plan()
    io = IO(c)
    if kind == 'profile':
        io.profiles[ANCHOR]['claimed'] = True
    elif kind == 'family':
        io.c['path_families'][OWNER]['family'][FAMILY][ANCHOR] = 'child'
    else:
        io.spec[FAMILY][ANCHOR] = 'child'
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.consumed


@pytest.mark.parametrize('field,value', [('claimed', True), ('public', True),
                                        ('is_alive', None), ('first_name', 'ZZ-Wrong')])
def test_new_profile_wrong_readback_stays_consumed(field, value):
    c = plan()
    io = IO(c)
    send = io.add_parent

    def wrong(anchor, fields):
        ack = send(anchor, fields)
        io.profiles[NEW][field] = value
        return ack

    io.add_parent = wrong
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1


def test_uncertain_send_not_retried():
    io = IO(plan())

    def fail(anchor, fields):
        io.posts.append((anchor, fields))
        raise OSError('ZZ uncertain')

    io.add_parent = fail
    r, io, st, _ = execute(io=io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1


def multihop_plan():
    c = plan()
    # Owner -> existing parent -> that parent's spouse (the child anchor).
    c['path'] = [OWNER, SPOUSE, ANCHOR]
    other = 'union-990001'
    c['family'] = {other: {SPOUSE: 'partner', ANCHOR: 'partner', OLD: 'child'}}
    c['path_unions'] = [FAMILY, other]
    c['path_union_members'] = {FAMILY: {OWNER: 'child', SPOUSE: 'partner'},
                               other: copy.deepcopy(c['family'][other])}
    c['path_families'] = {
        OWNER: {'family': {FAMILY: c['path_union_members'][FAMILY]},
                'external_edges': {SPOUSE: {other: 'partner'}}},
        SPOUSE: {'family': copy.deepcopy(c['path_union_members']), 'external_edges': {}},
        ANCHOR: {'family': copy.deepcopy(c['family']),
                 'external_edges': {SPOUSE: {FAMILY: 'partner'}}},
    }
    c['external_edges'] = copy.deepcopy(c['path_families'][ANCHOR]['external_edges'])
    return c


def test_multihop_connection_without_discovery():
    c = multihop_plan()
    io = IO(c)
    io.spec.update(copy.deepcopy(c['path_union_members']))
    # Anchor family must not expand the path's other union after creation.
    send = io.add_parent

    def create(anchor, fields):
        value = send(anchor, fields)
        del io.spec[FAMILY]
        return value

    io.add_parent = create
    r, io, _, _ = execute(c, io)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert len(io.reads) + len(io.posts) == model.request_budget(c)


@pytest.mark.parametrize('mutation', ['cycle', 'repeat_union', 'missing_hop', 'bad_role'])
def test_path_mutations_rejected(mutation):
    c = multihop_plan()
    if mutation == 'cycle':
        c['path'][1] = OWNER
    elif mutation == 'repeat_union':
        c['path_unions'][1] = FAMILY
    elif mutation == 'missing_hop':
        del c['path_families'][SPOUSE]['family'][FAMILY]
    else:
        c['path_families'][SPOUSE]['family'][FAMILY][OWNER] = 'sibling'
    with pytest.raises(model.Blocked):
        model.plan(c)


@pytest.mark.parametrize('ack', [{}, {'id': OWNER}, {'id': 'ZZ-unknown'}, {'error': 'ZZ-error'}])
def test_bad_ack_preserved_and_no_next_effect(ack):
    c = plan()
    io = IO(c)

    def create(anchor, fields):
        io.posts.append((anchor, fields))
        return ack

    io.add_parent = create
    r, io, st, snapshots = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1
    assert any(s['item'] and s['item'].get('create_response') == ack for s in snapshots)
    assert st.events == ['before', 'consume']


def test_wrong_post_create_union_stops_without_repair():
    c = plan()
    io = IO(c)
    send = io.add_parent

    def create(anchor, fields):
        ack = send(anchor, fields)
        io.spec[FAMILY][NEW] = 'child'
        return ack

    io.add_parent = create
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1
    assert st.events == ['before', 'consume', 'ack']


def test_expired_preflight_never_sends():
    c = plan()
    c['expires_at'] = 199
    r, io, st, _ = execute(c)
    assert r['phase'] == 'STOPPED' and not io.reads and not io.posts and not st.consumed


def test_saved_ack_storage_failure_keeps_consumed():
    c = plan()

    def save(value):
        if value['item'] and 'create_response' in value['item']:
            raise OSError('ZZ-save-failed')
        return b'ZZ-cipher'

    # The terminal save can itself fail; no effect follows it.
    io, st = IO(c), Store()
    with pytest.raises(OSError):
        execute(c, io, st, save)
    assert len(io.posts) == 1 and len(st.consumed) == 1


@pytest.mark.parametrize('field', ['public', 'claimed', 'is_alive'])
def test_context_field_change_is_not_silently_accepted(field):
    c = plan()
    io = IO(c)
    io.profiles[ANCHOR][field] = not io.profiles[ANCHOR][field]
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.consumed


def test_pre_send_anchor_recheck_detects_drift():
    c = plan()
    io = IO(c)
    read, reads = io.get_family, []

    def family(node):
        value = read(node)
        reads.append(node)
        if reads.count(ANCHOR) == 2:
            value['nodes'][FAMILY]['edges'][OWNER]['rel'] = 'partner'
        return value

    io.get_family = family
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.consumed


def test_positive_merge_blocks_even_when_omission_risk_accepted():
    io = IO(plan())
    io.profiles[ANCHOR]['merge_pending'] = True
    r, io, st, _ = execute(io=io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.consumed


def test_anchor_own_omitted_parent_union_cannot_bypass_first_parent_guard():
    c = plan()
    omitted = 'union-990001'
    c['external_edges'] = {ANCHOR: {omitted: 'child'}}
    c['path_families'][ANCHOR]['external_edges'] = copy.deepcopy(c['external_edges'])
    io = IO(c)
    with pytest.raises(model.Blocked):
        execute(c, io)
    assert not io.reads and not io.posts


def test_any_path_focus_boundary_is_rejected_before_reads():
    c = plan()
    c['path_families'][OWNER]['external_edges'] = {OWNER: {'union-990001': 'child'}}
    io = IO(c)
    with pytest.raises(model.Blocked):
        execute(c, io)
    assert not io.reads and not io.posts


@pytest.mark.parametrize('key', ['public', 'claimed', 'is_alive'])
@pytest.mark.parametrize('value', [0, 1, None, 'false'])
def test_served_context_booleans_require_actual_bool(key, value):
    c = plan()
    io = IO(c)
    io.profiles[ANCHOR][key] = value
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.consumed


@pytest.mark.parametrize('key', ['public', 'claimed', 'is_alive'])
@pytest.mark.parametrize('value', [0, 1, None, 'false'])
def test_served_created_booleans_require_actual_bool(key, value):
    c = plan()
    io = IO(c)
    send = io.add_parent

    def create(anchor, fields):
        ack = send(anchor, fields)
        io.profiles[NEW][key] = value
        return ack

    io.add_parent = create
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1 and len(st.consumed) == 1
