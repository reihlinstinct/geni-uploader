// Protected Node job only. Never logs raw result or sends a vendor request.
import{createHash}from'node:crypto';
import{persistProtectedJobEvidence}from'./protected-job-evidence.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('post-write handoff blocked');};
/** Called with the authenticated service response in memory. Fixed deployment
 * storage pins must name a NEW path/parent commit and the correct stage.
 * A private response is not persistence. Failure never triggers another create.
 */
export async function persistPostWriteHandoff(env,result,onProgress){
 try{
  need(result&&['consumed_readback_consistent_evidence_pending','consumed_uncertain'].includes(result.phase)&&result.retry_allowed===false&&result.post_write_evidence_durable===false&&result.production_enabled===false);
  const e=result.private_evidence;need(e&&e.schema_version===1&&e.mode==='private_post_write_evidence'&&e.binding&&e.binding.plan);
  const raw=env.FATHER_EVIDENCE_RELEASE_JSON;need(typeof raw==='string'&&hash(raw)===env.FATHER_EVIDENCE_RELEASE_SHA256);const c=JSON.parse(raw);need(c.storage?.stage==='readback'&&c.storage.operation_binding===e.binding.plan&&c.storage.run_id===env.GITHUB_RUN_ID);
  const bytes=Buffer.from(JSON.stringify({result_phase:result.phase,created_id:result.created_id,evidence:e}));need(bytes.length>0&&bytes.length<=1048000);
  const persisted=await persistProtectedJobEvidence(env,bytes,onProgress);
  return{phase:'post_write_ciphertext_persisted_completion_pending',descriptor:persisted.descriptor,created_id:result.created_id,post_write_evidence_durable:true,intent_verified:false,retry_allowed:false,production_enabled:false};
 }catch{throw Error('post-write handoff blocked; consumed intent must not be replayed');}
}
