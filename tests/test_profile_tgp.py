"""Synthetic title/gender/photo adapter contracts (#715). No network or real names."""
import copy

import pytest

import geni_uploader.runners.bounded_profile_tgp as core
from geni_uploader.core.people import Blocked

OWNER, TARGET, PHOTO = 'profile-101', 'profile-202', 'photo-808'
HASH = 'ab' * 32


def base_expected(**over):
    value = {'first_name': 'ZZ First', 'last_name': 'ZZ Last', 'gender': 'female',
             'is_alive': True, 'public': False, 'claimed': False, 'merge_pending': False,
             'unions': ['union-303'], 'names': {
                 'en-US': {'first_name': 'ZZ First', 'last_name': 'ZZ Last'},
                 'he': {'first_name': 'ZZ Given', 'last_name': 'ZZ Family'}}}
    value.update(over)
    return value


def plan(capability='gender', **over):
    c = {'schema': 1, 'owner': OWNER, 'target': TARGET, 'expect_name': 'ZZ Owner',
         'expires_at': 900, 'capability': capability}
    if capability == 'title':
        c['expected'] = base_expected()
        c['set'] = {'title': 'ZZ Title'}
        c['readback_contract'] = 'UNRESOLVED'
    elif capability == 'gender':
        c['expected'] = base_expected(gender='')
        c['set'] = {'gender': 'female'}
    else:
        c['expected'] = base_expected(mugshot_urls={'large': 'https://ZZ.invalid/main.jpg'})
        c['set'] = {'title': 'ZZ Caption'}
        c.update(image_sha256=HASH, consent_reference='ZZ-consent-1',
                 privacy_acknowledged=True, main_portrait='keep-current')
    c.update(over)
    return c


