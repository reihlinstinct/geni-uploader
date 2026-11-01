"""Synthetic ZZ fixtures only. No service, secret or network."""
import copy

import pytest

import bounded_parent_addition as b
from tests.test_guarded_family_additions import Store
from tests.test_one_time_parent_pilot import BODY

OWNER, ANCHOR, SPOUSE, NEW, OLD = [f'profile-{n}' for n in (991001, 991002, 991003, 991004, 991005)]
FAMILY, PARENTS = 'union-991001', 'union-991002'


def body(first, gender='male', alive=True):
    p = copy.deepcopy(BODY)
    p.update(first_name=first, gender=gender, is_alive=alive)
    for n in p['names'].values():
        n['first_name'] = first
    return p


def plan(existing=False, alive=True):
    profiles = {OWNER: body('ZZ-Root'), ANCHOR: body('ZZ-Anchor'),
                SPOUSE: body('ZZ-Spouse', 'female')}
    graph = {FAMILY: {OWNER: 'child', ANCHOR: 'partner', SPOUSE: 'partner'}}
    if existing:
        profiles[OLD] = body('ZZ-Old')
        graph[PARENTS] = {OLD: 'partner', ANCHOR: 'child'}
    return {'schema': 1, 'owner': OWNER, 'expect_name': 'ZZ-Root ZZ-Family',
        'anchor': ANCHOR, 'profiles': profiles, 'family': graph,
        'existing_parent': OLD if existing else None,
        'parent_union': PARENTS if existing else None,
        'entry': {'key': 'zz-grandparent', 'payload': body('ZZ-New', 'female', alive)},
        'expires_at': 999, 'allow_unknown_merge': True,
        'accept_hidden_duplicate_risk': True, 'accept_private_create_risk': True,
        'accept_union_selection_risk': True}


def family(focus, spec):
    nodes = {u: {'url': 'https://www.geni.com/api/' + u, 'status': 'spouse',
        'edges': {p: {'rel': r} for p, r in m.items()}} for u, m in spec.items()}
    for p in {p for m in spec.values() for p in m}:
        nodes[p] = {'id': p, 'url': 'https://www.geni.com/api/' + p,
                    'edges': {u: {'rel': m[p]} for u, m in spec.items() if p in m}}
    return {'focus': {'id': focus}, 'nodes': nodes}


class IO:
    def __init__(self, c):
        self.c, self.posts, self.reads = c, [], []
        self.spec = copy.deepcopy(c['family'])
        self.profiles = {p: dict(b.existing_payload(v), id=p) for p, v in c['profiles'].items()}

    def get_profile(self, p):
        self.reads.append(('profile', p))
        return copy.deepcopy(self.profiles[OWNER if p == 'profile' else p])

    def get_family(self, p):
        self.reads.append(('family', p))
        spec = self.spec if p == ANCHOR else {PARENTS: self.spec[PARENTS]}
        result = family(p, spec)
        if p == NEW:
            for profile in result['nodes']:
                if profile in self.c['profiles']:
                    result['nodes'][profile]['edges'].update({u: {'rel': m[profile]}
                        for u, m in self.c['family'].items() if profile in m and u not in spec})
        for profile, edges in self.c.get('external_edges', {}).items():
            if profile in result['nodes']:
                result['nodes'][profile]['edges'].update({u: {'rel': role}
                    for u, role in edges.items()})
        return result

    def get_union(self, u):
        self.reads.append(('union', u))
        return {'id': u, 'partners': [p for p, r in self.spec[u].items() if r == 'partner'],
                'children': [p for p, r in self.spec[u].items() if r == 'child']}

    def add_parent(self, anchor, payload):
        assert anchor == ANCHOR and payload == b.vendor_parent_payload(self.c['entry']['payload'])
        self.posts.append((anchor, payload))
        self.profiles[NEW] = dict(payload, id=NEW)
        self.spec.setdefault(PARENTS, {ANCHOR: 'child'})[NEW] = 'partner'
        return {'id': NEW}


def execute(c, io=None, st=None, clock=lambda: 200, save=None):
    io, st, snapshots = io or IO(c), st or Store(), []

    def capture(r):
        snapshots.append(copy.deepcopy(r))
        return b'ZZ-cipher'
    return b.execute(c, io, st, save or capture, clock), io, st, snapshots


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('alive', [False, True])
def test_complete_one_parent_living_or_deceased(existing, alive):
    c = plan(existing, alive)
    original = copy.deepcopy(c)
    r, io, st, snapshots = execute(c)
    assert r['phase'] == 'VERIFIED' and r['item']['id'] == NEW
    assert r['item']['union_id'] == PARENTS and r['production_enabled'] is False
    assert len(io.posts) == 1 and len(st.consumed) == 1
    assert st.events == ['before', 'consume', 'ack', 'final']
    assert io.posts[0][1]['public'] is False and io.posts[0][1]['is_alive'] is alive
    assert snapshots[-1] == r and c == original


