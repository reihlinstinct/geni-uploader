"""Offline single-attempt seam. Not a live adapter, durable ledger or permit."""
from copy import deepcopy
from threading import Lock

from parent_adapter_contract import classify_create, describe
from parent_intent_model import advance, binding_hash, consume, validate
from people_core import Blocked, digest, require


class SyntheticOwnerStore:
    """In-memory owner-global CAS only. No persistence or authority guarantee."""
    def __init__(self):
        self.rows = {}
        self.lock = Lock()

    def consume(self, binding):
        with self.lock:
            require(binding['owner'] not in self.rows)
            state = consume(binding, 0)
            self.rows[binding['owner']] = deepcopy(state)
            return deepcopy(state)

    def transition(self, binding, version, event, evidence, created_id=None):
        with self.lock:
            before = self.rows[binding['owner']]
            require(before['binding'] == binding)
            state = advance(before, version, event, evidence, created_id)
            self.rows[binding['owner']] = deepcopy(state)
            return deepcopy(state)


class SyntheticFatherTransport:
    """In-memory transport only. Accepts no credential, URL, client or callback."""
    def __init__(self):
        self.requests = []
        self.fail_after_send = False
        self.created_id = 'profile-999002'

    def post(self, descriptor):
        self.requests.append(deepcopy(descriptor))
        if self.fail_after_send:
            raise Blocked('synthetic post outcome uncertain')
        return 200, ('{"id":"' + self.created_id + '"}').encode()


def descriptor(binding, payload):
    binding_hash(binding)
    require(binding['connection_id'] == 'ZZ-secondary')
    require(type(payload) is dict and payload.get('gender') == 'male')
    result = describe('POST', binding['owner'] + '/add-parent', payload)
    require(result['body_hash'] == binding['payload_hash'])
    return result


def simulate_once(binding, payload, store, transport):
    """Consume then one synthetic POST. No success without separate readback.

    Content bindings are NOT authenticated; evidence hashes here identify fixed
    synthetic events, NOT encrypted artifacts. No production caller can use this
    function as authority, global exclusion or proof of durable intent.
    """
    require(type(store) is SyntheticOwnerStore and type(transport) is SyntheticFatherTransport)
    binding, payload = deepcopy(binding), deepcopy(payload)
    request = descriptor(binding, payload)
    state = store.consume(binding)
    validate(state)
    try:
        status, raw = transport.post(request)
        response = classify_create(sent=True, status=status, raw=raw)
        require(response['phase'] == 'acknowledged_not_verified')
        state = store.transition(binding, 1, 'acknowledge',
                                 digest({'synthetic_event': 'acknowledgment'}), response['object_id'])
    except Exception:  # noqa: BLE001 - post-intent uncertainty must never permit replay
        # Every post-intent error, including invalid ack/persistence failure,
        # blocks replay. Do not claim to have saved uncertainty if store fails.
        try:
            state = store.transition(binding, 1, 'uncertain',
                                     digest({'synthetic_event': 'post_intent_uncertain'}))
        except Exception:  # noqa: BLE001 - post-intent uncertainty must never permit replay
            return {'mode': 'synthetic_only', 'phase': 'uncertain_storage_unverified',
                    'production_enabled': False}
        return {'mode': 'synthetic_only', 'phase': state['phase'],
                'production_enabled': False}
    return {'mode': 'synthetic_only', 'phase': state['phase'],
            'production_enabled': False}
