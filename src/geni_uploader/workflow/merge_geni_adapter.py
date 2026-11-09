"""Exact-pair Geni merge adapter: approved-plan preflight, one POST, combined readback.

This module is the engine's provider adapter for released exact-pair merges. It is
not wired to any runner, workflow, CLI or credential source, and the public merge
execution release stays closed (merge_engine.execute always gates first). No live
Geni call is made while the provider rate block stands: development and tests use
a fake opener behind the pinned transport only.

Contract (consumed by merge_engine._execute_admitted):
- now() returns a UTC epoch int for fresh admission checks.
- preflight(pair, binding) re-admits the binding against constructor-held trusted
  release data, re-reads the owner and both exact profiles, requires equality with
  the approved plan (IDs and tracked-field snapshots), and returns a ready plan.
- post_once(plan) sends exactly one merge POST in the approved path order. No
  retry, no fallback direction, no partner discovery, no field resolution.
- readback(pair, plan, response) re-reads both profiles, identifies the actual
  remaining profile, verifies both survive, verifies tracked data is preserved or
  enumerated as a retained conflict, and reports conflicts for human resolution in
  the provider's Conflict Center. Conflicts never stop the executor; anything
  missing, hidden, partial, redirected, pending or changed is UNKNOWN via the
  engine. False flags are never assumed from omitted fields. An actual remaining
  profile that is not the approved survivor is reported as the explicit outcome
  remaining_is_approved_survivor=False with the actual remaining ID; the adapter
  fails closed on a flip (identity_verified=False), so a flip is never VERIFIED:
  the current engine records UNKNOWN and stops, and the engine lane's update
  records the distinct SURVIVOR_FLIP_REVIEW_REQUIRED.
Any transport failure (including 429) latches the adapter: every later call fails
without a new request, so a rate block can never be fed more calls.
"""

import copy
import hashlib
import json
import re
import time

from geni_uploader.core.merge_request import (
    InvalidMergeRequest,
    digest,
    validate,
    verify_resolution,
)
from geni_uploader.workflow.merge_engine import admit
from geni_uploader.workflow.merge_http import BoundedJSONHTTP

# Section: Released plan schema, tracked coverage and policy binding

PLAN_SCHEMA = "geni-explicit-merge-plan/v1"

# Tracked-field coverage for preservation and conflict comparison. The approved
# plan pins these exact keys per profile plus the policy digest below, so a
# coverage change is a plan mismatch, never a silent behavior change.
TRACKED_FIELDS = (
    "display_name",
    "first_name",
    "middle_name",
    "last_name",
    "maiden_name",
    "suffix",
    "nicknames",
    "names",
    "gender",
    "occupation",
    "about_me",
    "birth",
    "death",
    "baptism",
    "burial",
)

# Singular reads request every field the adapter relies on: identity and status
# flags plus the tracked coverage. Blank fields may be omitted by the provider;
# absence is recorded as null in snapshots and never read as an explicit false.
_GET_FIELDS = (
    "id",
    "guid",
    "name",
    "claimed",
    "locked",
    "is_alive",
    "public",
    "master_profile",
    "merge_note",
    "merge_pending",
    "merged_into",
) + TRACKED_FIELDS

# Conflict/readback policy identity. Conflicting tracked values are retained by
# the provider for human choice in its Conflict Center; the adapter enumerates
# and reports them and never selects, clears or resolves one. Readback requires
# every tracked value to survive exactly on the remaining profile or be fully
# enumerated as a conflict alternative; anything else is unverified.
_POLICY = {
    "tracked_fields": list(TRACKED_FIELDS),
    "conflict_handling": "report-only-conflict-center-v1",
    "readback": "exact-preserved-or-conflict-v1",
}

_NODE = r"profile-[1-9][0-9]{0,19}"
_MAX_TRACKED_BYTES = 65536
_MAX_PLAN_BYTES = 1024 * 1024


