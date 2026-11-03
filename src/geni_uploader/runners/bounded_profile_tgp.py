"""Protected title/gender/photo adapter model (#715). Injected effects only."""
import copy
import re

from geni_uploader.core.parent_contract import profile_id
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.bounded_profile_name_update import (
    SNAPSHOT_KEYS,
    merge_state,
    names,
    snapshot,
    union_reference,
)
from geni_uploader.runners.one_time_parent_pilot import canonical, sha

CAPABILITIES = ('title', 'gender', 'photo')
def caption(value):
    # Photo caption / profile title string safety (titles never enter name fields).
    require(type(value) is str and 0 < len(value) <= 200
            and not any(ord(c) < 32 for c in value))


def portrait(value):
    # PhotoImageSizeMap: at least one size, every entry a nonempty str -> str URL.
    require(type(value) is dict and len(value) >= 1)
    for size, url in value.items():
        require(type(size) is str and len(size) > 0
                and type(url) is str and url.startswith('https://'))


GENDERS = ('male', 'female', 'unknown')
BASE_KEYS = ('schema', 'owner', 'expect_name', 'target', 'expected', 'set',
             'expires_at', 'capability')
PHOTO_SNAPSHOT_KEYS = (*SNAPSHOT_KEYS, 'mugshot_urls')


def expected(value, capability):
    require(type(value) is dict)
    require(set(value) <= set(PHOTO_SNAPSHOT_KEYS if capability == 'photo'
                              else SNAPSHOT_KEYS))
    require(value.get('public') is False and value.get('is_alive') is True
            and value.get('claimed') is False)
    merge_state(value)
    require('first_name' in value and type(value.get('unions')) is list
            and len(value['unions']) <= 8)
    require(len({union_reference(u) for u in value['unions']}) == len(value['unions']))
    names({k: v for k, v in value.items() if k in ('first_name', 'last_name', 'maiden_name')})
    require(type(value.get('names')) is dict and set(value['names']) == {'en-US', 'he'})
    for fields in value['names'].values():
        names(fields)
        require('first_name' in fields)
    if capability == 'gender':
        # Admissible only when the current gender is absent or empty; a present
        # value (equal or different) blocks per the design's no-overwrite rule.
        require(value.get('gender') in (None, ''))
    else:
        require(value.get('gender') in GENDERS)
    if capability == 'photo':
        # keep-current requires an established existing main portrait, pinned
        # by the private preparation read and confirmed in preflight.
        portrait(value.get('mugshot_urls'))


