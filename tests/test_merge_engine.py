"""Synthetic admission/coordinator/claim races. No network or real identities."""

import copy

import pytest

from geni_uploader.core.merge_request import InvalidMergeRequest, digest
from geni_uploader.workflow.merge_claims import PrivateGitClaims
from geni_uploader.workflow.merge_engine import _execute_admitted, admit, execute

pytest_plugins = ["test_merge_request"]


@pytest.fixture
def binding(proposal):
    return {
        "proposal_sha256": digest(proposal),
        "private_commit": "a" * 40,
        "executor_sha": "b" * 40,
        "workflow_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "owner_id": "1",
        "dispatcher_id": "2",
        "reviewer_id": "1",
        "run_id": "3",
        "run_attempt": 1,
        "issued_at": 100,
        "expires_at": 200,
        "approval_event_sha256": "e" * 64,
    }


class Backend:
    def __init__(self):
        self.head = "a" * 40
        self.records = {}
        self.competing = False

    def snapshot(self):
        return self.head, copy.deepcopy(self.records)

    def compare_and_append(self, head, key, value):
        if self.competing or head != self.head:
            return False
        assert key not in self.records
        self.records[key] = copy.deepcopy(value)
        self.head = "b" * 40
        return True


class Adapter:
    def __init__(self, binding_hash, binding):
        self.binding_hash = binding_hash
        self.binding = binding
        self.posts = 0
        self.fail = False
        self.pending = False
        self.preserved = True

    def now(self):
        return 150

    def preflight(self, pair, binding):
        return {
            "ready": True,
            "pair_id": pair["pair_id"],
            "resolved_ids": ["profile-990001", "profile-990002"],
            "binding_sha256": self.binding_hash,
            "plan_sha256": binding["plan_sha256"],
        }

    def post_once(self, plan):
        self.posts += 1
        if self.fail:
            raise OSError("ZZ private failure must not escape")
        return {"http_status": 200}

    def readback(self, pair, plan, response):
        return {
            "identity_verified": True,
            "information_preserved": self.preserved,
            "conflict_center_checked": True,
            "conflicts": ["ZZ field retained"],
            "remaining_id": "profile-990002",
            "pending": self.pending,
        }


class Evidence:
    def __init__(self):
        self.rows = []
        self.fail = False

    def save(self, state):
        if self.fail:
            raise OSError("ZZ private storage failure")
        self.rows.append(copy.deepcopy(state))


# Section: Immutable admission and closed release


@pytest.mark.parametrize(
    "key,value",
    [
        ("run_attempt", 2),
        ("run_attempt", True),
        ("expires_at", 100),
        ("issued_at", 201),
        ("reviewer_id", "2"),
        ("owner_id", "2"),
        ("private_commit", "invalid"),
        ("plan_sha256", "bad"),
    ],
)
def test_bad_binding_rejected_even_if_both_copies_match(proposal, binding, key, value):
    binding[key] = value
    with pytest.raises(InvalidMergeRequest):
        admit(proposal, binding, copy.deepcopy(binding), 150)


def test_mismatched_trusted_binding_and_payload_rejected(proposal, binding):
    trusted = copy.deepcopy(binding)
    binding["run_id"] = "4"
    with pytest.raises(InvalidMergeRequest):
        admit(proposal, binding, trusted, 150)
    binding["run_id"] = "3"
    proposal["pairs"][0]["conflicts"] = "ZZ changed after approval"
    with pytest.raises(InvalidMergeRequest):
        admit(proposal, binding, trusted, 150)


def test_public_execution_is_unconditionally_closed():
    with pytest.raises(InvalidMergeRequest, match="live merge release is closed"):
        execute()


# Section: At-most-once and private readback failure states


