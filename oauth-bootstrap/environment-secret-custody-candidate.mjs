// Dormant fake-only candidate (#475). NOT imported by worker.mjs or any live path.
// Stores one complete credential bundle into one fixed GitHub environment secret.
// It never authenticates anyone, never grants Geni permission and never retries.
const API = 'https://api.github.com';
const BUNDLE_KEYS = ['schema', 'slot', 'owner', 'repository_id', 'environment', 'secret', 'connection_id',
  'generation', 'revocation_epoch', 'issued_at', 'provider_expires_at', 'expires_at', 'access_token', 'refresh_token'];
const ENTRY_KEYS = ['owner', 'repository_owner', 'repository_name', 'repository_id', 'environment', 'secret'];
const SEAL_OVERHEAD = 48; // libsodium sealed box: 32-byte ephemeral key + 16-byte MAC.
const MAX_BUNDLE = 49152;
const MAX_KEY_BODY = 4096;
const CALL_TIMEOUT_MS = 10000; // Per network call; a timeout is never retried.

class Blocked extends Error {}
const need = (x) => { if (!x) throw new Blocked(); };
const plain = (x) => x !== null && typeof x === 'object' && Object.getPrototypeOf(x) === Object.prototype;
const exact = (x, keys) => need(plain(x) && Object.keys(x).sort().join(',') === [...keys].sort().join(','));
const text = (x, re) => need(typeof x === 'string' && re.test(x));
const integer = (x) => need(Number.isSafeInteger(x) && x >= 0 && x < 2 ** 40);
const credential = (x) => need(typeof x === 'string' && x.length > 0 && x.length <= 16384 && !/[\s\x00-\x1f\x7f]/.test(x));
const ID = /^[1-9][0-9]{0,19}(?![\s\S])/;
const NAME = /^[A-Za-z0-9_.-]{1,100}(?![\s\S])/;
// A URL path segment of '.' or '..' is collapsed by URL resolution, so it is never a name.
const pathName = (x) => { text(x, NAME); need(x !== '.' && x !== '..'); };
const BASE64_CHUNK = 0x8000; // Bytes per String.fromCharCode call; never spreads the whole ciphertext.

function entry(slot, value) {
  text(slot, /^[a-z][a-z0-9-]{0,31}(?![\s\S])/);
  exact(value, ENTRY_KEYS);
  text(value.owner, /^profile-[1-9][0-9]{0,29}(?![\s\S])/);
  pathName(value.repository_owner);
  pathName(value.repository_name);
  text(value.repository_id, ID);
  text(value.environment, /^[A-Za-z0-9_-]{1,80}(?![\s\S])/);
  text(value.secret, /^GENI_[A-Z0-9_]{1,80}(?![\s\S])/);
  return Object.freeze({ slot, ...value });
}

function bundle(raw, fixed) {
  need(typeof raw === 'string' && raw.length > 0 && raw.length <= MAX_BUNDLE);
  let value;
  try { value = JSON.parse(raw); } catch { throw new Blocked(); }
  need(JSON.stringify(value) === raw); // Compact canonical JSON; duplicates and whitespace stop.
  exact(value, BUNDLE_KEYS);
  need(value.schema === 1 && value.slot === fixed.slot && value.owner === fixed.owner);
  need(value.repository_id === fixed.repository_id && value.environment === fixed.environment);
  need(value.secret === fixed.secret);
  text(value.connection_id, /^[a-f0-9]{64}(?![\s\S])/);
  for (const key of ['generation', 'revocation_epoch', 'issued_at', 'provider_expires_at', 'expires_at']) integer(value[key]);
  need(value.generation > 0 && value.expires_at > value.issued_at && value.expires_at <= value.provider_expires_at);
  credential(value.access_token);
  credential(value.refresh_token);
}

function base64Key(x) {
  text(x, /^[A-Za-z0-9+/]{43}=(?![\s\S])/);
  const bytes = Uint8Array.from(atob(x), (c) => c.charCodeAt(0));
  need(bytes.length === 32);
  return bytes;
}

// Reads at most MAX_KEY_BODY bytes from the response stream. It stops (and cancels
// the stream) at the first chunk that would cross the cap, never buffering past it.
async function boundedJson(response) {
  const stream = response && response.body;
  need(stream && typeof stream.getReader === 'function');
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      need(value instanceof Uint8Array);
      total += value.length;
      need(total <= MAX_KEY_BODY);
      chunks.push(value);
    }
  } catch (error) {
    try { reader.cancel().catch(() => {}); } catch { /* already closed */ }
    throw error;
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  let value;
  try { value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); } catch { throw new Blocked(); }
  return value;
}

// Chunked so the argument count per call stays bounded; output is identical to btoa of the whole string.
function base64Bytes(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += BASE64_CHUNK) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + BASE64_CHUNK));
  return btoa(binary);
}

// Releases a response body without reading it. Best effort: a missing body or a
// cancel that throws or rejects never changes the result and never surfaces provider text.
function discardBody(response) {
  try {
    const stream = response && response.body;
    if (stream && typeof stream.cancel === 'function') Promise.resolve(stream.cancel()).catch(() => {});
  } catch { /* ignored: the body is never read */ }
}

async function sha256Hex(raw) {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw)));
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('');
}