class IO:
    def __init__(self, c, anomaly=None, tag_form=TARGET):
        self.c, self.anomaly, self.posts = c, anomaly, []
        self.tag_form = tag_form
        self.value = dict(copy.deepcopy(c['expected']), id=TARGET)
        self.edges = {TARGET: {'edges': {'union-303': {'rel': 'partner'}}}}

    def get_profile(self, target):
        if target == 'profile':
            if self.anomaly == 'owner_mismatch':
                return {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Stranger'}
            return {'id': OWNER, 'first_name': 'ZZ', 'last_name': 'Owner'}
        value = copy.deepcopy(self.value)
        if self.posts and self.anomaly == 'mugshot_changed':
            value['mugshot_urls'] = {'large': 'https://ZZ.invalid/other.jpg'}
        return value

    def get_family(self, target):
        nodes = copy.deepcopy(self.edges)
        if self.posts and self.anomaly == 'graph':
            nodes[TARGET]['edges']['union-404'] = {'rel': 'child'}
        return {'focus': {'id': target}, 'nodes': nodes}

    def get_photo(self, photo_id):
        photo = {'id': photo_id, 'title': self.c['set']['title'],
                 'tags': [self.tag_form], 'sizes': {'large': 'https://ZZ.invalid/l.jpg'}}
        if self.anomaly == 'caption':
            photo['title'] = 'ZZ Other'
        if self.anomaly == 'tags':
            photo['tags'] = [self.tag_form, 'profile-999']
        if self.anomaly == 'sizes':
            photo['sizes'] = {}
        return photo

    def update(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        if self.anomaly != 'not_applied':
            self.value.update(body)
        return {'id': TARGET}

    def add_photo(self, target, body):
        self.posts.append((target, copy.deepcopy(body)))
        if self.anomaly == 'lost':
            raise OSError()
        return {'id': PHOTO}


class Store:
    def __init__(self, hashes=()):
        self.used, self.receipts, self.hashes = set(), [], set(hashes)
        self.recorded = []

    def consume(self, marker):
        if marker in self.used:
            raise Blocked()
        self.used.add(marker)

    def receipt(self, marker, stage, value):
        self.receipts.append(stage)

    def photo_hashes(self, target):
        return set(self.hashes)

    def record_photo_hash(self, target, image_sha256):
        self.recorded.append((target, image_sha256))


def run(c=None, anomaly=None, store=None, read_only=False):
    c = c or plan()
    io, store = IO(c, anomaly), store or Store()
    result = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=read_only)
    return result, io, store


# ---- gender ----

@pytest.mark.parametrize('read_only', [False, True])
def test_gender_fill_verified(read_only):
    r, io, store = run(plan('gender'), read_only=read_only)
    assert r['phase'] == ('READ_ONLY_TGP_VERIFIED' if read_only else 'VERIFIED')
    assert len(io.posts) == (not read_only)
    if not read_only:
        assert io.posts[0][1] == {'gender': 'female'}
        assert io.value['gender'] == 'female'
        assert store.receipts == ['before', 'ack', 'final']


@pytest.mark.parametrize('current', ['female', 'male', 'unknown'])
def test_gender_present_blocks(current):
    with pytest.raises(Blocked):
        core.plan(plan('gender', expected=base_expected(gender=current)))


def test_gender_absent_required():
    c = plan('gender')
    c['expected']['gender'] = None
    assert core.plan(c)['capability'] == 'gender'


def test_gender_invalid_value_blocks():
    with pytest.raises(Blocked):
        core.plan(plan('gender', set={'gender': 'ZZ'}))


# ---- title ----

def test_title_plan_mode_ok():
    r, io, _ = run(plan('title'), read_only=True)
    assert r['phase'] == 'READ_ONLY_TGP_VERIFIED' and not io.posts


def test_title_update_refused_while_readback_unresolved():
    with pytest.raises(Blocked):
        run(plan('title'), read_only=False)


def test_title_wrong_readback_marker_blocks():
    with pytest.raises(Blocked):
        core.plan(plan('title', readback_contract='photo-v1'))


def test_title_never_enters_name_fields():
    with pytest.raises(Blocked):
        core.plan(plan('title', set={'title': 'ZZ T', 'first_name': 'ZZ X'}))


# ---- photo ----

@pytest.mark.parametrize('read_only', [False, True])
def test_photo_upload_verified(read_only):
    r, io, store = run(plan('photo'), read_only=read_only)
    assert r['phase'] == ('READ_ONLY_TGP_VERIFIED' if read_only else 'VERIFIED')
    assert len(io.posts) == (not read_only)
    if not read_only:
        assert io.posts[0][1] == {'title': 'ZZ Caption'}
        assert store.receipts == ['before', 'ack', 'final']
        assert store.recorded == [(TARGET, HASH)]


@pytest.mark.parametrize('mut', ['absent', 'empty', 'not-dict', 'empty-url', 'bad-scheme'])
def test_photo_main_portrait_precondition_blocks(mut):
    c = plan('photo')
    if mut == 'absent':
        del c['expected']['mugshot_urls']
        with pytest.raises(Blocked):
            core.plan(c)
        return
    shapes = {'empty': {}, 'not-dict': 'https://ZZ.invalid/main.jpg',
              'empty-url': {'large': ''}, 'bad-scheme': {'large': 'http://ZZ.invalid/x.jpg'}}
    c['expected']['mugshot_urls'] = shapes[mut]
    with pytest.raises(Blocked):
        core.plan(c)
    c = plan('photo')
    io = IO(c)
    io.value['mugshot_urls'] = shapes[mut]
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts


@pytest.mark.parametrize('tag_form', [TARGET, 'https://www.geni.com/api/' + TARGET])
def test_photo_tag_wire_shapes_accepted(tag_form):
    c = plan('photo')
    io, store = IO(c, tag_form=tag_form), Store()
    r = core.execute(c, io, store, lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'VERIFIED'


def test_photo_wrong_tag_url_stops():
    c = plan('photo')
    io = IO(c, tag_form='https://www.geni.com/api/profile-999')
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED'


def test_photo_duplicate_hash_blocks():
    c = plan('photo')
    r, io, _ = run(c, store=Store(hashes={HASH}))
    assert r['phase'] == 'STOPPED' and not io.posts


def test_photo_duplicate_hash_other_target_ok():
    c = plan('photo')
    r, _, _ = run(c, store=Store(hashes=set()))
    assert r['phase'] == 'VERIFIED'


@pytest.mark.parametrize('field,value', [('privacy_acknowledged', False),
                                         ('main_portrait', 'set-as-main'),
                                         ('consent_reference', '')])
def test_photo_acknowledgments_required(field, value):
    with pytest.raises(Blocked):
        core.plan(plan('photo', **{field: value}))


def test_photo_bad_image_hash_blocks():
    with pytest.raises(Blocked):
        core.plan(plan('photo', image_sha256='zz'))


@pytest.mark.parametrize('anomaly', ['caption', 'tags', 'sizes', 'mugshot_changed', 'graph'])
def test_photo_readback_mismatch_stops(anomaly):
    r, _io, _ = run(plan('photo'), anomaly=anomaly)
    assert r['phase'] == 'STOPPED' and r['retry_allowed'] is False


def test_gender_update_acknowledged_but_not_applied_stops():
    r, io, _ = run(plan('gender'), anomaly='not_applied')
    assert r['phase'] == 'STOPPED' and r['retry_allowed'] is False
    assert len(io.posts) == 1


def test_owner_expect_name_gate_stops():
    r, io, _ = run(plan('gender'), anomaly='owner_mismatch')
    assert r['phase'] == 'STOPPED' and not io.posts


def test_photo_failed_post_terminal():
    r, io, store = run(plan('photo'), anomaly='lost')
    assert r['phase'] == 'STOPPED' and r['retry_allowed'] is False
    assert len(io.posts) == 1 and store.receipts == ['before']


def test_mixed_name_scope_rejected():
    with pytest.raises(Blocked):
        core.plan(plan('gender', set={'gender': 'female', 'last_name': 'ZZ X'}))


def test_photo_marker_pins_image_hash():
    a, b = plan('photo'), plan('photo', image_sha256='cd' * 32)
    assert core.marker(core.plan(a)) != core.marker(core.plan(b))


def test_photo_marker_pins_consent_reference():
    a, b = plan('photo'), plan('photo', consent_reference='ZZ-consent-2')
    assert core.marker(core.plan(a)) != core.marker(core.plan(b))


def test_plan_is_idempotent():
    for capability in ('title', 'gender', 'photo'):
        once = core.plan(plan(capability))
        assert core.plan(once) == once


@pytest.mark.parametrize('sizes', [[None], {}, {'large': ''}, [''], {'large': None}, [],
                                  ['', 'https://ZZ.invalid/x.jpg'],
                                  {'large': 'https://ZZ.invalid/x.jpg', 'small': ''}])
def test_photo_malformed_sizes_stop(sizes):
    c = plan('photo')
    io = IO(c)
    orig = io.get_photo
    def patched(photo_id):
        photo = orig(photo_id)
        photo['sizes'] = sizes
        return photo
    io.get_photo = patched
    r = core.execute(c, io, Store(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED'


# ---- runner level (protected_profile_tgp) ----

import geni_uploader.runners.protected_profile_tgp as runner

TOKEN = 'ZZtoken123'


FUTURE = 4_000_000_000


def vendor(c, read_only=False):
    v = runner.ScopedVendor(TOKEN, {**c, 'expires_at': FUTURE}, read_only=read_only)
    return v


def admit(v, method, route):
    v.last = None  # skip the 15s production rate-limit spacing in tests
    v.admit_vendor(method, route)


def test_scoped_vendor_gender_sequence():
    v = vendor(plan('gender'))
    assert [m for m, _ in v.sequence] == ['GET', 'GET', 'GET', 'POST', 'GET', 'GET']
    admit(v, 'GET', v.sequence[0][1])
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/' + TARGET + '/update')  # order enforced


def test_scoped_vendor_photo_sequence_and_photo_route():
    v = vendor(plan('photo'))
    assert [m for m, _ in v.sequence] == ['GET', 'GET', 'GET', 'POST', 'GET', 'GET', 'GET']
    with pytest.raises(Blocked):
        v.admit_vendor('GET', '/api/photo-notanumber')


def test_scoped_vendor_plan_mode_has_no_post():
    v = vendor(plan('photo'), read_only=True)
    assert all(m == 'GET' for m, _ in v.sequence)


def test_scoped_vendor_posts_once_only():
    v = vendor(plan('gender'))
    for method, route in v.sequence[:3]:
        admit(v, method, route)
    admit(v, 'POST', '/api/' + TARGET + '/update')
    with pytest.raises(Blocked):
        v.admit_vendor('POST', '/api/' + TARGET + '/update')


def test_scoped_vendor_read_only_refuses_post():
    v = vendor(plan('gender'), read_only=True)
    assert all(m == 'GET' for m, _ in v.sequence)
    for _method, _route in v.sequence:
        with pytest.raises(Blocked):
            v.admit_vendor('POST', '/api/' + TARGET + '/update')
        admit(v, _method, _route)


def test_config_contract():
    good = {'schema': 1, 'data_repo': 'reihlinstinct/ZZ-private', 'data_sha': 'ab' * 20,
            'data_path': 'plans/zz.json', 'owner': OWNER, 'expect_name': 'ZZ Owner',
            'recipient': 'age1zz', 'target': TARGET, 'expires_at': 900,
            'plan_sha256': HASH}
    # configuration() validates the base fields; only contract shape is ours
    c = dict(good)
    with pytest.raises(Blocked):
        runner.config({k: v for k, v in c.items() if k != 'plan_sha256'})
    with pytest.raises(Blocked):
        runner.config(dict(c, plan_sha256='zz'))
    with pytest.raises(Blocked):
        runner.config(dict(c, extra='zz'))
    with pytest.raises(Blocked):
        runner.config(dict(c, target=OWNER))


def test_runner_env_gate_fails_closed():
    # run() raises at env admission; main() converts any exception to exit 1.
    with pytest.raises(Blocked):
        runner.run({})


def test_photo_store_fails_closed_update_but_plan_mode_unaffected():
    class Ledger:
        def consume(self, marker):
            pass
        def receipt(self, marker, stage, value):
            pass
        def photo_hashes(self, target):
            raise NotImplementedError
        def record_photo_hash(self, target, image_sha256):
            raise NotImplementedError
    c = plan('photo')
    io = IO(c)
    r = core.execute(c, io, Ledger(), lambda _: b'ZZ', lambda: 200, read_only=False)
    assert r['phase'] == 'STOPPED' and not io.posts
    io = IO(c)
    r = core.execute(c, io, Ledger(), lambda _: b'ZZ', lambda: 200, read_only=True)
    assert r['phase'] == 'READ_ONLY_TGP_VERIFIED'


def test_production_photo_store_methods_unimplemented():
    import geni_uploader.runners.protected_family_additions as fam
    store = runner.PhotoStore.__new__(runner.PhotoStore)
    with pytest.raises(NotImplementedError):
        store.photo_hashes(TARGET)
    with pytest.raises(NotImplementedError):
        store.record_photo_hash(TARGET, HASH)
    _ = fam  # PhotoStore subclasses the family receipt store
