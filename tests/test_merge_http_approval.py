"""Pinned HTTPS semantics and synthetic snapshots. Only loopback HTTP in one test."""

import base64
import hashlib
import json
from urllib.error import HTTPError

import pytest
from test_github_review_evidence import fixture

from geni_uploader.core.merge_request import InvalidMergeRequest
from geni_uploader.workflow.merge_approval import read_protected_snapshot
from geni_uploader.workflow.merge_http import BoundedJSONHTTP


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


def client_with(raw, **kwargs):
    client = BoundedJSONHTTP("https://api.github.com", "ZZ-token")
    response = Response("https://api.github.com/ZZ", raw, **kwargs)
    client._opener = Opener({response.url: response})
    return client


# Section: One-attempt bounded JSON and fixed private errors


@pytest.mark.parametrize(
    "raw",
    [
        b'{"ZZ":1,"ZZ":2}',
        b"NaN",
        b'{"ZZ":1e400}',
        b'{"ZZ":-1e999}',
        b"\xff",
        b"x" * (1024 * 1024 + 1),
    ],
)
def test_invalid_json_never_leaks_raw_body(raw):
    client = client_with(raw)
    with pytest.raises(InvalidMergeRequest, match="^merge transport blocked; do not retry$"):
        client("GET", "/ZZ")
    assert len(client._opener.calls) == 1


@pytest.mark.parametrize("path", ["https://ZZ.invalid/", "//ZZ.invalid/", "/ZZ\n", "/ZZ#fragment"])
def test_unbound_path_never_calls_http(path):
    client = client_with(b"{}")
    with pytest.raises(InvalidMergeRequest):
        client("GET", path)
    assert not client._opener.calls


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_non_success_is_terminal(status):
    client = client_with(b"{}", status=status)
    with pytest.raises(InvalidMergeRequest):
        client("GET", "/ZZ")
    assert len(client._opener.calls) == 1


def test_redirect_pagination_and_http_exception_are_terminal():
    for value in [
        Response("https://ZZ.invalid/", b"{}"),
        Response("https://api.github.com/ZZ", b"{}", headers={"Link": "ZZ-next"}),
        HTTPError("https://api.github.com/ZZ", 429, "ZZ private", {}, None),
    ]:
        client = client_with(b"{}")
        client._opener.responses["https://api.github.com/ZZ"] = value
        with pytest.raises(InvalidMergeRequest):
            client("GET", "/ZZ")
        assert len(client._opener.calls) == 1


def snapshot_client():
    pins, data = fixture()
    intent = "b" * 64
    data[0].update(display_title="explicit-merge:" + intent, status="in_progress", conclusion=None)
    content = b"ZZ reviewed workflow bytes"
    workflow_hash = hashlib.sha256(content).hexdigest()
    root = "https://api.github.com/repos/ZZ-owner/ZZ-repo"
    urls = [
        root + "/actions/runs/42",
        root + "/environments/ZZ-human",
        root + "/actions/runs/42/approvals",
        root + "/environments/ZZ-human/deployment-branch-policies",
    ]
    responses = {url: Response(url, json.dumps(body).encode()) for url, body in zip(urls, data)}
    url = root + "/contents/" + pins["workflow"] + "?ref=" + pins["sha"]
    body = {
        "path": pins["workflow"],
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(content).decode(),
    }
    responses[url] = Response(url, json.dumps(body).encode())
    client = BoundedJSONHTTP("https://api.github.com", "ZZ-token")
    client._opener = Opener(responses)
    return client, pins, intent, workflow_hash, data, urls


# Section: Snapshot admission is still not execution authority


def test_bound_snapshot_stays_closed():
    client, pins, intent, workflow_hash, _, _ = snapshot_client()
    result = read_protected_snapshot(client, pins, intent, workflow_hash)
    assert result["fresh_snapshot_consistent"] is True
    assert result["post_permitted"] is False
    assert result["run_id"] == 42 and result["attempt"] == 1
    assert result["unresolved_release_gaps"]
    assert len(client._opener.calls) == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("display_title", "ZZ-other"),
        ("status", "completed"),
        ("conclusion", "success"),
        ("run_attempt", 2),
        ("head_sha", "c" * 40),
    ],
)
def test_changed_run_blocks(field, value):
    client, pins, intent, workflow_hash, data, urls = snapshot_client()
    data[0][field] = value
    client._opener.responses[urls[0]].raw = json.dumps(data[0]).encode()
    with pytest.raises(InvalidMergeRequest, match="^protected merge snapshot blocked$"):
        read_protected_snapshot(client, pins, intent, workflow_hash)


