// Unreleased live protected-review correlation. No POST permit or workflow deploy.
import{validateWorkerApprovalContent}from'./worker-single-human-approval.mjs';
import{createWorkerEvidenceTransport}from'./worker-evidence-transport.mjs';
const hash=async x=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',typeof x==='string'?new TextEncoder().encode(x):x)),b=>b.toString(16).padStart(2,'0')).join('');
const need=x=>{if(!x)throw Error('worker protected capture blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
export async function workerStaticPlanFingerprint(record){
 const staticRecord=Object.fromEntries(Object.entries(record).filter(([k])=>!['pins','sources'].includes(k)));
 staticRecord.pins=Object.fromEntries(Object.entries(record.pins).filter(([k])=>!['run_id','run_attempt','issued_at','expires_at'].includes(k)));
 staticRecord.expected_human_id=record.sources.owner_grant.principal_id;
 staticRecord.agent_sources=Object.fromEntries(['dispatch','code_review'].map(k=>[k,record.sources[k]]));
 staticRecord.run_attempt=1;staticRecord.max_window_seconds=900;
 return hash(canonical(staticRecord));
}
export async function inspectWorkerProtectedCapture(env,approvalRaw,binding,fetcher=fetch){
 let transport;
 try{
  exact(binding,['owner','connection','plan','payload','artifact','policy','run_id']);
  const record=validateWorkerApprovalContent(approvalRaw);
  const fresh=()=>{const now=Math.floor(Date.now()/1000);need(record.pins.issued_at<=now&&now<record.pins.expires_at);};fresh();
  const raw=env.FATHER_CAPTURE_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&await hash(raw)===env.FATHER_CAPTURE_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','owner','repo','repository_id','environment_id','reviewer_id','actor_id','workflow_path','workflow_content_sha256','executor_sha','run_id','plan_fingerprint','risk_hash']);
  need(c.mode==='unreleased_live_protected_capture'&&c.production_enabled===false);
  for(const k of['owner','repo'])need(typeof c[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}(?![\s\S])/.test(c[k]));
  for(const k of['repository_id','environment_id','reviewer_id','actor_id','run_id'])need(typeof c[k]==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(c[k]));
  need(c.actor_id!==c.reviewer_id&&/^\.github\/workflows\/[A-Za-z0-9_-]+\.ya?ml(?![\s\S])/.test(c.workflow_path)&&/^[a-f0-9]{64}(?![\s\S])/.test(c.workflow_content_sha256)&&/^[a-f0-9]{40}(?![\s\S])/.test(c.executor_sha));
  need(record.pins.owner===binding.owner&&record.pins.connection_id===binding.connection&&record.pins.payload_hash===binding.payload&&record.pins.artifact_hash===binding.artifact&&record.pins.policy_hash===binding.policy);
  need(c.plan_fingerprint===binding.plan&&await workerStaticPlanFingerprint(record)===binding.plan&&c.risk_hash===record.risk_hash&&c.run_id===binding.run_id&&record.pins.run_id===c.run_id&&record.pins.run_attempt===1&&record.pins.executor_sha===c.executor_sha&&record.pins.workflow_sha===c.executor_sha);
  need(record.sources.owner_grant.principal_id===c.reviewer_id&&record.sources.protected_review.principal_id===c.reviewer_id&&record.sources.dispatch.principal_id===c.actor_id);
  const credential=env.PRIVATE_GIT_CREDENTIAL;need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}(?![\s\S])/.test(credential));
  const root='/repos/'+c.owner+'/'+c.repo,run=root+'/actions/runs/'+c.run_id,environment=root+'/environments/father-create';
  const routes=[run,environment,environment+'/deployment-branch-policies',run+'/approvals',run+'/attempts/1/jobs?per_page=100',root+'/contents/'+c.workflow_path+'?ref='+c.executor_sha];
  transport=createWorkerEvidenceTransport({routes,credential},fetcher);
  const get=route=>transport.get(route);
  function rules(e,branches){
   need(String(e.id)===c.environment_id&&e.name==='father-create'&&e.can_admins_bypass===false&&e.deployment_branch_policy?.protected_branches===false&&e.deployment_branch_policy?.custom_branch_policies===true);
   need(Array.isArray(e.protection_rules)&&e.protection_rules.length===2);const types=e.protection_rules.map(x=>x.type).sort();need(types.join(',')==='branch_policy,required_reviewers');const r=e.protection_rules.find(x=>x.type==='required_reviewers');need(r.prevent_self_review===true&&Array.isArray(r.reviewers)&&r.reviewers.length===1&&r.reviewers[0].type==='User'&&String(r.reviewers[0].reviewer?.id)===c.reviewer_id);
   need(branches.total_count===1&&Array.isArray(branches.branch_policies)&&branches.branch_policies.length===1&&branches.branch_policies[0].name==='master'&&branches.branch_policies[0].type==='branch');
  }
  async function work(){
   const r=await get(run);need(String(r.id)===c.run_id&&r.run_attempt===1&&r.event==='workflow_dispatch'&&r.head_sha===c.executor_sha&&r.head_branch==='master'&&r.path===c.workflow_path&&String(r.actor?.id)===c.actor_id&&String(r.triggering_actor?.id)===c.actor_id);
   for(const k of['repository','head_repository'])need(String(r[k]?.id)===c.repository_id&&r[k].full_name===c.owner+'/'+c.repo);
   const e=await get(environment),b=await get(environment+'/deployment-branch-policies');rules(e,b);
   const a=await get(run+'/approvals');need(Array.isArray(a)&&a.length===1&&a[0].state==='approved'&&a[0].user?.type==='User'&&String(a[0].user.id)===c.reviewer_id&&a[0].environments?.length===1&&String(a[0].environments[0].id)===c.environment_id&&a[0].environments[0].name==='father-create');
   need(record.sources.owner_grant.content_hash===await hash(canonical(a))&&record.sources.protected_review.content_hash===await hash(canonical(a)));
   const jobs=await get(run+'/attempts/1/jobs?per_page=100');need(jobs.total_count===1&&jobs.jobs?.length===1);const job=jobs.jobs[0];need(job.name==='Approve plan '+c.plan_fingerprint+' risk '+c.risk_hash+' run '+c.run_id+' attempt 1'&&String(job.run_id)===c.run_id&&job.run_attempt===1&&job.head_sha===c.executor_sha&&job.status==='in_progress'&&job.conclusion===null);
   need(Number.isSafeInteger(job.id)&&job.id>0);
   const decision={repository_id:c.repository_id,run_id:c.run_id,run_attempt:1,job_id:String(job.id),environment_id:c.environment_id,reviewer_id:c.reviewer_id,actor_id:c.actor_id,executor_sha:c.executor_sha,workflow_path:c.workflow_path,plan_fingerprint:c.plan_fingerprint,risk_hash:c.risk_hash,review_content_hash:await hash(canonical(a))};
   need(record.sources.owner_grant.source_ref===await hash(canonical(decision))&&record.sources.protected_review.source_ref===await hash(canonical(decision)));
   // Exact immutable workflow bytes are reviewed off-line as the single-gate
   // workflow. A matching hash proves content, not who reviewed it.
   const file=await get(root+'/contents/'+c.workflow_path+'?ref='+c.executor_sha);need(file.type==='file'&&file.path===c.workflow_path&&file.encoding==='base64'&&typeof file.content==='string');const encoded=file.content.replace(/\n/g,'');need(encoded.length<=87384);const bytes=Uint8Array.from(atob(encoded),x=>x.charCodeAt(0));need(btoa(String.fromCharCode(...bytes))===encoded&&bytes.length<=65536&&await hash(bytes)===c.workflow_content_sha256);
   rules(await get(environment),await get(environment+'/deployment-branch-policies'));
   fresh();return{phase:'current_protected_capture_correlated',api_capture_correlated:true,static_plan_bound:true,immutable_workflow_bytes_verified:true,historical_protection_verified:false,independent_review_provenance_verified:false,shared_identity_limit:true,post_permitted:false,production_enabled:false};
  }
  return await work();
 }catch{throw Error('worker protected capture blocked');}finally{transport?.close();}
}
