"""Synthetic proof-latch adapter tests. Real HTTP construction seam patched."""
import copy
from unittest.mock import patch

import pytest

from geni_uploader.runners import protected_parent_pair_batch as p
from tests import test_bounded_parent_pair_batch as f


def setup(c=None):
    c = c or f.config(); c['max_requests'] = p.core.inventory(c)
    client = p.ScopedVendor('ZZ-token-123', c); backend = f.IO(c)
    io = p.IO(client)
    def request(method, route, body=None):
        client.admit_vendor(method, route)
        target = route.split('/api/', 1)[1].split('?', 1)[0]
        if method == 'POST':
            anchor, operation = target.split('/')
            return getattr(backend, operation.replace('-', '_'))(anchor, body)
        if target.endswith('/immediate-family'): return backend.get_family(target.split('/')[0])
        if target.startswith('union-'): return backend.get_union(target)
        return backend.get_profile(target)
    client.request = request
    return c, client, backend, io


def execute(c=None, mutate=None):
    with patch.object(p.time, 'time', lambda: 200), patch.object(p.time, 'monotonic', lambda: 0), \
            patch.object(p.time, 'sleep'):
        c, client, backend, io = setup(c)
        if mutate: mutate(client, backend, io)
        st = f.Store(); saved = []
        r = p.core.execute(c, io, st, lambda x: saved.append(copy.deepcopy(x)) or b'ZZ-cipher', lambda: 200)
        return r, client, backend, io, st


@pytest.mark.parametrize('four', [False, True])
def test_adapter_full_proof_batch(four):
    r, c, b, _, st = execute(f.four_groups() if four else None)
    assert r['phase'] == 'VERIFIED', (r['stage'], r['group'])
    assert len(b.posts) == len(st.consumed) == (9 if four else 3)
    assert not c.pending and c.calls == r['requests']


@pytest.mark.parametrize('missing', ['profile_proof', 'anchor_proof', 'reciprocal_proof'])
def test_ack_or_incomplete_proof_never_reopens_send(missing):
    def mutate(client, backend, io):
        old = io.get_union
        def get(u):
            if client.pending: setattr(io, missing, None)
            return old(u)
        io.get_union = get
    r, c, b, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'STOPPED' and c.pending and len(b.posts) == 1


@pytest.mark.parametrize('which', ['profile', 'anchor', 'reciprocal', 'union'])
def test_bad_cached_proofs_keep_latch_closed(which):
    def mutate(client, backend, io):
        old = io.get_union
        def get(u):
            if client.pending:
                if which == 'profile': io.profile_proof['public'] = True
                if which == 'anchor': io.anchor_proof['nodes'].pop(io.active['id'])
                if which == 'reciprocal': io.reciprocal_proof['nodes'].pop(io.active['id'])
                if which == 'union': backend.unions[u]['profile-990004'] = 'child'
            return old(u)
        io.get_union = get
    r, c, b, _, _ = execute(mutate=mutate)
    assert r['phase'] == 'STOPPED' and c.pending and len(b.posts) == 1


def test_raw_post_route_rejects_second_send_after_ack():
    with patch.object(p.time, 'time', lambda: 200), patch.object(p.time, 'sleep'):
        _, c, _, io = setup(); g = c.plan['groups'][0]
        io.add_parent(g['anchor'], p.graph.vendor_parent_payload(g['entries'][0]['payload']))
        with pytest.raises(p.core.Blocked): c.admit_vendor('POST', '/api/' + g['anchor'] + '/add-parent')
        assert c.pending and c.post_count == 1


def test_exact_payload_and_operation_order_before_post():
    with patch.object(p.time, 'time', lambda: 200):
        _, c, b, io = setup(); g = c.plan['groups'][0]
        with pytest.raises(p.core.Blocked): io.add_sibling(g['anchor'], g['sibling']['payload'])
        with pytest.raises(p.core.Blocked): io.add_parent(g['anchor'], {'first_name': 'ZZ'})
        assert not b.posts and c.post_count == 0