def test_wrong_workflow_or_approval_source_blocks():
    client, pins, intent, _, _, _ = snapshot_client()
    with pytest.raises(InvalidMergeRequest):
        read_protected_snapshot(client, pins, intent, "c" * 64)
    with pytest.raises(InvalidMergeRequest):
        read_protected_snapshot(lambda *args: {}, pins, intent, "c" * 64)


def test_workflow_draft_is_uninstalled_manual_only_and_closed():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1]
    path = root / "docs/explicit-merge-workflow-draft.yml"
    value = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert set(value["on"]) == {"workflow_dispatch"}
    assert set(value["jobs"]) == {"explicit-merge"}
    job = value["jobs"]["explicit-merge"]
    assert job["environment"] == "father-create"
    assert len(job["steps"]) == 1 and "exit 1" in job["steps"][0]["run"]
    assert "secrets." not in path.read_text()
    assert not (root / ".github/workflows" / path.name).exists()


# Section: Independent source, workflow and transport guards


def test_get_with_body_is_rejected_before_http():
    client = client_with(b"{}")
    with pytest.raises(InvalidMergeRequest):
        client("GET", "/ZZ", {"ZZ": "value"})
    assert not client._opener.calls


@pytest.mark.parametrize("kind", ["subclass", "origin"])
def test_otherwise_valid_snapshot_requires_exact_github_client(kind):
    client, pins, intent, workflow_hash, _, _ = snapshot_client()
    if kind == "subclass":

        class OtherClient(BoundedJSONHTTP):
            pass

        other = OtherClient("https://api.github.com", "ZZ-token")
        other._opener = client._opener
        client = other
    else:
        client.origin = "https://www.geni.com"
        responses = {}
        for url, response in client._opener.responses.items():
            target = url.replace("https://api.github.com", client.origin)
            response.url = target
            responses[target] = response
        client._opener.responses = responses
    with pytest.raises(InvalidMergeRequest, match="^protected merge snapshot blocked$"):
        read_protected_snapshot(client, pins, intent, workflow_hash)
    assert not client._opener.calls


@pytest.mark.parametrize(
    "field,value", [("encoding", "ZZ-not-base64"), ("path", "ZZ-other.yml"), ("type", "dir")]
)
def test_each_workflow_source_guard_blocks_valid_bytes(field, value):
    client, pins, intent, workflow_hash, _, _ = snapshot_client()
    url = next(url for url in client._opener.responses if "/contents/" in url)
    response = client._opener.responses[url]
    body = json.loads(response.raw)
    body[field] = value
    response.raw = json.dumps(body).encode()
    with pytest.raises(InvalidMergeRequest, match="^protected merge snapshot blocked$"):
        read_protected_snapshot(client, pins, intent, workflow_hash)
    assert len(client._opener.calls) == 5


@pytest.mark.parametrize("intent", ["A" * 64, "g" * 64, "a" * 63])
def test_digest_shape_guard_independent_of_title_and_workflow_hash(intent):
    client, pins, _, workflow_hash, data, urls = snapshot_client()
    data[0]["display_title"] = "explicit-merge:" + intent
    client._opener.responses[urls[0]].raw = json.dumps(data[0]).encode()
    with pytest.raises(InvalidMergeRequest, match="^protected merge snapshot blocked$"):
        read_protected_snapshot(client, pins, intent, workflow_hash)
    assert not client._opener.calls


def test_real_opener_blocks_redirect_without_followup():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from urllib.request import ProxyHandler, build_opener

    from geni_uploader.workflow.merge_http import _NoRedirect

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            if self.path == "/ZZ-start":
                self.send_response(302)
                self.send_header("Location", "/ZZ-followup")
            else:
                self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with pytest.raises(HTTPError) as error:
            opener.open(f"http://127.0.0.1:{server.server_port}/ZZ-start", timeout=5)
        assert error.value.code == 302
        assert calls == ["/ZZ-start"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_finite_json_float_remains_allowed():
    client = client_with(b'{"ZZ":1.25e2}')
    assert client("GET", "/ZZ") == {"ZZ": 125.0}


def test_actual_client_installs_no_redirect_and_ignores_ambient_proxy(monkeypatch):
    from urllib.request import ProxyHandler

    from geni_uploader.workflow.merge_http import _NoRedirect

    monkeypatch.setenv("HTTPS_PROXY", "http://ZZ-proxy.invalid:8888")
    monkeypatch.setenv("HTTP_PROXY", "http://ZZ-proxy.invalid:8888")
    client = BoundedJSONHTTP("https://api.github.com", "ZZ-token")
    assert any(isinstance(handler, _NoRedirect) for handler in client._opener.handlers)
    proxies = [handler for handler in client._opener.handlers if isinstance(handler, ProxyHandler)]
    assert not proxies or all(not handler.proxies for handler in proxies)
