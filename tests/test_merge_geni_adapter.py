"""Synthetic Geni merge adapter contract. Fake opener only; no network or real identities."""

import copy
import json
import re
import time
from urllib.error import HTTPError

import pytest

from geni_uploader.core.merge_request import InvalidMergeRequest, digest
from geni_uploader.workflow import merge_engine
from geni_uploader.workflow.merge_engine import _execute_admitted, admit, execute
from geni_uploader.workflow.merge_geni_adapter import (
    POLICY_SHA256,
    TRACKED_FIELDS,
    GeniMergeAdapter,
    _canonical_hash,
    _guid_path,
    _node_path,
)
from geni_uploader.workflow.merge_http import BoundedJSONHTTP

pytest_plugins = ["test_merge_request"]

ORIGIN = "https://www.geni.com"
SURVIVOR = "profile-990002"
SOURCE = "profile-990003"


def tracked(**values):
    base = {field: None for field in TRACKED_FIELDS}
    base.update(values)
    return base


SURVIVOR_TRACKED = tracked(first_name="ZZFirst", birth={"date": "ZZ-1900"})
SOURCE_TRACKED = tracked(first_name="ZZFirst", maiden_name="ZZSource", birth={"date": "ZZ-1901"})


def served(node, guid, name="ZZPersona", **extra):
    body = {
        "id": node,
        "guid": guid,
        "name": name,
        "merge_pending": False,
        "claimed": False,
        "locked": False,
    }
    body.update(extra)
    return body


class Response:
    def __init__(self, url, raw, status=200, headers=None):
        self.url, self.raw, self.status, self.headers = url, raw, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return self.raw[:count]


class Opener:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        value = self.responses[request.full_url]
        if isinstance(value, Exception):
            raise value
        return value


def route(url, body, **kwargs):
    return Response(url, json.dumps(body).encode(), **kwargs)


def transport_with(routes):
    client = BoundedJSONHTTP(ORIGIN, "ZZ-token")
    opener_routes = {}
    for path, body in routes.items():
        if isinstance(body, Exception):
            opener_routes[ORIGIN + path] = body
        else:
            opener_routes[ORIGIN + path] = route(ORIGIN + path, body)
    client._opener = Opener(opener_routes)
    return client


def premerge_routes():
    return {
        "/api/user": {"id": "profile-990001", "guid": "999001", "name": "ZZOwner"},
        _guid_path("101"): served(SURVIVOR, "101", **SURVIVOR_TRACKED),
        _guid_path("102"): served(SOURCE, "102", **SOURCE_TRACKED),
    }


def postmerge_routes():
    remaining = served(
        SURVIVOR, "101", first_name="ZZFirst", maiden_name="ZZSource", birth={"date": "ZZ-1900"}
    )
    # The retired profile survives and retains its exact pre-merge tracked
    # values; those retained values are the Conflict Center alternatives.
    retired = served(SOURCE, "102", merged_into=SURVIVOR, **SOURCE_TRACKED)
    return {_node_path(SURVIVOR): remaining, _node_path(SOURCE): retired}


@pytest.fixture
def approved_plan(proposal):
    return {
        "schema": "geni-explicit-merge-plan/v1",
        "request_id": "ZZ-request",
        "request_sha256": digest(proposal),
        "owner": "profile-990001",
        "expires_at": 1999999999,
        "policy_sha256": POLICY_SHA256,
        "pairs": [
            {
                "pair_id": "ZZ-pair",
                "path_order": [SURVIVOR, SOURCE],
                "survivor_guid": "101",
                "resolved": {
                    "101": {
                        "id": SURVIVOR,
                        "expect_name": "ZZPersona",
                        "tracked": copy.deepcopy(SURVIVOR_TRACKED),
                    },
                    "102": {
                        "id": SOURCE,
                        "expect_name": "ZZPersona",
                        "tracked": copy.deepcopy(SOURCE_TRACKED),
                    },
                },
            }
        ],
    }


@pytest.fixture
def binding(proposal, approved_plan):
    return {
        "proposal_sha256": digest(proposal),
        "private_commit": "a" * 40,
        "executor_sha": "b" * 40,
        "workflow_sha256": "c" * 64,
        "plan_sha256": _canonical_hash(approved_plan),
        "owner_id": "1",
        "dispatcher_id": "2",
        "reviewer_id": "1",
        "run_id": "3",
        "run_attempt": 1,
        "issued_at": 100,
        "expires_at": 200,
        "approval_event_sha256": "e" * 64,
    }


