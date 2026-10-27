"""Public policy copies stay consistent and distinguish conditional modes."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_privacy_copies_match_and_cover_hosted_data():
    policy = (ROOT / 'PRIVACY.md').read_text()
    assert policy == (ROOT / 'docs/privacy.md').read_text()
    for required in ('Local mode', 'Hosted GitHub Actions mode',
                     'Separately agreed assistance or token custody',
                     'Raw output can include', 'Git history',
                     'Removing an Actions secret does not',
                     'This is not implied by app registration'):
        assert required in policy
    assert 'The author collects no data' not in policy
    assert 'logs contain timestamps, steps, HTTP statuses and short' not in policy


def test_landing_links_terms_and_privacy_without_authorizing_access():
    landing = (ROOT / 'docs/index.md').read_text()
    assert '[Privacy Policy](privacy.md)' in landing
    assert '[Terms of use](terms.md)' in landing
    terms = (ROOT / 'docs/terms.md').read_text()
    assert 'do not create an account' in terms
    assert '[Privacy Policy](privacy.md)' in terms
    assert 'Geni' in terms and 'GitHub' in terms


def test_callback_is_client_side_fragment_only_with_pinned_script():
    import base64
    import hashlib
    import re
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    assert 'layout: null' in page
    assert "history.replaceState(null, '', location.pathname)" in page
    assert 'name="referrer" content="no-referrer"' in page
    assert "default-src 'none'" in page
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert "script-src 'sha256-" + digest + "'" in page
    for forbidden in ('document.cookie', 'localStorage',
                      'sessionStorage', 'fetch(', 'XMLHttpRequest', '<form',
                      '<iframe', '<img', 'src=', 'href=', 'console.', 'innerHTML'):
        assert forbidden not in page
    assert "new URLSearchParams(location.hash.slice(1))" in script
    assert "fields.get('access_token')" in script
    assert 'navigator.clipboard.writeText(output.value)' in script
    assert "output.value = ''" in script
    assert 'Never paste it into chat' in page
    assert 'Clipboard history' in (ROOT / 'PRIVACY.md').read_text()


def test_callback_script_extracts_only_fragment_copies_and_clears():
    import json
    import re
    import shutil
    import subprocess

    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable for offline DOM simulation')
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    harness = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
(async () => {
  for (const found of [true, false]) {
    const elements = Object.fromEntries(['token','copy','clear','status'].map(id =>
      [id, {value:'', hidden:true, textContent:'', handlers:{},
        addEventListener(k, fn) {this.handlers[k]=fn;}, focus(){}, select(){}}]));
    const events = [];
    const ctx = {URLSearchParams,
      location:{search:'', hash:found?'#access_token=ZZtoken%26value&expires_in=99':'#error=denied', pathname:'/callback.html'},
      history:{replaceState(a,b,c){events.push(c);}},
      navigator:{clipboard:{async writeText(value){events.push(value);}}},
      document:{getElementById(id){return elements[id];},
        addEventListener(k,fn){assert.equal(k,'DOMContentLoaded');fn();}}};
    vm.runInNewContext(SCRIPT, ctx);
    assert.equal(events[0], '/callback.html');
    assert.equal(elements.token.value, found?'ZZtoken&value':'');
    assert.equal(elements.copy.hidden, !found);
    if (found) {
      await elements.copy.handlers.click();
      assert.equal(events[1], 'ZZtoken&value');
      elements.clear.handlers.click();
      assert.equal(elements.token.value, '');
      assert.equal(elements.copy.hidden, true);
    }
  }
})();
'''.replace('SCRIPT', json.dumps(script))
    subprocess.run([node, '-e', harness], check=True, capture_output=True, text=True)


def test_callback_diagnostics_are_fixed_presence_only_before_url_clear():
    import json
    import re
    import shutil
    import subprocess

    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable for offline DOM simulation')
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    assert script.index('const diagnostics') < script.index('history.replaceState')
    assert script.count('.get(') == 1
    assert script.count("fields.get('access_token')") == 1
    assert script.count('location.search') == 1
    assert script.count('new URLSearchParams(location.search)') == 1
    harness = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const cases = [
  ['', '', 'refreshed or reopened'],
  ['?code=ZZSECRET', '', 'authorization-code field'],
  ['?access_token=ZZSECRET', '', 'token field was present in the query'],
  ['?error=ZZSECRET', '', 'error or status field'],
  ['?status=ZZSECRET', '', 'error or status field'],
  ['', '#error=ZZSECRET', 'error or status field'],
  ['', '#status=ZZSECRET', 'error or status field'],
  ['', '#unknown=ZZSECRET', 'fragment was present'],
  ['', '#access_token=', 'fragment was present'],
  ['?ZZSECRET=ZZSECRET', '', 'No recognized response fields'],
];
for (const [search, hash, expected] of cases) {
  const elements = Object.fromEntries(['token','copy','clear','status'].map(id =>
    [id, {value:'', hidden:true, textContent:'', addEventListener(){}}]));
  const location = {search, hash, pathname:'/callback.html'};
  const ctx = {URLSearchParams, location,
    history:{replaceState(a,b,c){assert.equal(c,'/callback.html');location.search='';location.hash='';}},
    document:{getElementById(id){return elements[id];},
      addEventListener(k,fn){fn();}}};
  vm.runInNewContext(SCRIPT, ctx);
  assert.ok(elements.status.textContent.includes(expected), elements.status.textContent);
  assert.ok(!elements.status.textContent.includes('ZZSECRET'));
  assert.equal(elements.token.value, '');
  assert.equal(elements.copy.hidden, true);
}
'''.replace('SCRIPT', json.dumps(script))
    subprocess.run([node, '-e', harness], check=True, capture_output=True, text=True)


def assert_response_parser_allowlist(script):
    import re
    # The parser objects must never escape to another variable, iterator or sink.
    # Pin every occurrence, not only get(): getAll/toString/spread also read values.
    assert 'new URL(' not in script
    assert '.searchParams' not in script
    assert script.count('location.hash') == 2
    assert script.count('location.search') == 1
    assert 'location.href' not in script
    assert script.count('URLSearchParams(') == 2
    assert script.count('new URLSearchParams(location.hash.slice(1))') == 1
    assert script.count('new URLSearchParams(location.search)') == 1
    expected = {
        'query': ['const query = new URLSearchParams(location.search);',
                  "code: query.has('code'),", "queryToken: query.has('access_token'),",
                  "queryError: query.has('error') || query.has('status'),",
                  "else if (diagnostics.queryToken) detail = 'A token field was present in the query, not the fragment. This page does not read query token values. Stop and check the authorization flow.';"],
        'fields': ['const fields = new URLSearchParams(location.hash.slice(1));',
                   "const token = fields.get('access_token') || '';",
                   "fragmentError: fields.has('error') || fields.has('status'),",
                   "let detail = 'No recognized response fields were found. If this page was refreshed or reopened, its earlier response was already cleared. Do not share the address.';"],
    }
    for name, lines in expected.items():
        actual = [line.strip() for line in script.splitlines()
                  if re.search(r'\b' + name + r'\b', line)]
        assert actual == lines


def test_response_parser_objects_have_no_unreviewed_reads_or_aliases():
    import re
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    assert_response_parser_allowlist(script)


def test_parser_allowlist_kills_alternate_reads_after_url_clear():
    import re

    import pytest
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    for mutation in ["document.title = query.getAll('code');",
                     'document.title = query.toString();',
                     'document.title = [...query];',
                     "document.title = fields.getAll('error');",
                     'document.title = fields.toString();',
                     'const alias = fields;',
                     'const p = new URLSearchParams(location.hash);',
                     'const p = new URL(location.href).searchParams;']:
        changed = script.replace("history.replaceState(null, '', location.pathname);",
                                 "history.replaceState(null, '', location.pathname);\n" + mutation)
        with pytest.raises(AssertionError):
            assert_response_parser_allowlist(changed)


# Independent review pin: a script change needs explicit review of this digest.
# CSP consistency alone cannot authorize a new response-value reader.
REVIEWED_CALLBACK_SCRIPT_SHA256 = 'e7712229a3edad74f18083d11722e13b97f4335c692c59de8055e57a9eec85ae'


def test_callback_script_matches_independently_reviewed_digest():
    import hashlib
    import re
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    script = re.search(r'<script>(.*?)</script>', page, re.DOTALL).group(1)
    assert hashlib.sha256(script.encode()).hexdigest() == REVIEWED_CALLBACK_SCRIPT_SHA256
