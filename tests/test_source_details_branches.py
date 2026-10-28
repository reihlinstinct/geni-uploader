"""Synthetic offline tests for source_details refusal branches and CLI paths (#98).

No production service calls: the API is a local fake, git runs only against
throwaway repositories under tmp_path, and every value is invented.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

import source_details as s

ITEM = {
    "key": "ZZsource",
    "kind": "document",
    "object_id": "101",
    "expect": {"source_url": "https://example.invalid/ZZsource"},
    "set": {"description_en": "ZZ approved description", "date": "1933-01-04"},
    "targets": [{"profile_id": "201", "expect_name": "ZZPerson ZZTest"}],
    "manual_facts": ["ZZ name citation"],
}
HASH = "0" * 64


def write(tmp_path, data, name="items.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


def manifest(tmp_path, item=None):
    return write(tmp_path, {"schema_version": 1, "items": [item or ITEM]})


def changed(**changes):
    item = copy.deepcopy(ITEM)
    for key, value in changes.items():
        if value is KeyError:
            del item[key]
        else:
            item[key] = value
    return item


class Fake:
    """Serves one document and profile; records every call."""

    def __init__(self, alive=False):
        self.calls = []
        self.alive = alive
        self.obj = {
            "id": "document-101",
            "title": "ZZ existing",
            "description": "ZZ old",
            "source_url": "https://example.invalid/ZZsource",
            "tags": ["profile-999"],
        }

    def __call__(self, method, kind, url, token=None, data=None):
        self.calls.append((method, kind, url, data))
        if kind == "profile":
            return {
                "id": "profile-201",
                "display_name": "ZZPerson ZZTest",
                "is_alive": self.alive() if callable(self.alive) else self.alive,
            }
        if method == "POST" and kind == "document_update":
            self.obj.update(data)
        if method == "POST" and kind == "document_tag":
            self.obj["tags"].append(url.rsplit("/", 1)[-1])
        return copy.deepcopy(self.obj)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


@pytest.fixture(autouse=True)
def _restore_allowlist():
    # main() widens the shared module-global allowlist; keep tests independent.
    saved = set(s.api.ALLOWLIST)
    yield
    s.api.ALLOWLIST.clear()
    s.api.ALLOWLIST.update(saved)


# --- load_records: every refusal fires before any network access -------------

BAD_DOCUMENTS = {
    "unknown_top_level_key": {"schema_version": 1, "items": [ITEM], "extra": 1},
    "wrong_schema_version": {"schema_version": 2, "items": [ITEM]},
    "items_not_list": {"schema_version": 1, "items": {"0": ITEM}},
    "items_empty": {"schema_version": 1, "items": []},
}

BAD_ITEMS = {
    "item_not_object": ["ZZ"],
    "missing_field": changed(manual_facts=KeyError),
    "description_only_false": changed(description_only=False),
    "unknown_kind": changed(kind="profile"),
    "non_numeric_object_id": changed(object_id="document-101"),
    "expect_empty": changed(expect={}),
    "expect_without_anchor": changed(expect={"description_sha256": HASH}),
    "expect_unknown_key": changed(expect={"title": "ZZ", "guid": "ZZ"}),
    "expect_empty_value": changed(expect={"title": ""}),
    "expect_bad_hash": changed(expect={"title": "ZZ", "description_sha256": "ZZ"}),
    "description_only_without_hash": changed(
        description_only=True, set={"description_en": "ZZ approved description"}
    ),
    "set_empty": changed(set={}),
    "set_field_not_for_kind": changed(kind="photo", set={"labels": "ZZ"}),
    "set_blank_value": changed(set={"title": "  "}),
    "description_only_with_title": changed(
        description_only=True,
        expect={"title": "ZZ", "description_sha256": HASH},
        set={"description_en": "ZZ approved description", "title": "ZZ new"},
    ),
    "targets_empty": changed(targets=[]),
    "target_extra_key": changed(
        targets=[{"profile_id": "201", "expect_name": "ZZA ZZB", "guid": "ZZ"}]
    ),
    "target_non_numeric_id": changed(
        targets=[{"profile_id": "profile-201", "expect_name": "ZZA ZZB"}]
    ),
    "target_single_word_name": changed(targets=[{"profile_id": "201", "expect_name": "ZZA"}]),
    "target_duplicate": changed(
        targets=[
            {"profile_id": "201", "expect_name": "ZZA ZZB"},
            {"profile_id": "201", "expect_name": "ZZA ZZB"},
        ]
    ),
    "manual_facts_not_list": changed(manual_facts="ZZ"),
}


# Each refusal must come from its own branch, not an earlier one.
MESSAGES = {
    "unknown_top_level_key": "schema",
    "wrong_schema_version": "schema",
    "items_not_list": "nonempty list",
    "items_empty": "nonempty list",
    "item_not_object": "item fields",
    "missing_field": "item fields",
    "description_only_false": "must be true",
    "unknown_kind": "ID or kind",
    "non_numeric_object_id": "ID or kind",
    "expect_empty": "title or source URL",
    "expect_without_anchor": "title or source URL",
    "expect_unknown_key": "title or source URL",
    "expect_empty_value": "title or source URL",
    "expect_bad_hash": "description hash",
    "description_only_without_hash": "requires expected old description hash",
    "set_empty": "metadata fields",
    "set_field_not_for_kind": "metadata fields",
    "set_blank_value": "metadata fields",
    "description_only_with_title": "English description fields only",
    "targets_empty": "explicit targets",
    "target_extra_key": "target identity",
    "target_non_numeric_id": "target identity",
    "target_single_word_name": "target identity",
    "target_duplicate": "duplicate target",
    "manual_facts_not_list": "manual_facts",
}


def test_every_bad_case_has_a_message():
    assert set(MESSAGES) == set(BAD_DOCUMENTS) | set(BAD_ITEMS)


@pytest.mark.parametrize("name", sorted(BAD_DOCUMENTS))
def test_invalid_document_refused(tmp_path, name):
    with pytest.raises(s.api.ApiError, match=MESSAGES[name]):
        s.load_records(write(tmp_path, BAD_DOCUMENTS[name]))


@pytest.mark.parametrize("name", sorted(BAD_ITEMS))
def test_invalid_item_refused(tmp_path, name):
    bad = BAD_ITEMS[name]
    items = bad if isinstance(bad, list) else [bad]
    with pytest.raises(s.api.ApiError, match=MESSAGES[name]):
        s.load_records(write(tmp_path, {"schema_version": 1, "items": items}))


def test_valid_description_only_item_accepted(tmp_path):
    item = changed(
        description_only=True,
        expect={"title": "ZZ existing", "description_sha256": HASH},
        set={"description_en": "ZZ approved description"},
    )
    assert s.load_records(manifest(tmp_path, item))[0]["description_only"] is True


# --- CLI: validate / plan / repair / snapshot -----------------------------------


def run_main(argv, fake=None, token="ZZtoken"):
    fake = fake or Fake()
    with (
        patch.object(sys, "argv", ["source_details.py", *argv]),
        patch.object(s.api, "execute", fake),
        patch.object(s.api, "get_token", return_value=token) as get_token,
    ):
        code = s.main()
    return code, fake, get_token


def test_cli_validate_reads_no_token_and_makes_no_call(tmp_path, capsys):
    code, fake, get_token = run_main(["validate", "--manifest", str(manifest(tmp_path))])
    assert code == 0
    assert "source-details schema valid" in capsys.readouterr().out
    assert fake.calls == [] and not get_token.called


@pytest.mark.parametrize(
    "argv, reason",
    [
        (["repair", "--state", "ZZstate"], "no confirm"),
        (["repair", "--confirm", "yes", "--state", "ZZstate"], "lower-case confirm"),
        (["repair", "--confirm", "YES"], "no state path"),
        (["snapshot"], "no output path"),
    ],
)
def test_cli_refusals_stop_before_token_or_network(tmp_path, capsys, argv, reason):
    rest = [str(tmp_path / "state.json") if a == "ZZstate" else a for a in argv[1:]]
    args = [argv[0], "--manifest", str(manifest(tmp_path)), *rest]
    code, fake, get_token = run_main(args)
    out = capsys.readouterr().out
    assert code == 1, reason
    assert "stopped category=api" in out
    assert fake.calls == [] and not get_token.called
    assert "ZZ" not in out  # nothing from the manifest is echoed
    assert not (tmp_path / "state.json.lock").exists()


def test_cli_plan_checks_identities_and_never_posts(tmp_path, capsys):
    code, fake, _ = run_main(["plan", "--manifest", str(manifest(tmp_path))])
    assert code == 0
    assert "no writes" in capsys.readouterr().out
    assert fake.calls and not fake.posts()


def test_cli_repair_writes_then_verifies(tmp_path, capsys):
    state = tmp_path / "state.json"
    code, fake, _ = run_main(
        ["repair", "--manifest", str(manifest(tmp_path)), "--confirm", "YES", "--state", str(state)]
    )
    assert code == 0
    assert json.loads(state.read_text()) == {"status": "verified"}
    assert [c[1] for c in fake.posts()] == ["document_update", "document_tag"]
    assert "stage=repair result=pass" in capsys.readouterr().out


def test_cli_repair_held_lock_stops_before_token(tmp_path, capsys):
    import fcntl

    state = tmp_path / "state.json"
    with open(str(state) + ".lock", "w", encoding="utf-8") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code, fake, get_token = run_main(
            [
                "repair",
                "--manifest",
                str(manifest(tmp_path)),
                "--confirm",
                "YES",
                "--state",
                str(state),
            ]
        )
    assert code == 1
    assert "stopped category=filesystem" in capsys.readouterr().out
    assert fake.calls == [] and not get_token.called


def test_cli_snapshot_writes_private_output(tmp_path, capsys):
    out = tmp_path / "snap.json"
    code, fake, _ = run_main(
        ["snapshot", "--manifest", str(manifest(tmp_path)), "--output", str(out)]
    )
    assert code == 0
    assert json.loads(out.read_text())["citations"] == "unsupported"
    assert not fake.posts()


def test_cli_missing_manifest_is_filesystem_category(tmp_path, capsys):
    code, fake, _ = run_main(["validate", "--manifest", str(tmp_path / "absent.json")])
    assert code == 1
    assert "stopped category=filesystem" in capsys.readouterr().out
    assert fake.calls == []


def test_cli_malformed_json_is_input_category(tmp_path, capsys):
    p = tmp_path / "items.json"
    p.write_text("{ZZ not json")
    code, _, _ = run_main(["validate", "--manifest", str(p)])
    assert code == 1
    assert "stopped category=input" in capsys.readouterr().out


@pytest.mark.parametrize(
    "make_error, category",
    [
        # Built at run time: other tests reload geni_upload, which replaces its classes.
        (lambda: s.api.ThrottledError("ZZ"), "throttled"),
        (lambda: s.api.UncertainWrite("ZZ"), "uncertain_write"),
        (lambda: s.api.VerificationError("ZZ"), "verification"),
        (lambda: subprocess.CalledProcessError(1, ["ZZ"]), "subprocess"),
        (lambda: TypeError("ZZ"), "input"),
        (lambda: s.api.ApiError("ZZ"), "api"),
    ],
    ids=["throttled", "uncertain_write", "verification", "subprocess", "input", "api"],
)
def test_cli_error_categories_never_echo(tmp_path, capsys, make_error, category):
    def failing(*_args, **_kwargs):
        raise make_error()

    code, _, _ = run_main(["plan", "--manifest", str(manifest(tmp_path))], fake=failing)
    out = capsys.readouterr().out
    assert code == 1
    assert f"stopped category={category};" in out
    assert "ZZ" not in out


# --- snapshot -------------------------------------------------------------------


def test_snapshot_stops_if_target_turns_living_and_writes_nothing(tmp_path):
    # verify_profile and deceased_target both see a deceased profile; the
    # snapshot's own read then sees it living and must stop.
    answers = iter([False, False, True])
    fake = Fake(alive=lambda: next(answers))
    out = tmp_path / "snap.json"
    with (
        patch.object(s.api, "execute", fake),
        pytest.raises(s.api.ApiError, match="no longer confirmed deceased"),
    ):
        s.snapshot(s.load_records(manifest(tmp_path)), "ZZtoken", out)
    assert not out.exists()


def test_snapshot_reads_a_shared_target_once(tmp_path):
    second = changed(key="ZZsecond", object_id="102")
    p = write(tmp_path, {"schema_version": 1, "items": [ITEM, second]})
    fake = Fake()
    out = tmp_path / "snap.json"
    with patch.object(s.api, "execute", fake):
        s.snapshot(s.load_records(p), "ZZtoken", out)
    assert len(json.loads(out.read_text())["profiles"]) == 1


# --- apply_plan: mixing and durable state sync ----------------------------------


def test_mixed_description_only_and_tag_repairs_refused(tmp_path):
    plain = (copy.deepcopy(ITEM), {}, [])
    desc = (changed(description_only=True), {}, [])
    with patch.object(s.api, "execute") as call, pytest.raises(s.api.ApiError, match="mixed"):
        s.apply_plan([plain, desc], "ZZtoken", tmp_path / "state")
    assert not call.called


def test_tags_removed_by_update_stop(tmp_path):
    fake = Fake()

    def dropping(method, kind, url, token=None, data=None):
        result = fake(method, kind, url, token, data)
        if method == "POST" and kind == "document_update":
            fake.obj["tags"] = []
        return result

    with patch.object(s.api, "execute", dropping):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(s.api.VerificationError, match="tags changed"):
            s.apply_plan(plan, "ZZtoken", tmp_path / "state")
    assert [c[1] for c in fake.posts()] == ["document_update"]


def test_tag_readback_missing_stops(tmp_path):
    fake = Fake()

    def ignored_tag(method, kind, url, token=None, data=None):
        if method == "POST" and kind == "document_tag":
            fake.calls.append((method, kind, url, data))
            return {}
        return fake(method, kind, url, token, data)

    with patch.object(s.api, "execute", ignored_tag):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(s.api.VerificationError, match="tag readback"):
            s.apply_plan(plan, "ZZtoken", tmp_path / "state")
    assert json.loads((tmp_path / "state").read_text())["status"] == "pending"


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def synthetic_repo(tmp_path):
    """A throwaway clone with a local bare origin; nothing leaves tmp_path."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(
        work,
        "-c",
        "user.name=ZZ",
        "-c",
        "user.email=zz@localhost",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "ZZ init",
    )
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    return origin, work