@pytest.mark.parametrize('stage,count', [('before', 0), ('ack', 1), ('final', 1)])
def test_storage_failure_no_more_effects(stage, count):
    r, io, _, _ = execute(plan(), st=Store(stage))
    assert r['phase'] == 'STOPPED' and len(io.posts) == count


def test_consumed_marker_cannot_be_retried_with_new_window():
    c = plan()
    _, _, st, _ = execute(c)
    c['expires_at'] += 1
    r, io, _, _ = execute(c, st=st)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('key,val', [('owner', ANCHOR), ('anchor', OWNER),
    ('existing_parent', OWNER), ('parent_union', PARENTS), ('expires_at', True),
    ('accept_hidden_duplicate_risk', False), ('accept_private_create_risk', False),
    ('accept_union_selection_risk', False), ('allow_unknown_merge', 'true')])
def test_invalid_plan_no_reads(key, val):
    c = plan()
    c[key] = val
    io = IO(c)
    with pytest.raises(b.Blocked):
        execute(c, io)
    assert io.reads == [] and io.posts == []


def test_preflight_expiry_no_reads():
    r, io, st, _ = execute(plan(), clock=lambda: 999)
    assert r['phase'] == 'STOPPED' and not io.reads and not st.events


@pytest.mark.parametrize('corruption', ['wrong_focus', 'extra_node', 'extra_union',
    'bad_url', 'bad_role', 'missing_reverse', 'adoption', 'foster', 'hidden_parent'])
@pytest.mark.parametrize('post', [False, True])
def test_graph_corruption_before_or_after_create(corruption, post):
    c, st = plan(), Store()
    io = IO(c)
    original = io.get_family

    def bad(p):
        f = original(p)
        if bool(io.posts) != post:
            return f
        u = PARENTS if post else FAMILY
        if corruption == 'wrong_focus':
            f['focus']['id'] = SPOUSE
        elif corruption == 'extra_node':
            f['nodes']['profile-991099'] = {}
        elif corruption == 'extra_union':
            f['nodes']['union-991099'] = {}
        elif corruption == 'bad_url':
            f['nodes'][u]['url'] += '?ZZ=1'
        elif corruption == 'bad_role':
            f['nodes'][u]['edges'][ANCHOR]['rel'] = 'foster_child'
        elif corruption == 'missing_reverse':
            f['nodes'][ANCHOR]['edges'] = {}
        elif corruption == 'adoption':
            f['nodes'][u]['adopted_children'] = [ANCHOR]
        elif corruption == 'foster':
            f['focus']['foster_children'] = []
        else:
            f['nodes'][u]['edges']['profile-991099'] = {'rel': 'partner'}
        return f
    io.get_family = bad
    r, io, st, _ = execute(c, io, st)
    assert r['phase'] == 'STOPPED' and len(io.posts) == int(post)
    assert len(st.consumed) == int(post)


@pytest.mark.parametrize('change', ['private', 'living', 'names', 'merge'])
def test_profile_mismatch_stops_before_send(change):
    c, io = plan(), IO(plan())
    if change == 'private':
        io.profiles[ANCHOR]['public'] = True
    elif change == 'living':
        io.profiles[ANCHOR]['is_alive'] = False
    elif change == 'names':
        io.profiles[ANCHOR]['names'] = {}
    else:
        io.profiles[ANCHOR]['merge_pending'] = True
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts and not st.events


def test_send_exception_consumed_uncertain_no_repair():
    io = IO(plan())

    def fail(*a):
        io.posts.append(a)
        raise OSError('ZZ-lost-ack')
    io.add_parent = fail
    r, io, st, _ = execute(plan(), io)
    assert r['item']['phase'] == 'UNCERTAIN' and len(st.consumed) == 1
    assert len(io.posts) == 1 and r['phase'] == 'STOPPED'


