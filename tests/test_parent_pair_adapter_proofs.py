"""Independent synthetic batch adapter admission proofs. Refs #789."""
import pytest

from geni_uploader.runners.one_time_parent_pilot import canonical, sha
from tests import test_bounded_parent_pair_batch as f
from tests.test_protected_parent_pair_batch import Private, execute, p, source_fixture


def resign(cfg, audit):
    cfg['overlap_sha256'] = sha(canonical(audit))


@pytest.mark.parametrize('fault', ['plan_hash_only', 'audit_plan_sha', 'audit_owner',
    'audit_schema', 'audit_risk_empty', 'audit_short', 'op_anchor', 'op_kind', 'op_payload'])
def test_audit_binding_each_check_independent(fault):
    cfg, c, audit = source_fixture()
    op = audit['operations'][0]
    if fault == 'plan_hash_only':  # audit agrees with cfg; only the plan bytes disagree
        cfg['plan_sha256'] = audit['plan_sha256'] = '0' * 64
    if fault == 'audit_plan_sha': audit['plan_sha256'] = '0' * 64
    if fault == 'audit_owner': audit['owner'] = 'profile-990004'
    if fault == 'audit_schema': audit['schema'] = 2
    if fault == 'audit_risk_empty': audit['risk_source_refs'] = []
    if fault == 'audit_short': audit['operations'].pop()
    if fault == 'op_anchor': op['anchor'] = 'profile-990004'
    if fault == 'op_kind': op['kind'] = 'sibling' if op['kind'] == 'parent' else 'parent'
    if fault == 'op_payload': op['payload_sha256'] = '0' * 64
    resign(cfg, audit)
    with pytest.raises(p.core.Blocked):
        p.admit_source(p.config(cfg), Private(cfg, c, audit))


@pytest.mark.parametrize('fault', ['overlap_is_data', 'max_over_ceiling', 'new_merge_int'])
def test_config_rejects(fault):
    cfg, _c, _audit = source_fixture()
    if fault == 'overlap_is_data': cfg['overlap_path'] = cfg['data_path']
    if fault == 'max_over_ceiling': cfg['max_requests'] = p.HARD_REQUEST_CEILING + 1
    if fault == 'new_merge_int': cfg['allow_new_unknown_merge'] = 1
    with pytest.raises(p.core.Blocked):
        p.config(cfg)

PROFILE_GET = '/api/profile?fields=' + p.FIELDS + '&only_ids=true'


@pytest.mark.parametrize('limit', ['inventory', 'max_requests', 'hard'])
def test_each_request_budget_blocks_on_its_own(limit, monkeypatch):
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    c = f.config(); c['max_requests'] = p.core.inventory(c)
    v = p.ScopedVendor('ZZ-token-123', c)
    if limit == 'inventory':
        v.plan['max_requests'] = p.HARD_REQUEST_CEILING; v.calls = p.core.inventory(v.plan)
    if limit == 'max_requests':
        v.plan['max_requests'] = 1; v.calls = 1
    if limit == 'hard':
        monkeypatch.setattr(p.core, 'inventory', lambda _plan: 10 ** 6)
        v.plan['max_requests'] = 10 ** 6; v.calls = p.HARD_REQUEST_CEILING
    before = v.calls
    with pytest.raises(p.core.Blocked):
        v.admit_vendor('GET', PROFILE_GET)
    assert v.calls == before


def test_pending_union_read_must_be_the_proof_derived_union():
    def mutate(client, backend, io):
        old = io.get_union
        io.get_union = lambda u: old('union-980004' if client.pending else u)
    r, c, b, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'STOPPED' and c.pending and len(b.posts) == 1


def test_bad_anchor_proof_on_second_operation_same_anchor():
    def mutate(client, backend, io):
        old = io.get_union
        def get(u):
            if client.pending and client.post_count == 2:
                io.anchor_proof['nodes'].pop(io.active['id'])
            return old(u)
        io.get_union = get
    r, c, b, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'STOPPED' and c.pending and len(b.posts) == 2


@pytest.mark.parametrize('ack', ['error_with_id', 'repeated_id'])
def test_ack_admission_rejects(ack):
    def mutate(client, backend, io):
        old = backend.add
        def add(anchor, body, role):
            value = old(anchor, body, role)
            if ack == 'error_with_id': value['error'] = 'ZZ-vendor-error'
            if ack == 'repeated_id' and client.created: value['id'] = client.created[0]
            return value
        backend.add = add
    r, c, b, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'STOPPED' and c.pending
    assert len(b.posts) == (1 if ack == 'error_with_id' else 2)


def test_cross_group_boundary_propagates_to_visible_anchor():
    import copy

    observed = []
    def mutate(client, backend, io):
        old = io.get_union
        def get(union):
            anchor = io.active['anchor'] if client.pending else None
            if anchor and client.post_count == 1:
                # A synthetic other-group proof graph sees this existing anchor.
                # No extra transport route or traversal is admitted.
                observer = 'profile-990004'
                io.graphs[observer] = copy.deepcopy(io.graphs[anchor])
                io.boundaries[observer] = {}
                value = old(union)
                observed.append(io.boundaries[observer][anchor][union])
                del io.graphs[observer]
                del io.boundaries[observer]
                return value
            return old(union)
        io.get_union = get
    r, client, backend, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'VERIFIED' and not client.pending
    assert len(backend.posts) == 3 and observed == ['child']
