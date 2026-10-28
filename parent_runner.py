"""Offline parent-operation simulation. No production transport or entry point."""
import copy

from human_parent_gate import require_production_release
from people_core import Blocked, bind, digest, exact, require, validate


def payloads(data):
    """Deterministic approved-name payload proposal, not verified API encoding."""
    validate(data)
    result = []
    for parent in data['parents']:
        require('en' in parent['names'])
        # English main-name encoding is a proposal until vendor proofs are reviewed.
        result.append({'names': copy.deepcopy(parent['names']),
                       **copy.deepcopy(parent['names']['en']),
                       'gender': parent['gender'], 'is_alive': parent['is_alive'],
                       'public': False})
    return result


class SyntheticTransport:
    """Exact-type, in-memory fixture only. Never accepts a URL or credential."""
    def __init__(self):
        self.created = {}
        self.posts = 0
        self.gets = 0
        self.fail_after_create = False
        self.fail_get = False

    def create(self, anchor, payload):
        self.posts += 1
        object_id = str(99000 + self.posts)
        self.created[object_id] = {'payload': copy.deepcopy(payload), 'anchor': anchor}
        if self.fail_after_create:
            raise Blocked('synthetic interrupted create')
        return object_id

    def read(self, object_id):
        self.gets += 1
        if self.fail_get:
            raise Blocked('synthetic unavailable readback')
        require(object_id in self.created)
        return copy.deepcopy(self.created[object_id])


def simulate(data, receipt, expected, now, journal, version, transport):
    """Exercise gate ordering and durable state on synthetic fixtures only.

    No external identity, graph completeness, OIDC, consent or default-locale
    behavior is proved here. This cannot be substituted for a production runner.
    Caller owns a disposable synthetic journal and explicit synthetic transport.
    """
    require(type(transport) is SyntheticTransport)
    data = copy.deepcopy(data)
    receipt = copy.deepcopy(receipt)
    receipt_hash = bind(data, receipt, expected, now())
    require(version == receipt['state_version'])
    owner = data['owner']['node']
    binding = {'receipt': receipt_hash, 'run_id': receipt['run_id'],
               'attempt': receipt['run_attempt'], 'anchor': owner}
    manifest = digest(data)
    proposed = payloads(data)  # validate entire batch before any intent
    for parent, payload in zip(data['parents'], proposed, strict=True):
        bind(data, receipt, expected, now())
        operation = parent['local_id']
        payload_hash = digest(payload)
        version = journal.transition(owner, version, operation, manifest, payload_hash,
                                     'intent', binding=binding)
        # Expiry here leaves durable uncertain intent, even with no POST.
        bind(data, receipt, expected, now())
        object_id = transport.create(owner, payload)
        version = journal.transition(owner, version, operation, manifest, payload_hash,
                                     'acknowledged', object_id, binding=binding)
        # Ack/GET may complete after expiry, without granting another POST.
        observed = transport.read(object_id)
        exact(observed, ('payload', 'anchor'))
        require(observed == {'payload': payload, 'anchor': owner})
        version = journal.transition(owner, version, operation, manifest, payload_hash,
                                     'verified', object_id, binding=binding)
    return {'mode': 'synthetic_only', 'version': version,
            'verified_count': len(proposed), 'production_enabled': False}


def resume_synthetic(journal, owner, operation, transport):
    require(type(transport) is SyntheticTransport)
    instruction = journal.resume(owner, operation)
    # Inspection only: no new POST or automatic journal verification.
    transport.read(instruction['object_id'])
    return {'mode': 'synthetic_only', 'action': 'get_only', 'production_enabled': False}


def run_production(*args, **kwargs):
    require_production_release()
