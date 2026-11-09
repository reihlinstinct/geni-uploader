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
        "owner": "profile-91",
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
        "id": "profile-42",
        "guid": "101",
        "name": "ZZPersona",
        "merge_pending": False,
        "claimed": False,
        "locked": False,
    }
    profile = proposal["pairs"][0]["left"]
    assert verify_resolution(profile, served) == "profile-42"
    for key, value in [
        ("guid", "999"),
        ("name", "ZZOther"),
        ("merge_pending", True),
        ("merged_into", "profile-9"),
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
