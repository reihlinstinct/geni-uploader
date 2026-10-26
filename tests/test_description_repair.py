"""Synthetic exact-existing-object metadata repair and lag-safe restart tests."""
import copy
import hashlib
import json
from unittest.mock import patch

import pytest

import source_details as s

ITEM = {'key': 'ZZsource', 'kind': 'document', 'object_id': '101',
        'expect': {'title': 'ZZ original source',
                   'description_sha256': hashlib.sha256(b'ZZ old').hexdigest()},
        'set': {'description_en': 'ZZ reviewed English source description.'},
        'targets': [{'profile_id': '201', 'expect_name': 'ZZPerson ZZTest'}],
        'manual_facts': [], 'description_only': True}


class Fake:
    def __init__(self):
        self.obj = {'id': 'document-101', 'title': 'ZZ original source',
                    'description': 'ZZ old', 'date': '1933-01-04',
                    'source_url': 'https://example.invalid/ZZsource',
                    'tags': [{'id': 'profile-999'}, {'id': 'profile-201'}]}
        self.posts = []
        self.lag = False
        self.change_tags = False

    def __call__(self, method, kind, url, token=None, data=None):
        if method == 'POST':
            self.posts.append((kind, url, data))
            assert kind == 'document_update'
            assert set(data) == {'description'}
            if not self.lag:
                self.obj.update(data)
            if self.change_tags:
                self.obj['tags'] = []
        if kind == 'profile':
            return {'id': 'profile-201', 'display_name': 'ZZPerson ZZTest', 'is_alive': False}
        return copy.deepcopy(self.obj)


def plan(fake):
    item = copy.deepcopy(ITEM)
    item['set'] = {'description': ITEM['set']['description_en']}
    return [(item, copy.deepcopy(fake.obj), ['201'])]


def test_no_tags_or_other_fields_updated_and_idempotent(tmp_path):
    fake = Fake()
    before = copy.deepcopy(fake.obj)
    state = tmp_path / 'state'
    with patch.object(s.api, 'execute', fake):
        s.apply_plan(plan(fake), 'ZZtoken', state)
        s.apply_plan(plan(fake), 'ZZtoken', state)
    assert len(fake.posts) == 1
    assert fake.obj == {**before, 'description': ITEM['set']['description_en']}


def test_lag_pending_never_replays_and_read_only_reconciles(tmp_path):
    fake = Fake()
    fake.lag = True
    state = tmp_path / 'state'
    with patch.object(s.api, 'execute', fake):
        with pytest.raises(s.api.VerificationError):
            s.apply_plan(plan(fake), 'ZZtoken', state)
        assert json.loads(state.read_text())['items']['document-101']['phase'] == 'pending'
        with pytest.raises(s.api.VerificationError):
            s.apply_plan(plan(fake), 'ZZtoken', state)
        fake.obj['description'] = ITEM['set']['description_en']
        s.apply_plan(plan(fake), 'ZZtoken', state)
    assert len(fake.posts) == 1
    assert json.loads(state.read_text())['items']['document-101']['phase'] == 'verified'


def test_pending_changed_binding_stops(tmp_path):
    fake = Fake()
    state = tmp_path / 'state'
    with patch.object(s.api, 'execute', fake):
        s.apply_plan(plan(fake), 'ZZtoken', state)
        changed = plan(fake)
        changed[0][0]['set']['description'] = 'ZZ changed approved English description.'
        with pytest.raises(s.api.ApiError, match='binding'):
            s.apply_plan(changed, 'ZZtoken', state)
    assert len(fake.posts) == 1


def test_sync_failure_prevents_post(tmp_path):
    fake = Fake()
    with patch.object(s.api, 'execute', fake), \
            patch.object(s, '_sync_description_state', side_effect=RuntimeError('ZZ sync')), \
            pytest.raises(RuntimeError):
        s.apply_plan(plan(fake), 'ZZtoken', tmp_path / 'state', sync_state=True)
    assert not fake.posts


def test_missing_tags_stops_before_post(tmp_path):
    fake = Fake()
    del fake.obj['tags']
    with patch.object(s.api, 'execute', fake), pytest.raises(s.api.ApiError, match='tag-list'):
        s.apply_plan(plan(fake), 'ZZtoken', tmp_path / 'state')
    assert not fake.posts


