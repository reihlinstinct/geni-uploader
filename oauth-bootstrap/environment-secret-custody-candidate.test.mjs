import test from 'node:test';
import assert from 'node:assert/strict';
import { createEnvironmentSecretCustody } from './environment-secret-custody-candidate.mjs';

const KEY = btoa(String.fromCharCode(...new Uint8Array(32).fill(7)));
const BASE = 'https://api.github.com/repos/zz-owner/zz-repo/environments/ZZ-father/secrets/';
const config = () => ({ schema: 1, destinations: {
  secondary: { owner: 'profile-999001', repository_owner: 'zz-owner', repository_name: 'zz-repo',
    repository_id: '999002', environment: 'ZZ-father', secret: 'GENI_ZZ_CUSTODY' },
} });
const bundleObject = () => ({ schema: 1, slot: 'secondary', owner: 'profile-999001', repository_id: '999002',
  environment: 'ZZ-father', secret: 'GENI_ZZ_CUSTODY', connection_id: 'a'.repeat(64), generation: 2,
  revocation_epoch: 3, issued_at: 100, provider_expires_at: 1200, expires_at: 900,
  access_token: 'ZZ-ACCESS-SENTINEL', refresh_token: 'ZZ-REFRESH-SENTINEL' });
const bundleJson = (b = bundleObject()) => JSON.stringify(b);
const respond = (status, body = '', extra = {}) => ({ status, redirected: false, type: 'basic', text: async () => body, ...extra });

function harness({ key = respond(200, JSON.stringify({ key_id: '568250167242549743', key: KEY })), put = respond(201), seal } = {}) {
  const trace = [];
  const sealed = [];
  const deps = {
    fetch: async (url, init) => {
      trace.push({ url, method: init.method, redirect: init.redirect, body: init.body, headers: init.headers });
      if (trace.length === 1) { if (key instanceof Error) throw key; return typeof key === 'function' ? key() : key; }
      if (put instanceof Error) throw put;
      return typeof put === 'function' ? put() : put;
    },
    seal: seal ?? (async (message, publicKey) => { sealed.push({ message: new TextDecoder().decode(message), publicKey });
      return new Uint8Array(message.length + 48).fill(9); }),
  };
  return { trace, sealed, deps, custody: createEnvironmentSecretCustody(config(), deps) };
}
const noSentinel = (x) => assert.doesNotMatch(JSON.stringify(x), /SENTINEL/);
const result = (status, slot = 'secondary') => ({ status, slot, authenticated: false, write_permitted: false });

test('stores one complete bundle with exactly two fixed calls and a value-free result', async () => {
  const h = harness();
  const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  assert.deepEqual(r, result('stored_created'));
  assert.ok(Object.isFrozen(r));
  assert.deepEqual(h.trace.map((t) => [t.method, t.url, t.redirect]), [
    ['GET', BASE + 'public-key', 'manual'], ['PUT', BASE + 'GENI_ZZ_CUSTODY', 'manual']]);
  assert.deepEqual(JSON.parse(h.trace[1].body), { encrypted_value: btoa(String.fromCharCode(...new Uint8Array(bundleJson().length + 48).fill(9))), key_id: '568250167242549743' });
  assert.equal(h.sealed.length, 1);
  assert.equal(h.sealed[0].message, bundleJson()); // The whole bundle, never a raw access token.
  assert.deepEqual([...h.sealed[0].publicKey], new Array(32).fill(7));
  for (const t of h.trace) { noSentinel(t); assert.equal(Object.hasOwn(t.headers, 'Authorization'), false); }
  noSentinel(r);
});

test('204 update is reported distinctly', async () => {
  const h = harness({ put: respond(204) });
  assert.deepEqual(await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }), result('stored_updated'));
});

