// Unreleased private v2 approval content join. No protected human action permit.
import{createHash}from'node:crypto';
import{fetchAndAdmitSingleHuman}from'./approval-admission.mjs';
import{verifyImmutablePrewriteEvidence}from'./immutable-prewrite-evidence.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('protected approval service blocked');};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
export async function verifyProtectedApprovalContent(env,binding){
 try{
  const raw=env.FATHER_APPROVAL_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=65536&&hash(raw)===env.FATHER_APPROVAL_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','source','expected_record','plan_fingerprint']);
  need(c.mode==='unreleased_single_human_private_service'&&c.production_enabled===false&&/^[a-f0-9]{64}$/.test(c.plan_fingerprint));
  exact(binding,['owner','connection','plan','payload','artifact','policy','run_id']);
  const p=c.expected_record.pins;
  need(p.owner===binding.owner&&p.connection_id===binding.connection&&p.payload_hash===binding.payload&&p.artifact_hash===binding.artifact&&p.policy_hash===binding.policy&&p.run_id===binding.run_id&&c.plan_fingerprint===binding.plan);
  // Admission validates exact content and provenance of the private Git bytes.
  // Authentication of the capture writer and actual human click remains OPEN.
  const approval=await fetchAndAdmitSingleHuman({source:c.source,credential:env.PRIVATE_GIT_CREDENTIAL,expectedRecord:c.expected_record});
  const evidence=await verifyImmutablePrewriteEvidence(env,binding);
  need(evidence.descriptor.recipient===p.recipient);
  need(p.service_sha===env.FATHER_REVIEWED_SERVICE_SHA&&p.executor_sha===env.FATHER_REVIEWED_EXECUTOR_SHA&&p.workflow_sha===env.FATHER_REVIEWED_WORKFLOW_SHA);
  return{phase:'private_v2_and_prewrite_content_joined',approval,evidence,protected_human_action_verified:false,post_permitted:false,production_enabled:false};
 }catch{throw Error('protected approval service blocked');}
}
