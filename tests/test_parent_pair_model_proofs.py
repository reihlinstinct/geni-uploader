"""Independent synthetic batch model proof checks. Refs #788."""
import copy

import pytest

from tests.test_bounded_parent_pair_batch import IO, config, four_groups, m, run


def entry(key, name, gender):
    from tests.test_bounded_parent_pair_batch import f
    return {'key': key, 'payload': f.fixture.body(name, gender)}


@pytest.mark.parametrize('change', ['schema', 'three_entries', 'same_anchor_twice',
    'two_siblings', 'key_format', 'sibling_payload'])
def test_plan_rejects_each_shape_alone(change):
    c = config(); g = c['groups'][0]
    if change == 'schema': c['schema'] = 2
    if change == 'three_entries': g['entries'].append(entry('zz-third', 'ZZ-Third', 'female'))
    if change == 'same_anchor_twice':
        g2 = copy.deepcopy(g); g2['sibling'] = None
        g2['entries'] = [entry('zz-a', 'ZZ-A', 'male'), entry('zz-b', 'ZZ-B', 'female')]
        c['groups'].append(g2)
    if change == 'two_siblings':
        c = four_groups()
        c['groups'][0]['sibling'] = entry('zz-sib-two', 'ZZ-Sib-Two', 'male')
    if change == 'key_format': g['sibling']['key'] = 'ZZ_Upper'
    if change == 'sibling_payload': g['sibling']['payload']['is_alive'] = None
    with pytest.raises(m.Blocked):
        m.plan(c)


def test_owner_name_mismatch_stops_before_any_read_of_others_or_send():
    c = config(); c['expect_name'] = 'Zzunrelated Zzperson'
    r, io, _, _ = run(c)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('where,posts', [('path_baseline', 0), ('anchor_before_second', 1),
    ('anchor_after_second', 2), ('created_reciprocal', 1)])
def test_each_family_proof_blocks_on_its_own(where, posts):
    c = config(); io = IO(c); g = c['groups'][0]; anchor = g['anchor']
    state = {'unions_after_first': 0, 'anchor_reads_after_second': 0}
    old_union = io.get_union
    def union(u):
        if len(io.posts) == 1: state['unions_after_first'] += 1
        return old_union(u)
    io.get_union = union
    old = io.get_family
    def get(n):
        v = old(n)
        hit = False
        if where == 'path_baseline':
            hit = not io.posts and n == g['path'][0] != anchor
        if where == 'anchor_before_second':
            hit = n == anchor and len(io.posts) == 1 and state['unions_after_first'] == 1
        if where == 'anchor_after_second' and n == anchor and len(io.posts) == 2:
            state['anchor_reads_after_second'] += 1
            hit = state['anchor_reads_after_second'] == 1
        if where == 'created_reciprocal':
            hit = len(io.posts) == 1 and n not in g['profiles']
        if hit:
            v['nodes'][n]['edges']['union-980004'] = {'rel': 'partner'}
        return v
    io.get_family = get
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == posts, (r['stage'], len(io.posts))


def test_path_union_extra_member_stops_before_send():
    c = config(); io = IO(c); u = c['groups'][0]['path_unions'][0]
    io.unions[u]['profile-990004'] = 'child'
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and not io.posts


def test_error_ack_with_valid_id_stops():
    c = config(); io = IO(c); old = io.add_parent
    io.add_parent = lambda a, b: dict(old(a, b), error='ZZ-vendor-error')
    r, io, _, _ = run(c, io)
    assert r['phase'] == 'STOPPED' and len(io.posts) == 1


