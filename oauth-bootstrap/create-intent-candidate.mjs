// OFFLINE candidate only. Not a DurableObject export or execution authorization.
// No route/binding/deploy, authentication, encryption, transport or reset API.
const deny = () => { throw new Error('offline intent candidate blocked'); };
const check = v => { if (!v) deny(); };
const hash = v => check(typeof v === 'string' && /^[a-f0-9]{64}$/.test(v));
const id = v => check(typeof v === 'string' && /^profile-[1-9][0-9]{0,29}$/.test(v));
const exact = (v, keys) => check(v !== null && typeof v === 'object' &&
  !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype &&
  JSON.stringify(Object.keys(v).sort()) === JSON.stringify([...keys].sort()));
const BIND = ['owner', 'connection', 'plan', 'payload', 'artifact', 'policy'];
function binding(v) {
  exact(v, BIND); id(v.owner);
  check(typeof v.connection === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(v.connection));
  for (const k of ['plan', 'payload', 'artifact', 'policy']) hash(v[k]);
}
function equal(a, b) { return BIND.every(k => a[k] === b[k]); }
function validate(s, owner) {
  exact(s, ['binding', 'version', 'phase', 'created_id', 'evidence', 'production_enabled']);
  binding(s.binding); check(s.binding.owner === owner && s.production_enabled === false);
  check(Number.isInteger(s.version) && s.version >= 1 && s.version <= 4);
  check(Array.isArray(s.evidence) && s.evidence.length === s.version - 1);
  s.evidence.forEach(hash); check(new Set(s.evidence).size === s.evidence.length);
  if (s.created_id !== null) { id(s.created_id); check(s.created_id !== owner); }
  const shapes = {
    consumed: s.version === 1 && s.created_id === null,
    acknowledged: s.version === 2 && s.created_id !== null,
    uncertain: (s.version === 2 && s.created_id === null) ||
      (s.version === 3 && s.created_id !== null),
    verified: [3, 4].includes(s.version) && s.created_id !== null,
  };
  check(typeof s.phase === 'string' && Object.hasOwn(shapes, s.phase) && shapes[s.phase]);
}
export class OfflineCreateIntentCandidate {
  constructor(storage, owner) {
    id(owner); check(storage && typeof storage.transaction === 'function');
    // Future DO routing must authenticate and bind this owner to ONE namespace.
    // Caller-selected/new namespaces evade exclusion. This class cannot fix that.
    this.storage = storage; this.owner = owner;
  }
  async consume(input, expectedVersion) {
    const b = structuredClone(input); binding(b);
    check(b.owner === this.owner && expectedVersion === 0);
    return this.storage.transaction(async tx => {
      const prior = await tx.get('intent'); check(prior === undefined);
      check(await tx.get('event:1') === undefined);
      const s = { binding: b, version: 1, phase: 'consumed', created_id: null,
        evidence: [], production_enabled: false };
      validate(s, this.owner);
      await tx.put('intent', s);
      await tx.put('event:1', s);
      return structuredClone(s); // NEVER an execution permit.
    });
  }
  async advance(input, expectedVersion, event, evidence, createdId = null) {
    const b = structuredClone(input); binding(b); hash(evidence);
    check(b.owner === this.owner && Number.isInteger(expectedVersion));
    check(typeof event === 'string');
    return this.storage.transaction(async tx => {
      const prior = await tx.get('intent'); validate(prior, this.owner);
      check(equal(prior.binding, b) && prior.version === expectedVersion);
      check(!prior.evidence.includes(evidence));
      const allowed = { consumed: ['acknowledge', 'uncertain'],
        acknowledged: ['verify', 'uncertain'], uncertain: ['reconcile_verified'], verified: [] };
      check(allowed[prior.phase].includes(event));
      const s = structuredClone(prior);
      if (['acknowledge', 'reconcile_verified'].includes(event)) {
        id(createdId); check(s.created_id === null || s.created_id === createdId);
        s.created_id = createdId;
      } else check(createdId === null);
      s.phase = { acknowledge: 'acknowledged', uncertain: 'uncertain',
        verify: 'verified', reconcile_verified: 'verified' }[event];
      s.version++; s.evidence.push(evidence); validate(s, this.owner);
      check(await tx.get(`event:${s.version}`) === undefined);
      await tx.put('intent', s); await tx.put(`event:${s.version}`, s);
      return structuredClone(s);
    });
  }
}
