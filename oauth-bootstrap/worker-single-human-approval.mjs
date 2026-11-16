// Dormant content-only validator. No source authentication, routes or grants.
const need=x=>{if(!x)throw Error('worker approval content blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const id=x=>need(typeof x==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(x));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
const time=x=>need(Number.isSafeInteger(x)&&x>0&&x<2**40);
const assurance='single_human_owner_agent_dispatch_independent_agent_review';
const roles={owner_grant:'protected_environment_exact_payload_approval',protected_review:'protected_environment_human_action',dispatch:'designated_agent_workflow_dispatch',code_review:'independent_agent_exact_head_review'};
const exclusions=['add_child','add_mother','add_partner','delete','fact_cite','marriage','merge','profile_update','retry','source_upload','tag','union_update'];
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
function parse(raw){
 need(typeof raw==='string'&&new TextEncoder().encode(raw).length<=65536);
 // Preserve Python strict integer semantics across JSON: 1.0/1e0 must not become
 // an accepted JS integer. These bounded records have no valid float fields.
 const tokens=raw.match(/"(?:[^"\\]|\\.)*"|[^\s{}\[\]:,]+/g)||[];
 for(const t of tokens)if(t[0]!=='"'&&!['true','false','null'].includes(t))need(/^-?(0|[1-9][0-9]*)(?![\s\S])/.test(t)&&Number.isSafeInteger(Number(t)));
 return JSON.parse(raw);
}
function validate(raw){
 const r=parse(raw);exact(r,['schema_version','mode','assurance','human_count','production_enabled','pins','exclusions','risk_hash','sources','reviewed_executor_sha','revocation_epoch']);
 need(r.schema_version===2&&r.mode==='single_human_approval_content'&&r.assurance===assurance&&r.human_count===1&&r.production_enabled===false);
 const p=r.pins;exact(p,['owner','connection_id','operation','payload_hash','graph_hash','data_hash','executor_sha','workflow_sha','artifact_hash','service_sha','policy_hash','recipient','run_id','run_attempt','nonce','issued_at','expires_at']);
 need(typeof p.owner==='string'&&/^profile-[1-9][0-9]{0,29}(?![\s\S])/.test(p.owner)&&typeof p.connection_id==='string'&&/^[A-Za-z0-9_-]{1,100}(?![\s\S])/.test(p.connection_id)&&p.operation==='single_father_add_parent');
 for(const k of ['payload_hash','graph_hash','data_hash','artifact_hash','policy_hash','recipient','nonce'])hex(p[k],64);
 for(const k of ['executor_sha','workflow_sha','service_sha'])hex(p[k],40);
 id(p.run_id);need(p.run_attempt===1);time(p.issued_at);time(p.expires_at);need(p.expires_at>p.issued_at&&p.expires_at-p.issued_at<=900);
 need(Array.isArray(r.exclusions)&&JSON.stringify(r.exclusions)===JSON.stringify(exclusions));hex(r.risk_hash,64);
 need(Number.isSafeInteger(r.revocation_epoch)&&r.revocation_epoch>=0&&r.revocation_epoch<2**40&&r.reviewed_executor_sha===p.executor_sha);
 exact(r.sources,Object.keys(roles));for(const[role,kind]of Object.entries(roles)){const s=r.sources[role];exact(s,['kind','principal_id','source_ref','content_hash']);need(s.kind===kind);id(s.principal_id);hex(s.source_ref,64);hex(s.content_hash,64);}
 const s=r.sources;need(s.owner_grant.principal_id===s.protected_review.principal_id&&s.dispatch.principal_id!==s.owner_grant.principal_id&&s.code_review.principal_id!==s.dispatch.principal_id&&s.code_review.principal_id!==s.owner_grant.principal_id);
 need(s.owner_grant.source_ref===s.protected_review.source_ref&&s.owner_grant.content_hash===s.protected_review.content_hash&&new Set(['owner_grant','dispatch','code_review'].map(k=>s[k].source_ref)).size===3);
 return r;
}
export function validateWorkerApprovalContent(raw){try{return validate(raw);}catch{throw Error('worker approval content blocked');}}
export async function checkWorkerApprovalContent(raw,expectedRaw,now){try{
 const r=validate(raw),e=validate(expectedRaw);need(canonical(r)===canonical(e));time(now);need(r.pins.issued_at<=now&&now<r.pins.expires_at);
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(r)));const record_hash=Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
 return{phase:'single_human_content_consistent_only',schema_version:2,assurance,human_count:1,two_humans_verified:false,content_consistent:true,record_hash,owner_approval_verified:false,protected_human_action_verified:false,dispatch_provenance_verified:false,independent_review_verified:false,revocation_verified:false,post_permitted:false,production_enabled:false};
}catch{throw Error('worker approval content blocked');}}
