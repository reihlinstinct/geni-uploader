"""Fixture-only one-father composition. No live route, HTTP, token or grant."""
from copy import deepcopy

from human_parent_gate import require_production_release
from parent_adapter_contract import payload
from people_core import Blocked, digest, exact, require
from profile_result import validate as result_validate


class FixtureBoundaries:
    """Exact-type synthetic boundaries. Caller supplies only fixture data, not callbacks.

    This is not a durable intent service, encryption, private writer or vendor
    response. It rehearses orchestration and exposes every unresolved boundary.
    A shared instance models canonical-owner consumption across changed plans.
    """

    def __init__(self, observed, *, fault=None):
        self.observed = deepcopy(observed)
        self.fault = fault
        self.consumed = set()
        self.events = []
        self.posts = 0
        self.saved = []

    def step(self, name):
        self.events.append(name)
        if self.fault == name:
            raise Blocked('synthetic boundary interrupted')

    def consume(self, owner):
        self.step('consume_before')
        require(owner not in self.consumed)
        self.consumed.add(owner)
        self.step('consume_after')

    def store(self, stage, value):
        self.step(stage + '_store_before')
        self.saved.append((stage, digest(value)))
        self.step(stage + '_store_after')
        return digest({'stage': stage, 'value': value})

    def post(self, owner, proposed):
        require(owner in self.consumed)
        self.step('post_before')
        self.posts += 1
        self.step('post_after')
        return {'id': self.observed['profile_id']}


def execute_fixture(plan, boundaries, now):
    """Only exact fixture class accepted; no injected callable can perform live work.

    Preserve consumed/uncertain after all post-consumption faults. No automatic
    retry, reset, refresh, source upload or remedial write ever occurs.
    """
    require(type(boundaries) is FixtureBoundaries)
    require(type(now) is int)
    exact(plan, ('mode', 'production_enabled', 'pins', 'payload', 'field_origins',
                 'issued_at', 'expires_at', 'preflight'))
    require(plan['mode'] == 'synthetic_father_composition' and plan['production_enabled'] is False)
    proposed = payload(plan['payload'])
    require(proposed['gender'] == 'male')
    require(type(plan['issued_at']) is int and type(plan['expires_at']) is int
            and 0 < plan['expires_at'] - plan['issued_at'] <= 900
            and plan['issued_at'] <= now < plan['expires_at'])
    pins = plan['pins']
    exact(pins, ('owner', 'payload_hash', 'run_hash', 'artifact_hash', 'approval_hash'))
    require(pins['payload_hash'] == digest(proposed))
    # No dates/places/source/research fields pass payload(); direct-source naming
    # provenance remains supplied fixture content, never authenticated approval.
    exact(plan['field_origins'], ('names', 'relationship', 'control_facts'))
    require(plan['field_origins'] == {'names': 'direct_source_person',
                                    'relationship': 'direct_source_person',
                                    'control_facts': 'explicitly_reviewed'})
    pre = plan['preflight']
    exact(pre, ('owner', 'collected_at', 'merge_status', 'existing_parent_status',
                'unknown_risk_explicit', 'adverse'))
    require(pre['owner'] == pins['owner'] and type(pre['collected_at']) is int
            and 0 <= now - pre['collected_at'] <= 60)
    require(pre['merge_status'] in ('NO_OBSERVED_MERGE', 'UNKNOWN')
            and pre['existing_parent_status'] in ('NO_OBSERVED_PARENT', 'UNKNOWN')
            and pre['adverse'] is False)
    require(type(pre['unknown_risk_explicit']) is bool)
    if 'UNKNOWN' in (pre['merge_status'], pre['existing_parent_status']):
        require(pre['unknown_risk_explicit'] is True)
    # Shape all expected result pins before permanently consuming fixture intent.
    expected = boundaries.observed
    candidate = {'schema_version': 1, 'mode': 'offline_profile_result', 'pins': pins,
                 'profile_id': expected['profile_id'], 'profile_url': expected['profile_url'],
                 'acknowledgment_ref': 'a' * 64, 'readback_ref': 'b' * 64,
                 'source_refs': [], 'phase': 'profile_verified_sources_pending',
                 'production_enabled': False, 'provenance_authenticated': False}
    result_validate(candidate, pins)
    boundaries.step('preflight_complete')
    try:
        boundaries.consume(pins['owner'])
        boundaries.store('pre_write', {'pins': pins, 'payload': proposed, 'preflight': pre})
        ack = boundaries.post(pins['owner'], proposed)
        boundaries.store('acknowledgment', ack)
        boundaries.step('readback_before')
        exact(expected, ('profile_id', 'profile_url', 'payload', 'child', 'parents'))
        require(expected['profile_id'] == ack['id'] and expected['child'] == pins['owner']
                and expected['payload'] == proposed and expected['parents'] == [ack['id']])
        boundaries.step('readback_after')
        read_ref = boundaries.store('readback', expected)
        result = {**candidate, 'acknowledgment_ref': digest(ack), 'readback_ref': read_ref}
        result_validate(result, pins)
        boundaries.store('result', result)
        return {'phase': 'fixture_profile_verified_sources_pending', 'result': result,
                'production_enabled': False, 'authenticated': False,
                'unknown_graph_preserved': 'UNKNOWN' in (pre['merge_status'],
                                                       pre['existing_parent_status'])}
    except (Blocked, KeyError, TypeError, ValueError):
        return {'phase': 'fixture_consumed_uncertain' if pins['owner'] in boundaries.consumed
                else 'fixture_blocked_unconsumed', 'production_enabled': False,
                'retry_allowed': False, 'next_action': 'human_read_only_reconciliation'}


def execute_production(*args, **kwargs):
    require_production_release()
