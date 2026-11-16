// Protected Node job only. Never logs raw result or sends a vendor request.
import{createHash}from'node:crypto';
import{persistProtectedJobEvidence}from'./protected-job-evidence.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('post-write handoff blocked');};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const fields=['owner','connection','plan','payload','artifact','policy'];
function binding(x){
 exact(x,fields);need(typeof x.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(x.owner)&&typeof x.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(x.connection));
 for(const k of ['plan','payload','artifact','policy'])need(typeof x[k]==='string'&&/^[a-f0-9]{64}$/.test(x[k]));
}
export function validatePostWriteHandoff(env,result){
 exact(result,['phase','created_id','private_evidence','retry_allowed','post_write_evidence_durable','production_enabled']);
 need(['consumed_readback_consistent_evidence_pending','consumed_uncertain'].includes(result.phase)&&result.retry_allowed===false&&result.post_write_evidence_durable===false&&result.production_enabled===false);
 const e=result.private_evidence;exact(e,['schema_version','mode','binding','acknowledgment','profile','family','union']);need(e.schema_version===1&&e.mode==='private_post_write_evidence');binding(e.binding);
 const fixed=env.FATHER_POSTWRITE_BINDING_JSON;need(typeof fixed==='string'&&fixed.length<=4096&&hash(fixed)===env.FATHER_POSTWRITE_BINDING_SHA256);
 const expected=JSON.parse(fixed);binding(expected);need(JSON.stringify(expected)===fixed&&fields.every(k=>e.binding[k]===expected[k]));
 const id=result.created_id;need(id===null||(typeof id==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(id)&&id!==expected.owner));
 for(const k of ['acknowledgment','profile','family','union'])need(e[k]===null||(Object.getPrototypeOf(e[k])===Object.prototype));
 if(id!==null)need(e.acknowledgment?.id===id);
 if(result.phase==='consumed_readback_consistent_evidence_pending')need(id!==null&&e.profile?.id===id&&e.family?.focus?.id===expected.owner&&typeof e.union?.id==='string'&&/^union-[1-9][0-9]{0,29}$/.test(e.union.id));
 return e;
}
/** Called with the authenticated service response in memory. Fixed deployment
 * storage pins must name a NEW path/parent commit and the correct stage.
 * A private response is not persistence. Failure never triggers another create.
 */
export async function persistPostWriteHandoff(env,result,onProgress){
 try{
  const e=validatePostWriteHandoff(env,result);
  const raw=env.FATHER_EVIDENCE_RELEASE_JSON;need(typeof raw==='string'&&hash(raw)===env.FATHER_EVIDENCE_RELEASE_SHA256);const c=JSON.parse(raw);need(c.storage?.stage==='readback'&&c.storage.operation_binding===e.binding.plan&&c.storage.run_id===env.GITHUB_RUN_ID);
  const bytes=Buffer.from(JSON.stringify({result_phase:result.phase,created_id:result.created_id,evidence:e}));need(bytes.length>0&&bytes.length<=1048000);
  const persisted=await persistProtectedJobEvidence(env,bytes,onProgress);
  return{phase:'post_write_ciphertext_persisted_completion_pending',descriptor:persisted.descriptor,created_id:result.created_id,post_write_evidence_durable:true,intent_verified:false,retry_allowed:false,production_enabled:false};
 }catch{throw Error('post-write handoff blocked; consumed intent must not be replayed');}
}