def make_adapter(routes, proposal, binding, approved_plan, clock=lambda: 150):
    return GeniMergeAdapter(
        transport_with(routes),
        proposal,
        binding,
        copy.deepcopy(binding),
        approved_plan,
        clock=clock,
    )


class Ledger:
    def __init__(self):
        self.claims = []

    def claim(self, key, binding_hash):
        self.claims.append(key)
        return True


class Evidence:
    def __init__(self):
        self.rows = []

    def save(self, state):
        self.rows.append(copy.deepcopy(state))


# Section: Approved plan schema validation


def test_canonical_hash_matches_engine_binding_hash():
    sample = {"ZZ": [1, {"b": True, "a": None}], "a": "x"}
    assert _canonical_hash(sample) == merge_engine._hash(sample)


def test_valid_plan_constructs(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    assert adapter.now() == 150


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", "geni-explicit-merge-plan/v0"),
        ("request_id", "ZZ-other"),
        ("owner", "profile-990004"),
        ("expires_at", 0),
        ("expires_at", 2000000001),
        ("policy_sha256", "0" * 64),
        ("request_sha256", "0" * 64),
        ("pairs", []),
    ],
)
def test_plan_rejections(proposal, binding, approved_plan, key, value):
    approved_plan[key] = value
    if key == "request_sha256" or key == "policy_sha256":
        binding["plan_sha256"] = _canonical_hash(approved_plan)
    if key == "request_id":
        binding["plan_sha256"] = _canonical_hash(approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter plan blocked$"):
        make_adapter(premerge_routes(), proposal, binding, approved_plan)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda pp: pp.update({"pair_id": "ZZ-other"}),
        lambda pp: pp.update({"path_order": [SURVIVOR]}),
        lambda pp: pp.update({"path_order": [SURVIVOR, SURVIVOR]}),
        lambda pp: pp.update({"path_order": ["profile-990004", "profile-990001"]}),
        lambda pp: pp.update({"survivor_guid": "102"}),
        lambda pp: pp["resolved"].pop("102"),
        lambda pp: pp["resolved"]["101"].update({"id": "profile-990004"}),
        lambda pp: pp["resolved"]["101"].update({"expect_name": "ZZOther"}),
        lambda pp: pp["resolved"]["101"]["tracked"].pop("birth"),
        lambda pp: pp["resolved"]["101"]["tracked"].update({"ZZ-extra": 1}),
        lambda pp: pp["resolved"]["101"].update({"tracked": {"birth": "x" * 70000}}),
    ],
)
def test_pair_plan_rejections(proposal, binding, approved_plan, mutate):
    mutate(approved_plan["pairs"][0])
    binding["plan_sha256"] = _canonical_hash(approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter plan blocked$"):
        make_adapter(premerge_routes(), proposal, binding, approved_plan)


def test_plan_digest_must_match_binding(proposal, binding, approved_plan):
    binding["plan_sha256"] = "0" * 64
    with pytest.raises(InvalidMergeRequest, match="^merge adapter plan blocked$"):
        make_adapter(premerge_routes(), proposal, binding, approved_plan)


def test_tracked_with_null_bytes_still_bounded(proposal, binding, approved_plan):
    big = tracked(first_name="x" * 70000)
    approved_plan["pairs"][0]["resolved"]["101"]["tracked"] = big
    binding["plan_sha256"] = _canonical_hash(approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter plan blocked$"):
        make_adapter(premerge_routes(), proposal, binding, approved_plan)


# Section: Clock and wire shape


def test_constructor_rejects_non_geni_origin(proposal, binding, approved_plan):
    transport = BoundedJSONHTTP("https://api.github.com", "ZZ-token")
    transport._opener = Opener({})
    with pytest.raises(InvalidMergeRequest, match="^merge adapter transport blocked$"):
        GeniMergeAdapter(
            transport, proposal, binding, copy.deepcopy(binding), approved_plan, clock=lambda: 150
        )


def test_now_is_utc_epoch_int_with_real_clock(proposal, binding, approved_plan):
    adapter = GeniMergeAdapter(
        transport_with({}), proposal, binding, copy.deepcopy(binding), approved_plan
    )
    assert type(adapter.now()) is int and abs(adapter.now() - int(time.time())) < 60


def test_clock_must_return_positive_number(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan, clock=lambda: -1)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter clock blocked$"):
        adapter.now()


def test_guid_and_node_paths_are_exact_and_unpaged():
    fields = (
        "id,guid,name,claimed,locked,is_alive,public,master_profile,merge_note,"
        "merge_pending,merged_into,display_name,first_name,middle_name,last_name,"
        "maiden_name,suffix,nicknames,names,gender,occupation,about_me,birth,death,"
        "baptism,burial"
    )
    assert _guid_path("101") == "/api/profile-g101?only_ids=true&fields=" + fields
    assert _node_path(SURVIVOR) == "/api/" + SURVIVOR + "?only_ids=true&fields=" + fields


# Section: Preflight


def test_preflight_happy_shape(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    assert plan["ready"] is True
    assert plan["pair_id"] == "ZZ-pair"
    assert plan["resolved_ids"] == [SURVIVOR, SOURCE]
    assert plan["path_order"] == [SURVIVOR, SOURCE]
    assert plan["expected_survivor_id"] == SURVIVOR
    assert plan["binding_sha256"] == admit(proposal, binding, copy.deepcopy(binding), 150)
    assert plan["plan_sha256"] == binding["plan_sha256"]
    assert set(plan["before"]) == {SURVIVOR, SOURCE}
    assert plan["before"][SOURCE]["tracked"] == SOURCE_TRACKED


@pytest.mark.parametrize(
    "node,extra",
    [
        ("101", {"merge_pending": True}),
        ("101", {"merged_into": SOURCE}),
        ("101", {"claimed": True}),
        ("102", {"locked": True}),
        ("102", {"name": "ZZOther"}),
        ("101", {"guid": "999"}),
        ("102", {"id": "profile-990004"}),
        ("101", {"first_name": "ZZChanged"}),
    ],
)
def test_preflight_rejects_drift_and_unmergeable(proposal, binding, approved_plan, node, extra):
    routes = premerge_routes()
    routes[_guid_path(node)] = dict(routes[_guid_path(node)], **extra)
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest):
        adapter.preflight(proposal["pairs"][0], binding)


def test_preflight_rejects_owner_mismatch(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/user"] = {"id": "profile-990004"}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter owner blocked$"):
        adapter.preflight(proposal["pairs"][0], binding)


def test_preflight_rejects_binding_mismatch(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    other = dict(binding, run_id="9")
    with pytest.raises(InvalidMergeRequest, match="^merge adapter binding blocked$"):
        adapter.preflight(proposal["pairs"][0], other)


def test_preflight_rejects_expired_binding(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan, clock=lambda: 250)
    with pytest.raises(InvalidMergeRequest):
        adapter.preflight(proposal["pairs"][0], binding)


def test_preflight_rejects_expired_plan(proposal, binding, approved_plan):
    approved_plan["expires_at"] = 150
    binding["expires_at"] = 300
    binding["plan_sha256"] = _canonical_hash(approved_plan)
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter plan blocked$"):
        adapter.preflight(proposal["pairs"][0], binding)


def test_preflight_rejects_foreign_or_tampered_pair(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter preflight blocked$"):
        adapter.preflight({"pair_id": "ZZ-other"}, binding)
    tampered = copy.deepcopy(proposal["pairs"][0])
    tampered["left"]["expect_name"] = "ZZOther"
    with pytest.raises(InvalidMergeRequest, match="^merge adapter preflight blocked$"):
        adapter.preflight(tampered, binding)


def test_transport_failure_latches_without_new_calls(proposal, binding, approved_plan):
    routes = {"/api/user": HTTPError(ORIGIN + "/api/user", 429, "ZZ", {}, None)}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge transport HTTP failure; do not retry$"):
        adapter.preflight(proposal["pairs"][0], binding)
    assert len(adapter._transport._opener.calls) == 1
    with pytest.raises(InvalidMergeRequest, match="^merge adapter halted; do not retry$"):
        adapter.preflight(proposal["pairs"][0], binding)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter halted; do not retry$"):
        adapter.post_once({"pair_id": "ZZ-pair"})
    assert len(adapter._transport._opener.calls) == 1


# Section: Single POST


def test_post_once_exact_path_and_single_use(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    response = adapter.post_once(plan)
    assert response == {"id": SURVIVOR}
    posts = [r for r in adapter._transport._opener.calls if r.get_method() == "POST"]
    assert len(posts) == 1
    assert posts[0].full_url == ORIGIN + "/api/" + SURVIVOR + "/merge/" + SOURCE
    assert posts[0].data is None
    with pytest.raises(InvalidMergeRequest, match="^merge adapter post blocked$"):
        adapter.post_once(plan)
    assert len([r for r in adapter._transport._opener.calls if r.get_method() == "POST"]) == 1


def test_post_once_requires_preflight_and_approved_order(proposal, binding, approved_plan):
    adapter = make_adapter(premerge_routes(), proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter post blocked$"):
        adapter.post_once({"ready": True, "pair_id": "ZZ-pair", "path_order": [SURVIVOR, SOURCE]})
    plan = adapter.preflight(proposal["pairs"][0], binding)
    tampered = dict(plan, path_order=[SOURCE, SURVIVOR])
    with pytest.raises(InvalidMergeRequest, match="^merge adapter post blocked$"):
        adapter.post_once(tampered)


def test_post_once_rejects_in_place_mutated_plan(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    plan["path_order"].reverse()
    with pytest.raises(InvalidMergeRequest, match="^merge adapter post blocked$"):
        adapter.post_once(plan)
    assert len([r for r in adapter._transport._opener.calls if r.get_method() == "POST"]) == 0


def test_readback_rejects_in_place_mutated_before(proposal, binding, approved_plan):
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, postmerge_routes())
    plan["before"][SURVIVOR]["tracked"]["birth"] = {"date": "ZZ-1901"}
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, response)


def test_post_once_rechecks_freshness_at_the_attempt(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    now = [150]
    adapter = make_adapter(routes, proposal, binding, approved_plan, clock=lambda: now[0])
    plan = adapter.preflight(proposal["pairs"][0], binding)
    # The binding expires at 200; a POST long after preflight is never sent.
    now[0] = 10**9
    with pytest.raises(InvalidMergeRequest, match="^merge adapter post blocked$"):
        adapter.post_once(plan)
    assert len([r for r in adapter._transport._opener.calls if r.get_method() == "POST"]) == 0


def test_post_once_http_failure_latches(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = HTTPError(
        ORIGIN + "/api/" + SURVIVOR + "/merge/" + SOURCE, 500, "ZZ", {}, None
    )
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    with pytest.raises(InvalidMergeRequest, match="^merge transport HTTP failure; do not retry$"):
        adapter.post_once(plan)
    assert "ZZ-pair" in adapter._posted
    with pytest.raises(InvalidMergeRequest, match="^merge adapter halted; do not retry$"):
        adapter.post_once(plan)
    assert len([r for r in adapter._transport._opener.calls if r.get_method() == "POST"]) == 1


# Section: Readback


def verified_adapter(proposal, binding, approved_plan, post_routes):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    routes.update(post_routes)
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    response = adapter.post_once(plan)
    return adapter, plan, response


def test_readback_happy_reports_conflicts(proposal, binding, approved_plan):
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, postmerge_routes())
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback == {
        "identity_verified": True,
        "information_preserved": True,
        "conflict_center_checked": True,
        "conflicts": [
            {"field": "birth", "kept": {"date": "ZZ-1900"}, "alternative": {"date": "ZZ-1901"}}
        ],
        "remaining_id": SURVIVOR,
        "remaining_is_approved_survivor": True,
        "pending": False,
    }


def test_readback_direction_flip_is_a_distinct_reported_outcome(
    proposal, binding, approved_plan
):
    remaining = served(SOURCE, "102", **SOURCE_TRACKED)
    retired = served(SURVIVOR, "101", merged_into=SOURCE, **SURVIVOR_TRACKED)
    routes = {_node_path(SOURCE): remaining, _node_path(SURVIVOR): retired}
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["remaining_id"] == SOURCE
    assert readback["remaining_is_approved_survivor"] is False
    # Fail closed: the current engine records UNKNOWN and stops; the engine
    # lane's update prioritizes the flip flag as SURVIVOR_FLIP_REVIEW_REQUIRED.
    assert readback["identity_verified"] is False
    assert readback["information_preserved"] is True
    assert readback["conflict_center_checked"] is True
    assert readback["conflicts"] == [
        {"field": "birth", "kept": {"date": "ZZ-1901"}, "alternative": {"date": "ZZ-1900"}}
    ]


def test_readback_survivor_adopting_source_value_is_a_reported_conflict(
    proposal, binding, approved_plan
):
    routes = postmerge_routes()
    routes[_node_path(SURVIVOR)] = served(
        SURVIVOR, "101", first_name="ZZFirst", maiden_name="ZZSource", birth={"date": "ZZ-1901"}
    )
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["remaining_id"] == SURVIVOR
    assert readback["identity_verified"] is True
    # The survivor adopted the source value, so its own pre-merge value is
    # served nowhere: unverified, not preserved, still enumerated as a conflict.
    assert readback["information_preserved"] is False
    assert readback["conflict_center_checked"] is True
    assert readback["conflicts"] == [
        {"field": "birth", "kept": {"date": "ZZ-1901"}, "alternative": {"date": "ZZ-1900"}}
    ]


def test_readback_unconfirmed_conflict_alternatives_are_unchecked(
    proposal, binding, approved_plan
):
    routes = postmerge_routes()
    del routes[_node_path(SOURCE)]["maiden_name"]
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["identity_verified"] is True
    assert readback["information_preserved"] is True
    assert readback["conflict_center_checked"] is False


def test_readback_new_value_on_previously_blank_field_is_unverified(
    proposal, binding, approved_plan
):
    routes = postmerge_routes()
    routes[_node_path(SURVIVOR)]["suffix"] = "ZZJr"
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["information_preserved"] is False
    assert readback["conflicts"] == [
        {"field": "birth", "kept": {"date": "ZZ-1900"}, "alternative": {"date": "ZZ-1901"}}
    ]


def test_readback_rejects_caller_substituted_plan(proposal, binding, approved_plan):
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, postmerge_routes())
    tampered_order = copy.deepcopy(plan)
    tampered_order["path_order"] = [SOURCE, SURVIVOR]
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], tampered_order, response)
    tampered_before = copy.deepcopy(plan)
    tampered_before["before"][SURVIVOR]["tracked"]["birth"] = {"date": "ZZ-1999"}
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], tampered_before, response)


def test_preflight_rejects_listing_shaped_response(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes[_guid_path("101")] = {"results": [served(SURVIVOR, "101", **SURVIVOR_TRACKED)]}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest):
        adapter.preflight(proposal["pairs"][0], binding)


def test_blank_string_is_not_a_value(proposal, binding, approved_plan):
    approved_plan["pairs"][0]["resolved"]["102"]["tracked"]["maiden_name"] = ""
    binding["plan_sha256"] = _canonical_hash(approved_plan)
    routes = premerge_routes()
    routes[_guid_path("102")] = dict(routes[_guid_path("102")], maiden_name="")
    post = postmerge_routes()
    post[_node_path(SURVIVOR)] = served(SURVIVOR, "101", first_name="ZZFirst",
                                        birth={"date": "ZZ-1900"})
    post[_node_path(SOURCE)] = served(SOURCE, "102", merged_into=SURVIVOR,
                                      **dict(SOURCE_TRACKED, maiden_name=""))
    routes.update(post)
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    plan = adapter.preflight(proposal["pairs"][0], binding)
    response = adapter.post_once(plan)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["information_preserved"] is True
    assert readback["conflict_center_checked"] is True
    assert readback["conflicts"] == [
        {"field": "birth", "kept": {"date": "ZZ-1900"}, "alternative": {"date": "ZZ-1901"}}
    ]


@pytest.mark.parametrize(
    "remaining_extra,retired_extra",
    [
        ({"merged_into": SOURCE}, {"merged_into": SURVIVOR}),
        ({}, {"merged_into": None}),
        ({}, {"merged_into": "profile-990004"}),
        ({"guid": "999"}, {"merged_into": SURVIVOR}),
        ({"name": "ZZOther"}, {"merged_into": SURVIVOR}),
        ({"claimed": True}, {"merged_into": SURVIVOR}),
        ({"locked": True}, {"merged_into": SURVIVOR}),
    ],
)
def test_readback_rejects_wrong_postconditions(
    proposal, binding, approved_plan, remaining_extra, retired_extra
):
    routes = postmerge_routes()
    routes[_node_path(SURVIVOR)] = dict(routes[_node_path(SURVIVOR)], **remaining_extra)
    routes[_node_path(SOURCE)] = dict(routes[_node_path(SOURCE)], **retired_extra)
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, response)


