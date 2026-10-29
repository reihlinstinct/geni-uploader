// Dormant authoritative storage component. No public route or authentication grant.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('sqlite issuance reservation blocked');};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const canonical=x=>x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
function checked(p){
 exact(p,['binding','public_run_id','namespace_id','issuer_repository_id','issuer_run_id','issuer_sha','issuer_workflow_sha']);
 exact(p.binding,['owner','connection','plan','payload','artifact','policy']);const b=p.binding;
 need(typeof b.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(b.owner)&&typeof b.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(b.connection));
 for(const k of ['plan','payload','artifact','policy'])need(typeof b[k]==='string'&&/^[a-f0-9]{64}$/.test(b[k]));
 for(const k of ['public_run_id','issuer_repository_id','issuer_run_id'])need(typeof p[k]==='string'&&/^[1-9][0-9]{0,19}$/.test(p[k]));
 need(typeof p.namespace_id==='string'&&/^[a-f0-9]{32}$/.test(p.namespace_id));
 for(const k of ['issuer_sha','issuer_workflow_sha'])need(typeof p[k]==='string'&&/^[a-f0-9]{40}$/.test(p[k]));
 return structuredClone(p);
}
const slot='permanent-issuance-attempt';
/** Only a future authenticated deployment-owned wrapper may supply storage/pins.
 * This function does not prove that provenance. The canonical owner DO must
 * check actual namespace and issuer JWT/approval before calling it.
 */
async function reserve(storage,pins){
 const fixed=checked(pins),receipt=hash(canonical(fixed));need(storage&&typeof storage.transaction==='function');
 return storage.transaction(async tx=>{
  need(await tx.get(slot)===undefined);
  const record={schema_version:1,phase:'permanent_issuance_attempt_reserved',pins:fixed,receipt_sha256:receipt,production_enabled:false,post_permitted:false};
  await tx.put(slot,record);
  return Object.freeze({phase:record.phase,receipt_sha256:receipt,production_enabled:false,post_permitted:false,retry_allowed:false});
 });
}
/** Read-only inspection, never a reset/resume/second-issuance operation. */
async function inspect(storage,pins){
 const fixed=checked(pins);need(storage&&typeof storage.transaction==='function');
 return storage.transaction(async tx=>{
  const r=await tx.get(slot);need(r);exact(r,['schema_version','phase','pins','receipt_sha256','production_enabled','post_permitted']);
  need(r.schema_version===1&&r.phase==='permanent_issuance_attempt_reserved'&&r.production_enabled===false&&r.post_permitted===false&&canonical(r.pins)===canonical(fixed)&&r.receipt_sha256===hash(canonical(fixed)));
  return Object.freeze({phase:'permanent_issuance_attempt_inspected_read_only',receipt_sha256:r.receipt_sha256,production_enabled:false,post_permitted:false,retry_allowed:false});
 });
}

// Await inside the boundary: synchronous and rejected transaction errors must
// never carry storage values, causes or provider diagnostics to a caller.
export async function reserveSqliteIssuance(storage,pins){
 try{return await reserve(storage,pins);}catch{throw Error('sqlite issuance reservation blocked');}
}
export async function inspectSqliteIssuance(storage,pins){
 try{return await inspect(storage,pins);}catch{throw Error('sqlite issuance reservation blocked');}
}
