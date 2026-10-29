import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
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
const streamOf = (chunks, log = []) => new ReadableStream({
  pull(controller) {
    if (chunks.length === 0) { controller.close(); return; }
    const chunk = chunks.shift();
    log.push(chunk.length);
    controller.enqueue(typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk);
  },
  cancel() { log.push('cancelled'); },
}, { highWaterMark: 0 }); // Pull only on demand, so the log shows what the reader asked for.
const waitFor = async (cond) => { for (let i = 0; i < 200 && !cond(); i++) await new Promise((r) => setImmediate(r)); assert.ok(cond()); };
const respond = (status, body = '', extra = {}) => ({ status, redirected: false, type: 'basic', body: streamOf([body]),
  text: async () => { throw Error('unbounded text() used'); }, ...extra });
const sha = (raw) => createHash('sha256').update(raw).digest('hex');

function harness({ key = () => respond(200, JSON.stringify({ key_id: '568250167242549743', key: KEY })), put = respond(201), seal } = {}) {
  const trace = [];
  const sealed = [];
  const timers = new Map();
  let nextTimer = 1;
  const deps = {
    fetch: async (url, init) => {
      trace.push({ url, method: init.method, redirect: init.redirect, body: init.body, headers: init.headers, signal: init.signal });
      if (init.method === 'GET') { if (key instanceof Error) throw key; return typeof key === 'function' ? key() : key; }
      if (put instanceof Error) throw put;
      return typeof put === 'function' ? put() : put;
    },
    seal: seal ?? (async (message, publicKey) => { sealed.push({ message: new TextDecoder().decode(message), publicKey });
      return new Uint8Array(message.length + 48).fill(9); }),
    setTimeout: (fn, ms) => { const id = nextTimer++; timers.set(id, { fn, ms }); return id; },
    clearTimeout: (id) => { timers.delete(id); },
  };
  const fire = () => { const all = [...timers.values()]; timers.clear(); for (const t of all) t.fn(); };
  return { trace, sealed, deps, timers, fire, custody: createEnvironmentSecretCustody(config(), deps) };
}
const noSentinel = (x) => assert.doesNotMatch(JSON.stringify(x), /SENTINEL/);
const result = (status, slot = 'secondary', digest = null) => ({ status, slot, bundle_sha256: digest, authenticated: false, write_permitted: false });

test('stores one complete bundle with exactly two fixed calls and a value-free result', async () => {
  const h = harness();
  const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  assert.deepEqual(r, result('stored_created', 'secondary', sha(bundleJson())));
  assert.ok(Object.isFrozen(r));
  assert.equal(h.timers.size, 0); // Every per-call deadline is cleared.
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
  assert.deepEqual(await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }),
    result('stored_updated', 'secondary', sha(bundleJson())));
});

test('no global fetch and no default dependency', async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => { throw Error('global fetch used'); };
  try {
    const h = harness();
    assert.equal((await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
  } finally { globalThis.fetch = saved; }
  const fn = () => {};
  for (const deps of [undefined, {}, { fetch: async () => {} }, { seal: async () => {} }, { fetch: 1, seal: 2 },
    { fetch: fn, seal: fn }, { fetch: fn, seal: fn, setTimeout: fn }, { fetch: fn, seal: fn, setTimeout: fn, clearTimeout: 1 },
    { fetch: fn, seal: fn, setTimeout: fn, clearTimeout: fn, url: 'https://example.invalid' }]) {
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
    respond(200, '', { body: null }), respond(200, '', { body: 'not a stream' }),
    respond(200, '', { body: streamOf(['{"key_id":"1",', 7]) }), respond(200, '', { body: streamOf([new Uint8Array([0xff, 0xfe])]) }),
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
  assert.deepEqual(await h.custody.storeBundle(request), result('stored_created', 'secondary', sha(bundleJson())));
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


test('success acknowledges the SHA-256 of the exact canonical bundle; every failure carries null', async () => {
  const other = bundleJson({ ...bundleObject(), generation: 3 });
  const h = harness();
  const r = await h.custody.storeBundle({ slot: 'secondary', bundleJson: other });
  assert.equal(r.bundle_sha256, sha(other));
  assert.match(r.bundle_sha256, /^[0-9a-f]{64}$/);
  assert.notEqual(r.bundle_sha256, sha(bundleJson()));
  assert.equal(h.sealed[0].message, other);
  for (const [opts, status] of [[{ key: respond(500) }, 'public_key_failed'], [{ seal: async () => 'x' }, 'seal_failed'],
    [{ put: respond(500) }, 'write_state_unknown']]) {
    const f = harness(opts);
    assert.deepEqual(await f.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }), result(status));
  }
  assert.deepEqual(await harness().custody.storeBundle({ slot: 'secondary', bundleJson: ' ' }), result('input_rejected'));
});

test('public-key body is read as a bounded stream and cancelled at the cap', async () => {
  const log = [];
  const chunks = [new Uint8Array(4000).fill(32), new Uint8Array(200).fill(32), new Uint8Array(100000).fill(32)];
  const h = harness({ key: respond(200, '', { body: streamOf(chunks, log) }) });
  assert.deepEqual(await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }), result('public_key_failed'));
  assert.deepEqual(log, [4000, 200, 'cancelled']); // The 100000-byte chunk is never pulled.
  const good = JSON.stringify({ key_id: '568250167242549743', key: KEY });
  const split = harness({ key: respond(200, '', { body: streamOf([good.slice(0, 5), good.slice(5, 20), good.slice(20)]) }) });
  assert.equal((await split.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
  const exact = harness({ key: respond(200, '', { body: streamOf([good + ' '.repeat(4096 - good.length)]) }) });
  assert.equal((await exact.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
});

test('public-key timeout aborts the call, reports public_key_failed and never writes', async () => {
  let signal;
  const h = harness({ key: () => new Promise(() => {}) });
  const pending = h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  await waitFor(() => h.trace.length === 1 && h.timers.size === 1);
  signal = h.trace[0].signal;
  assert.equal(signal.aborted, false);
  assert.deepEqual([...h.timers.values()].map((t) => t.ms), [10000]);
  h.fire();
  assert.deepEqual(await pending, result('public_key_failed'));
  assert.equal(signal.aborted, true);
  assert.deepEqual(h.trace.map((t) => t.method), ['GET']);
  assert.equal(h.sealed.length, 0);
});

test('PUT timeout is write_state_unknown, is never retried, and keeps the slot busy until the call settles', async () => {
  let finish;
  let puts = 0;
  const h = harness({ put: () => (++puts === 1 ? new Promise((resolve) => { finish = resolve; }) : respond(201)) });
  const pending = h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() });
  await waitFor(() => h.trace.length === 2 && h.timers.size === 1);
  assert.deepEqual(h.trace.map((t) => t.method), ['GET', 'PUT']);
  h.fire();
  assert.deepEqual(await pending, result('write_state_unknown'));
  assert.equal(h.trace[1].signal.aborted, true);
  // The abandoned PUT may still commit: a second write for this slot must not race it.
  assert.deepEqual(await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() }), result('slot_busy'));
  finish(respond(201));
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  assert.equal((await h.custody.storeBundle({ slot: 'secondary', bundleJson: bundleJson() })).status, 'stored_created');
  assert.equal(h.trace.filter((t) => t.method === 'PUT').length, 2); // One per accepted call, none automatic.
});
