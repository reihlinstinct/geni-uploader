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


def test_callback_reads_only_access_token_with_pinned_script():
    import base64
    import hashlib
    import re
    page = (ROOT / 'docs/oauth-callback.html').read_text()
    assert 'layout: null' in page
    assert '{{' not in page and '{%' not in page
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
    assert "fields.getAll('access_token')" in script
    assert "query.getAll('access_token')" in script
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
    const ctx = {URLSearchParams, window:{addEventListener(){}},
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
    assert script.count('.get(') == 0
    assert script.count('.getAll(') == 2
    assert script.count("fields.getAll('access_token')") == 1
    assert script.count("query.getAll('access_token')") == 1
    assert script.count('location.search') == 1
    assert script.count('new URLSearchParams(location.search)') == 1
    harness = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const cases = [
  ['', '', 'refreshed or reopened'],
  ['?code=ZZSECRET', '', 'authorization-code field'],
  ['?access_token=', '', 'empty token field'],
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
  const ctx = {URLSearchParams, window:{addEventListener(){}}, location,
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


def test_query_token_copy_conflicts_and_clear_failure():
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
    harness = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
for(const [search,hash,ok,failClear] of [
 ['?access_token=ZZtoken%26value','',true,false],
 ['','#access_token=ZZtoken%26value',true,false],
 ['?access_token=ZZ+token','',false,false],
 ['?access_token=ZZone&access_token=ZZtwo','',false,false],
 ['?access_token=ZZone&%61ccess_token=ZZone','',false,false],
 ['?access_token=ZZone','#access_token=ZZone',false,false],
 ['?access_token=ZZone','#access_token=ZZtwo',false,false],
 ['?access_token=ZZtoken','',false,true]
]){
 const elements=Object.fromEntries(['token','copy','clear','status'].map(id=>[id,{value:'',hidden:true,textContent:'',handlers:{},addEventListener(k,fn){this.handlers[k]=fn;},focus(){},select(){}}]));
 const events=[];let restored;const location={search,hash,pathname:'/callback.html'};
 vm.runInNewContext(SCRIPT,{URLSearchParams,window:{addEventListener(k,fn){assert.equal(k,'pageshow');restored=fn;}},location,history:{replaceState(){events.push('clear');if(failClear)throw Error('ZZsecret');location.search='';location.hash='';}},navigator:{clipboard:{async writeText(v){events.push(v);}}},document:{getElementById(id){return elements[id];},addEventListener(k,fn){fn();}}});
 assert.equal(events[0],'clear');assert.equal(!elements.copy.hidden,ok);
 assert(!elements.status.textContent.includes('ZZsecret'));
 if(ok){assert.equal(elements.token.value,'ZZtoken&value');await elements.copy.handlers.click();assert.equal(events[1],'ZZtoken&value');restored({persisted:true});assert.equal(elements.token.value,'');assert.equal(elements.copy.hidden,true);await elements.clear.handlers.click();assert.equal(events.at(-1),'');}
 else {assert.equal(elements.token.value,'');assert.equal(events.length,1);}
}
})();
""".replace('SCRIPT', json.dumps(script))
    subprocess.run([node, '-e', harness], check=True, capture_output=True, text=True)


def test_query_form_encoding_preserves_encoded_plus():
    import shutil
    import subprocess

    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    subprocess.run([node, '-e', "const a=require('node:assert/strict');a.equal(new URLSearchParams('?access_token=ZZ%2Btoken').get('access_token'),'ZZ+token');a.equal(new URLSearchParams('?access_token=ZZ+token').get('access_token'),'ZZ token');"], check=True)
