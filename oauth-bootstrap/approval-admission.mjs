// Fixed GitHub immutable-record provenance. Never owner consent or POST permit.
import {createHash} from 'node:crypto';
const receipts=new WeakMap();
const fail=()=>{throw Error('approval admission blocked');};
const need=x=>{if(!x)fail();};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
const hash=x=>createHash('sha256').update(x).digest('hex');
const blob=x=>createHash('sha1').update(Buffer.from('blob '+x.length+'\0')).update(x).digest('hex');
const PIN_KEYS=['owner','connection_id','operation','payload_hash','graph_hash','data_hash','executor_sha','workflow_sha','artifact_hash','service_sha','policy_hash','recipient','run_id','run_attempt','nonce','issued_at','expires_at'];
const EXCLUSIONS=['add_child','add_mother','add_partner','delete','fact_cite','marriage','merge','profile_update','retry','source_upload','tag','union_update'];
function pins(p){
 exact(p,PIN_KEYS);need(/^profile-[1-9][0-9]{0,29}$/.test(p.owner)&&typeof p.owner==='string');
 need(typeof p.connection_id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(p.connection_id));
 need(p.operation==='single_father_add_parent');
 for(const k of ['payload_hash','graph_hash','data_hash','artifact_hash','policy_hash','recipient','nonce'])hex(p[k],64);
 for(const k of ['executor_sha','workflow_sha','service_sha'])hex(p[k],40);
 need(typeof p.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(p.run_id)&&p.run_attempt===1);
 for(const k of ['issued_at','expires_at'])need(Number.isSafeInteger(p[k])&&p[k]>0&&p[k]<2**40);
 need(p.expires_at>p.issued_at&&p.expires_at-p.issued_at<=900);
}
function parse(bytes,cap=65536){
 need(bytes instanceof Uint8Array&&bytes.length>0&&bytes.length<=cap);
 const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes),value=JSON.parse(raw),stack=[];
 const tokens=raw.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[];
 for(let i=0;i<tokens.length;i++){const t=tokens[i];
  if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);
  else if(t==='}'||t===']')stack.pop();else if(t.startsWith('"')&&tokens[i+1]===':'){
   const set=stack.at(-1),k=JSON.parse(t);need(set instanceof Set&&!set.has(k));set.add(k);}
  need(stack.length<=8);
 }
 return value;
}
function sourcePins(p){
 exact(p,['repository_id','owner','repo','commit','path','blob_sha','content_sha256']);
 need(typeof p.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(p.repository_id));
 for(const k of ['owner','repo'])need(typeof p[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(p[k]));
 hex(p.commit,40);hex(p.blob_sha,40);hex(p.content_sha256,64);
 need(typeof p.path==='string'&&p.path.length<=500);const parts=p.path.split('/');need(parts.length<=8&&parts.every(x=>/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(x)&&x!=='.'&&x!=='..'));
 return parts;
}
/** Release code must supply immutable reviewed source pins, never request JSON. */
export async function fetchPrivateApproval({source,credential}){
 const ctl=new AbortController();let timer;
 try{
  const parts=sourcePins(source);need(typeof credential==='string'&&credential.length>0&&credential.length<=4096&&/^[A-Za-z0-9_]+$/.test(credential));
  const root='/repos/'+source.owner+'/'+source.repo;let count=0;
  const get=async route=>{need(++count<=11);const r=await fetch('https://api.github.com'+route,{redirect:'manual',signal:ctl.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'X-GitHub-Api-Version':'2022-11-28'}});
   need(r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const declared=r.headers.get('content-length');if(declared!==null)need(/^[0-9]+$/.test(declared)&&Number(declared)<=131072);
   const reader=r.body.getReader();let total=0;const chunks=[];try{for(;;){const v=await reader.read();if(v.done)break;total+=v.value.length;need(total<=131072);chunks.push(v.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   // API envelopes can be128KiB; the actual approval object remains64KiB.
   const raw=Buffer.concat(chunks);need(raw.length>0);return parseEnvelope(raw);
  };
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{ctl.abort();reject(Error('approval admission blocked'));},5000);});
  const work=async()=>{
   const repo=await get('/repositories/'+source.repository_id);need(String(repo.id)===source.repository_id&&repo.private===true&&repo.full_name===source.owner+'/'+source.repo);
   const commit=await get(root+'/git/commits/'+source.commit);need(commit.sha===source.commit);hex(commit.tree?.sha,40);let tree=commit.tree.sha;
   for(let i=0;i<parts.length;i++){
    const t=await get(root+'/git/trees/'+tree);need(t.sha===tree&&t.truncated===false&&Array.isArray(t.tree)&&t.tree.length<=1000);
    const found=t.tree.filter(e=>e.path===parts[i]);need(found.length===1);const f=found[0];hex(f.sha,40);
    if(i<parts.length-1){need(f.type==='tree'&&f.mode==='040000');tree=f.sha;}
    else need(f.type==='blob'&&f.mode==='100644'&&f.sha===source.blob_sha);
   }
   const b=await get(root+'/git/blobs/'+source.blob_sha);need(b.sha===source.blob_sha&&b.encoding==='base64'&&Number.isSafeInteger(b.size)&&b.size>0&&b.size<=65536&&typeof b.content==='string');
   const encoded=b.content.replace(/\n/g,'');need(/^[A-Za-z0-9+/]*={0,2}$/.test(encoded));const bytes=Buffer.from(encoded,'base64');need(bytes.toString('base64')===encoded&&bytes.length===b.size&&blob(bytes)===source.blob_sha&&hash(bytes)===source.content_sha256);
   parse(bytes);const receipt=Object.freeze({record_provenance_verified:true,owner_approval_verified:false,production_enabled:false});
   receipts.set(receipt,{bytes:Buffer.from(bytes),source:structuredClone(source),fetchedAt:Math.floor(Date.now()/1000)});return receipt;
  };
  return await Promise.race([work(),deadline]);
 }catch{fail();}finally{ctl.abort();clearTimeout(timer);}
}
function parseEnvelope(bytes){return parse(bytes,131072);}
export function admitApproval({approvalBytes,expectedPins,authenticatedRecord,expectedApprovals,nowUnix}){
 try{
  const receipt=receipts.get(authenticatedRecord);need(receipt);need(Number.isSafeInteger(nowUnix)&&nowUnix>0&&nowUnix<2**40);
  const systemNow=Math.floor(Date.now()/1000);need(Math.abs(systemNow-nowUnix)<=5&&systemNow>=receipt.fetchedAt&&systemNow-receipt.fetchedAt<=30);
  need(approvalBytes instanceof Uint8Array&&Buffer.from(approvalBytes).equals(receipt.bytes));const r=parse(approvalBytes);
  exact(r,['schema_version','mode','production_enabled','pins','exclusions','approvals']);need(r.schema_version===1&&r.mode==='offline_approval_record'&&r.production_enabled===false);pins(r.pins);pins(expectedPins);
  need(PIN_KEYS.every(k=>r.pins[k]===expectedPins[k]));need(r.pins.issued_at<=systemNow&&systemNow<r.pins.expires_at);
  need(Array.isArray(r.exclusions)&&JSON.stringify(r.exclusions)===JSON.stringify(EXCLUSIONS));exact(expectedApprovals,['owner','human_reviewer']);
  need(Array.isArray(r.approvals)&&r.approvals.length===2);
  for(const [i,role]of ['owner','human_reviewer'].entries()){
   const a=r.approvals[i],want=expectedApprovals[role];exact(a,['role','approver_ref','evidence_ref']);exact(want,['approver_ref','evidence_ref']);need(a.role===role);
   for(const k of ['approver_ref','evidence_ref']){hex(a[k],64);need(a[k]===want[k]);}
  }
  need(r.approvals[0].approver_ref!==r.approvals[1].approver_ref&&r.approvals[0].evidence_ref!==r.approvals[1].evidence_ref);
  return {phase:'private_record_content_admitted_only',record_provenance_verified:true,content_consistent:true,owner_approval_verified:false,payload_approval_verified:false,review_provenance_verified:false,post_permitted:false,production_enabled:false,record_sha256:hash(receipt.bytes),release_gaps:['authenticated_owner_record_creation','protected_human_review_correlation','permanent_replay_consumption']};
 }catch{fail();}
}

/** Join the existing immutable private byte receipt to the single-human v2
 * shape. Capture authentication is still a separate release obligation; a
 * matching record/config hash is not proof of the human clicking the gate.
 */
export function admitSingleHumanApproval({approvalBytes,expectedRecord,authenticatedRecord}){
 try{
  const receipt=receipts.get(authenticatedRecord);need(receipt);
  const now=Math.floor(Date.now()/1000);need(now>=receipt.fetchedAt&&now-receipt.fetchedAt<=30);
  need(approvalBytes instanceof Uint8Array&&Buffer.from(approvalBytes).equals(receipt.bytes));
  const validate=r=>{
   exact(r,['schema_version','mode','assurance','human_count','production_enabled','pins','exclusions','risk_hash','sources','reviewed_executor_sha','revocation_epoch']);
   need(r.schema_version===2&&r.mode==='single_human_approval_content'&&r.assurance==='single_human_owner_agent_dispatch_independent_agent_review'&&r.human_count===1&&r.production_enabled===false);
   pins(r.pins);need(r.pins.issued_at<=now&&now<r.pins.expires_at);
   need(JSON.stringify(r.exclusions)===JSON.stringify(EXCLUSIONS));hex(r.risk_hash,64);
   need(Number.isSafeInteger(r.revocation_epoch)&&r.revocation_epoch>=0&&r.revocation_epoch<2**40&&r.reviewed_executor_sha===r.pins.executor_sha);
   const kinds={owner_grant:'protected_environment_exact_payload_approval',protected_review:'protected_environment_human_action',dispatch:'designated_agent_workflow_dispatch',code_review:'independent_agent_exact_head_review'};
   exact(r.sources,Object.keys(kinds));
   for(const [role,kind]of Object.entries(kinds)){
    const x=r.sources[role];exact(x,['kind','principal_id','source_ref','content_hash']);
    need(x.kind===kind&&typeof x.principal_id==='string'&&/^[1-9][0-9]{0,19}$/.test(x.principal_id));hex(x.source_ref,64);hex(x.content_hash,64);
   }
   const s=r.sources;need(s.owner_grant.principal_id===s.protected_review.principal_id&&s.owner_grant.source_ref===s.protected_review.source_ref&&s.owner_grant.content_hash===s.protected_review.content_hash);
   need(new Set([s.owner_grant.principal_id,s.dispatch.principal_id,s.code_review.principal_id]).size===3);
   need(new Set([s.owner_grant.source_ref,s.dispatch.source_ref,s.code_review.source_ref]).size===3);
  };
  const record=parse(approvalBytes);validate(record);validate(expectedRecord);
  const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
  need(canonical(record)===canonical(expectedRecord));
  return {phase:'private_single_human_content_admitted_only',record_provenance_verified:true,content_consistent:true,human_count:1,two_humans_verified:false,owner_approval_verified:false,protected_human_action_verified:false,post_permitted:false,production_enabled:false,record_sha256:hash(receipt.bytes)};
 }catch{fail();}
}
/** Private immutable fetch and v2 admission stay in the same module. Raw bytes
 * and module-owned receipt never cross the service request boundary.
 */
export async function fetchAndAdmitSingleHuman({source,credential,expectedRecord}){
 const receipt=await fetchPrivateApproval({source,credential});
 const stored=receipts.get(receipt);need(stored);
 return admitSingleHumanApproval({approvalBytes:stored.bytes,expectedRecord,authenticatedRecord:receipt});
}