def _canonical_hash(value):
    """Canonical-JSON SHA256. Must stay byte-identical to merge_engine._hash."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


POLICY_SHA256 = _canonical_hash(_POLICY)


def _require(condition, message):
    if not condition:
        raise InvalidMergeRequest(message)


def _node_ok(value):
    return type(value) is str and re.fullmatch(_NODE, value) is not None


def _guid_ok(value):
    return type(value) is str and re.fullmatch(r"[1-9][0-9]{0,24}", value) is not None


def _detach(value, message):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        raise InvalidMergeRequest(message) from None


def _blank(value):
    return value is None or value == "" or value == [] or value == {}


def _extract_tracked(served):
    """Snapshot the tracked coverage exactly as served; absent fields are null."""
    return {field: served.get(field) for field in TRACKED_FIELDS}


def _guid_path(guid):
    return "/api/profile-g" + guid + "?only_ids=true&fields=" + ",".join(_GET_FIELDS)


def _node_path(node):
    return "/api/" + node + "?only_ids=true&fields=" + ",".join(_GET_FIELDS)


def _merge_path(path_order):
    return "/api/" + path_order[0] + "/merge/" + path_order[1]


# Section: Approved plan validation (adapter-owned schema, plan producer contract)


def _validate_plan(plan, proposal):
    """Strict approved-plan shape and equality with the admitted proposal.

    The approved plan is private data produced from verified reads. It pins, per
    ordered pair: the POST path order, the survivor choice, both resolved canonical
    node IDs and the exact tracked-field snapshots, plus owner, request digest,
    expiry and the policy hash. ID-only approval is rejected: data drift cannot
    hide behind unchanged IDs.
    """
    _require(type(plan) is dict, "merge adapter plan blocked")
    _require(
        set(plan)
        == {"schema", "request_id", "request_sha256", "owner", "expires_at", "policy_sha256", "pairs"},
        "merge adapter plan blocked",
    )
    _require(plan["schema"] == PLAN_SCHEMA, "merge adapter plan blocked")
    _require(plan["request_id"] == proposal["request_id"], "merge adapter plan blocked")
    _require(plan["request_sha256"] == digest(proposal), "merge adapter plan blocked")
    _require(plan["owner"] == proposal["owner"], "merge adapter plan blocked")
    expires = plan["expires_at"]
    _require(
        type(expires) is int and 0 < expires <= proposal["expires_at"] < 2**63,
        "merge adapter plan blocked",
    )
    _require(plan["policy_sha256"] == POLICY_SHA256, "merge adapter plan blocked")
    pairs = plan["pairs"]
    _require(type(pairs) is list and len(pairs) == len(proposal["pairs"]), "merge adapter plan blocked")
    for pair_plan, pair in zip(pairs, proposal["pairs"]):
        _validate_pair_plan(pair_plan, pair)
    raw = json.dumps(plan, ensure_ascii=False)
    _require(len(raw.encode()) <= _MAX_PLAN_BYTES, "merge adapter plan blocked")
    return json.loads(raw)


def _validate_pair_plan(pair_plan, pair):
    _require(type(pair_plan) is dict, "merge adapter plan blocked")
    _require(
        set(pair_plan) == {"pair_id", "path_order", "survivor_guid", "resolved"},
        "merge adapter plan blocked",
    )
    _require(pair_plan["pair_id"] == pair["pair_id"], "merge adapter plan blocked")
    _require(pair_plan["survivor_guid"] == pair["survivor_guid"], "merge adapter plan blocked")
    order = pair_plan["path_order"]
    _require(
        type(order) is list
        and len(order) == 2
        and order[0] != order[1]
        and all(_node_ok(node) for node in order),
        "merge adapter plan blocked",
    )
    resolved = pair_plan["resolved"]
    _require(type(resolved) is dict, "merge adapter plan blocked")
    expected_guids = {pair["left"]["guid"], pair["right"]["guid"]}
    _require(set(resolved) == expected_guids, "merge adapter plan blocked")
    ids = []
    for side in (pair["left"], pair["right"]):
        entry = resolved[side["guid"]]
        _require(type(entry) is dict, "merge adapter plan blocked")
        _require(set(entry) == {"id", "expect_name", "tracked"}, "merge adapter plan blocked")
        _require(_node_ok(entry["id"]), "merge adapter plan blocked")
        _require(entry["expect_name"] == side["expect_name"], "merge adapter plan blocked")
        tracked = entry["tracked"]
        _require(type(tracked) is dict, "merge adapter plan blocked")
        _require(set(tracked) == set(TRACKED_FIELDS), "merge adapter plan blocked")
        try:
            raw = json.dumps(tracked, ensure_ascii=False)
        except (TypeError, ValueError):
            raise InvalidMergeRequest("merge adapter plan blocked") from None
        _require(len(raw.encode()) <= _MAX_TRACKED_BYTES, "merge adapter plan blocked")
        ids.append(entry["id"])
    _require(set(ids) == set(order), "merge adapter plan blocked")


# Section: The adapter


class GeniMergeAdapter:
    """Approved-plan merge adapter. One attempt per pair; halts on transport failure."""

    def __init__(self, transport, proposal, binding, trusted, approved_plan, clock=time.time):
        if type(transport) is not BoundedJSONHTTP or transport.origin != "https://www.geni.com":
            raise InvalidMergeRequest("merge adapter transport blocked")
        if not callable(clock):
            raise InvalidMergeRequest("merge adapter clock blocked")
        self._transport = transport
        self._proposal = validate(proposal)
        self._binding = _detach(binding, "merge adapter binding blocked")
        self._trusted = _detach(trusted, "merge adapter binding blocked")
        self._plan = _validate_plan(approved_plan, self._proposal)
        if _canonical_hash(self._plan) != self._binding.get("plan_sha256"):
            raise InvalidMergeRequest("merge adapter plan blocked")
        self._clock = clock
        self._halted = False
        self._plans = {}
        self._posted = set()

    def now(self):
        """UTC epoch int for the engine's fresh admission check."""
        value = self._clock()
        if type(value) not in (int, float) or not 0 < value < 2**63:
            raise InvalidMergeRequest("merge adapter clock blocked")
        return int(value)

    def preflight(self, pair, binding):
        """Fresh admission, owner recheck and exact per-pair identity/data re-read."""
        self._require_open()
        _require(type(pair) is dict, "merge adapter preflight blocked")
        _require(binding == self._binding, "merge adapter binding blocked")
        binding_hash = admit(self._proposal, binding, self._trusted, self.now())
        _require(
            binding.get("plan_sha256") == _canonical_hash(self._plan),
            "merge adapter plan blocked",
        )
        _require(self.now() < self._plan["expires_at"], "merge adapter plan blocked")
        pair_id = pair.get("pair_id")
        source_pair = next(
            (p for p in self._proposal["pairs"] if p["pair_id"] == pair_id), None
        )
        _require(source_pair is not None and source_pair == pair, "merge adapter preflight blocked")
        pair_plan = self._pair_plan(pair_id)
        owner = self._get("/api/user")
        _require(
            type(owner) is dict and owner.get("id") == self._proposal["owner"],
            "merge adapter owner blocked",
        )
        before = {}
        for side in (source_pair["left"], source_pair["right"]):
            served = self._get(_guid_path(side["guid"]))
            _require(type(served) is dict, "merge adapter preflight blocked")
            node = verify_resolution(side, served)
            approved = pair_plan["resolved"][side["guid"]]
            _require(node == approved["id"], "merge adapter preflight blocked")
            tracked = _extract_tracked(served)
            _require(tracked == approved["tracked"], "merge adapter preflight blocked")
            before[node] = {"guid": side["guid"], "name": served["name"], "tracked": tracked}
        plan = {
            "ready": True,
            "pair_id": pair_id,
            "binding_sha256": binding_hash,
            "plan_sha256": binding["plan_sha256"],
            "resolved_ids": list(pair_plan["path_order"]),
            "path_order": list(pair_plan["path_order"]),
            "expected_survivor_id": pair_plan["resolved"][pair_plan["survivor_guid"]]["id"],
            "before": before,
        }
        self._plans[pair_id] = copy.deepcopy(plan)
        # The caller gets its own deep copy: mutating it can never alias the
        # adapter-owned artifact that post_once and readback act on.
        return copy.deepcopy(plan)

    def post_once(self, plan):
        """Exactly one merge POST in the approved path order. Never retried.

        Only the adapter's own preflight artifact is honored: a caller-supplied
        plan that differs from it never reaches the transport.
        """
        self._require_open()
        pair_id = plan.get("pair_id") if type(plan) is dict else None
        stored = self._plans.get(pair_id)
        _require(
            stored is not None and plan == stored and pair_id not in self._posted,
            "merge adapter post blocked",
        )
        # Freshness is re-checked at the single attempt, not only at preflight.
        _require(
            self.now() < min(self._binding["expires_at"], self._plan["expires_at"]),
            "merge adapter post blocked",
        )
        # The POST path comes only from the adapter-owned artifact: the approved
        # path order, never caller-mutable data.
        order = stored["path_order"]
        # Consume before the attempt: an exception can follow vendor receipt.
        self._posted.add(pair_id)
        try:
            return self._transport("POST", _merge_path(order))
        # One-attempt boundary: consume happened before the call; latch, then re-raise.
        except Exception:
            self._halted = True
            raise

    def readback(self, pair, plan, response):
        """Combined-data and Conflict Center readback after the single attempt.

        Only the adapter's own preflight artifact is honored: a caller-supplied
        plan that differs from it is rejected. Both profiles must survive:
        exactly one remaining with no merged_into, the other retired into it.
        If the actual remaining profile is not the approved survivor, the
        explicit outcome remaining_is_approved_survivor=False is returned with
        the actual remaining ID and the adapter fails closed
        (identity_verified=False): the current engine records UNKNOWN and stops,
        and the engine lane's update records the distinct
        SURVIVOR_FLIP_REVIEW_REQUIRED. A flip is never VERIFIED. The retired
        profile must still carry its exact pre-merge tracked values: those
        retained values are the provider's Conflict Center alternatives, so
        their presence is what conflict_center_checked confirms. Conflicts are
        enumerated for human resolution and never stop the executor; missing,
        hidden, partial, redirected, pending or changed data fails verification.
        """
        self._require_open()
        _require(type(pair) is dict and type(plan) is dict, "merge adapter readback blocked")
        pair_id = pair.get("pair_id")
        stored = self._plans.get(pair_id)
        _require(
            stored is not None and plan == stored and pair_id in self._posted,
            "merge adapter readback blocked",
        )
        order = stored["path_order"]
        before = stored["before"]
        if type(response) is dict:
            _require(response.get("merge_pending") is not True, "merge adapter readback blocked")
            _require(
                response.get("id") in (None, order[0], order[1]),
                "merge adapter readback blocked",
            )
        served = {}
        for node in order:
            body = self._get(_node_path(node))
            _require(type(body) is dict, "merge adapter readback blocked")
            served[node] = body
        remaining = [node for node in order if _blank(served[node].get("merged_into"))]
        retired = [node for node in order if not _blank(served[node].get("merged_into"))]
        _require(len(remaining) == 1 and len(retired) == 1, "merge adapter readback blocked")
        remaining_id, retired_id = remaining[0], retired[0]
        _require(
            served[retired_id]["merged_into"] == remaining_id, "merge adapter readback blocked"
        )
        # A flipped direction is an explicit, distinctly named outcome with the
        # actual remaining ID reported, never VERIFIED. The adapter fails closed
        # (identity_verified=False): the current engine records UNKNOWN and
        # stops, and the engine lane's update records the distinct
        # SURVIVOR_FLIP_REVIEW_REQUIRED.
        approved_survivor = remaining_id == stored["expected_survivor_id"]
        for node in order:
            body = served[node]
            _require(body.get("id") == node, "merge adapter readback blocked")
            _require(body.get("guid") == before[node]["guid"], "merge adapter readback blocked")
            _require(body.get("name") == before[node]["name"], "merge adapter readback blocked")
            _require(body.get("merge_pending") is False, "merge adapter readback blocked")
        _require(served[remaining_id].get("claimed") is False, "merge adapter readback blocked")
        _require(served[remaining_id].get("locked") is False, "merge adapter readback blocked")
        # Conflict Center check: the retired profile survives and must retain its
        # exact pre-merge tracked values, which are the conflict alternatives.
        conflict_center_checked = _extract_tracked(served[retired_id]) == before[retired_id][
            "tracked"
        ]
        after_tracked = _extract_tracked(served[remaining_id])
        preserved, conflicts = _coverage(before, remaining_id, retired_id, after_tracked)
        return {
            "identity_verified": approved_survivor,
            "information_preserved": preserved,
            "conflict_center_checked": conflict_center_checked,
            "conflicts": conflicts,
            "remaining_id": remaining_id,
            "remaining_is_approved_survivor": approved_survivor,
            "pending": False,
        }

    # Section: Private helpers

    def _pair_plan(self, pair_id):
        for pair_plan in self._plan["pairs"]:
            if pair_plan["pair_id"] == pair_id:
                return pair_plan
        raise InvalidMergeRequest("merge adapter preflight blocked")

    def _require_open(self):
        if self._halted:
            raise InvalidMergeRequest("merge adapter halted; do not retry")

    def _get(self, path):
        self._require_open()
        try:
            return self._transport("GET", path)
        except Exception:  # transport failures latch the adapter; re-raise unchanged
            self._halted = True
            raise


