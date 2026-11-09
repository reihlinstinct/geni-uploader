"""Synthetic offline merge proposals do not grant authority or reach a service."""

import copy

import pytest

from geni_uploader.core.merge_request import (
    InvalidMergeRequest,
    digest,
    require_live_release,
    validate,
    verify_resolution,
)


@pytest.fixture
def proposal():
    def profile(guid):
        return {
            "url": f"https://www.geni.com/people/ZZPersona/{guid}",
            "guid": guid,
            "expect_name": "ZZPersona",
        }

    return {
        "schema": "geni-explicit-merge/v1",
        "request_id": "ZZ-request",
        "owner": "profile-990001",
        "expires_at": 2000000000,
        "pairs": [
            {
                "pair_id": "ZZ-pair",
                "left": profile("101"),
                "right": profile("102"),
                "survivor_guid": "101",
                "evidence": [{"source": "ZZ-source", "reason": "ZZ-synthetic match"}],
                "conflicts": "ZZ-no conflict asserted by fixture",
            }
        ],
    }


# Section: Exact pair and content contracts


def test_detached_valid_proposal_and_order_independent_digest(proposal):
    result = validate(proposal)
    assert result == proposal and result is not proposal
    assert digest(proposal) == digest(dict(reversed(list(proposal.items()))))
    changed = copy.deepcopy(proposal)
    changed["pairs"][0]["survivor_guid"] = "102"
    assert digest(changed) != digest(proposal)


@pytest.mark.parametrize(
    "field,value",
    [("survivor_guid", "103"), ("evidence", []), ("conflicts", ""), ("pair_id", "bad/path")],
)
def test_rejects_missing_choice_or_evidence(proposal, field, value):
    proposal["pairs"][0][field] = value
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


def test_rejects_self_pair_and_overlapping_batch(proposal):
    other = copy.deepcopy(proposal["pairs"][0])
    other["pair_id"] = "ZZ-other"
    proposal["pairs"].append(other)
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)
    proposal["pairs"] = [other]
    other["right"] = other["left"]
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/people/ZZ/101",
        "https://www.geni.com/people/ZZ/999",
        "https://www.geni.com/people/ZZ/101?token=ZZ",
        "https://www.geni.com:443/people/ZZ/101",
    ],
)
def test_rejects_unbound_url(proposal, url):
    proposal["pairs"][0]["left"]["url"] = url
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


def test_unknown_fields_and_bool_timestamp_rejected(proposal):
    proposal["approve"] = True
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)
    del proposal["approve"]
    proposal["expires_at"] = True
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


# Section: Captured resolution and unconditional release gate


def test_canonical_resolution_does_not_conflate_guid_with_node(proposal):
    served = {
        "id": "profile-990002",
        "guid": "101",
        "name": "ZZPersona",
        "merge_pending": False,
        "claimed": False,
        "locked": False,
    }
    profile = proposal["pairs"][0]["left"]
    assert verify_resolution(profile, served) == "profile-990002"
    for key, value in [
        ("guid", "999"),
        ("name", "ZZOther"),
        ("merge_pending", True),
        ("merged_into", "profile-990003"),
        ("claimed", True),
        ("locked", True),
        ("id", "profile-g101"),
        ("results", []),
    ]:
        with pytest.raises(InvalidMergeRequest):
            verify_resolution(profile, {**served, key: value})
    del served["merge_pending"]
    with pytest.raises(InvalidMergeRequest):
        verify_resolution(profile, served)


def test_release_cannot_be_opened_by_proposal_or_environment(proposal, monkeypatch):
    monkeypatch.setenv("APPROVE_MERGE", "yes")
    validate(proposal)
    with pytest.raises(InvalidMergeRequest, match="live merge release is closed"):
        require_live_release()


def test_shared_survivor_allowed_without_chains(proposal):
    other = copy.deepcopy(proposal["pairs"][0])
    other["pair_id"] = "ZZ-second"
    other["right"]["guid"] = "103"
    other["right"]["url"] = "https://www.geni.com/people/ZZPersona/103"
    proposal["pairs"].append(other)
    assert len(validate(proposal)["pairs"]) == 2
    other["survivor_guid"] = "102"
    other["left"]["guid"] = "102"
    other["left"]["url"] = "https://www.geni.com/people/ZZPersona/102"
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


# Section: Review regressions for bounds, display safety and batch guards


