"""Synthetic behavioural contract fixtures for the higher-level API paths.

The remaining slice 2 cases of #93 (design: docs/API-CLIENT-DESIGN.md
section 3.2), built on the slice 2b loopback runner in test_contracts.py.
Each file tests/contracts_behavior/<function>/<case>.json names one engine
function (verify_profile, list_tagged or durable_upload) and one or more
runs. Each run lists the exact requests the function must make, in order,
with the response the fake server returns for each, and the expected
outcome. Runs of one case share the on-disk journal, so a later run is a
fresh restart of the same item.

Everything goes through the real engine and the real execute() against a
127.0.0.1 server. "{base}" in a response is the fake server's own URL and
"{alias}" the same server under another host name, so a cross-host link
that the engine wrongly followed still lands on the fake and is counted.
Values are invented (ids 1000001/1000002, "Test Person").
No live client, no real token, no network beyond loopback.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_contracts import FakeGeni

import geni_upload as g

ROOT = Path(__file__).parent / "contracts_behavior"
FIXTURES = sorted(ROOT.glob("*/*.json"))
TOKEN = "ZZsynthetic"
SYNTHETIC_IDS = {"1000001", "1000002"}
SYNTHETIC_NAMES = {"Test Person", "Other Person"}
OUTCOMES = {"ok", "ApiError", "ThrottledError", "UncertainWrite", "VerificationError"}

# The behaviours #93 asks to pin. A case name missing here means a removed
# fixture, which must be a reviewed test change.
REQUIRED = {
    "verify_profile": {
        "node_id_match",
        "node_id_name_mismatch_no_fallthrough",
        "empty_results_falls_to_guid",
        "node_http_error_falls_to_guid",
        "guid_bare_node_id",
        "guid_mismatch",
        "guid_name_mismatch",
        "guid_wrong_type_id",
        "guid_missing_id",
        "empty_results_both_forms",
        "throttled_no_fallthrough",
        "guid_throttled",
    },
    "list_tagged": {
        "documents_single_page",
        "documents_bare_id",
        "documents_wrong_type_id",
        "documents_empty_results",
        "documents_singleton",
        "documents_invalid_singleton",
        "documents_next_page_chain",
        "documents_next_absolute_same_endpoint",
        "documents_cross_endpoint_next_page",
        "documents_cross_host_next_page",
        "documents_conflicting_pagination",
        "documents_page_cap_unproven",
        "documents_server_error_raises",
        "photos_single_page",
        "photos_cross_endpoint_unavailable",
        "photos_server_error_unavailable",
        "photos_throttled_raises",
    },
    "durable_upload": {
        "add_without_id_never_replays",
        "add_wrong_type_id_never_replays",
        "add_server_error_never_replays",
        "add_bare_id_tag_verified",
        "tag_readback_failure_never_recreates",
        "tag_uncertain_blocks_resume",
    },
}

# durable_upload harness: one synthetic document item, primary target only.
PID = "1000001"
ITEM = {
    "title": "Test Source",
    "source_url": "https://example.invalid/source",
    "description_en": "Synthetic source description for contract tests",
}
KIND_ARGS = {"documents": ("document", "document_add", "document_tag")}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def isolated(monkeypatch):
    """No real sleeps and fresh rate state; the allowlist is the real base
    set (these paths need no runtime widening)."""
    monkeypatch.setattr(g, "_sleep", lambda _s: None)
    monkeypatch.setattr(g, "_RATE", {"min_interval": 0.0, "last": 0.0, "retry_after": 0.0})
    return monkeypatch


def anchors(value):
    """A set of anchor tuples as a sorted JSON-comparable list."""
    if value is None:
        return None
    return sorted((list(a) for a in value), key=json.dumps)


def journal_view(manifest):
    status = g.load_status(manifest)
    (rec,) = status["items"].values()
    return {
        "status": rec.get("status"),
        "create_intent": rec.get("create_intent", False),
        "object_id": rec.get("object_id"),
        "tag_phase": (rec.get("tags") or {}).get(PID, {}).get("phase"),
        "blocked": rec.get("blocked", False),
    }


def call(function, args, tmp_path):
    if function == "verify_profile":
        return list(g.verify_profile(TOKEN, args["pid"], args["expect_name"]))
    if function == "list_tagged":
        return anchors(g.list_tagged(TOKEN, args["pid"], args["kind"]))
    if function == "durable_upload":
        kind = args["kind"]
        base, add_kind, tag_kind = KIND_ARGS[kind]
        manifest = str(tmp_path / "manifest.yaml")
        state_path = str(tmp_path / "state.json")
        # Fresh restart: only what the previous run made durable survives.
        state = g.load_state(state_path)
        status = g.load_status(manifest)
        return g.durable_upload(
            dict(ITEM),
            kind,
            base,
            add_kind,
            tag_kind,
            PID,
            PID,
            TOKEN,
            f"{PID}:{kind}:{ITEM['title']}",
            state,
            state_path,
            status,
            manifest,
            g.RunLog(None),
            False,
            {},
        )
    raise AssertionError(f"unknown function {function}")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_behavior_case(path, isolated, tmp_path):
    case = load(path)
    function, args = case["call"]["function"], case["call"]["args"]
    for number, run in enumerate(case["runs"], 1):
        expect = run["expect"]
        with FakeGeni(run["responses"]) as fake:
            alias = f"http://localhost:{fake.server.server_port}"
            fake.responses = [
                json.loads(json.dumps(spec).replace("{base}", fake.base).replace("{alias}", alias))
                for spec in run["responses"]
            ]
            isolated.setattr(g, "API_BASE", fake.base)
            if expect["outcome"] == "ok":
                assert call(function, args, tmp_path) == expect["result"], f"run {number}"
            else:
                with pytest.raises(g.ApiError) as raised:
                    call(function, args, tmp_path)
                assert type(raised.value).__name__ == expect["outcome"], f"run {number}"
            seen = [(method, p) for method, p, _ in fake.requests]
        wanted = [(spec["method"], spec["path"]) for spec in run["responses"]]
        assert seen == wanted, f"run {number}"
        assert len(seen) == expect["requests"], f"run {number}"
        if "journal" in expect:
            assert journal_view(str(tmp_path / "manifest.yaml")) == expect["journal"], (
                f"run {number}"
            )


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_behavior_fixture_shape(path):
    case = load(path)
    assert set(case) == {"call", "runs"}
    assert case["call"]["function"] == path.parent.name
    assert case["runs"]
    for run in case["runs"]:
        assert set(run) == {"responses", "expect"}
        expect = run["expect"]
        assert expect["outcome"] in OUTCOMES
        assert ("result" in expect) == (expect["outcome"] == "ok")
        assert expect["requests"] == len(run["responses"])
        assert ("journal" in expect) == (path.parent.name == "durable_upload")
        for spec in run["responses"]:
            assert set(spec) == {"method", "path", "status", "body"}
            assert spec["method"] in ("GET", "POST")
            assert spec["path"].startswith("/")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_behavior_fixture_values_are_synthetic(path):
    text = path.read_text(encoding="utf-8")
    for run in re.findall(r"\d{5,}", text):
        assert run in SYNTHETIC_IDS, run
    for name in re.findall(r'"(?:name|display_name)": "([^"]*)"', text):
        assert name in SYNTHETIC_NAMES, name
    for host in re.findall(r"https?://([^/\"]+)", text):
        assert host.endswith(".invalid"), host


def test_every_required_behavior_has_a_fixture():
    present = {}
    for path in FIXTURES:
        present.setdefault(path.parent.name, set()).add(path.stem)
    assert present == REQUIRED


def test_no_post_on_any_resumed_run():
    """Every run after the first is a restart: it may read, never write
    again, except a tag that never had an intent (none in these cases)."""
    for path in FIXTURES:
        for run in load(path)["runs"][1:]:
            assert all(spec["method"] == "GET" for spec in run["responses"]), path
