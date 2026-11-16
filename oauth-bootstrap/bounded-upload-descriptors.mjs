// Called only AFTER fixed-issuer workload verification by the local service.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('upload descriptor admission blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
/** Descriptor parameters are untrusted data, never owner permission. Fixed source
 * identity/path, operation and recipient come from reviewed deployment policy.
 * No URL, credential or caller-supplied repository is accepted by this interface.
 */
export function bindUploadedDescriptors(env,descriptors,binding){
 try{
  const raw=env.FATHER_UPLOAD_POLICY_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_UPLOAD_POLICY_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','approval','evidence','binding','recipient','credential_sha256']);
  need(c.mode==='unreleased_fixed_upload_policy'&&c.production_enabled===false);
  exact(binding,['owner','connection','plan','payload','artifact','policy','run_id']);exact(c.binding,Object.keys(binding));need(Object.keys(binding).every(k=>c.binding[k]===binding[k]));
  for(const s of[c.approval,c.evidence]){
   exact(s,['repository_id','owner','repo','path']);need(typeof s.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(s.repository_id));
   for(const k of['owner','repo','path'])need(typeof s[k]==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(s[k])&&!['.','..'].includes(s[k]));
  }
  need(c.approval.repository_id===c.evidence.repository_id&&c.approval.owner===c.evidence.owner&&c.approval.repo===c.evidence.repo&&c.approval.path!==c.evidence.path);hex(c.recipient,64);hex(c.credential_sha256,64);
  need(typeof env.GENI_SECONDARY_ACCESS_TOKEN==='string'&&hash(env.GENI_SECONDARY_ACCESS_TOKEN)===c.credential_sha256);
  exact(descriptors,['approval','prewrite']);const a=descriptors.approval,d=descriptors.prewrite;
  exact(a,['commit','blob_sha','content_sha256']);hex(a.commit,40);hex(a.blob_sha,40);hex(a.content_sha256,64);
  exact(d,['schema_version','mode','production_enabled','schema','stage','sha256','byte_length','recipient','operation_binding','run_id','run_attempt','blob_id','commit']);
  need(d.schema_version===1&&d.mode==='offline_ciphertext_descriptor'&&d.production_enabled===false&&d.schema==='geni-evidence-ciphertext-v1'&&d.stage==='pre_write'&&d.run_attempt===1&&d.run_id===binding.run_id&&d.operation_binding===binding.plan&&d.recipient===c.recipient);
  hex(d.sha256,64);hex(d.blob_id,40);hex(d.commit,40);need(Number.isSafeInteger(d.byte_length)&&d.byte_length>22&&d.byte_length<=1048576);
  // Snapshot before any await. No submitted reference may change readback pins.
  const approval={mode:'unreleased_single_human_private_service',production_enabled:false,source:{...c.approval,...structuredClone(a)},plan_fingerprint:binding.plan};
  const evidence={mode:'unreleased_private_prewrite_admission',production_enabled:false,source:{...c.evidence,commit:d.commit},descriptor:structuredClone(d),credential_sha256:c.credential_sha256,binding:structuredClone(binding)};
  const out={...env};out.FATHER_APPROVAL_RELEASE_JSON=JSON.stringify(approval);out.FATHER_APPROVAL_RELEASE_SHA256=hash(out.FATHER_APPROVAL_RELEASE_JSON);out.FATHER_PREWRITE_RELEASE_JSON=JSON.stringify(evidence);out.FATHER_PREWRITE_RELEASE_SHA256=hash(out.FATHER_PREWRITE_RELEASE_JSON);
  return out;
 }catch{throw Error('upload descriptor admission blocked');}
}
