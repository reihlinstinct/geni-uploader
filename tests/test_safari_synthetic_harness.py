"""Synthetic static harness guardrails, not an iPhone behavior test."""
import base64
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_static_synthetic_page_csp_and_fixed_values():
    html = (ROOT / 'docs/zz-safari-test.html').read_text()
    scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
    assert len(scripts) == 1
    digest = base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in html
    assert 'name="referrer" content="no-referrer"' in html
    assert "connect-src 'none'" in html
    assert "default-src 'none'" in html
    assert html.index('Content-Security-Policy') < html.index('<script>')
    assert 'ZZsyntheticToken1234567890' in html
    assert '&token_type=bearer&expires_in=120' in html
    assert 'Never paste a real token' in html
    assert not re.search(r'<(?:script|link|img|iframe)\b[^>]*(?:src|href)=', html)
    for forbidden_markup in ('http-equiv="refresh"', '<a ', '<form ', '<object ',
                             '<embed ', 'url('):
        assert forbidden_markup not in html.lower()
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


def test_extractor_equivalence_and_node_cases(tmp_path):
    script = (ROOT / "docs/zz-safari-test-extractor.js").read_text()
    normalized = script.replace("reihlinstinct.github.io", "www.geni.com").replace(
        "/geni-uploader/zz-safari-test.html", "/platform/oauth/auth_success")
    production = ROOT / "tools/safari-token/extract-token.js"
    if production.exists():
        assert normalized == production.read_text()
        cases = ROOT / "tools/safari-token/test-extract.js"
    else:
        # Interim pin only until the production parser lands.
        assert hashlib.sha256(normalized.encode()).hexdigest() == "5acf53cec45539095a04e175c51cf6be834e49704582e7826e18c861df3d85b7"
        cases = ROOT / "tests/safari_harness_node.cjs"
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable; parser execution not verified")
    (tmp_path / "extract-token.js").write_text(normalized)
    shutil.copyfile(cases, tmp_path / "test.cjs")
    subprocess.run([node, str(tmp_path / "test.cjs")], check=True, timeout=20)
