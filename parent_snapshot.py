"""Offline supplied evidence parser. No network, provenance or write authority."""
import re

from people_core import Blocked, digest, require


def identifier(value, kind='profile'):
    return type(value) is str and re.fullmatch(kind + r'-[0-9]{1,30}', value) is not None


def bounded(value, depth=0, budget=None):
    if budget is None:
        budget = [2000]
    budget[0] -= 1
    require(depth <= 8 and budget[0] >= 0)
    if type(value) is dict:
        require(len(value) <= 100)
        for key, leaf in value.items():
            require(type(key) is str and len(key) <= 100)
            bounded(leaf, depth + 1, budget)
    elif type(value) is list:
        require(len(value) <= 100)
        for leaf in value:
            bounded(leaf, depth + 1, budget)
    else:
        require(value is None or type(value) in (str, bool, int))
        if type(value) is str:
            require(len(value) <= 1024)


def parse(snapshot, expected_owner):
    """Canonical IDs only, no guid/name matching. Missing is never false/empty.

    Caller supplies raw four-part snapshot, not a live response or custody
    bundle. Output contains no supplied identity/name, and never a permit.
    Hash identifies supplied content only, not its truth or authenticity.
    """
    require(identifier(expected_owner))
    bounded(snapshot)
    require(type(snapshot) is dict)
    require(set(snapshot) == {'self', 'owner', 'family', 'unions'})
    require(type(snapshot['unions']) is list
            and len(snapshot['unions']) <= 10
            and all(type(value) is dict for value in snapshot['unions']))
    statuses = []
    for key in ('self', 'owner'):
        value = snapshot[key]
        require(type(value) is dict and value.get('id') == expected_owner
                and not set(value) & {'results', 'error'})
        statuses.append(merge_status(value))
        if not set(value) <= PROFILE_FIELDS:
            statuses.append('unknown')
    family = snapshot['family']
    graph = 'unknown'
    count = None
    if type(family) is dict:
        focus = family.get('focus')
        if type(focus) is dict:
            statuses.append(merge_status(focus))
            if 'id' in focus:
                require(focus['id'] == expected_owner)
            else:
                statuses.append('unknown')
            if not set(focus) <= PROFILE_FIELDS:
                statuses.append('unknown')
        else:
            statuses.append('unknown')
        nodes = family.get('nodes')
        if type(nodes) is dict:
            for key, value in nodes.items():
                if type(value) is dict:
                    statuses.append(merge_status(value))
                    fields = PROFILE_FIELDS if identifier(key) else UNION_FIELDS
                    if (not (identifier(key) or identifier(key, 'union'))
                            or value.get('id') != key or not set(value) <= fields):
                        statuses.append('unknown')
                else:
                    statuses.append('unknown')
        else:
            statuses.append('unknown')
        try:
            count = observed_parents(snapshot, expected_owner)
            graph = 'observed_consistent_not_complete'
        except Blocked:
            pass
    else:
        statuses.append('unknown')
    return {'schema_version': 1, 'kind': 'unauthenticated_offline_snapshot_review',
            'snapshot_hash': digest(snapshot), 'owner_id_matches': True,
            'merge_status': ('blocked' if 'blocked' in statuses else
                             'unknown' if 'unknown' in statuses else 'explicit_clear'),
            'graph_status': graph, 'observed_parent_count': count,
            'hidden_parent_completeness': 'unknown', 'slot_semantics': 'unknown',
            'evidence_authenticated': False, 'create_enabled': False}


def merge_status(value):
    if 'merged_into' in value and value['merged_into'] is not None:
        return 'blocked'
    if value.get('merge_pending') is True:
        return 'blocked'
    if value.get('merge_pending') is False and (
            'merged_into' not in value or value['merged_into'] is None):
        return 'explicit_clear'
    return 'unknown'


PROFILE_FIELDS = {'id', 'guid', 'first_name', 'middle_name', 'last_name', 'maiden_name',
                  'names', 'public', 'is_alive', 'merge_pending', 'merged_into', 'unions'}

UNION_FIELDS = {'id', 'partners', 'children', 'adopted_children', 'foster_children'}


def observed_parents(snapshot, owner):
    family = snapshot['family']
    require(set(family) == {'focus', 'nodes'})
    require(type(family['focus']) is dict and family['focus'].get('id') == owner)
    nodes, unions = family['nodes'], snapshot['unions']
    require(type(nodes) is dict and len(nodes) <= 100
            and type(unions) is list and len(unions) <= 10)
    allowed = PROFILE_FIELDS
    union_fields = UNION_FIELDS
    for value in (snapshot['self'], snapshot['owner'], family['focus']):
        require(set(value) <= allowed)
    for key, value in nodes.items():
        require((identifier(key) or identifier(key, 'union')) and type(value) is dict
                and value.get('id') == key)
        require(set(value) <= (allowed if identifier(key) else union_fields))
    require(owner in nodes)
    seen, parents = set(), set()
    for union in unions:
        require(type(union) is dict and set(union) <= union_fields)
        uid = union.get('id')
        require(identifier(uid, 'union') and uid in nodes and uid not in seen)
        seen.add(uid)
        for field in ('partners', 'children', 'adopted_children', 'foster_children'):
            values = union.get(field)
            require(type(values) is list and all(identifier(v) and v in nodes for v in values))
            require(len(values) == len(set(values)))
            if field in nodes[uid]:
                require(nodes[uid][field] == values)
        require(not set(union['partners']) & set(union['children']))
        if owner in union['children'] + union['adopted_children'] + union['foster_children']:
            parents.update(union['partners'])
    require(seen == {key for key in nodes if identifier(key, 'union')})
    for key, value in nodes.items():
        if identifier(key) and 'unions' in value:
            require(type(value['unions']) is list
                    and all(identifier(uid, 'union') and uid in seen for uid in value['unions']))
    return len(parents)
