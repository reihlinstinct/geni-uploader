// Unreleased live protected-review correlation. No POST permit or workflow deploy.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('live protected capture blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
export function staticPlanFingerprint(record){
 const staticRecord=Object.fromEntries(Object.entries(record).filter(([k])=>!['pins','sources'].includes(k)));
 staticRecord.pins=Object.fromEntries(Object.entries(record.pins).filter(([k])=>!['run_id','run_attempt','issued_at','expires_at'].includes(k)));
 staticRecord.expected_human_id=record.sources.owner_grant.principal_id;
 staticRecord.agent_sources=Object.fromEntries(['dispatch','code_review'].map(k=>[k,record.sources[k]]));
 staticRecord.run_attempt=1;staticRecord.max_window_seconds=900;
 return hash(canonical(staticRecord));
}
export async function inspectLiveProtectedCapture(env,record,binding){
 const ctl=new AbortController();let timer,active=true;
 try{
  const raw=env.FATHER_CAPTURE_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_CAPTURE_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','owner','repo','repository_id','environment_id','reviewer_id','actor_id','workflow_path','workflow_content_sha256','executor_sha','run_id','plan_fingerprint','risk_hash']);
  need(c.mode==='unreleased_live_protected_capture'&&c.production_enabled===false);
  for(const k of['owner','repo'])need(typeof c[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(c[k]));
  for(const k of['repository_id','environment_id','reviewer_id','actor_id','run_id'])need(typeof c[k]==='string'&&/^[1-9][0-9]{0,19}$/.test(c[k]));
  need(c.actor_id!==c.reviewer_id&&/^\.github\/workflows\/[A-Za-z0-9_-]+\.ya?ml$/.test(c.workflow_path)&&/^[a-f0-9]{64}$/.test(c.workflow_content_sha256)&&/^[a-f0-9]{40}$/.test(c.executor_sha));
  need(c.plan_fingerprint===binding.plan&&staticPlanFingerprint(record)===binding.plan&&c.risk_hash===record.risk_hash&&c.run_id===binding.run_id&&record.pins.run_id===c.run_id&&record.pins.run_attempt===1&&record.pins.executor_sha===c.executor_sha&&record.pins.workflow_sha===c.executor_sha);
  need(record.sources.owner_grant.principal_id===c.reviewer_id&&record.sources.protected_review.principal_id===c.reviewer_id&&record.sources.dispatch.principal_id===c.actor_id);
  const credential=env.PRIVATE_GIT_CREDENTIAL;need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(credential));
  const root='/repos/'+c.owner+'/'+c.repo,run=root+'/actions/runs/'+c.run_id,environment=root+'/environments/father-create';let n=0;
  async function get(route){
   need(active&&++n<=8);const r=await fetch('https://api.github.com'+route,{redirect:'manual',signal:ctl.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'X-GitHub-Api-Version':'2022-11-28'}});
   need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const declared=r.headers.get('content-length');need(declared===null||(/^[0-9]+$/.test(declared)&&Number(declared)<=1048576));
   const chunks=[],reader=r.body.getReader();let size=0;try{for(;;){const x=await reader.read();if(x.done)break;size+=x.value.length;need(active&&size<=1048576);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];
   for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const k=JSON.parse(t),s=stack.at(-1);need(s instanceof Set&&!s.has(k));s.add(k);}need(stack.length<=16);}
   return JSON.parse(text);
  }
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
   need(record.sources.owner_grant.content_hash===hash(canonical(a))&&record.sources.protected_review.content_hash===hash(canonical(a)));
   const jobs=await get(run+'/attempts/1/jobs?per_page=100');need(jobs.total_count===1&&jobs.jobs?.length===1);const job=jobs.jobs[0];need(job.name==='Approve plan '+c.plan_fingerprint+' risk '+c.risk_hash+' run '+c.run_id+' attempt 1'&&String(job.run_id)===c.run_id&&job.run_attempt===1&&job.head_sha===c.executor_sha&&job.status==='in_progress'&&job.conclusion===null);
   need(Number.isSafeInteger(job.id)&&job.id>0);
   const decision={repository_id:c.repository_id,run_id:c.run_id,run_attempt:1,job_id:String(job.id),environment_id:c.environment_id,reviewer_id:c.reviewer_id,actor_id:c.actor_id,executor_sha:c.executor_sha,workflow_path:c.workflow_path,plan_fingerprint:c.plan_fingerprint,risk_hash:c.risk_hash,review_content_hash:hash(canonical(a))};
   need(record.sources.owner_grant.source_ref===hash(canonical(decision))&&record.sources.protected_review.source_ref===hash(canonical(decision)));
   // Exact immutable workflow bytes are reviewed off-line as the single-gate
   // workflow. A matching hash proves content, not who reviewed it.
   const file=await get(root+'/contents/'+c.workflow_path+'?ref='+c.executor_sha);need(file.type==='file'&&file.path===c.workflow_path&&file.encoding==='base64'&&typeof file.content==='string');const encoded=file.content.replace(/\n/g,''),bytes=Buffer.from(encoded,'base64');need(bytes.toString('base64')===encoded&&bytes.length<=65536&&hash(bytes)===c.workflow_content_sha256);
   rules(await get(environment),await get(environment+'/deployment-branch-policies'));
   return{phase:'current_protected_capture_correlated',api_capture_correlated:true,static_plan_bound:true,immutable_workflow_bytes_verified:true,historical_protection_verified:false,independent_review_provenance_verified:false,shared_identity_limit:true,post_permitted:false,production_enabled:false};
  }
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('live protected capture blocked'));},10000);});return await Promise.race([work(),deadline]);
 }catch{throw Error('live protected capture blocked');}finally{active=false;ctl.abort();clearTimeout(timer);}
}
