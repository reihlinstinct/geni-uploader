"""Offline content contract for created-profile receipts. Never write authority."""
import re
from copy import deepcopy
from urllib.parse import unquote, urlsplit

from parent_intent_model import _hash, _id
from people_core import Blocked, exact, require

PINS = ('owner', 'payload_hash', 'run_hash', 'artifact_hash', 'approval_hash')
FIELDS = ('schema_version', 'mode', 'pins', 'profile_id', 'profile_url',
          'acknowledgment_ref', 'readback_ref', 'source_refs', 'phase',
          'production_enabled', 'provenance_authenticated')
PHASES = ('created_unverified', 'profile_verified_sources_pending',
          'profile_verified_sources_attached', 'profile_verified_sources_cited')


def validate(value, expected_pins):
    """Check supplied content against expected pins, not live/vendor provenance.

    profile_url must be supplied from the vendor response/readback, not built
    from profile_id. These checks alone cannot establish that origin or resolve
    a numeric URL GUID to its distinct API profile id. Private storage, an
    authenticated writer, and exact source-stage approvals remain caller duties.
    """
    exact(value, FIELDS)
    exact(expected_pins, PINS)
    exact(value['pins'], PINS)
    require(value['pins'] == expected_pins)
    _id(expected_pins['owner'], 'profile-')
    for key in PINS[1:]:
        _hash(expected_pins[key])
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(value['mode'] == 'offline_profile_result')
    require(value['production_enabled'] is False
            and value['provenance_authenticated'] is False)
    _id(value['profile_id'], 'profile-')
    require(value['profile_id'] != expected_pins['owner'])
    url = value['profile_url']
    require(type(url) is str and 0 < len(url) <= 2048
            and url.isascii() and not any(c.isspace() or ord(c) < 32 for c in url))
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise Blocked('offline profile URL blocked') from exc
    require(parsed.scheme == 'https' and parsed.netloc == 'www.geni.com'
            and not parsed.query and not parsed.fragment)
    # Numeric profile URL GUIDs are vendor-supplied, not API profile ids.
    prefix = '/people/'
    require(parsed.path.startswith(prefix))
    parts = parsed.path[len(prefix):].split('/')
    require(len(parts) == 2 and 0 < len(parts[0]) <= 300
            and all(c.isalnum() or c in '-_%' for c in parts[0])
            and parts[1].isascii() and parts[1].isdigit()
            and 0 < len(parts[1]) <= 30 and parts[1][0] != '0')
    require(re.search(r'%(?![0-9A-Fa-f]{2})', parts[0]) is None)
    decoded = unquote(parts[0], errors='replace')
    require(not any(c in decoded for c in '/\\?#%')
            and not any(c.isspace() or ord(c) < 32 for c in decoded)
            and '\ufffd' not in decoded)
    _hash(value['acknowledgment_ref'])
    require(type(value['phase']) is str and value['phase'] in PHASES)
    if value['phase'] == 'created_unverified':
        require(value['readback_ref'] is None)
    else:
        _hash(value['readback_ref'])
        require(value['readback_ref'] != value['acknowledgment_ref'])
    refs = value['source_refs']
    require(type(refs) is list and len(refs) <= 100)
    for ref in refs:
        _hash(ref)
    require(len(set(refs)) == len(refs))
    if value['phase'] in PHASES[:2]:
        require(not refs)
    else:
        require(bool(refs))
    return deepcopy(value)
