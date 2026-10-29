// Synthetic fixed storage policy and immutable descriptors, no live data.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
export function uploadFixture(env){
 const a=JSON.parse(env.FATHER_APPROVAL_RELEASE_JSON),e=JSON.parse(env.FATHER_PREWRITE_RELEASE_JSON);
 const {commit,blob_sha,content_sha256,...fixedApproval}=a.source;
 const {commit:unused,...fixedEvidence}=e.source;
 const c={mode:'unreleased_fixed_upload_policy',production_enabled:false,approval:fixedApproval,evidence:fixedEvidence,binding:e.binding,recipient:e.descriptor.recipient,credential_sha256:e.credential_sha256};
 const raw=JSON.stringify(c);env.FATHER_UPLOAD_POLICY_JSON=raw;env.FATHER_UPLOAD_POLICY_SHA256=hash(raw);
 // No post-upload commit/blob fields need deployment provisioning.
 delete env.FATHER_APPROVAL_RELEASE_JSON;delete env.FATHER_APPROVAL_RELEASE_SHA256;delete env.FATHER_PREWRITE_RELEASE_JSON;delete env.FATHER_PREWRITE_RELEASE_SHA256;
 return{approval:{commit,blob_sha,content_sha256},prewrite:e.descriptor};
}