def _coverage(before, remaining_id, retired_id, after_tracked):
    """Exact preservation check and complete conflict enumeration over coverage.

    For each tracked field: the remaining profile's post-merge value must equal
    its own pre-merge value or the retired profile's. When both pre-merge values
    were non-blank and differ, the value that did not survive is a retained
    conflict, reported for human choice in the provider's Conflict Center. Any
    other outcome (lost, hidden or partial data) is unverified, never success.
    """
    preserved = True
    conflicts = []
    for field in TRACKED_FIELDS:
        post = after_tracked.get(field)
        pre_kept = before[remaining_id]["tracked"].get(field)
        pre_other = before[retired_id]["tracked"].get(field)
        if _blank(pre_kept) and _blank(pre_other):
            # Nothing was tracked before the merge; a value appearing now is an
            # unexplained change, never success.
            if not _blank(post):
                preserved = False
            continue
        if not _blank(pre_kept) and not _blank(pre_other) and pre_kept != pre_other:
            if post == pre_kept:
                conflicts.append({"field": field, "kept": pre_kept, "alternative": pre_other})
            elif post == pre_other:
                conflicts.append({"field": field, "kept": pre_other, "alternative": pre_kept})
                # The remaining profile adopted the retired profile's value, so
                # its own pre-merge value is served nowhere: the retired-side
                # check cannot confirm it, and with no real Conflict Center read
                # this alternative is unverified, not preserved.
                preserved = False
            else:
                preserved = False
        else:
            want = pre_kept if not _blank(pre_kept) else pre_other
            if post != want:
                preserved = False
    return preserved, conflicts