@pytest.mark.parametrize("field,maximum", [("expect_name", 512), ("url", 512)])
def test_profile_padding_cannot_bypass_bounds(proposal, field, maximum):
    profile = proposal["pairs"][0]["left"]
    profile[field] += " " * maximum
    with pytest.raises(InvalidMergeRequest, match="^invalid merge proposal$"):
        digest(proposal)


@pytest.mark.parametrize("field,maximum", [("source", 2048), ("reason", 4000)])
def test_evidence_padding_cannot_bypass_bounds(proposal, field, maximum):
    proposal["pairs"][0]["evidence"][0][field] += " " * maximum
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


@pytest.mark.parametrize(
    "text",
    [
        "ZZ" + " " * 4000,
        "ZZ\x00",
        "ZZ\x7f",
        "ZZ\x85",
        "ZZ\u202e",
        "ZZ\u2066",
        "ZZ\u200b",
        "ZZ\u2028",
        "ZZ\u2029",
        "ZZ\ud800",
    ],
)
def test_unsafe_text_has_fixed_failure_without_payload(proposal, text):
    proposal["pairs"][0]["conflicts"] = text
    for operation in (validate, digest):
        with pytest.raises(InvalidMergeRequest) as error:
            operation(proposal)
        assert str(error.value) == "invalid merge proposal"
        assert not hasattr(error.value, "object")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.geni.com/people/ZZ\nPersona/1\t01",
        "https://www.geni.com/people/ZZ\rPersona/101",
        "HTTPS://www.geni.com/people/ZZPersona/101",
        "https://www.geni.com/people/" + "Z" * 512 + "/101",
    ],
)
def test_url_is_bound_without_parser_normalization(proposal, url):
    proposal["pairs"][0]["left"]["url"] = url
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


@pytest.mark.parametrize(
    "expiry", [0, -1, 2**63, 10**5000], ids=["zero", "negative", "boundary", "huge"]
)
def test_expiry_bounds_have_fixed_failure(proposal, expiry):
    proposal["expires_at"] = expiry
    with pytest.raises(InvalidMergeRequest, match="^invalid merge proposal$"):
        digest(proposal)


def _additional_pair(proposal, number):
    pair = copy.deepcopy(proposal["pairs"][0])
    pair["pair_id"] = f"ZZ-pair-{number}"
    pair["right"]["guid"] = str(102 + number)
    pair["right"]["url"] = f"https://www.geni.com/people/ZZPersona/{102 + number}"
    return pair


@pytest.mark.parametrize("reverse", [False, True])
def test_both_chain_orders_rejected(proposal, reverse):
    other = _additional_pair(proposal, 1)
    other["survivor_guid"] = "103"
    proposal["pairs"].append(other)
    if reverse:
        proposal["pairs"].reverse()
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


def test_duplicate_pair_id_rejected_independently(proposal):
    other = _additional_pair(proposal, 1)
    other["pair_id"] = proposal["pairs"][0]["pair_id"]
    proposal["pairs"].append(other)
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


@pytest.mark.parametrize(
    "field,value", [("expect_name", "ZZOther"), ("url", "https://www.geni.com/people/ZZOther/101")]
)
def test_shared_guid_requires_identical_expectations(proposal, field, value):
    other = _additional_pair(proposal, 1)
    other["left"][field] = value
    proposal["pairs"].append(other)
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


def test_pair_and_evidence_caps(proposal):
    proposal["pairs"].extend(_additional_pair(proposal, n) for n in range(1, 10))
    assert len(validate(proposal)["pairs"]) == 10
    proposal["pairs"].append(_additional_pair(proposal, 10))
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)
    proposal["pairs"] = proposal["pairs"][:1]
    pair = proposal["pairs"][0]
    pair["evidence"] *= 20
    assert len(validate(proposal)["pairs"][0]["evidence"]) == 20
    pair["evidence"].append(copy.deepcopy(pair["evidence"][0]))
    with pytest.raises(InvalidMergeRequest):
        validate(proposal)


@pytest.mark.parametrize("missing", ["merge_pending", "claimed", "locked", "error"])
def test_resolution_missing_flags_and_error_guard(proposal, missing):
    served = {
        "id": "profile-990002",
        "guid": "101",
        "name": "ZZPersona",
        "merge_pending": False,
        "claimed": False,
        "locked": False,
    }
    if missing == "error":
        served["error"] = None
    else:
        del served[missing]
    with pytest.raises(InvalidMergeRequest):
        verify_resolution(proposal["pairs"][0]["left"], served)
