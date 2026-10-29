// Dormant protected Node job orchestration. No installed workflow or CLI entry.
import{createHash}from'node:crypto';
import{persistPrivateApprovalRecord}from'./private-approval-writer.mjs';
import{persistProtectedJobEvidence}from'./protected-job-evidence.mjs';
import{persistPostWriteHandoff}from'./post-write-job-handoff.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('protected father runner blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const bindingFields=['owner','connection','plan','payload','artifact','policy'];
function config(env){
 const raw=env.FATHER_RUNNER_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=65536&&hash(raw)===env.FATHER_RUNNER_RELEASE_SHA256);
 const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','service_origin','binding','prewrite_sha256','prewrite_storage','postwrite_storage']);
 need(c.mode==='unreleased_protected_father_runner'&&c.production_enabled===false);
 const u=new URL(c.service_origin);need(u.protocol==='https:'&&u.origin===c.service_origin&&!u.username&&!u.password&&!u.port);
 need(typeof c.binding?.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(c.binding.owner)&&typeof c.binding.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(c.binding.connection));
 for(const k of ['plan','payload','artifact','policy'])need(typeof c.binding[k]==='string'&&/^[a-f0-9]{64}$/.test(c.binding[k]));
 exact(c.binding,[...bindingFields,'run_id']);need(c.binding.run_id===env.GITHUB_RUN_ID&&env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_REF==='refs/heads/master'&&env.GITHUB_EVENT_NAME==='workflow_dispatch');
 need(typeof env.FATHER_POSTWRITE_BINDING_JSON==='string'&&hash(env.FATHER_POSTWRITE_BINDING_JSON)===env.FATHER_POSTWRITE_BINDING_SHA256);const fixed=JSON.parse(env.FATHER_POSTWRITE_BINDING_JSON);need(bindingFields.every(k=>c.binding[k]===fixed[k]));
 for(const k of ['prewrite_sha256'])need(typeof c[k]==='string'&&/^[a-f0-9]{64}$/.test(c[k]));
 for(const [k,stage]of [['prewrite_storage','pre_write'],['postwrite_storage','readback']]){const p=c[k];need(p&&p.storage?.stage===stage&&p.storage.operation_binding===c.binding.plan&&p.storage.run_id===c.binding.run_id);}
 const pre=c.prewrite_storage.storage,post=c.postwrite_storage.storage;
 const approvalRaw=env.FATHER_APPROVAL_STORAGE_JSON;need(typeof approvalRaw==='string'&&hash(approvalRaw)===env.FATHER_APPROVAL_STORAGE_SHA256);const a=JSON.parse(approvalRaw);
 need(a.plan_fingerprint===c.binding.plan&&a.run_id===c.binding.run_id);
 for(const k of ['repository_id','owner','repo','branch'])need(pre[k]===post[k]&&pre[k]===a[k]);
 need(c.prewrite_storage.recipient===c.postwrite_storage.recipient&&pre.recipient===post.recipient&&pre.existing_total_bytes===0&&post.existing_total_bytes===0);
 need(new Set([pre.path,post.path,a.path]).size===3);
 return c;
}
function storageEnv(env,release,parent,total=0){
 const p=structuredClone(release);if(parent!==undefined)p.storage.parent_commit=parent;p.storage.existing_total_bytes=total;
 const raw=JSON.stringify(p);return{...env,FATHER_EVIDENCE_RELEASE_JSON:raw,FATHER_EVIDENCE_RELEASE_SHA256:hash(raw)};
}
async function service(env,c,route,body){
 need(typeof env.FATHER_WORKLOAD_TOKEN==='string'&&env.FATHER_WORKLOAD_TOKEN.length>0&&env.FATHER_WORKLOAD_TOKEN.length<=16384);
 const ctl=new AbortController();let timer,active=true;
 try{
  const work=async()=>{const r=await fetch(c.service_origin+route,{method:'POST',redirect:'manual',signal:ctl.signal,headers:{'content-type':'application/json'},body:JSON.stringify({workload_token:env.FATHER_WORKLOAD_TOKEN,plan_hash:c.binding.plan,...body})});need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const reader=r.body.getReader(),chunks=[];let n=0;try{for(;;){const x=await reader.read();if(x.done)break;n+=x.value.length;need(active&&n<=1048576);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const k=JSON.parse(t),set=stack.at(-1);need(set instanceof Set&&!set.has(k));set.add(k);}need(stack.length<=20);}return JSON.parse(text);};
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('service response uncertain'));},60000);});return await Promise.race([work(),deadline]);
 }finally{active=false;ctl.abort();clearTimeout(timer);}
}
/** The caller supplies private captured approval and prewrite bytes in memory.
 * Both are pinned before any write. No arbitrary callback/destination/dependency
 * injection. Partial receipts go only to the caller's private journal callback.
 * No automatic retry at any boundary, including service response loss.
 */
export async function runProtectedFatherJob(env,approvalBytes,prewriteBytes,onProgress){
 let executeAttempted=false;
 try{
  const c=config(env);need(typeof onProgress==='function'&&approvalBytes instanceof Uint8Array&&prewriteBytes instanceof Uint8Array&&hash(prewriteBytes)===c.prewrite_sha256);
  const approval=await persistPrivateApprovalRecord(env,approvalBytes,x=>onProgress({stage:'approval',receipt:x}));
  const preEnv=storageEnv(env,c.prewrite_storage,approval.source.commit);
  const pre=await persistProtectedJobEvidence(preEnv,prewriteBytes,x=>onProgress({stage:'pre_write',receipt:x}));
  // The only service request that can reach the dormant create route.
  await onProgress({stage:'execute_attempt',receipt:{execute_attempted:true}});
  executeAttempted=true;
  const result=await service(env,c,'/execute',{uploads:{approval:{commit:approval.source.commit,blob_sha:approval.source.blob_sha,content_sha256:approval.source.content_sha256},prewrite:pre.descriptor}});
  const postEnv=storageEnv(env,c.postwrite_storage,pre.descriptor.commit,pre.descriptor.byte_length);
  const persisted=await persistPostWriteHandoff(postEnv,result,x=>onProgress({stage:'readback',receipt:x}));
  await onProgress({stage:'completion_attempt',receipt:{execute_attempted:true}});
  const completion=await service(env,c,'/complete',{descriptor:persisted.descriptor});
  need(completion.phase==='ciphertext_receipt_accounted_reconciliation_required'&&completion.intent_verified===false&&completion.retry_allowed===false&&completion.production_enabled===false);
  return{phase:'protected_job_receipt_accounted_reconciliation_required',created_id:persisted.created_id,descriptor:persisted.descriptor,intent_verified:false,retry_allowed:false,production_enabled:false};
 }catch{
  const error=Error(executeAttempted?'protected father runner stopped; create may have been consumed, never replay':'protected father runner stopped before execute');error.execute_attempted=executeAttempted;throw error;
 }
}
