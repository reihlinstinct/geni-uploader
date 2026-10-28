"""Synthetic API contract fixtures, driven through the real execute().

Slice 2b of #93 (design: docs/API-CLIENT-DESIGN.md section 3). Each file
tests/contracts/<kind>/<case>.json holds one request, the responses a
loopback-only fake server returns in order, and the expected outcome.
Values are invented (ids 1000001/1000002, "Test Person"). No live client,
no token, no network beyond 127.0.0.1.

This layer pins transport semantics per allowlisted kind: GET retries 5xx,
429 stops at once, POST is never replayed and an unknown POST outcome is
UncertainWrite, and a non-allowlisted kind is refused before any request.
"""

import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import geni_upload as g

CONTRACTS = Path(__file__).parent / "contracts"
FIXTURES = sorted(CONTRACTS.glob("*/*.json"))

# The pairs source_details.main() adds at runtime. test_contract_allowlist_photo
# (slice 2a) pins the real widening; here they only enable those fixtures.
WIDENED = frozenset(
    {("GET", "document"), ("GET", "photo"), ("POST", "document_update"), ("POST", "photo_update")}
)
PARAMS = {"profile": "1000001", "object": "1000002"}
OUTCOMES = {"ok", "refused", "ApiError", "ThrottledError", "UncertainWrite"}
# Every allowlisted kind must carry these cases, so a new kind cannot land
# without its transport contract.
REQUIRED = {
    "GET": {
        "ok",
        "server_error_retried",
        "server_error_exhausted",
        "throttled_stops",
        "invalid_json",
    },
    "POST": {
        "ok",
        "server_error_uncertain",
        "invalid_json_uncertain",
        "dropped_connection_uncertain",
        "throttled_stops",
    },
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FakeGeni:
    """Loopback server that serves a fixed response sequence and records
    every request. A request beyond the sequence gets 418 and is recorded,
    so an unexpected replay shows up in the request count."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode() if length else ""
                fake.requests.append((self.command, self.path, body))
                index = len(fake.requests) - 1
                if index >= len(fake.responses):
                    self.send_response(418)
                    self.end_headers()
                    return
                spec = fake.responses[index]
                if spec.get("drop"):
                    self.close_connection = True
                    return
                payload = (spec["raw"] if "raw" in spec else json.dumps(spec["body"])).encode()
                self.send_response(spec["status"])
                for name, value in spec.get("headers", {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _serve
            do_POST = _serve

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


@pytest.fixture
def isolated(monkeypatch):
    """No real sleeps, fresh rate state, and the runtime widening applied to
    a copy of ALLOWLIST so the module global is never mutated."""
    sleeps = []
    monkeypatch.setattr(g, "_sleep", sleeps.append)
    monkeypatch.setattr(g, "_RATE", {"min_interval": 0.0, "last": 0.0, "retry_after": 0.0})
    monkeypatch.setattr(g, "ALLOWLIST", set(g.ALLOWLIST) | WIDENED)
    return sleeps


def test_fixtures_exist():
    assert len(FIXTURES) >= 60


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_contract_case(path, isolated):
    case = load(path)
    req, expect = case["request"], case["expect"]
    with FakeGeni(case["responses"]) as fake:
        url = fake.base + req["path_template"].format(**PARAMS)
        call = (req["method"], req["kind"], url)
        kwargs = {"token": "ZZsynthetic", "data": req.get("data")}
        if expect["outcome"] == "ok":
            assert g.execute(*call, **kwargs) == expect["result"]
        elif expect["outcome"] == "refused":
            with pytest.raises(g.ApiError, match="non-allowlisted call refused"):
                g.execute(*call, **kwargs)
        else:
            with pytest.raises(g.ApiError) as raised:
                g.execute(*call, **kwargs)
            assert type(raised.value).__name__ == expect["outcome"]
        requests = list(fake.requests)
    assert len(requests) == expect["requests"], requests
    expected_path = req["path_template"].format(**PARAMS)
    assert all(m == req["method"] and p == expected_path for m, p, _ in requests)
    if req["method"] == "POST" and requests:
        assert requests[0][2] == "title=Test+Source"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_shape(path):
    case = load(path)
    assert set(case) == {"request", "responses", "expect"}
    req, expect = case["request"], case["expect"]
    assert req["kind"] == path.parent.name
    assert req["method"] in ("GET", "POST")
    assert expect["outcome"] in OUTCOMES
    assert isinstance(expect["requests"], int)
    assert expect["requests"] <= len(case["responses"])
    assert ("result" in expect) == (expect["outcome"] == "ok")
    allowed = (req["method"], req["kind"]) in (g.ALLOWLIST | WIDENED)
    assert allowed == (expect["outcome"] != "refused")
    for spec in case["responses"]:
        assert spec.get("drop") or ("status" in spec and ("body" in spec) != ("raw" in spec))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_values_are_synthetic(path):
    """Invented values only: any id-like digit run is one of the fixed
    synthetic ids, and any name is the fixed test name."""
    text = path.read_text(encoding="utf-8")
    for run in re.findall(r"\d{5,}", text):
        assert run in PARAMS.values(), run
    for name in re.findall(r'"(?:name|display_name)": "([^"]*)"', text):
        assert name == "Test Person"


def test_every_allowlisted_kind_has_the_required_cases():
    cases = {}
    for path in FIXTURES:
        req = load(path)["request"]
        cases.setdefault((req["method"], req["kind"]), set()).add(path.stem)
    for method, kind in sorted(g.ALLOWLIST | WIDENED):
        missing = REQUIRED[method] - cases.get((method, kind), set())
        assert not missing, f"{method} {kind} lacks {sorted(missing)}"


def test_runner_detects_a_replayed_post(isolated):
    """Self-test: if execute() replayed a POST after a 5xx, the request count
    in server_error_uncertain would catch it."""
    case = load(CONTRACTS / "photo_update" / "server_error_uncertain.json")
    real = g.execute

    def replaying(method, kind, url, token=None, data=None):
        try:
            return real(method, kind, url, token, data)
        except g.UncertainWrite:
            return real(method, kind, url, token, data)

    with FakeGeni(case["responses"]) as fake:
        url = fake.base + case["request"]["path_template"].format(**PARAMS)
        with pytest.raises(g.ApiError):
            replaying("POST", "photo_update", url, "ZZsynthetic", {"title": "Test Source"})
        assert len(fake.requests) == 2 != case["expect"]["requests"]


def test_runner_detects_a_retried_throttle(isolated):
    """Self-test: a client that retried after 429 would send a second
    request, which the 418 overflow records."""
    case = load(CONTRACTS / "profile" / "throttled_stops.json")
    with FakeGeni(case["responses"]) as fake:
        url = fake.base + case["request"]["path_template"].format(**PARAMS)
        for _ in range(2):
            with pytest.raises(g.ApiError):
                g.execute("GET", "profile", url)
        assert len(fake.requests) == 2 != case["expect"]["requests"]