@pytest.mark.parametrize('method,route', [('GET', '/api/profile-990004?only_ids=true'),
    ('GET', '/api/union-980004?only_ids=true'), ('POST', '/api/profile-990004/add-parent'),
    ('DELETE', '/api/profile'), ('GET', 'https://evil.invalid/')])
def test_real_connection_guard_before_network(method, route, monkeypatch):
    import geni_uploader.runners.one_time_parent_pilot as transport
    monkeypatch.setattr(p.time, 'time', lambda: 200)
    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', lambda *_a, **_k:
                        (_ for _ in ()).throw(AssertionError('ZZ network forbidden')))
    c = f.config(); c['max_requests'] = p.core.inventory(c); v = p.ScopedVendor('ZZ-token-123', c)
    with pytest.raises(p.core.Blocked): v.request(method, route)
    assert v.calls == 0


def test_expiry_after_wait_consumes_but_never_connects(monkeypatch):
    now = [200]
    monkeypatch.setattr(p.time, 'time', lambda: now[0])
    monkeypatch.setattr(p.time, 'monotonic', lambda: 0)
    monkeypatch.setattr(p.time, 'sleep', lambda _: now.__setitem__(0, 1000))
    c = f.config(); c['max_requests'] = p.core.inventory(c); v = p.ScopedVendor('ZZ-token-123', c)
    v.last = 0
    with pytest.raises(p.core.Blocked): v.admit_vendor('GET', '/api/profile?fields=' + p.FIELDS + '&only_ids=true')
    assert v.calls == 1


def test_protected_ceiling_lower_than_model():
    c = f.config(); c['max_requests'] = 121
    with pytest.raises(p.core.Blocked): p.ScopedVendor('ZZ-token-123', c)


def source_fixture():
    from geni_uploader.runners.one_time_parent_pilot import canonical, sha
    c = f.config(); c['max_requests'] = p.core.inventory(c)
    audit = {'schema': 1, 'owner': c['owner'], 'plan_sha256': sha(canonical(c)),
             'operations': [], 'risk_source_refs': ['ZZ-owner-risk-source']}
    for g in c['groups']:
        for kind, e in [('parent', x) for x in g['entries']] + [('sibling', g['sibling'])]:
            audit['operations'].append({'anchor': g['anchor'], 'kind': kind,
                'entry_key': e['key'], 'payload_sha256': sha(canonical(e['payload'])),
                'source_refs': ['ZZ-fact-source'], 'prior_review_refs': ['ZZ-prior-operation-audit'],
                'overlapping_markers': []})
    cfg = {'schema': 1, 'data_repo': 'ZZ/tree', 'data_sha': 'a' * 40,
           'data_path': 'ZZ-plan.json', 'owner': c['owner'], 'expect_name': c['expect_name'],
           'recipient': 'age1' + 'a' * 58, 'allow_unknown_merge': True,
           'allow_new_unknown_merge': True, 'accept_hidden_parent_risk': True,
           'accept_private_create_risk': True, 'expires_at': 999,
           'plan_sha256': sha(canonical(c)), 'max_requests': c['max_requests'],
           'overlap_path': 'ZZ-audit.json', 'overlap_sha256': sha(canonical(audit))}
    return cfg, c, audit


class Private:
    def __init__(self, cfg, plan, audit):
        self.documents = {cfg['data_path']: plan, cfg['overlap_path']: audit}
    def load(self, path): return copy.deepcopy(self.documents[path])


def test_immutable_admission_and_risk_crosspins():
    cfg, c, audit = source_fixture()
    assert p.admit_source(p.config(cfg), Private(cfg, c, audit)) == c


@pytest.mark.parametrize('fault', ['plan_hash', 'audit_hash', 'owner', 'new_policy',
    'overlap', 'source_missing', 'wrong_key', 'budget'])
