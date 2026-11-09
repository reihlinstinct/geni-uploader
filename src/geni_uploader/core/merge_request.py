"""Offline exact-pair merge proposal validation. No transport or approval authority."""

import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit


class InvalidMergeRequest(ValueError):
    """Fixed-message validation failure, without private input values."""


# Section: Offline proposal admission


def validate(value):
    """Return a detached proposal after strict shape and identity checks."""
    _keys(value, {"schema", "request_id", "owner", "expires_at", "pairs"})
    _require(value["schema"] == "geni-explicit-merge/v1")
    _require(_label(value["request_id"]))
    _require(_node(value["owner"]))
    _require(type(value["expires_at"]) is int and 0 < value["expires_at"] < 2**63)
    pairs = value["pairs"]
    _require(type(pairs) is list and 1 <= len(pairs) <= 10)
    sources, survivors, pair_ids = set(), set(), set()
    profiles = {}
    for pair in pairs:
        _keys(pair, {"pair_id", "left", "right", "survivor_guid", "evidence", "conflicts"})
        _require(_label(pair["pair_id"]) and pair["pair_id"] not in pair_ids)
        pair_ids.add(pair["pair_id"])
        for side in ("left", "right"):
            profile = pair[side]
            _profile(profile)
            _require(profile["guid"] not in profiles or profiles[profile["guid"]] == profile)
            profiles[profile["guid"]] = profile
        _require(pair["survivor_guid"] in (pair["left"]["guid"], pair["right"]["guid"]))
        source = (
            next(
                p["guid"]
                for p in (pair["left"], pair["right"])
                if p["guid"] != pair["survivor_guid"]
            )
            if pair["left"]["guid"] != pair["right"]["guid"]
            else None
        )
        _require(source is not None and source not in sources and source not in survivors)
        _require(pair["survivor_guid"] not in sources)
        sources.add(source)
        survivors.add(pair["survivor_guid"])
        _require(type(pair["evidence"]) is list and 1 <= len(pair["evidence"]) <= 20)
        for item in pair["evidence"]:
            _keys(item, {"source", "reason"})
            _text(item["source"], 2048)
            _text(item["reason"], 4000)
        _text(pair["conflicts"], 4000)
    return json.loads(json.dumps(value, ensure_ascii=False))


def digest(value):
    """Content digest for a future trusted approval binding, not approval itself."""
    admitted = validate(value)
    raw = json.dumps(admitted, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_resolution(profile, served):
    """Offline check of a captured GET result. Never follow merged identities."""
    _profile(profile)
    _require(type(served) is dict and "results" not in served and "error" not in served)
    _require(_node(served.get("id")) and served.get("guid") == profile["guid"])
    _require(served.get("name") == profile["expect_name"])
    _require(served.get("merge_pending") is False)
    _require(not served.get("merged_into"))
    _require(served.get("claimed") is False and served.get("locked") is False)
    return served["id"]


def require_live_release():
    """Unconditional gate: no live merge adapter has been released."""
    raise InvalidMergeRequest("live merge release is closed")


# Section: Strict private-data primitives


def _require(condition):
    if not condition:
        raise InvalidMergeRequest("invalid merge proposal")


def _keys(value, expected):
    _require(type(value) is dict and set(value) == expected)


def _text(value, maximum):
    _require(type(value) is str and value.strip() and len(value) <= maximum)
    _require(
        not any(
            unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} and c not in "\n\t"
            for c in value
        )
    )


def _label(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


def _node(value):
    return type(value) is str and re.fullmatch(r"profile-[1-9][0-9]{0,19}", value) is not None


def _profile(value):
    _keys(value, {"url", "guid", "expect_name"})
    guid = value["guid"]
    _require(type(guid) is str and re.fullmatch(r"[1-9][0-9]{0,24}", guid) is not None)
    _text(value["expect_name"], 512)
    _text(value["url"], 512)
    _require(value["url"].startswith("https://") and not any(c.isspace() for c in value["url"]))
    url = urlsplit(value["url"])
    _require(url.scheme == "https" and url.netloc == "www.geni.com")
    _require(not url.query and not url.fragment)
    _require(re.fullmatch(r"/people/[^/]+/" + guid, url.path) is not None)
