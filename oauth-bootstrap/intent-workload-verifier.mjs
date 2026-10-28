// Offline only. Local trusted PUBLIC key. No network, owner grant or POST permit.
import { jwtVerify } from 'jose';
const fail = () => { throw new Error('offline workload identity rejected'); };
const check = v => { if (!v) fail(); };
export const PIN_CLAIMS = Object.freeze(['iss', 'aud', 'sub', 'repository', 'repository_id',
  'repository_owner_id', 'workflow_ref', 'workflow_sha', 'sha', 'ref', 'environment',
  'event_name', 'actor_id', 'run_id', 'run_attempt', 'runner_environment']);
function exact(value, keys) {
  check(value && typeof value === 'object' && !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort()));
}
function segment(text) {
  check(typeof text === 'string' && /^[A-Za-z0-9_-]+$/.test(text));
  const bytes = Buffer.from(text, 'base64url');
  check(bytes.toString('base64url') === text);
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const value = JSON.parse(raw);
  // Flat claims only. JSON.parse loses duplicate keys, so require canonical
  // serialization modulo whitespace via a strict flat-object tokenizer.
  check(value && typeof value === 'object' && !Array.isArray(value));
  const pairs = raw.match(/"(?:[^"\\]|\\.)*"\s*:/g) || [];
  const names = pairs.map(p => JSON.parse(p.slice(0, p.lastIndexOf(':')).trim()));
  check(new Set(names).size === names.length && names.length === Object.keys(value).length);
  for (const v of Object.values(value)) check(typeof v === 'string' || typeof v === 'number');
  return value;
}
export async function verifyOfflineWorkload(token, publicKey, pins, now) {
  try {
    exact(pins, [...PIN_CLAIMS, 'kid']);
    check(PIN_CLAIMS.every(k => typeof pins[k] === 'string' && pins[k].length > 0 && pins[k].length <= 500));
    check(pins.iss === 'https://token.actions.githubusercontent.com' && pins.event_name === 'workflow_dispatch' &&
      pins.run_attempt === '1' && pins.runner_environment === 'github-hosted' && pins.ref === 'refs/heads/master');
    for (const k of ['repository_id', 'repository_owner_id', 'actor_id', 'run_id'])
      check(/^[1-9][0-9]{0,29}$/.test(pins[k]));
    for (const k of ['workflow_sha', 'sha']) check(/^[a-f0-9]{40}$/.test(pins[k]));
    check(typeof pins.kid === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(pins.kid));
    check(Number.isSafeInteger(now) && now > 0);
    check(publicKey?.type === 'public' && typeof token === 'string' && token.length <= 16384);
    const parts = token.split('.'); check(parts.length === 3);
    check(/^[A-Za-z0-9_-]+$/.test(parts[2]) &&
      Buffer.from(parts[2], 'base64url').toString('base64url') === parts[2]);
    const header = segment(parts[0]); exact(header, ['alg', 'kid', 'typ']);
    check(header.alg === 'RS256' && header.typ === 'JWT' && header.kid === pins.kid);
    const decoded = segment(parts[1]); exact(decoded, [...PIN_CLAIMS, 'iat', 'nbf', 'exp', 'jti']);
    check(typeof decoded.jti === 'string' && /^[A-Za-z0-9_-]{1,200}$/.test(decoded.jti));
    for (const k of ['iat', 'nbf', 'exp']) check(Number.isSafeInteger(decoded[k]));
    check(decoded.iat <= now && decoded.nbf <= now && decoded.exp > now &&
      decoded.exp > decoded.iat && decoded.nbf >= decoded.iat && decoded.nbf < decoded.exp &&
      now - decoded.iat <= 300 && decoded.exp - decoded.iat <= 600);
    const verified = await jwtVerify(token, publicKey, { algorithms: ['RS256'],
      issuer: pins.iss, audience: pins.aud, typ: 'JWT', currentDate: new Date(now * 1000),
      clockTolerance: 0 });
    check(PIN_CLAIMS.every(k => verified.payload[k] === pins[k]));
    return { mode: 'offline_workload_identity_only', workload_verified: true,
      owner_approval_verified: false, replay_protection_provided: false,
      production_enabled: false };
  } catch { fail(); }
}