def test_source_admission_blocks_before_vendor(fault):
    from geni_uploader.runners.one_time_parent_pilot import canonical, sha
    cfg, c, audit = source_fixture()
    if fault == 'plan_hash': cfg['plan_sha256'] = '0' * 64
    if fault == 'audit_hash': cfg['overlap_sha256'] = '0' * 64
    if fault == 'owner': cfg['owner'] = 'profile-990004'
    if fault == 'new_policy': cfg['allow_new_unknown_merge'] = False
    if fault == 'budget': cfg['max_requests'] += 1
    if fault == 'overlap': audit['operations'][0]['overlapping_markers'] = ['ZZ-consumed']
    if fault == 'source_missing': audit['operations'][0]['source_refs'] = []
    if fault == 'wrong_key': audit['operations'][0]['entry_key'] = 'ZZ-wrong'
    if fault in ('overlap', 'source_missing', 'wrong_key'):
        cfg['overlap_sha256'] = sha(canonical(audit))
    with pytest.raises(p.core.Blocked): p.admit_source(p.config(cfg), Private(cfg, c, audit))


def test_actual_private_git_base64_decoder_boundary():
    import base64

    from geni_uploader.runners.one_time_parent_pilot import PrivateGit, canonical
    cfg, c, audit = source_fixture()
    calls = []
    class Git:
        def request(self, method, route, body=None):
            calls.append((method, route))
            assert method == 'GET' and body is None
            if '/contents/' not in route: return {'private': True, 'full_name': cfg['data_repo']}
            doc = audit if cfg['overlap_path'] in route else c
            raw = canonical(doc)
            return {'type': 'file', 'encoding': 'base64', 'size': len(raw),
                    'content': base64.b64encode(raw).decode()}
    private = PrivateGit(Git(), cfg['data_repo'], cfg['data_sha'], cfg['owner'])
    assert p.admit_source(p.config(cfg), private) == c
    assert len(calls) == 4 and all(x[0] == 'GET' for x in calls)


def test_batch_profile_reads_explicitly_request_claimed_without_legacy_change():
    from geni_uploader.runners.one_time_parent_pilot import FIELDS as legacy_fields
    from geni_uploader.runners.protected_parent_addition import FIELDS as parent_fields
    assert 'claimed' not in legacy_fields.split(',')
    assert parent_fields == legacy_fields
    assert p.FIELDS.split(',').count('claimed') == 1
    c = f.config(); c['max_requests'] = p.core.inventory(c)
    client = p.ScopedVendor('ZZ-token-123', c); calls = []
    client.request = lambda method, route, body=None: calls.append((method, route)) or {'ZZ': True}
    io = p.IO(client)
    assert io.get_profile('profile') == {'ZZ': True}
    assert calls == [('GET', '/api/profile?fields=' + p.FIELDS + '&only_ids=true')]


def test_legacy_profile_route_without_claimed_rejected_before_transport():
    from geni_uploader.runners.one_time_parent_pilot import FIELDS as legacy_fields
    with patch.object(p.time, 'time', lambda: 200):
        c = f.config(); c['max_requests'] = p.core.inventory(c)
        client = p.ScopedVendor('ZZ-token-123', c)
        with pytest.raises(p.core.Blocked):
            client.admit_vendor('GET', '/api/profile?fields=' + legacy_fields + '&only_ids=true')
        assert client.calls == 0


@pytest.mark.parametrize('created', [False, True])
def test_claimed_omission_still_blocks_before_any_next_write(created):
    def mutate(client, backend, io):
        if not created:
            backend.profiles[client.plan['owner']].pop('claimed')
        else:
            original = backend.get_profile
            def get_profile(target):
                value = original(target)
                if target in client.created: value.pop('claimed', None)
                return value
            backend.get_profile = get_profile
    result, client, backend, _, _ = execute(mutate=mutate)
    assert result['phase'] == 'STOPPED'
    assert len(backend.posts) == (1 if created else 0)
    assert client.pending is created
