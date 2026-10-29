// Offline only. Local trusted PUBLIC key. No network, owner grant or POST permit.
import { jwtVerify } from 'jose';
const fail = () => { throw new Error('offline workload identity rejected'); };
const check = v => { if (!v) fail(); };
export const PIN_CLAIMS = Object.freeze(['iss', 'aud', 'sub', 'repository', 'repository_id',
  'repository_owner_id', 'workflow_ref', 'workflow_sha', 'sha', 'ref', 'environment',
  'event_name', 'actor_id', 'run_id', 'run_attempt', 'runner_environment']);
// Extras are informational only. Never use these instead of a required pin.
const OPTIONAL_INFORMATIONAL = Object.freeze(['actor','repository_owner','repository_visibility',
  'run_number','workflow','head_ref','base_ref','ref_type','check_run_id']);
const OPTIONAL_WORKFLOW = Object.freeze(['job_workflow_ref','job_workflow_sha']);
export function validateWorkloadHeader(header,pins){
  check(header&&Object.getPrototypeOf(header)===Object.prototype);
  check(Object.keys(header).every(k=>['alg','kid','typ','x5t'].includes(k)));
  check(header.alg==='RS256'&&header.typ==='JWT'&&header.kid===pins.kid);
  if('x5t' in header)check(typeof header.x5t==='string'&&/^[A-Za-z0-9_-]{1,200}$/.test(header.x5t));
}
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
    check(pins&&typeof pins==='object');
    const workflowKeys=OPTIONAL_WORKFLOW.filter(k=>k in pins);
    check(workflowKeys.length===0||workflowKeys.length===2);
    exact(pins, [...PIN_CLAIMS, 'kid',...workflowKeys]);
    for(const k of workflowKeys)check(typeof pins[k]==='string'&&pins[k].length>0&&pins[k].length<=500);
    if(workflowKeys.length)check(/^[a-f0-9]{40}$/.test(pins.job_workflow_sha));
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
    const header = segment(parts[0]);validateWorkloadHeader(header,pins);
    const decoded = segment(parts[1]);
    const required=[...PIN_CLAIMS,'iat','nbf','exp','jti',...workflowKeys];
    check(required.every(k=>Object.hasOwn(decoded,k)));
    check(Object.keys(decoded).every(k=>required.includes(k)||OPTIONAL_INFORMATIONAL.includes(k)||/^repo_property_[A-Za-z0-9_]{1,100}$/.test(k)));
    for(const k of Object.keys(decoded).filter(k=>!required.includes(k)))check(typeof decoded[k]==='string'&&decoded[k].length<=500);
    // A reusable-workflow claim without a reviewed pin is never informational.
    check(OPTIONAL_WORKFLOW.every(k=>!(k in decoded)||workflowKeys.includes(k)));
    check(typeof decoded.jti === 'string' && /^[A-Za-z0-9_-]{1,200}$/.test(decoded.jti));
    for (const k of ['iat', 'nbf', 'exp']) check(Number.isSafeInteger(decoded[k]));
    check(decoded.iat <= now && decoded.nbf <= now && decoded.exp > now &&
      decoded.exp > decoded.iat && decoded.nbf >= decoded.iat && decoded.nbf < decoded.exp &&
      now - decoded.iat <= 300 && decoded.exp - decoded.iat <= 600);
    const verified = await jwtVerify(token, publicKey, { algorithms: ['RS256'],
      issuer: pins.iss, audience: pins.aud, typ: 'JWT', currentDate: new Date(now * 1000),
      clockTolerance: 0 });
    check([...PIN_CLAIMS,...workflowKeys].every(k => verified.payload[k] === pins[k]));
    return { mode: 'offline_workload_identity_only', workload_verified: true,
      owner_approval_verified: false, replay_protection_provided: false,
      production_enabled: false };
  } catch { fail(); }
}
