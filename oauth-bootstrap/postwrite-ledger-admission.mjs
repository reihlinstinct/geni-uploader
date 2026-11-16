// Dormant post-write ciphertext receipt admission. Never declares VERIFIED.
import{createHash}from'node:crypto';
import{verifyImmutablePostwriteEvidence}from'./immutable-prewrite-evidence.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('postwrite receipt blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
/** Called only after workload auth. Caller controls immutable upload identifiers,
 * never destination, recipient, operation, credential or binding policy.
 */
export async function verifyUploadedPostwrite(env,binding,descriptor){
 const raw=env.FATHER_POSTWRITE_POLICY_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_POSTWRITE_POLICY_SHA256);
 const p=JSON.parse(raw);need(JSON.stringify(p)===raw);exact(p,['mode','production_enabled','source','binding','recipient','credential_sha256']);
 need(p.mode==='unreleased_fixed_postwrite_policy'&&p.production_enabled===false);exact(binding,['owner','connection','plan','payload','artifact','policy','run_id']);exact(p.binding,Object.keys(binding));need(Object.keys(binding).every(k=>binding[k]===p.binding[k]));
 need(descriptor&&descriptor.recipient===p.recipient);
 exact(p.source,['repository_id','owner','repo','path']);
 const c={mode:'unreleased_private_postwrite_admission',production_enabled:false,source:{...p.source,commit:descriptor.commit},descriptor:structuredClone(descriptor),credential_sha256:p.credential_sha256,binding:structuredClone(binding)},r=JSON.stringify(c);
 const verified=await verifyImmutablePostwriteEvidence({...env,FATHER_POSTWRITE_RELEASE_JSON:r,FATHER_POSTWRITE_RELEASE_SHA256:hash(r)},binding);
 return{...verified,source:structuredClone(c.source)};
}
