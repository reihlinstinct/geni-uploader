"""Isolated batch adapter candidate. No invocation until protected run admission."""
import copy
import time

from geni_uploader.core import bounded_parent_pair_batch as core
from geni_uploader.core.people import require
from geni_uploader.runners import bounded_parent_addition as graph
from geni_uploader.runners import bounded_relative_parent as profile
from geni_uploader.runners.one_time_parent_pilot import FIELDS as LEGACY_FIELDS
from geni_uploader.runners.one_time_parent_pilot import HTTPS
from geni_uploader.runners.protected_parent_addition import IO as ParentIO

HARD_REQUEST_CEILING = 120
# This adapter requires claimed as a served boolean. Do not weaken the check or
# change legacy runners: explicitly request the field on this isolated route.
FIELDS = LEGACY_FIELDS + ",claimed"


class ScopedVendor(HTTPS):
    def __init__(self, token, value):
        self.plan = core.plan(value)
        require(core.inventory(self.plan) <= HARD_REQUEST_CEILING
                and self.plan['max_requests'] <= HARD_REQUEST_CEILING)
        super().__init__('www.geni.com', token, capture_failure=True)
        self.operations = []
        for g in self.plan['groups']:
            self.operations.extend((g['anchor'], 'parent', e) for e in g['entries'])
            if g['sibling'] is not None:
                self.operations.append((g['anchor'], 'sibling', g['sibling']))
        self.profiles = {'profile', *(n for g in self.plan['groups'] for n in g['profiles'])}
        self.families = {n for g in self.plan['groups'] for n in g['path']}
        self.unions = {u for g in self.plan['groups'] for u in g['path_unions']}
        self.post_count = 0
        self.pending = False
        self.created = []

    def admit_vendor(self, method, route):
        require(self.calls < core.inventory(self.plan)
                and self.calls < self.plan['max_requests']
                and self.calls < HARD_REQUEST_CEILING and time.time() < self.plan['expires_at'])
        if method == 'GET':
            allowed = {'/api/' + p + '?fields=' + FIELDS + '&only_ids=true' for p in self.profiles}
            allowed |= {'/api/' + p + '/immediate-family?only_ids=true' for p in self.families}
            allowed |= {'/api/' + u + '?only_ids=true' for u in self.unions}
            require(route in allowed)
        else:
            require(method == 'POST' and not self.pending and self.post_count < len(self.operations))
            anchor, kind, _ = self.operations[self.post_count]
            require(route == '/api/' + anchor + '/add-' + kind)
            # Never reopen on ACK or an exception. Only independently verified proofs.
            self.pending = True
            self.post_count += 1
        self.calls += 1  # consume before waiting/transport; never retry after expiry
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.plan['expires_at'])
        self.last = time.monotonic()


class IO(ParentIO):
    def __init__(self, client, *, debug=False):
        super().__init__(client, debug=debug)
        self.graphs = {g['anchor']: copy.deepcopy(g['family']) for g in client.plan['groups']}
        self.boundaries = {g['anchor']: copy.deepcopy(g['external_edges']) for g in client.plan['groups']}
        self.targets = {}
        self.active = None
        self.profile_proof = self.anchor_proof = self.reciprocal_proof = None

    def get_profile(self, target):
        actual = self.request('GET', '/api/' + target + '?fields=' + FIELDS + '&only_ids=true')
        if self.active and target == self.active['id']:
            profile.profile_check(actual, self.active['entry']['payload'], target,
                                  self.client.plan['allow_new_unknown_merge'], created=True)
            self.profile_proof = copy.deepcopy(actual)
        return actual

    def get_family(self, target):
        actual = self.request('GET', '/api/' + target + '/immediate-family?only_ids=true')
        if self.active:
            if target == self.active['anchor']: self.anchor_proof = copy.deepcopy(actual)
            if target == self.active['id']: self.reciprocal_proof = copy.deepcopy(actual)
        return actual

    def bind_union(self):
        a = self.active
        require(a is not None and self.anchor_proof is not None)
        anchor, created = a['anchor'], a['id']
        expected = copy.deepcopy(self.graphs[anchor])
        target = self.targets.get(anchor)
        if target is None:
            group = next(g for g in self.client.plan['groups'] if g['anchor'] == anchor)
            spec = dict(group, family=copy.deepcopy(self.graphs[anchor]),
                        external_edges=copy.deepcopy(self.boundaries[anchor]),
                        parent_union=None, existing_parent=None)
            target, members = profile.parent_union_after(self.anchor_proof, spec, created)
            expected[target] = members
        else:
            expected[target][created] = 'partner' if a['kind'] == 'parent' else 'child'
            graph.graph_check(self.anchor_proof, anchor, expected,
                              external_edges=self.boundaries[anchor])
        return target, expected

    def get_union(self, target):
        if self.client.pending:
            a = self.active
            require(a is not None and self.profile_proof is not None
                    and self.reciprocal_proof is not None)
            profile.profile_check(self.profile_proof, a['entry']['payload'], a['id'],
                                  self.client.plan['allow_new_unknown_merge'], created=True)
            union, expected = self.bind_union()
            require(target == union)
            boundary = graph.boundary_edges(
                {'family': expected, 'external_edges': self.boundaries[a['anchor']]},
                union, expected[union])
            graph.graph_check(self.reciprocal_proof, a['id'], {union: expected[union]},
                              external_edges=boundary)
            self.client.unions.add(union)  # only proof-derived, never response URL
            actual = self.request('GET', '/api/' + union + '?only_ids=true')
            graph.direct_union_check(actual, union, expected[union])
            self.targets[a['anchor']] = union
            self.graphs[a['anchor']] = expected
            for other, spec in self.graphs.items():
                if other != a['anchor'] and a['anchor'] in {p for m in spec.values() for p in m}:
                    self.boundaries[other].setdefault(a['anchor'], {})[union] = 'child'
            self.client.pending = False
            self.active = None
            return actual
        require(target in self.client.unions)
        return self.request('GET', '/api/' + target + '?only_ids=true')

    def add(self, anchor, body, kind):
        c = self.client
        require(not c.pending and c.post_count < len(c.operations))
        expected_anchor, expected_kind, entry = c.operations[c.post_count]
        require(anchor == expected_anchor and kind == expected_kind
                and body == graph.vendor_parent_payload(entry['payload']))
        self.profile_proof = self.anchor_proof = self.reciprocal_proof = None
        actual = self.request('POST', '/api/' + anchor + '/add-' + kind, body)
        # This ACK-derived route admission is not a verification or latch release.
        require(type(actual) is dict and 'error' not in actual)
        created = actual.get('id'); core.profile_id(created)
        visible = {p for g in c.plan['groups'] for b in g['path_families'].values()
                   for m in b['family'].values() for p in m}
        require(created not in visible and created not in c.profiles)
        c.created.append(created); c.profiles.add(created); c.families.add(created)
        self.active = {'anchor': anchor, 'kind': kind, 'entry': copy.deepcopy(entry), 'id': created}
        return actual

    def add_parent(self, anchor, body): return self.add(anchor, body, 'parent')
    def add_sibling(self, anchor, body): return self.add(anchor, body, 'sibling')


