"""Allowlist snapshot and photo-path contract tests (slice 2a of #93).

Synthetic offline tests. No production service calls: `execute` is replaced
by an in-memory fake, and the allowlist is read in a fresh child interpreter
because source_details.main() widens the module-global set at runtime.
"""
import ast
import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import source_details as s

ROOT = Path(__file__).resolve().parents[1]

BASE_ALLOWLIST = {
    ("GET", "user"), ("GET", "user_managed_profiles"),
    ("GET", "profile"), ("GET", "profile_documents"), ("GET", "profile_photos"),
    ("POST", "document_add"), ("POST", "photo_add"),
    ("POST", "document_tag"), ("POST", "photo_tag"),
}
SOURCE_DETAILS_WIDENING = {
    ("GET", "document"), ("GET", "photo"),
    ("POST", "document_update"), ("POST", "photo_update"),
}


def test_base_allowlist_snapshot_in_fresh_interpreter():
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import json, geni_upload;"
            "print(json.dumps(sorted(geni_upload.ALLOWLIST)))")
    env = {"PATH": "/usr/bin:/bin"}
    out = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True,
                         text=True, timeout=60, env=env, check=True).stdout
    assert {tuple(pair) for pair in json.loads(out)} == BASE_ALLOWLIST


def _widening_calls():
    tree = ast.parse((ROOT / "source_details.py").read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "ALLOWLIST"):
            calls.append(node)
    return calls


def test_source_details_widening_snapshot():
    calls = _widening_calls()
    assert len(calls) == 1, "exactly one ALLOWLIST mutation is reviewed"
    call = calls[0]
    assert call.func.attr == "update" and not call.keywords and len(call.args) == 1
    assert set(ast.literal_eval(call.args[0])) == SOURCE_DETAILS_WIDENING


def test_widening_never_adds_delete_untag_or_profile_writes():
    allowed = BASE_ALLOWLIST | SOURCE_DETAILS_WIDENING
    assert not {kind for _, kind in allowed} & {
        "document_delete", "photo_delete", "document_untag", "photo_untag",
        "profile_update", "profile_add", "citation"}
    assert all(method in {"GET", "POST"} for method, _ in allowed)


# --- photo path parity with the document path --------------------------------

def item_for(kind):
    return {"key": "ZZsource", "kind": kind, "object_id": "101",
            "expect": {"source_url": "https://example.invalid/ZZsource"},
            "set": {"description_en": "ZZ approved description", "date": "1933-01-04"},
            "targets": [{"profile_id": "201", "expect_name": "ZZPerson ZZTest"}],
            "manual_facts": ["ZZ name citation"]}


def manifest(tmp_path, item):
    p = tmp_path / "items.json"
    p.write_text(json.dumps({"schema_version": 1, "items": [item]}))
    return p


class KindFake:
    """In-memory Geni stand-in for one existing object of either kind."""

    def __init__(self, kind, served_id=None, ignore_update=False):
        self.kind = kind
        self.calls = []
        self.ignore_update = ignore_update
        self.obj = {"id": served_id or f"{kind}-101", "title": "ZZ existing",
                    "description": "ZZ old", "source_url": "https://example.invalid/ZZsource",
                    "tags": ["profile-999"]}

    def __call__(self, method, kind, url, token=None, data=None):
        self.calls.append((method, kind, url, data))
        if kind == "profile":
            return {"id": "profile-201", "display_name": "ZZPerson ZZTest", "is_alive": False}
        assert kind.split("_")[0] == self.kind, "calls must stay on the item's kind"
        if method == "POST" and kind == f"{self.kind}_update" and not self.ignore_update:
            self.obj.update(data)
        if method == "POST" and kind == f"{self.kind}_tag":
            self.obj["tags"].append(url.rsplit("/", 1)[-1])
        return copy.deepcopy(self.obj)

    def posts(self):
        return [(m, k, u) for m, k, u, _ in self.calls if m == "POST"]


@pytest.mark.parametrize("kind", ["document", "photo"])
def test_repair_uses_kind_endpoints_keeps_tags_and_is_idempotent(tmp_path, kind):
    fake = KindFake(kind)
    with patch.object(s.api, "execute", fake):
        items = s.load_records(manifest(tmp_path, item_for(kind)))
        s.apply_plan(s.checked_plan(items, "ZZtoken"), "ZZtoken", tmp_path / "state")
        first = fake.posts()
        s.apply_plan(s.checked_plan(items, "ZZtoken"), "ZZtoken", tmp_path / "state")
    assert fake.posts() == first, "second run must not POST again"
    assert [k for _, k, _ in first] == [f"{kind}_update", f"{kind}_tag"]
    assert first[0][2].endswith(f"/{kind}-101/update")
    assert first[1][2].endswith(f"/{kind}-101/tag/profile-201")
    gets = {(m, k) for m, k, _, _ in fake.calls if m == "GET"}
    assert (("GET", kind) in gets) and (("GET", "profile") in gets)
    assert set(fake.obj["tags"]) == {"profile-999", "profile-201"}
    assert fake.obj["description"] == item_for(kind)["set"]["description_en"]