def test_tag_change_does_not_verify_and_no_retry(tmp_path):
    fake = Fake()
    fake.change_tags = True
    state = tmp_path / 'state'
    with patch.object(s.api, 'execute', fake):
        with pytest.raises(s.api.VerificationError):
            s.apply_plan(plan(fake), 'ZZtoken', state)
        with pytest.raises(s.api.VerificationError):
            s.apply_plan(plan(fake), 'ZZtoken', state)
    assert len(fake.posts) == 1


@pytest.mark.parametrize('bad', [{'date': '1933-01-01'}, {'title': 'ZZ replacement'},
                               {'description': 'ZZ English source description.'}])
def test_description_only_schema_cannot_change_other_metadata(tmp_path, bad):
    item = copy.deepcopy(ITEM)
    item['set'] = bad
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [item]}))
    with pytest.raises(s.api.ApiError):
        s.load_records(manifest)


def test_concurrent_description_edit_stops_before_post(tmp_path):
    fake = Fake()
    original = plan(fake)
    fake.obj['description'] = 'ZZ concurrent human edit'
    with patch.object(s.api, 'execute', fake), pytest.raises(s.api.ApiError, match='precondition'):
        s.apply_plan(original, 'ZZtoken', tmp_path / 'state')
    assert not fake.posts


def test_uncertain_response_pending_never_replayed(tmp_path):
    fake = Fake()
    state = tmp_path / 'state'
    def uncertain(method, *args, **kwargs):
        if method == 'POST':
            fake(method, *args, **kwargs)
            raise s.api.UncertainWrite('ZZ response lost')
        return fake(method, *args, **kwargs)
    with patch.object(s.api, 'execute', uncertain), pytest.raises(s.api.UncertainWrite):
        s.apply_plan(plan(fake), 'ZZtoken', state)
    with patch.object(s.api, 'execute', fake):
        s.apply_plan(plan(fake), 'ZZtoken', state)
    assert len(fake.posts) == 1


def test_loader_renders_english_only_into_api_field(tmp_path):
    manifest = tmp_path / 'manifest.json'
    item = copy.deepcopy(ITEM)
    item['set']['description'] = 'תיאור מקור בעברית'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [item]}))
    fake = Fake()
    with patch.object(s.api, 'execute', fake):
        result = s.checked_plan(s.load_records(manifest), 'ZZtoken')
    assert result[0][0]['set'] == {'description': 'ZZ reviewed English source description.\n\nתיאור מקור בעברית'}


def test_description_hash_alone_is_not_an_identity_anchor(tmp_path):
    item = copy.deepcopy(ITEM)
    del item['expect']['title']
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': 1, 'items': [item]}))
    with pytest.raises(s.api.ApiError, match='expected title or source URL'):
        s.load_records(manifest)


def test_checkpoint_fsyncs_file_then_replaces_then_fsyncs_directory_before_post(tmp_path):
    fake = Fake()
    events = []
    real_fsync, real_replace = s.os.fsync, s.os.replace
    def fsync(fd):
        import stat
        events.append('dir-fsync' if stat.S_ISDIR(s.os.fstat(fd).st_mode) else 'file-fsync')
        return real_fsync(fd)
    def replace(src, dest):
        events.append('replace')
        return real_replace(src, dest)
    def execute(method, *args, **kwargs):
        if method == 'POST':
            assert events[-3:] == ['file-fsync', 'replace', 'dir-fsync']
            events.append('post')
        return fake(method, *args, **kwargs)
    with patch.object(s.os, 'fsync', fsync), patch.object(s.os, 'replace', replace), \
            patch.object(s.api, 'execute', execute):
        s.apply_plan(plan(fake), 'ZZtoken', tmp_path / 'state')
    assert events.count('post') == 1


def test_fsync_failure_prevents_post(tmp_path):
    fake = Fake()
    with patch.object(s.os, 'fsync', side_effect=OSError('ZZ fsync failed')), \
            patch.object(s.api, 'execute', fake), pytest.raises(OSError):
        s.apply_plan(plan(fake), 'ZZtoken', tmp_path / 'state')
    assert not fake.posts
