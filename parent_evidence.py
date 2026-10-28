"""Offline review of already supplied parent-evidence snapshots. No transport."""
import re

from people_core import Blocked, exact, require


def node(value):
    require(type(value) is str and re.fullmatch(r'profile-[0-9]{1,30}', value) is not None)
    return value


def review(snapshot, owner):
    """Report observations, never certify hidden-parent completeness or readiness.

    Caller supplies a private snapshot. This function cannot authenticate its
    provenance, consent or vendor semantics. Its return is public-safe counts
    and fixed status strings, never the supplied names, IDs or raw errors.
    """
    node(owner)
    exact(snapshot, ('self', 'owner', 'family', 'unions'))
    require(type(snapshot['self']) is dict and type(snapshot['owner']) is dict)
    require(node(snapshot['self'].get('id')) == owner
            and node(snapshot['owner'].get('id')) == owner)
    family = snapshot['family']
    require(type(family) is dict and set(family) == {'focus', 'nodes'})
    require(type(family['focus']) is dict and node(family['focus'].get('id')) == owner)
    require(type(family['nodes']) is dict and len(family['nodes']) <= 100)
    require(type(snapshot['unions']) is list and len(snapshot['unions']) <= 10)
    for profile in (snapshot['self'], snapshot['owner'], family['focus']):
        require(profile.get('merge_pending') is False and profile.get('merged_into') is None)
    profiles = {}
    for key, value in family['nodes'].items():
        require(type(value) is dict and value.get('id') == key)
        if type(key) is str and key.startswith('profile-'):
            node(key)
            profiles[key] = value
        else:
            require(type(key) is str and re.fullmatch(r'union-[0-9]{1,30}', key) is not None)
    parents = set()
    union_ids = set()
    for union in snapshot['unions']:
        exact(union, ('id', 'children', 'partners'))
        require(type(union['id']) is str
                and re.fullmatch(r'union-[0-9]{1,30}', union['id']) is not None)
        require(union['id'] not in union_ids)
        union_ids.add(union['id'])
        for field in ('children', 'partners'):
            require(type(union[field]) is list and len(union[field]) <= 100)
            require(len({node(v) for v in union[field]}) == len(union[field]))
        if owner in union['children']:
            require(owner not in union['partners'])
            parents.update(union['partners'])
    require(parents <= profiles.keys())
    privacy = sum(type(profiles[p].get('public')) is bool
                  and profiles[p]['public'] is False
                  and type(profiles[p].get('is_alive')) is bool for p in parents)
    return {'status': 'blocked_vendor_proof_required',
            'observed_parent_count': len(parents),
            'explicit_private_life_readback_count': privacy,
            'hidden_parent_completeness': 'unproved',
            'add_parent_slot_semantics': 'unproved',
            'create_enabled': False}


def collect(*args, **kwargs):
    raise Blocked('human-run evidence transport not implemented or enabled')
