"""Dormant fixed-endpoint HTTP candidate. Shipped production gate ALWAYS blocks.

Not a released executor. No CLI or credential retrieval. Tests replace the gate
and HTTPSConnection with fixtures; no real Geni request is part of development.
"""
import http.client
import json

from geni_uploader.core.intent import _id
from geni_uploader.core.parent_contract import LIMIT, classify_create, payload
from geni_uploader.core.people import require
from human_parent_gate import require_production_release


class ClosedParentHTTP:
    """One-shot per-instance transport, NOT shared durable intent or owner auth.

    The service must consume authenticated owner-global durable intent BEFORE
    invoking send, and retain that consumption through every outcome. This class
    cannot establish that prerequisite. Its unconditional release gate prevents
    callers from treating a local instance or receipt as permission to send.
    """

    def __init__(self):
        self._attempted = False

    def send(self, owner, approved_payload, token):
        require_production_release()  # ALWAYS raises in the shipped package.
        require(not self._attempted)
        _id(owner, 'profile-')
        reviewed = payload(approved_payload)
        require(reviewed['gender'] == 'male')
        require(type(token) is str and 0 < len(token) <= 8192
                and token.isascii() and all(33 <= ord(c) <= 126 for c in token))
        raw = json.dumps(reviewed, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        require(len(raw) <= 65536)
        # Burn local latch before even constructing a connection. Connection,
        # request, response, timeout or close failure never makes this reusable.
        self._attempted = True
        client = None
        try:
            client = http.client.HTTPSConnection('www.geni.com', port=443, timeout=10)
            client.request('POST', '/api/' + owner + '/add-parent', body=raw,
                           headers={'Authorization': 'Bearer ' + token,
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'})
            response = client.getresponse()
            body = response.read(LIMIT + 1)
            # Classification is deliberately strict and remains unverified.
            # No Location following, retry, refresh or alternate-host fallback.
            return classify_create(sent=True, status=response.status, raw=body)
        except (OSError, http.client.HTTPException, ValueError):
            return classify_create(sent=True)
        finally:
            if client is not None:
                try:
                    client.close()
                except (OSError, http.client.HTTPException, ValueError):
                    pass  # A close failure cannot change consumed/uncertain status.