def config(value):
    import re

    from geni_uploader.core.people import exact
    from geni_uploader.runners.one_time_parent_pilot import configuration
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'allow_unknown_merge', 'allow_new_unknown_merge',
                  'accept_hidden_parent_risk', 'accept_private_create_risk', 'expires_at',
                  'plan_sha256', 'max_requests', 'overlap_path', 'overlap_sha256'))
    configuration({k: v for k, v in value.items() if k not in
                   ('allow_new_unknown_merge', 'plan_sha256', 'max_requests',
                    'overlap_path', 'overlap_sha256')})
    require(type(value['allow_new_unknown_merge']) is bool
            and type(value['max_requests']) is int
            and 1 <= value['max_requests'] <= HARD_REQUEST_CEILING)
    for key in ('plan_sha256', 'overlap_sha256'):
        require(type(value[key]) is str and re.fullmatch(r'[a-f0-9]{64}', value[key]))
    require(type(value['overlap_path']) is str and re.fullmatch(
        r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.json', value['overlap_path'])
        and '..' not in value['overlap_path'] and value['overlap_path'] != value['data_path'])
    return copy.deepcopy(value)


def admit_source(c, private):
    """Real immutable decode/hash boundary; no vendor object or token needed here."""
    from geni_uploader.core.people import exact
    from geni_uploader.runners.one_time_parent_pilot import canonical, sha
    approved = private.load(c['data_path'])
    require(sha(canonical(approved)) == c['plan_sha256'])
    approved = core.plan(approved)
    require(all(approved[k] == c[k] for k in ('owner', 'expect_name', 'expires_at',
                'allow_unknown_merge', 'allow_new_unknown_merge', 'max_requests')))
    require(core.inventory(approved) <= HARD_REQUEST_CEILING)
    # A separately pinned immutable audit document names every proposed operation,
    # its original source identity, prior-operation search and owner risk sources.
    # This record is reviewed evidence, never a self-authenticating authorization.
    audit = private.load(c['overlap_path'])
    require(sha(canonical(audit)) == c['overlap_sha256'])
    exact(audit, ('schema', 'owner', 'plan_sha256', 'operations', 'risk_source_refs'))
    require(type(audit['schema']) is int and audit['schema'] == 1
            and audit['owner'] == c['owner'] and audit['plan_sha256'] == c['plan_sha256'])
    require(type(audit['risk_source_refs']) is list and audit['risk_source_refs']
            and all(type(x) is str and 1 <= len(x) <= 256 for x in audit['risk_source_refs']))
    operations = []
    for group in approved['groups']:
        operations.extend((group['anchor'], 'parent', e) for e in group['entries'])
        if group['sibling'] is not None:
            operations.append((group['anchor'], 'sibling', group['sibling']))
    require(type(audit['operations']) is list and len(audit['operations']) == len(operations))
    for actual, (anchor, kind, e) in zip(audit['operations'], operations, strict=True):
        exact(actual, ('anchor', 'kind', 'entry_key', 'payload_sha256', 'source_refs',
                       'prior_review_refs', 'overlapping_markers'))
        require(actual['anchor'] == anchor and actual['kind'] == kind
                and actual['entry_key'] == e['key']
                and actual['payload_sha256'] == sha(canonical(e['payload'])))
        for name in ('source_refs', 'prior_review_refs'):
            require(type(actual[name]) is list and actual[name]
                    and all(type(x) is str and 1 <= len(x) <= 256 for x in actual[name]))
        require(type(actual['overlapping_markers']) is list)
        # This first release refuses every overlap. A reviewed audit must say no
        # overlapping prior operation, with its search evidence pinned above.
        # No spent/uncertain operation can be admitted under a new namespace.
        require(actual['overlapping_markers'] == [])
    return approved