def test_readback_never_assumes_false_from_omitted_flags(proposal, binding, approved_plan):
    routes = postmerge_routes()
    del routes[_node_path(SURVIVOR)]["merge_pending"]
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, response)
    routes = postmerge_routes()
    routes[_node_path(SOURCE)]["merge_pending"] = True
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, response)


def test_readback_rejects_pending_response_and_foreign_id(proposal, binding, approved_plan):
    adapter, plan, _ = verified_adapter(proposal, binding, approved_plan, postmerge_routes())
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, {"merge_pending": True})
    with pytest.raises(InvalidMergeRequest, match="^merge adapter readback blocked$"):
        adapter.readback(proposal["pairs"][0], plan, {"id": "profile-990004"})


def test_readback_lost_data_is_unverified_not_success(proposal, binding, approved_plan):
    routes = postmerge_routes()
    del routes[_node_path(SURVIVOR)]["maiden_name"]
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["identity_verified"] is True
    assert readback["information_preserved"] is False
    assert readback["conflict_center_checked"] is True


def test_readback_partial_value_is_unverified_and_not_a_conflict(proposal, binding, approved_plan):
    routes = postmerge_routes()
    routes[_node_path(SURVIVOR)]["birth"] = {"date": "ZZ-1902"}
    adapter, plan, response = verified_adapter(proposal, binding, approved_plan, routes)
    readback = adapter.readback(proposal["pairs"][0], plan, response)
    assert readback["information_preserved"] is False
    assert [c["field"] for c in readback["conflicts"]] == []