@pytest.mark.parametrize('which', ['profile', 'union', 'new_family'])
def test_post_create_verification_failure_stays_consumed(which):
    io = IO(plan())
    if which == 'profile':
        original = io.get_profile
        io.get_profile = lambda p: dict(original(p), public=True) if p == NEW else original(p)
    elif which == 'union':
        io.get_union = lambda u: {'id': u, 'partners': [], 'children': [ANCHOR]}
    else:
        original = io.get_family
        io.get_family = lambda p: {'focus': {'id': p}, 'nodes': {}} if p == NEW else original(p)
    r, io, st, _ = execute(plan(), io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == len(st.consumed) == 1
    assert r['item']['phase'] == 'ACKNOWLEDGED_NOT_VERIFIED'


def test_capture_failure_before_create_has_no_remote_writes():
    io, st = IO(plan()), Store()

    def fail(r):
        raise OSError('ZZ-encryption-failure')
    with pytest.raises(OSError):
        execute(plan(), io, st, save=fail)
    assert io.reads == [('profile', 'profile')] and not io.posts and not st.events


def test_marker_is_anchor_payload_bound_not_union_or_window():
    c = plan()
    m = b.marker(c)
    c['expires_at'] += 100
    assert b.marker(c) == m
    c['anchor'] = 'profile-991099'
    assert b.marker(c) != m


@pytest.mark.parametrize('vendor_life_status', [True, False, None])
def test_unknown_source_life_status_not_asserted_or_invented(vendor_life_status):
    c = plan()
    c['entry']['payload']['is_alive'] = None
    io = IO(c)
    original = io.add_parent

    def add(*args):
        result = original(*args)
        assert 'is_alive' not in io.posts[0][1]
        if vendor_life_status is not None:
            io.profiles[NEW]['is_alive'] = vendor_life_status
        return result
    io.add_parent = add
    r, _, _, _ = execute(c, io)
    assert r['phase'] == 'VERIFIED' and r['item']['source_life_status'] is None
    assert c['entry']['payload']['is_alive'] is None


def test_unknown_life_still_requires_private_and_explicit_null():
    c = plan()
    del c['entry']['payload']['is_alive']
    with pytest.raises(b.Blocked):
        b.plan(c)
    c['entry']['payload']['is_alive'] = None
    c['entry']['payload']['public'] = True
    with pytest.raises(b.Blocked):
        b.plan(c)


def test_expiry_after_consume_blocks_send_permanently():
    c, io = plan(), IO(plan())
    st = Store()
    original = st.consume
    expired = []

    def consume(marker):
        original(marker)
        expired.append(True)
    st.consume = consume
    r, io, st, _ = execute(c, io, st, clock=lambda: 999 if expired else 200)
    assert r['phase'] == 'STOPPED' and not io.posts and len(st.consumed) == 1


def test_owner_wrong_identity_stops_before_other_reads():
    c, io = plan(), IO(plan())
    io.profiles[OWNER]['id'] = SPOUSE
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and io.reads == [('profile', 'profile')]
    assert not st.events and not io.posts


def test_first_parent_two_new_unions_fail_before_any_union_read():
    c, io = plan(), IO(plan())
    original = io.get_family

    def bad(p):
        f = original(p)
        if io.posts and p == ANCHOR:
            f['nodes']['union-991099'] = {}
        return f
    io.get_family = bad
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(st.consumed) == 1
    assert not any(kind == 'union' for kind, _ in io.reads)


def test_established_owner_without_bilingual_names_is_pinned_not_rewritten():
    c = plan()
    c['profiles'][OWNER] = {'first_name': 'ZZ-Root', 'last_name': 'ZZ-Family',
        'gender': 'male', 'public': False, 'is_alive': True}
    r, io, _, _ = execute(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert io.posts[0][0] == ANCHOR


@pytest.mark.parametrize('change', [{'public': True}, {'is_alive': None},
    {'extra': 'ZZ'}, {'first_name': ''}])
def test_established_profile_snapshot_still_closed_and_private(change):
    v = {'first_name': 'ZZ-Root', 'gender': 'male', 'public': False, 'is_alive': True}
    v.update(change)
    with pytest.raises(b.Blocked):
        b.existing_payload(v)


def test_pinned_boundary_edge_required_not_unknown_or_wrong_role():
    c = plan()
    members = {ANCHOR: 'child', NEW: 'partner'}
    f = family(NEW, {PARENTS: members})
    extra = b.boundary_edges(c, PARENTS, members)
    with pytest.raises(b.Blocked):
        b.graph_check(f, NEW, {PARENTS: members}, external_edges=extra)
    f['nodes'][ANCHOR]['edges'][FAMILY] = {'rel': 'partner'}
    b.graph_check(f, NEW, {PARENTS: members}, external_edges=extra)
    for edge in ({'rel': 'child'}, {'rel': 'partner', 'ZZ': 1}):
        f['nodes'][ANCHOR]['edges'][FAMILY] = edge
        with pytest.raises(b.Blocked):
            b.graph_check(f, NEW, {PARENTS: members}, external_edges=extra)
    f['nodes'][ANCHOR]['edges'][FAMILY] = {'rel': 'partner'}
    f['nodes'][ANCHOR]['edges']['union-991099'] = {'rel': 'partner'}
    with pytest.raises(b.Blocked):
        b.graph_check(f, NEW, {PARENTS: members}, external_edges=extra)


@pytest.mark.parametrize('field,value', [('existing_parent', OWNER), ('existing_parent', ANCHOR)])
def test_existing_parent_distinctness(field, value):
    c = plan(True)
    c[field] = value
    with pytest.raises(b.Blocked):
        b.plan(c)


def test_second_parent_gender_and_expected_owner_name():
    c = plan(True)
    c['entry']['payload']['gender'] = c['profiles'][OLD]['gender']
    with pytest.raises(b.Blocked):
        b.plan(c)
    c = plan()
    c['expect_name'] = 'ZZ-Wrong ZZ-Identity'
    result, io, _, _ = execute(c)
    assert result['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('change', ['duplicates', 'adopted', 'foster'])
def test_direct_union_duplicate_or_nonbiological_member_rejected(change):
    x = {'id': PARENTS, 'partners': [NEW], 'children': [ANCHOR]}
    if change == 'duplicates':
        x['children'].append(ANCHOR)
    else:
        x[change+'_children'] = [ANCHOR]
    with pytest.raises(b.Blocked):
        b.direct_union_check(x, PARENTS, {NEW: 'partner', ANCHOR: 'child'})


def test_preconsume_expiry_no_marker_or_post():
    c, io, st = plan(), IO(plan()), Store()
    expired = []
    original = st.receipt

    def receipt(*args):
        original(*args)
        expired.append(True)
    st.receipt = receipt
    result, io, st, _ = execute(c, io, st, clock=lambda: 999 if expired else 200)
    assert result['phase'] == 'STOPPED' and not io.posts and not st.consumed


EXTERNAL = 'union-991088'


@pytest.mark.parametrize('existing', [False, True])
def test_exact_spouse_parent_boundary_preserved(existing):
    c = plan(existing)
    c['external_edges'] = {SPOUSE: {EXTERNAL: 'child'}}
    original = copy.deepcopy(c)
    r, io, st, _ = execute(c)
    assert r['phase'] == 'VERIFIED' and len(io.posts) == 1
    assert st.events == ['before', 'consume', 'ack', 'final']
    assert c == original
    assert all(target != EXTERNAL for _, target in io.reads)


@pytest.mark.parametrize('boundary', [None, [], {OWNER: {EXTERNAL: 'child'}},
    {ANCHOR: {EXTERNAL: 'child'}}, {OLD: {EXTERNAL: 'child'}},
    {SPOUSE: {}}, {SPOUSE: {EXTERNAL: 'partner'}},
    {SPOUSE: {FAMILY: 'child'}}, {SPOUSE: {'union-ZZ': 'child'}},
    {SPOUSE: {EXTERNAL: 'child', 'union-991089': 'child'}},
    {SPOUSE: {EXTERNAL: {'rel': 'child'}}}])
def test_invalid_spouse_boundary_rejected_before_reads(boundary):
    c = plan()
    c['external_edges'] = boundary
    io = IO(c)
    with pytest.raises(b.Blocked):
        execute(c, io)
    assert not io.reads and not io.posts


@pytest.mark.parametrize('post', [False, True])
@pytest.mark.parametrize('corruption', ['missing', 'wrong_role', 'extra', 'materialized'])
def test_spouse_boundary_mismatch_stops_at_exact_graph(post, corruption):
    c = plan()
    c['external_edges'] = {SPOUSE: {EXTERNAL: 'child'}}
    io = IO(c)
    original = io.get_family

    def bad(p):
        f = original(p)
        if p != ANCHOR or bool(io.posts) != post:
            return f
        edges = f['nodes'][SPOUSE]['edges']
        if corruption == 'missing':
            del edges[EXTERNAL]
        elif corruption == 'wrong_role':
            edges[EXTERNAL] = {'rel': 'partner'}
        elif corruption == 'extra':
            edges['union-991089'] = {'rel': 'child'}
        else:
            f['nodes'][EXTERNAL] = {}
        return f
    io.get_family = bad
    r, io, st, _ = execute(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == int(post)
    assert len(st.consumed) == int(post)
    assert not any(kind == 'union' for kind, _ in io.reads)


def test_boundary_and_window_never_reset_consumption_marker():
    c = plan()
    old = b.marker(c)
    c['external_edges'] = {SPOUSE: {EXTERNAL: 'child'}}
    c['expires_at'] += 100
    assert b.marker(c) == old
    _, _, store, _ = execute(c)
    c['external_edges'] = {}
    r, io, _, _ = execute(c, st=store)
    assert r['phase'] == 'STOPPED' and not io.posts