// `config` comes only from trusted deployment construction, never from a callback,
// query or body. `fetch`, `seal`, `setTimeout` and `clearTimeout` are required
// injections; there is no default and no global fetch or timer.
export function createEnvironmentSecretCustody(config, deps) {
  exact(config, ['schema', 'destinations']);
  need(config.schema === 1 && plain(config.destinations));
  const slots = Object.keys(config.destinations);
  need(slots.length > 0 && slots.length <= 8);
  const registry = new Map(slots.map((slot) => [slot, entry(slot, config.destinations[slot])]));
  const destinations = new Set([...registry.values()].map((e) => [e.repository_id, e.environment, e.secret].join('\0')));
  need(destinations.size === registry.size); // Two slots never share one secret.
  exact(deps, ['fetch', 'seal', 'setTimeout', 'clearTimeout']);
  const { fetch, seal, setTimeout: setTimer, clearTimeout: clearTimer } = deps;
  need([fetch, seal, setTimer, clearTimer].every((f) => typeof f === 'function'));
  const inFlight = new Set();

  // Runs one network step under its own deadline. On timeout it aborts the signal
  // and rejects; the abandoned step is tracked so its slot stays busy until it settles.
  function timed(pending, step) {
    const controller = new AbortController();
    const work = Promise.resolve().then(() => step(controller.signal));
    const record = { settled: false };
    record.done = work.then(() => { record.settled = true; }, () => { record.settled = true; });
    pending.push(record);
    let timer;
    const deadline = new Promise((resolve, reject) => {
      timer = setTimer(() => { controller.abort(); reject(new Blocked()); }, CALL_TIMEOUT_MS);
    });
    return Promise.race([work, deadline]).finally(() => clearTimer(timer));
  }

  async function store(slot, raw) {
    const fixed = registry.get(slot);
    need(fixed);
    bundle(raw, fixed);
    if (inFlight.has(slot)) return { status: 'slot_busy' }; // A concurrent write for one slot stops, never queues.
    const digest = await sha256Hex(raw); // Of the exact bundle that will be sealed, before any call.
    if (inFlight.has(slot)) return { status: 'slot_busy' };
    inFlight.add(slot);
    const pending = [];
    try {
      const base = API + '/repos/' + encodeURIComponent(fixed.repository_owner) + '/' +
        encodeURIComponent(fixed.repository_name) + '/environments/' + encodeURIComponent(fixed.environment) + '/secrets/';
      const headers = { Accept: 'application/vnd.github+json' };
      let key;
      try {
        const body = await timed(pending, async (signal) => {
          const response = await fetch(base + 'public-key', { method: 'GET', headers: { ...headers }, redirect: 'manual', signal });
          if (!(response && response.status === 200 && response.redirected !== true && response.type !== 'opaqueredirect')) {
            discardBody(response); // A rejected public-key response is never read either.
            throw new Blocked();
          }
          return boundedJson(response);
        });
        exact(body, ['key_id', 'key']);
        text(body.key_id, /^[A-Za-z0-9_-]{1,128}(?![\s\S])/);
        key = { key_id: body.key_id, key: base64Key(body.key) };
      } catch { return { status: 'public_key_failed' }; }
      let encrypted;
      try {
        const message = new TextEncoder().encode(raw);
        const cipher = await seal(message, key.key.slice());
        need(cipher instanceof Uint8Array && cipher.length === message.length + SEAL_OVERHEAD);
        encrypted = base64Bytes(cipher);
      } catch { return { status: 'seal_failed' }; }
      try {
        const put = JSON.stringify({ encrypted_value: encrypted, key_id: key.key_id });
        const status = await timed(pending, async (signal) => {
          const response = await fetch(base + encodeURIComponent(fixed.secret), {
            method: 'PUT', headers: { ...headers, 'Content-Type': 'application/json' }, redirect: 'manual', body: put, signal,
          });
          discardBody(response); // Every status: the provider body is never read.
          need(response && (response.status === 201 || response.status === 204) && response.redirected !== true);
          return response.status;
        });
        return { status: status === 201 ? 'stored_created' : 'stored_updated', bundle_sha256: digest };
      } catch { return { status: 'write_state_unknown' }; } // The PUT may have committed: no retry, no fallback.
    } finally {
      // A timed-out call may still be running: keep the slot busy until it settles.
      const open = pending.filter((r) => !r.settled);
      if (open.length === 0) inFlight.delete(slot);
      else Promise.all(open.map((r) => r.done)).then(() => inFlight.delete(slot));
    }
  }

  return Object.freeze({
    async storeBundle(request) {
      let status;
      let digest = null;
      let slot = null;
      try {
        exact(request, ['slot', 'bundleJson']);
        // Snapshot both strings before any await; later caller mutation cannot reach the write.
        slot = request.slot;
        const raw = request.bundleJson;
        need(typeof slot === 'string' && registry.has(slot));
        const outcome = await store(slot, raw);
        status = outcome.status;
        // Only a confirmed store acknowledges the digest; every failure carries null.
        if (status === 'stored_created' || status === 'stored_updated') digest = outcome.bundle_sha256;
      } catch { status = 'input_rejected'; digest = null; slot = registry.has(slot) ? slot : null; }
      return Object.freeze({ status, slot, bundle_sha256: digest, authenticated: false, write_permitted: false });
    },
  });
}
