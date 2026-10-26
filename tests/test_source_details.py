"""Synthetic offline tests. No production service calls."""
import copy
import json
import os
from unittest.mock import patch

import pytest

import source_details as s

ITEM = {"key": "ZZsource", "kind": "document", "object_id": "101",
        "expect": {"source_url": "https://example.invalid/ZZsource"},
        "set": {"description": "ZZ approved description", "date": "1933-01-04"},
        "targets": [{"profile_id": "201", "expect_name": "ZZPerson ZZTest"}],
        "manual_facts": ["ZZ name citation"]}


def manifest(tmp_path, item=None):
    p = tmp_path / "items.json"
    p.write_text(json.dumps({"schema_version": 1, "items": [item or ITEM]}))
    return p


class Fake:
    def __init__(self, alive=False):
        self.calls = []
        self.alive = alive
        self.obj = {"id": "document-101", "title": "ZZ existing", "description": "ZZ old",
                    "source_url": "https://example.invalid/ZZsource", "tags": ["profile-999"]}

    def __call__(self, method, kind, url, token=None, data=None):
        self.calls.append((method, kind, url, data))
        if kind == "profile":
            return {"id": "profile-201", "display_name": "ZZPerson ZZTest",
                    "is_alive": self.alive, "about_me": "ZZ excluded",
                    "relatives": [{"is_alive": True, "name": "ZZ living"}]}
        if method == "POST" and kind == "document_update":
            self.obj.update(data)
        if method == "POST" and kind == "document_tag":
            self.obj["tags"].append("profile-201")
        return copy.deepcopy(self.obj)


def test_schema_rejects_unknown_event(tmp_path):
    item = copy.deepcopy(ITEM)
    item["set"]["event"] = "ZZ unsupported"
    with pytest.raises(s.api.ApiError):
        s.load_records(manifest(tmp_path, item))


@pytest.mark.parametrize("alive", [True, None, "false", 0])
def test_living_or_unknown_fails_before_write(tmp_path, alive):
    fake = Fake(alive)
    with patch.object(s.api, "execute", fake), pytest.raises(s.api.ApiError):
        s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
    assert not any(c[0] == "POST" for c in fake.calls)


def test_existing_object_repair_keeps_tags_and_is_idempotent(tmp_path):
    fake = Fake()
    with patch.object(s.api, "execute", fake):
        items = s.load_records(manifest(tmp_path))
        s.apply_plan(s.checked_plan(items, "ZZtoken"), "ZZtoken", tmp_path / "state")
        n = len([c for c in fake.calls if c[0] == "POST"])
        s.apply_plan(s.checked_plan(items, "ZZtoken"), "ZZtoken", tmp_path / "state")
        assert len([c for c in fake.calls if c[0] == "POST"]) == n
    assert fake.obj["description"] == ITEM["set"]["description"]
    assert set(fake.obj["tags"]) == {"profile-999", "profile-201"}
    assert n == 2


def test_mismatch_no_post(tmp_path):
    fake = Fake()
    fake.obj["source_url"] = "https://example.invalid/ZZwrong"
    with patch.object(s.api, "execute", fake), pytest.raises(s.api.ApiError):
        s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
    assert not any(c[0] == "POST" for c in fake.calls)


def test_timeout_stops_and_blocks_future_repair(tmp_path):
    fake = Fake()
    def uncertain(method, kind, url, token=None, data=None):
        if method == "POST":
            raise s.api.UncertainWrite("ZZ uncertain")
        return fake(method, kind, url, token, data)
    state = tmp_path / "state"
    with patch.object(s.api, "execute", uncertain):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(s.api.UncertainWrite):
            s.apply_plan(plan, "ZZtoken", state)
        with pytest.raises(s.api.ApiError, match="unresolved"):
            s.apply_plan(plan, "ZZtoken", state)
    assert json.loads(state.read_text())["status"] == "pending"


def test_snapshot_private_allowlist_no_relatives(tmp_path):
    fake = Fake()
    output = tmp_path / "snapshot.json"
    with patch.object(s.api, "execute", fake):
        s.snapshot(s.load_records(manifest(tmp_path)), "ZZtoken", output)
    data = output.read_text()
    assert "ZZ living" not in data
    assert "about_me" not in data
    assert "unsupported" in data
    assert os.stat(output).st_mode & 0o777 == 0o600
    with pytest.raises(s.api.ApiError):
        s.private_json(output, {})


def test_no_new_profile_or_citation_endpoint_added():
    assert ("POST", "profile_update") not in s.api.ALLOWLIST
    assert ("POST", "citation") not in s.api.ALLOWLIST


def test_duplicate_source_rejected(tmp_path):
    p = manifest(tmp_path)
    p.write_text(json.dumps({"schema_version": 1, "items": [ITEM, ITEM]}))
    with pytest.raises(s.api.ApiError, match="duplicate"):
        s.load_records(p)


def test_website_guid_not_guessed_as_node_id():
    with (patch.object(s.api, "execute", return_value={"results": []}) as call,
          pytest.raises(s.api.ApiError)):
        s.object_read("ZZtoken", "document", "999999")
    assert call.call_count == 1


def test_workflow_user_only_manual_and_fails_closed_on_stale_image():
    from pathlib import Path
    root = Path(s.__file__).parent
    text = (root / ".github/workflows/geni-upload.yml").read_text()
    assert "workflow_dispatch:" in text
    for trigger in ("schedule:", "push:", "pull_request:", "repository_dispatch:"):
        assert trigger not in text
    assert "github.actor == 'reihl'" in text
    assert "github.triggering_actor == 'reihl'" in text
    assert 'SOURCE_DETAILS_IMAGE_READY:-no' in text
    assert '--sync-state' in text


def test_missing_readback_stops_with_pending_state(tmp_path):
    fake = Fake()
    def ignored(method, kind, url, token=None, data=None):
        if method == "POST":
            return {}
        return fake(method, kind, url, token, data)
    with patch.object(s.api, "execute", ignored):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(s.api.VerificationError):
            s.apply_plan(plan, "ZZtoken", tmp_path / "state")
    assert json.loads((tmp_path / "state").read_text())["status"] == "pending"


def test_checkpoint_commit_uses_local_identity():
    from pathlib import Path
    text = Path(s.__file__).read_text()
    assert "user.email=source-details@localhost" in text
    assert "users.noreply.github.com" not in text


def test_released_metadata_image_is_pinned_with_explicit_readiness():
    from pathlib import Path
    text = (Path(s.__file__).parent / ".github/workflows/geni-upload.yml").read_text()
    assert "sha256:f9ec8988296da9634e2c1cb5feb5df8060b7c99edb804cd0c301741045873909" in text
    assert 'SOURCE_DETAILS_IMAGE_READY: "yes"' in text
    assert '${SOURCE_DETAILS_IMAGE_READY:-no}' in text
