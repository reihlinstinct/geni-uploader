"""Pinned-origin bounded JSON transport. No credentials are read or calls made on import."""

import json
import math
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from geni_uploader.core.merge_request import InvalidMergeRequest

# Section: Redirect-free, one-attempt private transport


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BoundedJSONHTTP:
    """An exact configured origin, bearer passed privately, no retries or logging."""

    def __init__(self, origin, token):
        if origin not in {"https://api.github.com", "https://www.geni.com"}:
            raise InvalidMergeRequest("merge transport origin blocked")
        if type(token) is not str or not token or any(c.isspace() for c in token):
            raise InvalidMergeRequest("merge transport credential blocked")
        self.origin = origin
        self._token = token
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def __call__(self, method, path, body=None):
        try:
            if method not in {"GET", "POST", "PATCH"} or type(path) is not str:
                raise InvalidMergeRequest("merge transport request blocked")
            parsed = urlsplit(path)
            if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc:
                raise InvalidMergeRequest("merge transport path blocked")
            if parsed.fragment or any(c.isspace() or ord(c) < 32 for c in path):
                raise InvalidMergeRequest("merge transport path blocked")
            if method == "GET" and body is not None:
                raise InvalidMergeRequest("merge transport request blocked")
            data = None if body is None else json.dumps(body, allow_nan=False).encode()
            if data is not None and len(data) > 1024 * 1024:
                raise InvalidMergeRequest("merge transport body blocked")
            headers = {"Authorization": "Bearer " + self._token, "Accept": "application/json"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            if self.origin == "https://api.github.com":
                headers["X-GitHub-Api-Version"] = "2026-03-10"
            request = Request(self.origin + path, data=data, headers=headers, method=method)
            with self._opener.open(request, timeout=30) as response:
                if response.status != 200 and response.status != 201:
                    raise InvalidMergeRequest("merge transport status blocked")
                if response.url != self.origin + path:
                    raise InvalidMergeRequest("merge transport redirect blocked")
                if response.headers.get("Link"):
                    raise InvalidMergeRequest("merge transport pagination blocked")
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise InvalidMergeRequest("merge transport response too large")
            return json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique,
                parse_constant=lambda _: _bad_json(),
                parse_float=_finite_float,
            )
        except HTTPError:
            raise InvalidMergeRequest("merge transport HTTP failure; do not retry") from None
        except Exception:  # noqa: BLE001 - no raw URL, credential or provider exception may escape
            raise InvalidMergeRequest("merge transport blocked; do not retry") from None


def _bad_json():
    raise InvalidMergeRequest("merge transport JSON blocked")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        _bad_json()
    return number


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _bad_json()
        result[key] = value
    return result