# Section: Engine integration and the closed release gate


def test_engine_flow_verified_with_conflicts(proposal, binding, approved_plan):
    adapter, _, _ = verified_adapter(proposal, binding, approved_plan, postmerge_routes())
    # Fresh adapter: the one above already consumed its single POST.
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    routes.update(postmerge_routes())
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    ledger, evidence = Ledger(), Evidence()
    results = _execute_admitted(
        proposal, binding, copy.deepcopy(binding), 150, adapter, ledger, evidence
    )
    assert [r["status"] for r in results] == ["VERIFIED"]
    assert results[0]["post_attempted"] is True
    assert results[0]["readback"]["remaining_id"] == SURVIVOR
    assert results[0]["readback"]["conflicts"][0]["field"] == "birth"
    assert [row["status"] for row in evidence.rows] == ["CLAIMED", "VERIFIED"]


def test_engine_flow_flip_fails_closed_until_the_engine_update_lands(
    proposal, binding, approved_plan
):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    routes[_node_path(SOURCE)] = served(SOURCE, "102", **SOURCE_TRACKED)
    routes[_node_path(SURVIVOR)] = served(SURVIVOR, "101", merged_into=SOURCE, **SURVIVOR_TRACKED)
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    results = _execute_admitted(
        proposal, binding, copy.deepcopy(binding), 150, adapter, Ledger(), Evidence()
    )
    # The base engine has no flip handling: the fail-closed
    # identity_verified=False records UNKNOWN and stops the batch, never
    # VERIFIED. Once this slice rebases onto the engine lane's update, the
    # remaining_is_approved_survivor=False flag takes priority and the
    # outcome becomes SURVIVOR_FLIP_REVIEW_REQUIRED.
    assert [r["status"] for r in results] == ["UNKNOWN"]
    assert results[0]["post_attempted"] is True


def test_engine_flow_unknown_on_failed_readback_stops_batch(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    bad = postmerge_routes()
    del bad[_node_path(SURVIVOR)]["maiden_name"]
    routes.update(bad)
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    results = _execute_admitted(
        proposal, binding, copy.deepcopy(binding), 150, adapter, Ledger(), Evidence()
    )
    assert [r["status"] for r in results] == ["UNKNOWN"]
    assert results[0]["post_attempted"] is True


def test_release_gate_stays_closed_with_a_working_adapter(proposal, binding, approved_plan):
    routes = premerge_routes()
    routes["/api/" + SURVIVOR + "/merge/" + SOURCE] = {"id": SURVIVOR}
    routes.update(postmerge_routes())
    adapter = make_adapter(routes, proposal, binding, approved_plan)
    with pytest.raises(InvalidMergeRequest, match=re.escape("live merge release is closed")):
        execute(proposal, binding, copy.deepcopy(binding), 150, adapter, Ledger(), Evidence())
