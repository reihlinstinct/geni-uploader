// Dormant v2 storage primitive, not authenticated identity or namespace proof.
const need=x=>{if(!x)throw Error('worker issuance reservation blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
const canonical=x=>x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=async x=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(x))),b=>b.toString(16).padStart(2,'0')).join('');
function checked(p){
 exact(p,['binding','public_run_id','namespace_id','issuer']);exact(p.binding,['owner','connection','plan','payload','artifact','policy']);
 const b=p.binding;need(typeof b.owner==='string'&&/^profile-[1-9][0-9]{0,29}(?![\s\S])/.test(b.owner)&&typeof b.connection==='string'&&/^[A-Za-z0-9_-]{1,100}(?![\s\S])/.test(b.connection));
 for(const k of ['plan','payload','artifact','policy'])hex(b[k],64);
 need(typeof p.public_run_id==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(p.public_run_id));hex(p.namespace_id,32);
 exact(p.issuer,['script','version_id','bundle_sha256','installation_audit_sha256']);
 need(typeof p.issuer.script==='string'&&/^[A-Za-z][A-Za-z0-9_-]{0,62}(?![\s\S])/.test(p.issuer.script));
 need(typeof p.issuer.version_id==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?![\s\S])/.test(p.issuer.version_id));
 hex(p.issuer.bundle_sha256,64);hex(p.issuer.installation_audit_sha256,64);return structuredClone(p);
}
const slot='permanent-issuance-attempt';
export async function reserveWorkerIssuanceV2(storage,pins){try{
 const fixed=checked(pins),receipt=await hash(canonical(fixed));need(storage&&typeof storage.transaction==='function');
 return await storage.transaction(async tx=>{need(await tx.get(slot)===undefined);await tx.put(slot,{schema_version:2,phase:'permanent_issuance_attempt_reserved',pins:fixed,receipt_sha256:receipt,production_enabled:false,post_permitted:false});return Object.freeze({schema_version:2,phase:'permanent_issuance_attempt_reserved',receipt_sha256:receipt,production_enabled:false,post_permitted:false,retry_allowed:false});});
}catch{throw Error('worker issuance reservation blocked');}}
export async function inspectWorkerIssuanceV2(storage,pins){try{
 const fixed=checked(pins),receipt=await hash(canonical(fixed));need(storage&&typeof storage.transaction==='function');
 return await storage.transaction(async tx=>{const r=await tx.get(slot);exact(r,['schema_version','phase','pins','receipt_sha256','production_enabled','post_permitted']);need(r.schema_version===2&&r.phase==='permanent_issuance_attempt_reserved'&&r.production_enabled===false&&r.post_permitted===false&&canonical(r.pins)===canonical(fixed)&&r.receipt_sha256===receipt);return Object.freeze({schema_version:2,phase:'permanent_issuance_attempt_inspected_read_only',receipt_sha256:receipt,production_enabled:false,post_permitted:false,retry_allowed:false});});
}catch{throw Error('worker issuance reservation blocked');}}