test('no global fetch and no default dependency', async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => { throw Error('global fetch used'); };
  try {
    const h = harness();
    assert.equal((await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
  } finally { globalThis.fetch = saved; }
  for (const deps of [undefined, {}, { fetch: async () => {} }, { seal: async () => {} }, { fetch: 1, seal: 2 },
    { fetch: async () => {}, seal: async () => {}, url: 'https://example.invalid' }]) {
    assert.throws(() => createEnvironmentSecretCustody(config(), deps));
  }
});

test('registry is closed, trusted-config only and validated at construction', () => {
  const bad = [];
  for (const key of Object.keys(config().destinations.secondary)) {
    const c = config(); delete c.destinations.secondary[key]; bad.push(c);
    const d = config(); d.destinations.secondary[key] = 'ZZ\nbad'; bad.push(d);
  }
  const extra = config(); extra.destinations.secondary.api = 'https://example.invalid'; bad.push(extra);
  const top = config(); top.origin = 'https://example.invalid'; bad.push(top);
  const shared = config(); shared.destinations.tertiary = { ...shared.destinations.secondary, owner: 'profile-999009' }; bad.push(shared);
  bad.push({ schema: 2, destinations: config().destinations }, { schema: 1, destinations: {} }, null);
  for (const c of bad) assert.throws(() => createEnvironmentSecretCustody(c, harness().deps));
});

test('config mutation after construction cannot redirect the write', async () => {
  const c = config();
  const h = harness();
  const custody = createEnvironmentSecretCustody(c, h.deps);
  c.destinations.secondary.repository_owner = 'zz-attacker';
  c.destinations.secondary.secret = 'GENI_ZZ_OTHER';
  c.destinations.evil = { ...c.destinations.secondary };
  assert.equal((await custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
  assert.deepEqual(h.trace.map((t) => t.url), [BASE + 'public-key', BASE + 'GENI_ZZ_CUSTODY']);
  assert.equal((await custody.storeBundle({ slot: 'evil', bundleJson: bundleJson() })).status, 'input_rejected');
});

test('unknown slots, wrong owner/destination and malformed bundles stop before any call', async () => {
  const cases = [];
  for (const slot of ['primary', '__proto__', 'constructor', 'toString', '', 1, null]) cases.push({ slot, bundleJson: bundleJson() });
  for (const [key, value] of [['slot', 'primary'], ['owner', 'profile-999004'], ['repository_id', '999009'],
    ['environment', 'ZZ-other'], ['secret', 'GENI_ZZ_OTHER'], ['schema', 2], ['generation', 0], ['generation', true],
    ['expires_at', 1300], ['expires_at', 100], ['issued_at', -1], ['connection_id', 'A'.repeat(64)],
    ['access_token', ''], ['access_token', 'ZZ SENTINEL'], ['refresh_token', 'ZZ\nSENTINEL'], ['access_token', 1]]) {
    cases.push({ slot: 'secondary', bundleJson: bundleJson({ ...bundleObject(), [key]: value }) });
  }
  for (const key of Object.keys(bundleObject())) { const b = bundleObject(); delete b[key]; cases.push({ slot: 'secondary', bundleJson: bundleJson(b) }); }
  const raw = bundleJson();
  cases.push({ slot: 'secondary', bundleJson: bundleJson({ ...bundleObject(), raw_token: 'ZZ-SENTINEL' }) },
    { slot: 'secondary', bundleJson: ' ' + raw }, { slot: 'secondary', bundleJson: raw.replace('"schema":1', '"schema":1,"schema":1') },
    { slot: 'secondary', bundleJson: raw.replace('"generation":2', '"generation":2.0') }, { slot: 'secondary', bundleJson: '[]' },
    { slot: 'secondary', bundleJson: 'x'.repeat(49153) }, { slot: 'secondary', bundleJson: bundleObject() },
    { slot: 'secondary', bundleJson: raw, owner: 'profile-999004' }, { slot: 'secondary' }, null, 'secondary');
  for (const request of cases) {
    const h = harness();
    const r = await h.custody.storeBundle(request);
    assert.equal(r.status, 'input_rejected', JSON.stringify(request)?.slice(0, 80));
    assert.equal(r.authenticated, false); assert.equal(r.write_permitted, false);
    assert.equal(h.trace.length, 0); noSentinel(r);
  }
});

test('public-key redirects, wrong status and bad shapes stop with no write', async () => {
  const good = { key_id: '568250167242549743', key: KEY };
  const keys = [respond(301, JSON.stringify(good)), respond(302), respond(304), respond(201, JSON.stringify(good)),
    respond(404), respond(500, 'ZZ-SENTINEL'), respond(200, JSON.stringify(good), { redirected: true }),
    respond(0, '', { type: 'opaqueredirect' }), respond(200, 'not json'), respond(200, JSON.stringify({ ...good, extra: 1 })),
    respond(200, JSON.stringify({ key: KEY })), respond(200, JSON.stringify({ ...good, key_id: 'ZZ id' })),
    respond(200, JSON.stringify({ ...good, key: btoa('short') })), respond(200, JSON.stringify({ ...good, key: KEY + 'AA' })),
    respond(200, JSON.stringify({ ...good, key: 7 })), respond(200, ' '.repeat(4097)), respond(200, '[]'),
    { status: 200 }, null, new Error('ZZ-SENTINEL network')];
  for (const key of keys) {
    const h = harness({ key });
    const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
    assert.deepEqual(r, result('public_key_failed'));
    assert.deepEqual(h.trace.map((t) => t.method), ['GET']);
    assert.equal(h.sealed.length, 0);
  }
});

test('seal failure or wrong ciphertext shape stops before the write', async () => {
  for (const seal of [async () => { throw Error('ZZ-SENTINEL'); }, async (m) => new Uint8Array(m.length),
    async (m) => Array.from(new Uint8Array(m.length + 48)), async () => 'ZZ-SENTINEL', async (m) => new Uint8Array(m.length + 49)]) {
    const h = harness({ seal });
    const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
    assert.deepEqual(r, result('seal_failed'));
    assert.deepEqual(h.trace.map((t) => t.method), ['GET']);
  }
});

test('write failure or ambiguous status is unknown state, never success, never retried', async () => {
  for (const put of [respond(200), respond(202), respond(301), respond(403, 'ZZ-SENTINEL'), respond(409), respond(422),
    respond(500), respond(201, '', { redirected: true }), null, new Error('ZZ-SENTINEL reset')]) {
    const h = harness({ put });
    const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
    assert.deepEqual(r, result('write_state_unknown'));
    assert.deepEqual(h.trace.map((t) => t.method), ['GET', 'PUT']);
    noSentinel(r);
  }
});

test('request strings are snapshotted before any await', async () => {
  let request;
  const h = harness({ key: () => { request.slot = 'tertiary'; request.bundleJson = 'ZZ-MUTATED'; return respond(200, JSON.stringify({ key_id: '1', key: KEY })); } });
  request = { slot: 'secondary', bundleJson: bundleJson() };
  assert.deepEqual(await h.custody.storeBundle(request), result('stored_created'));
  assert.equal(h.sealed[0].message, bundleJson());
  assert.equal(h.trace[1].url, BASE + 'GENI_ZZ_CUSTODY');
});

test('concurrent write for the same slot stops and the slot is freed afterwards', async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const h = harness({ key: async () => { await gate; return respond(200, JSON.stringify({ key_id: '1', key: KEY })); } });
  const first = h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  assert.deepEqual(await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }), result('slot_busy'));
  release();
  assert.equal((await first).status, 'stored_created');
  assert.equal(h.trace.filter((t) => t.method === 'PUT').length, 1);
  const again = harness();
  assert.equal((await again.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
});

test('only fixed API paths: no dispatch, Geni or arbitrary URL is reachable', async () => {
  const h = harness();
  await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  for (const t of h.trace) {
    assert.ok(t.url.startsWith(BASE));
    assert.doesNotMatch(t.url, /dispatch|workflows|geni\.com|\?|#/);
  }
});