@needs_git
def test_sync_state_pushes_pending_before_first_post(tmp_path, monkeypatch):
    origin, work = synthetic_repo(tmp_path)
    monkeypatch.chdir(work)
    monkeypatch.setenv("GENI_UPLOAD_REF", "main")
    fake = Fake()
    remote_at_first_post = []

    def recording(method, kind, url, token=None, data=None):
        if method == "POST" and not remote_at_first_post:
            remote_at_first_post.append(
                git(tmp_path, "--git-dir", str(origin), "show", "main:state.json")
            )
        return fake(method, kind, url, token, data)

    with patch.object(s.api, "execute", recording):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        s.apply_plan(plan, "ZZtoken", work / "state.json", sync_state=True)
    assert json.loads(remote_at_first_post[0]) == {"status": "pending"}
    remote = git(tmp_path, "--git-dir", str(origin), "show", "main:state.json")
    assert json.loads(remote) == {"status": "verified"}
    author = git(work, "log", "-1", "--format=%an <%ae>")
    assert author == "source-details <source-details@localhost>"


@needs_git
def test_sync_state_without_branch_stops_before_any_post(tmp_path, monkeypatch):
    _, work = synthetic_repo(tmp_path)
    monkeypatch.chdir(work)
    monkeypatch.delenv("GENI_UPLOAD_REF", raising=False)
    fake = Fake()
    with patch.object(s.api, "execute", fake):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(s.api.ApiError, match="explicit branch"):
            s.apply_plan(plan, "ZZtoken", work / "state.json", sync_state=True)
    assert fake.posts() == []


@needs_git
def test_sync_state_outside_a_repository_stops_before_any_post(tmp_path, monkeypatch):
    bare_dir = tmp_path / "plain"
    bare_dir.mkdir()
    monkeypatch.chdir(bare_dir)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GENI_UPLOAD_REF", "main")
    fake = Fake()
    with patch.object(s.api, "execute", fake):
        plan = s.checked_plan(s.load_records(manifest(tmp_path)), "ZZtoken")
        with pytest.raises(subprocess.CalledProcessError):
            s.apply_plan(plan, "ZZtoken", bare_dir / "state.json", sync_state=True)
    assert fake.posts() == []
    assert os.listdir(bare_dir) in ([], ["state.json"])
