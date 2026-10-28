"""Pure future-adapter descriptors. No HTTP client, credential or production transport."""
import copy
import json
import re

from people_core import Blocked, digest, exact, require, text

LIMIT = 1024 * 1024


def profile_id(value):
    require(type(value) is str and re.fullmatch(r'profile-[0-9]{1,30}', value) is not None)


def payload(value):
    require(type(value) is dict and type(value.get('names')) is dict)
    names = value['names']
    require(set(names) == {'he', 'en'})
    for fields in names.values():
        require(type(fields) is dict and 'first_name' in fields
                and set(fields) <= {'first_name', 'middle_name', 'last_name', 'maiden_name'})
        for leaf in fields.values(): text(leaf)
    exact(value, ('names', *names['en'], 'gender', 'is_alive', 'public'))
    require(all(value[key] == leaf for key, leaf in names['en'].items()))
    require(value['gender'] in ('male', 'female') and type(value['is_alive']) is bool
            and value['public'] is False)
    return copy.deepcopy(value)


def describe(method, route, body=None):
    """No URLs or credentials accepted. Returned descriptor is not an HTTP request."""
    require(type(method) is str and type(route) is str)
    if method == 'GET':
        require(body is None and (route == 'profile' or re.fullmatch(
            r'(?:profile-[0-9]{1,30}(?:/immediate-family)?|union-[0-9]{1,30})', route)))
        reviewed_body = None
    else:
        require(method == 'POST' and re.fullmatch(r'profile-[0-9]{1,30}/add-parent', route))
        reviewed_body = payload(body)
    return {'kind': 'offline_request_descriptor', 'method': method, 'route': route,
            'body': reviewed_body, 'body_hash': digest(reviewed_body),
            'credential_included': False, 'redirects_allowed': False, 'retries_allowed': False,
            'production_enabled': False}


def classify_create(*, sent, status=None, raw=None, expected_id=None):
    """Synthetic response classification only. No durable journal transition.

    Sent means transmission may have begun, not just that a response arrived.
    Nothing here verifies identity, parent link, privacy, names or remote state.
    Even a valid canonical acknowledgement still requires separate readback.
    """
    require(type(sent) is bool)
    if not sent:
        require(status is None and raw is None and expected_id is None)
        return {'phase': 'blocked_before_send', 'retry_allowed': False,
                'production_enabled': False}
    uncertain = {'phase': 'UNCERTAIN', 'retry_allowed': False,
                 'next_action': 'human_read_only_reconciliation', 'production_enabled': False}
    if type(status) is not int or status != 200 or type(raw) is not bytes or len(raw) > LIMIT:
        return uncertain
    try:
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                require(key not in obj)
                obj[key] = value
            return obj
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        require(type(value) is dict)
        # Deliberately strict contract fixture; actual vendor return shape unproved.
        exact(value, ('id',))
        profile_id(value['id'])
        if expected_id is not None:
            profile_id(expected_id)
            require(value['id'] == expected_id)
    except (Blocked, ValueError, TypeError, RecursionError, UnicodeError):
        return uncertain
    return {'phase': 'acknowledged_not_verified', 'object_id': value['id'],
            'retry_allowed': False, 'next_action': 'human_read_only_verification',
            'production_enabled': False}