def plan(value):
    change = value.get('set')
    require(type(change) is dict)
    capability = value.get('capability')
    require(capability in CAPABILITIES)
    if capability == 'title':
        exact(value, (*BASE_KEYS, 'readback_contract'))
    elif capability == 'photo':
        # mugshot_urls is added at top level by a prior plan() pass; accepting
        # it here keeps plan() idempotent (the runner plans twice).
        value = dict(value)
        prior = value.pop('mugshot_urls', None)
        exact(value, (*BASE_KEYS, 'image_sha256', 'consent_reference',
                      'privacy_acknowledged', 'main_portrait'))
        if prior is not None:
            # Raw input carries the map in expected; a re-planned input carries
            # it only at top level (the snapshot strips it). Re-inject so the
            # expected() contract below validates it once.
            if 'mugshot_urls' in value['expected']:
                require(prior == value['expected']['mugshot_urls'])
            else:
                value['expected'] = dict(value['expected'], mugshot_urls=prior)
    else:
        exact(value, BASE_KEYS)
    require(type(value['schema']) is int and value['schema'] == 1)
    profile_id(value['owner'])
    profile_id(value['target'])
    require(value['owner'] != value['target'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    expected(value['expected'], capability)
    if capability == 'title':
        # No supported readback contract exists yet: plan-only capability.
        require(value['readback_contract'] == 'UNRESOLVED')
        exact(change, ('title',))
        caption(change['title'])
    elif capability == 'gender':
        exact(change, ('gender',))
        require(change['gender'] in GENDERS)
    else:
        exact(change, ('title',))
        caption(change['title'])
        require(type(value['image_sha256']) is str
                and re.fullmatch(r'[a-f0-9]{64}', value['image_sha256']))
        require(type(value['consent_reference']) is str
                and 0 < len(value['consent_reference']) <= 200)
        require(value['privacy_acknowledged'] is True)
        require(value['main_portrait'] == 'keep-current')
    result = copy.deepcopy(value)
    result['expected'] = snapshot(dict(value['expected']))
    if capability == 'photo':
        # Main portrait is a preflight precondition, not part of the name snapshot.
        result['mugshot_urls'] = value['expected']['mugshot_urls']
    return result


def graph(actual, target):
    require(type(actual) is dict and actual.get('focus', {}).get('id') == target)
    nodes = actual.get('nodes')
    require(type(nodes) is dict and target in nodes and 1 <= len(nodes) <= 64)
    result = {}
    for node, body in nodes.items():
        require(type(body) is dict and type(body.get('edges')) is dict)
        result[node] = body['edges']
    return copy.deepcopy(result)


def tag_target(value):
    # Wire shape: tags are strings, either 'profile-<digits>' or its API URL.
    require(type(value) is str)
    match = re.fullmatch(r'(?:https://www\.geni\.com/api/)?(profile-[0-9]{1,30})', value)
    require(match is not None)
    return match.group(1)


def photo_readback(photo, target, caption):
    require(type(photo) is dict and 'error' not in photo)
    require(photo.get('title') == caption)
    tags = photo.get('tags')
    require(type(tags) is list and len(tags) == 1)
    require(tag_target(tags[0]) == target)
    sizes = photo.get('sizes')
    require(type(sizes) in (dict, list))
    entries = list(sizes.values()) if type(sizes) is dict else sizes
    # At least one supported nonempty size entry; malformed entries block.
    require(len(entries) >= 1 and all(type(e) is str and len(e) > 0 for e in entries))


def marker(c):
    # Neither expiry nor executor/source commit can mint another send.
    keys = ('owner', 'target', 'expected', 'set', 'capability',
            *(('image_sha256', 'consent_reference') if c['capability'] == 'photo' else ()))
    return 'profile-tgp-consumed-v1-' + sha(canonical({k: c[k] for k in keys}))


def execute(value, io, store, save, clock, *, read_only):
    c = plan(value)
    require(type(read_only) is bool)
    capability = c['capability']
    # Title writes refuse dispatch while no supported readback contract exists.
    require(capability != 'title' or read_only)
    r = {'phase': 'STOPPED', 'stage': 'preflight', 'retry_allowed': False,
         'responses': [], 'read_only': read_only, 'target': c['target'],
         'capability': capability}

    def now():
        require(clock() < c['expires_at'])

    def read(kind, target):
        now()
        r['stage'] = 'read_' + kind
        actual = getattr(io, 'get_' + kind)(target)
        r['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(r))
        return actual

    try:
        owner = read('profile', 'profile')
        require(owner.get('id') == c['owner'])
        full = ' '.join(owner.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in full.casefold().split() for w in c['expect_name'].split()))
        before = read('profile', c['target'])
        require(before.get('id') == c['target'] and snapshot(before) == c['expected'])
        if capability == 'photo':
            portrait(before.get('mugshot_urls'))
            require(before['mugshot_urls'] == c['mugshot_urls'])
        edges = graph(read('family', c['target']), c['target'])
        if read_only:
            r.update(phase='READ_ONLY_TGP_VERIFIED', stage='complete')
            save(copy.deepcopy(r))
            return r
        if capability == 'photo':
            require(c['image_sha256'] not in store.photo_hashes(c['target']))
        intent = marker(c)
        now()
        r['stage'] = 'before'
        store.receipt(intent, 'before', save(copy.deepcopy(r)))
        now()
        r['stage'] = 'consume'
        store.consume(intent)
        now()
        r.update(stage='send', phase='UNCERTAIN')
        if capability == 'photo':
            response = io.add_photo(c['target'], c['set'])
        else:
            response = io.update(c['target'], c['set'])
        require(type(response) is dict and 'error' not in response)
        r['update_response'] = response
        r.update(stage='ack', phase='ACKNOWLEDGED_NOT_VERIFIED')
        now()
        store.receipt(intent, 'ack', save(copy.deepcopy(r)))
        if capability == 'photo':
            photo_id = response.get('id')
            require(type(photo_id) is str and len(photo_id) > 0)
            photo_readback(read('photo', photo_id), c['target'], c['set']['title'])
            after = read('profile', c['target'])
            require(after.get('id') == c['target'] and snapshot(after) == c['expected']
                    and after.get('mugshot_urls') == c['mugshot_urls'])
        else:
            after = read('profile', c['target'])
            want = copy.deepcopy(c['expected'])
            want.update(c['set'])
            require(after.get('id') == c['target'] and snapshot(after) == want)
        require(graph(read('family', c['target']), c['target']) == edges)
        now()
        r.update(phase='VERIFIED', stage='final')
        store.receipt(intent, 'final', save(copy.deepcopy(r)))
        if capability == 'photo':
            # The VERIFIED receipt is already retained. A future durable ledger
            # must register the hash WITH that receipt (or derive hashes from
            # VERIFIED receipts): no VERIFIED receipt without duplicate
            # registration. PhotoStore fails closed until then.
            store.record_photo_hash(c['target'], c['image_sha256'])
        r['stage'] = 'complete'
        save(copy.deepcopy(r))
    except (Blocked, OSError, ValueError, TypeError, KeyError, AttributeError,
            RecursionError, NotImplementedError):
        # NotImplementedError: the photo ledger is not wired yet (P2-6); fail
        # closed with STOPPED evidence rather than crashing mid-sequence.
        r['phase'] = 'STOPPED'
        save(copy.deepcopy(r))
    return r