@pytest.mark.parametrize("kind, served", [("photo", "document-101"), ("photo", "photo-102"),
                                          ("photo", "101"), ("document", "photo-101")])
def test_object_read_requires_exact_typed_id_before_any_post(tmp_path, kind, served):
    fake = KindFake(kind, served_id=served)
    with patch.object(s.api, "execute", fake), pytest.raises(s.api.ApiError):
        s.checked_plan(s.load_records(manifest(tmp_path, item_for(kind))), "ZZtoken")
    assert fake.posts() == []


def test_photo_update_unconfirmed_readback_stops_before_tag(tmp_path):
    fake = KindFake("photo", ignore_update=True)
    with patch.object(s.api, "execute", fake), pytest.raises(s.api.VerificationError):
        items = s.load_records(manifest(tmp_path, item_for("photo")))
        s.apply_plan(s.checked_plan(items, "ZZtoken"), "ZZtoken", tmp_path / "state")
    assert [k for _, k, _ in fake.posts()] == ["photo_update"]
    assert json.loads((tmp_path / "state").read_text())["status"] == "pending"


def test_photo_rejects_document_only_field(tmp_path):
    item = item_for("photo")
    item["set"]["labels"] = "ZZ label"
    with pytest.raises(s.api.ApiError):
        s.load_records(manifest(tmp_path, item))



# --- effective runtime allowlist ------------------------------------------

RUNTIME_PROBE = """
import json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
def _hook(event, args):
    if event.startswith("socket.") or event in {"urllib.Request", "subprocess.Popen"}:
        raise RuntimeError("BLOCKED:" + event)
sys.addaudithook(_hook)
import geni_upload, source_details
def _no_network(*args, **kwargs):
    raise AssertionError("execute must not run in the allowlist probe")
geni_upload.execute = _no_network
geni_upload.get_token = lambda args: "ZZsynthetic-probe-token"
seen = []
def _stop(items, token):
    seen.append(sorted(geni_upload.ALLOWLIST))
    raise SystemExit(0)
source_details.checked_plan = _stop
sys.argv = ["source_details", "plan", "--manifest", sys.argv[3]]
try:
    source_details.main()
except SystemExit:
    pass
print(json.dumps(seen[0] if seen else None))
"""


def effective_allowlist(tmp_path, source_dir=ROOT):
    """The ALLOWLIST as source_details.main() leaves it, just before plan work."""
    manifest_path = tmp_path / "items.json"
    manifest_path.write_text(json.dumps({"schema_version": 1, "items": [item_for("photo")]}))
    out = subprocess.run(
        [sys.executable, "-I", "-c", RUNTIME_PROBE, str(source_dir), str(ROOT),
         str(manifest_path)],
        capture_output=True, text=True, timeout=60, env={"PATH": "/usr/bin:/bin"},
        check=True, cwd=tmp_path,
    ).stdout
    value = json.loads(out.strip().splitlines()[-1])
    assert value is not None, "main() never reached the plan stage"
    return {tuple(pair) for pair in value}


def test_effective_runtime_allowlist_of_source_details_main(tmp_path):
    assert effective_allowlist(tmp_path) == BASE_ALLOWLIST | SOURCE_DETAILS_WIDENING


@pytest.mark.parametrize("mutation", [
    "api.ALLOWLIST |= {('POST', 'photo_delete')}",
    "api.ALLOWLIST.add(('POST', 'photo_delete'))",
    "setattr(api, 'ALLOWLIST', api.ALLOWLIST | {('POST', 'photo_delete')})",
])
def test_runtime_snapshot_catches_planted_widening(tmp_path, mutation):
    source = (ROOT / "source_details.py").read_text(encoding="utf-8")
    anchor = '("POST", "document_update"), ("POST", "photo_update")})\n'
    assert source.count(anchor) == 1
    mutated = tmp_path / "mutated"
    mutated.mkdir()
    (mutated / "source_details.py").write_text(
        source.replace(anchor, anchor + "        " + mutation + "\n"), encoding="utf-8")
    effective = effective_allowlist(tmp_path, mutated)
    assert ("POST", "photo_delete") in effective
    assert effective != BASE_ALLOWLIST | SOURCE_DETAILS_WIDENING