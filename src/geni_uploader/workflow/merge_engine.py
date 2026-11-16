"""Closed merge execution coordinator. No transport, credential or CLI wiring."""

import hashlib
import json
import re

from geni_uploader.core.merge_request import InvalidMergeRequest, digest, require_live_release

# Section: Exact binding admission


BINDING_KEYS = {
    "proposal_sha256",
    "private_commit",
    "executor_sha",
    "workflow_sha256",
    "plan_sha256",
    "owner_id",
    "dispatcher_id",
    "reviewer_id",
    "run_id",
    "run_attempt",
    "issued_at",
    "expires_at",
    "approval_event_sha256",
}


def _require(condition):
    if not condition:
        raise InvalidMergeRequest("merge run blocked")


def _hex(value, length):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{" + str(length) + r"}", value)


def _id(value):
    return type(value) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value)


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def admit(proposal, binding, trusted, now):
    """Compare content to separately authenticated release/job expectations.

    This function does not authenticate either dict. Callers cannot supply their
    own trusted copy as proof. A released adapter must recover authenticated job,
    human approval and effective environment evidence independently.
    """
    _require(type(binding) is dict and set(binding) == BINDING_KEYS)
    _require(type(trusted) is dict and set(trusted) == BINDING_KEYS)
    _require(binding == trusted)
    _require(binding["proposal_sha256"] == digest(proposal))
    for key in ("proposal_sha256", "workflow_sha256", "plan_sha256", "approval_event_sha256"):
        _require(_hex(binding[key], 64))
    for key in ("private_commit", "executor_sha"):
        _require(_hex(binding[key], 40))
    for key in ("owner_id", "dispatcher_id", "reviewer_id", "run_id"):
        _require(_id(binding[key]))
    _require(binding["reviewer_id"] == binding["owner_id"])
    _require(binding["dispatcher_id"] != binding["reviewer_id"])
    _require(type(binding["run_attempt"]) is int and binding["run_attempt"] == 1)
    _require(type(now) is int)
    _require(type(binding["issued_at"]) is int and type(binding["expires_at"]) is int)
    _require(0 < binding["issued_at"] <= now < binding["expires_at"] < 2**63)
    _require(binding["expires_at"] <= proposal["expires_at"])
    return _hash(binding)


# Section: Closed public entry point and one-attempt coordinator


def execute(*args, **kwargs):
    """No live release exists, regardless of supplied binding or adapters."""
    require_live_release()
    return _execute_admitted(*args, **kwargs)  # pragma: no cover


def _execute_admitted(proposal, binding, trusted, now, adapter, ledger, evidence):
    """Internal coordinator for synthetic tests, not a released execution path.

    adapter preflight/readback must validate both exact identities and all released
    coverage/postconditions. A boolean HTTP success is not that contract. Evidence
    must persist private results synchronously; a failed save stops the batch.
    Ledger must durably claim each operation exactly once, before an attempt.
    """
    binding_hash = admit(proposal, binding, trusted, now)
    results = []
    for pair in proposal["pairs"]:
        # Fresh clock/revocation checks belong to the released preflight adapter.
        state = {"pair_id": pair["pair_id"], "status": "NOT_ATTEMPTED", "post_attempted": False}
        # A new run/expiry/plan must never reset an already consumed approval.
        key = _hash(
            {
                "approval_event_sha256": binding["approval_event_sha256"],
                "pair_guids": sorted([pair["left"]["guid"], pair["right"]["guid"]]),
            }
        )
        try:
            admit(proposal, binding, trusted, adapter.now())
            plan = adapter.preflight(pair, binding)
            _require(type(plan) is dict and plan.get("ready") is True)
            _require(plan.get("binding_sha256") == binding_hash)
            _require(plan.get("plan_sha256") == binding["plan_sha256"])
            _require(plan.get("pair_id") == pair["pair_id"])
            ids = plan.get("resolved_ids")
            _require(type(ids) is list and len(ids) == 2 and ids[0] != ids[1])
            _require(
                all(type(v) is str and re.fullmatch(r"profile-[1-9][0-9]{0,19}", v) for v in ids)
            )
            if not ledger.claim(key, binding_hash):
                state["status"] = "ALREADY_CLAIMED_REVIEW_REQUIRED"
                _persist(evidence, state)
                results.append(state)
                break
            state["status"] = "CLAIMED"
            _persist(evidence, state)
        except Exception:  # noqa: BLE001 - terminal boundary, no external exception text
            # Never expose raw adapter exceptions or private provider bodies.
            state["status"] = "BLOCKED"
            _persist(evidence, state)
            results.append(state)
            break
        try:
            # Set this before calling; an exception can occur after vendor receipt.
            state["post_attempted"] = True
            response = adapter.post_once(plan)
            readback = adapter.readback(pair, plan, response)
            readback = _detached_readback(readback)
            state["readback"] = readback
            if readback.get("remaining_is_approved_survivor") is not True:
                state["status"] = "SURVIVOR_FLIP_REVIEW_REQUIRED"
            else:
                _require(readback.get("identity_verified") is True)
                _require(readback.get("information_preserved") is True)
                _require(readback.get("conflict_center_checked") is True)
                conflicts = readback.get("conflicts")
                _require(type(conflicts) is list and len(conflicts) <= 256)
                for conflict in conflicts:
                    _require(
                        type(conflict) is dict and set(conflict) == {"field", "kept", "alternative"}
                    )
                    _require(type(conflict["field"]) is str and 0 < len(conflict["field"]) <= 128)
                _require(type(readback.get("remaining_id")) is str)
                _require(re.fullmatch(r"profile-[1-9][0-9]{0,19}", readback["remaining_id"]))
                _require(readback["remaining_id"] in ids)
                _require(readback.get("pending") is False)
                # Conflicts are retained for human choice, never selected or cleared.
                state["status"] = "VERIFIED"
        except Exception:  # noqa: BLE001 - terminal boundary, no external exception text
            state["status"] = "UNKNOWN"
        _persist(evidence, state)
        results.append(state)
        if state["status"] != "VERIFIED":
            break
    return results


def _persist(evidence, state):
    try:
        evidence.save(state)
    except Exception:  # noqa: BLE001 - private persistence boundary
        raise InvalidMergeRequest("private merge evidence unavailable; stop") from None


def _detached_readback(value):
    """Retain bounded JSON evidence, never mutable adapter-owned references."""
    _require(type(value) is dict)
    encoded = json.dumps(value, allow_nan=False, ensure_ascii=True)
    _require(len(encoded) <= 1024 * 1024)
    return json.loads(encoded)
