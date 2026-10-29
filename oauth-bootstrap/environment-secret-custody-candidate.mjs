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

class Blocked extends Error {}
const need = (x) => { if (!x) throw new Blocked(); };
const plain = (x) => x !== null && typeof x === 'object' && Object.getPrototypeOf(x) === Object.prototype;
const exact = (x, keys) => need(plain(x) && Object.keys(x).sort().join(',') === [...keys].sort().join(','));
const text = (x, re) => need(typeof x === 'string' && re.test(x));
const integer = (x) => need(Number.isSafeInteger(x) && x >= 0 && x < 2 ** 40);
const credential = (x) => need(typeof x === 'string' && x.length > 0 && x.length <= 16384 && !/[\s\x00-\x1f\x7f]/.test(x));
const ID = /^[1-9][0-9]{0,19}(?![\s\S])/;
const NAME = /^[A-Za-z0-9_.-]{1,100}(?![\s\S])/;

function entry(slot, value) {
  text(slot, /^[a-z][a-z0-9-]{0,31}(?![\s\S])/);
  exact(value, ENTRY_KEYS);
  text(value.owner, /^profile-[1-9][0-9]{0,29}(?![\s\S])/);
  text(value.repository_owner, NAME);
  text(value.repository_name, NAME);
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

async function boundedJson(response) {
  need(response && typeof response.text === 'function');
  const raw = await response.text();
  need(typeof raw === 'string' && raw.length <= MAX_KEY_BODY);
  let value;
  try { value = JSON.parse(raw); } catch { throw new Blocked(); }
  return value;
}

// `config` comes only from trusted deployment construction, never from a callback,
// query or body. `fetch` and `seal` are required injections; there is no default.
export function createEnvironmentSecretCustody(config, deps) {
  exact(config, ['schema', 'destinations']);
  need(config.schema === 1 && plain(config.destinations));
  const slots = Object.keys(config.destinations);
  need(slots.length > 0 && slots.length <= 8);
  const registry = new Map(slots.map((slot) => [slot, entry(slot, config.destinations[slot])]));
  const destinations = new Set([...registry.values()].map((e) => [e.repository_id, e.environment, e.secret].join('\0')));
  need(destinations.size === registry.size); // Two slots never share one secret.
  exact(deps, ['fetch', 'seal']);
  const { fetch, seal } = deps;
  need(typeof fetch === 'function' && typeof seal === 'function');
  const inFlight = new Set();

  async function store(slot, raw) {
    const fixed = registry.get(slot);
    need(fixed);
    bundle(raw, fixed);
    if (inFlight.has(slot)) return 'slot_busy'; // A concurrent write for one slot stops, never queues.
    inFlight.add(slot);
    try {
      const base = API + '/repos/' + encodeURIComponent(fixed.repository_owner) + '/' +
        encodeURIComponent(fixed.repository_name) + '/environments/' + encodeURIComponent(fixed.environment) + '/secrets/';
      const headers = { Accept: 'application/vnd.github+json' };
      let key;
      try {
        const response = await fetch(base + 'public-key', { method: 'GET', headers: { ...headers }, redirect: 'manual' });
        need(response && response.status === 200 && response.redirected !== true && response.type !== 'opaqueredirect');
        const body = await boundedJson(response);
        exact(body, ['key_id', 'key']);
        text(body.key_id, /^[A-Za-z0-9_-]{1,128}(?![\s\S])/);
        key = { key_id: body.key_id, key: base64Key(body.key) };
      } catch { return 'public_key_failed'; }
      let encrypted;
      try {
        const message = new TextEncoder().encode(raw);
        const cipher = await seal(message, key.key.slice());
        need(cipher instanceof Uint8Array && cipher.length === message.length + SEAL_OVERHEAD);
        encrypted = btoa(String.fromCharCode(...cipher));
      } catch { return 'seal_failed'; }
      try {
        const response = await fetch(base + encodeURIComponent(fixed.secret), {
          method: 'PUT', headers: { ...headers, 'Content-Type': 'application/json' }, redirect: 'manual',
          body: JSON.stringify({ encrypted_value: encrypted, key_id: key.key_id }),
        });
        need(response && (response.status === 201 || response.status === 204) && response.redirected !== true);
        return response.status === 201 ? 'stored_created' : 'stored_updated';
      } catch { return 'write_state_unknown'; } // The PUT may have committed: no retry, no fallback.
    } finally { inFlight.delete(slot); }
  }

  return Object.freeze({
    async storeBundle(request) {
      let status;
      let slot = null;
      try {
        exact(request, ['slot', 'bundleJson']);
        // Snapshot both strings before any await; later caller mutation cannot reach the write.
        slot = request.slot;
        const raw = request.bundleJson;
        need(typeof slot === 'string' && registry.has(slot));
        status = await store(slot, raw);
      } catch { status = 'input_rejected'; slot = registry.has(slot) ? slot : null; }
      return Object.freeze({ status, slot, authenticated: false, write_permitted: false });
    },
  });
}