@pytest.mark.parametrize("failure", ["none", "post", "pending", "preservation"])
def test_one_attempt_then_verified_or_unknown(proposal, binding, failure):
    backend, evidence = Backend(), Evidence()
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    adapter.fail = failure == "post"
    adapter.pending = failure == "pending"
    adapter.preserved = failure != "preservation"
    run = lambda: _execute_admitted(
        proposal, binding, binding, 150, adapter, PrivateGitClaims(backend), evidence
    )
    result = run()
    assert adapter.posts == 1
    assert result[0]["status"] == ("VERIFIED" if failure == "none" else "UNKNOWN")
    assert result[0]["post_attempted"] is True
    assert evidence.rows[0]["status"] == "CLAIMED"
    assert evidence.rows[0]["post_attempted"] is False
    assert run()[0]["status"] == "ALREADY_CLAIMED_REVIEW_REQUIRED"
    assert adapter.posts == 1


def test_contended_claim_never_posts(proposal, binding):
    backend = Backend()
    backend.competing = True
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    result = _execute_admitted(
        proposal, binding, binding, 150, adapter, PrivateGitClaims(backend), Evidence()
    )
    assert adapter.posts == 0
    assert result[0]["status"] == "ALREADY_CLAIMED_REVIEW_REQUIRED"


def test_evidence_unavailable_stops_before_post(proposal, binding):
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    evidence = Evidence()
    evidence.fail = True
    with pytest.raises(InvalidMergeRequest, match="private merge evidence unavailable; stop"):
        _execute_admitted(
            proposal, binding, binding, 150, adapter, PrivateGitClaims(Backend()), evidence
        )
    assert adapter.posts == 0


# Section: Revalidation, bad readback and cross-run durable evidence


def test_expired_fresh_clock_blocks_before_claim(proposal, binding):
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    adapter.now = lambda: 200
    backend = Backend()
    result = _execute_admitted(
        proposal, binding, binding, 150, adapter, PrivateGitClaims(backend), Evidence()
    )
    assert result[0]["status"] == "BLOCKED"
    assert not backend.records and adapter.posts == 0


def test_unknown_first_pair_stops_second_pair(proposal, binding):
    other = copy.deepcopy(proposal["pairs"][0])
    other["pair_id"] = "ZZ-second"
    other["right"] = {
        "guid": "103",
        "expect_name": "ZZPersona",
        "url": "https://www.geni.com/people/ZZPersona/103",
    }
    proposal["pairs"].append(other)
    binding["proposal_sha256"] = digest(proposal)
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    adapter.fail = True
    result = _execute_admitted(
        proposal, binding, binding, 150, adapter, PrivateGitClaims(Backend()), Evidence()
    )
    assert len(result) == adapter.posts == 1
    assert result[0]["status"] == "UNKNOWN"


def test_foreign_remaining_id_is_unknown(proposal, binding):
    adapter = Adapter(admit(proposal, binding, binding, 150), binding)
    original = adapter.readback
    adapter.readback = lambda *args: {**original(*args), "remaining_id": "profile-990003"}
    result = _execute_admitted(
        proposal, binding, binding, 150, adapter, PrivateGitClaims(Backend()), Evidence()
    )
    assert result[0]["status"] == "UNKNOWN"


def test_ledger_restart_object_preserves_claim(proposal, binding):
    backend = Backend()
    first = PrivateGitClaims(backend)
    assert first.claim("c" * 64, "d" * 64)
    assert PrivateGitClaims(backend).claim("c" * 64, "d" * 64) is False
    assert len(backend.records) == 1


def test_malformed_or_failed_backend_uses_fixed_exception():
    backend = Backend()
    backend.head = "ZZ-invalid"
    with pytest.raises(InvalidMergeRequest, match="^merge claim unavailable; stop$"):
        PrivateGitClaims(backend).claim("c" * 64, "d" * 64)
    with pytest.raises(InvalidMergeRequest, match="^invalid merge claim$"):
        PrivateGitClaims(backend).claim("ZZ-secret", "d" * 64)
