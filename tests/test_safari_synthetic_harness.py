"""Synthetic static harness guardrails, not an iPhone behavior test."""
import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_static_synthetic_page_csp_and_fixed_values():
    html = (ROOT / 'docs/zz-safari-test.html').read_text()
    scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
    assert len(scripts) == 1
    digest = base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in html
    assert 'name="referrer" content="no-referrer"' in html
    assert "connect-src 'none'" in html
    assert 'ZZsyntheticToken1234567890' in html
    assert '&token_type=bearer&expires_in=120' in html
    assert 'Never paste a real token' in html
    assert not re.search(r'<(?:script|link|img|iframe)\b[^>]*(?:src|href)=', html)
    # Source-level smoke check only.
    for forbidden in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage',
                      'sessionStorage', 'navigator.clipboard', 'document.cookie'):
        assert forbidden not in html


def test_test_extractor_has_only_synthetic_host_and_path():
    script = (ROOT / 'docs/zz-safari-test-extractor.js').read_text()
    assert 'u.hostname !== "reihlinstinct.github.io"' in script
    assert 'u.pathname !== "/geni-uploader/zz-safari-test.html"' in script
    assert 'u.hostname !== "www.geni.com"' not in script
    assert 'u.pathname !== "/platform/oauth/auth_success"' not in script
    assert 'completion(token)' in script
    assert 'Stop: could not clear the success URL.' in script
