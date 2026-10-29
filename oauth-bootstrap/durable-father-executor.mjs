// Dormant executor. The unconditional imported release gate blocks real writes.
import{createHash}from'node:crypto';
import{OfflineCreateIntentCandidate}from'./create-intent-candidate.mjs';
import{requireFatherRelease}from'./father-release-gate.mjs';
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('durable father executor blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
export async function accountEvidence(storage,binding,descriptor){
 exact(descriptor,['sha256','byte_length','stage','operation_binding','run_id','recipient']);
 need(/^[a-f0-9]{64}$/.test(descriptor.sha256)&&/^[a-f0-9]{64}$/.test(descriptor.recipient)&&Number.isSafeInteger(descriptor.byte_length)&&descriptor.byte_length>0&&descriptor.byte_length<=1048576&&descriptor.operation_binding===binding.plan&&/^[1-9][0-9]{0,19}$/.test(descriptor.run_id)&&['pre_write','acknowledgment','readback','reconciliation'].includes(descriptor.stage));
 return storage.transaction(tx=>accountEvidenceInTransaction(tx,binding,descriptor));
}
async function accountEvidenceInTransaction(tx,binding,descriptor){
  const intent=await tx.get('intent');need(intent&&canonical(intent.binding)===canonical(binding));
  let ledger=await tx.get('evidence-ledger');if(ledger===undefined)ledger={binding:structuredClone(binding),run_id:descriptor.run_id,recipient:descriptor.recipient,total_bytes:0,objects:[]};
  exact(ledger,['binding','run_id','recipient','total_bytes','objects']);need(canonical(ledger.binding)===canonical(binding)&&ledger.run_id===descriptor.run_id&&ledger.recipient===descriptor.recipient&&Array.isArray(ledger.objects)&&ledger.objects.length<100&&Number.isSafeInteger(ledger.total_bytes));
  need(ledger.objects.every(x=>x&&x.operation_binding===binding.plan&&x.run_id===descriptor.run_id&&x.recipient===descriptor.recipient&&['pre_write','acknowledgment','readback','reconciliation'].includes(x.stage)&&Number.isSafeInteger(x.byte_length)&&x.byte_length>0&&/^[a-f0-9]{64}$/.test(x.sha256))&&ledger.total_bytes===ledger.objects.reduce((s,x)=>s+x.byte_length,0)&&new Set(ledger.objects.map(x=>x.sha256)).size===ledger.objects.length&&!ledger.objects.some(x=>x.sha256===descriptor.sha256));
  const reservation=await tx.get('postwrite-reservation');need(ledger.total_bytes+descriptor.byte_length+(reservation?.phase==='reserved'&&descriptor.stage!=='readback'?reservation.byte_limit:0)<=8388608);ledger.objects.push(structuredClone(descriptor));ledger.total_bytes+=descriptor.byte_length;await tx.put('evidence-ledger',ledger);return structuredClone(ledger);
}
function payload(p,b){
 need(p&&typeof p==='object'&&p.names&&typeof p.names==='object');exact(p.names,['he','en']);
 for(const v of Object.values(p.names)){need(v&&typeof v==='object'&&typeof v.first_name==='string'&&v.first_name.length>0&&v.first_name.length<=160&&Object.keys(v).every(k=>['first_name','middle_name','last_name','maiden_name'].includes(k))&&Object.values(v).every(x=>typeof x==='string'&&x.length>0&&x.length<=160));}
 exact(p,['names',...Object.keys(p.names.en),'gender','is_alive','public']);need(p.gender==='male'&&typeof p.is_alive==='boolean'&&p.public===false&&Object.keys(p.names.en).every(k=>p[k]===p.names.en[k])&&hash(canonical(p))===b.payload);
}
async function fixedRequest(method,route,token,body){
 const ctl=new AbortController();let timer,active=true;
 try{
  const work=async()=>{const r=await fetch('https://www.geni.com/api/'+route,{method,redirect:'manual',signal:ctl.signal,headers:{Authorization:'Bearer '+token,Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const len=r.headers.get('content-length');need(len===null||(/^[0-9]+$/.test(len)&&Number(len)<=1048576));const reader=r.body.getReader(),chunks=[];let n=0;try{for(;;){const x=await reader.read();if(x.done)break;n+=x.value.length;need(active&&n<=1048576);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}const bytes=Buffer.concat(chunks),text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const set=stack.at(-1),k=JSON.parse(t);need(set instanceof Set&&!set.has(k));set.add(k);}need(stack.length<=16);}const v=JSON.parse(text);need(v&&typeof v==='object'&&!Array.isArray(v)&&!['error','results','paging','pagination','next_page'].some(k=>k in v));return{value:v,hash:hash(bytes)};};
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('vendor request uncertain'));},10000);});return await Promise.race([work(),deadline]);
 }finally{active=false;ctl.abort();clearTimeout(timer);}
}
export async function executeDurableFather(storage,binding,approvedPayload,token,prewrite){
 requireFatherRelease(); // ALWAYS throws in shipped code, before state or network.
 payload(approvedPayload,binding);need(typeof token==='string'&&/^[A-Za-z0-9._~-]{8,4096}$/.test(token));
 const store=new OfflineCreateIntentCandidate(storage,binding.owner);await store.consume(binding,0);
 let version=1,created=null;const evidence={schema_version:1,mode:'private_post_write_evidence',binding:structuredClone(binding),acknowledgment:null,profile:null,family:null,union:null};
 try{
  await accountEvidence(storage,binding,prewrite);
  const ack=await fixedRequest('POST',binding.owner+'/add-parent',token,approvedPayload);
  evidence.acknowledgment=ack.value;
  need(typeof ack.value.id==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(ack.value.id)&&ack.value.id!==binding.owner);created=ack.value.id;
  // Record returned ID immediately, before any later readback/evidence failure.
  await store.advance(binding,1,'acknowledge',ack.hash,created);version=2;
  const profile=await fixedRequest('GET',created+'?only_ids=true',token);
  evidence.profile=profile.value;
  need(profile.value.id===created&&profile.value.public===false&&profile.value.is_alive===approvedPayload.is_alive&&profile.value.gender==='male'&&canonical(profile.value.names)===canonical(approvedPayload.names)&&Object.keys(approvedPayload.names.en).every(k=>profile.value[k]===approvedPayload[k]));
  const family=await fixedRequest('GET',binding.owner+'/immediate-family?only_ids=true',token);evidence.family=family.value;need(family.value.focus?.id===binding.owner&&family.value.nodes&&typeof family.value.nodes==='object'&&!Array.isArray(family.value.nodes)&&Object.keys(family.value.nodes).length<=100);
  for(const [id,node]of Object.entries(family.value.nodes))need(node&&node.id===id&&/^(profile|union)-[1-9][0-9]{0,29}$/.test(id));
  need(family.value.nodes[created]?.id===created&&family.value.nodes[binding.owner]?.id===binding.owner);
  const unions=Object.values(family.value.nodes).filter(x=>/^union-[1-9][0-9]{0,29}$/.test(x?.id)&&Array.isArray(x.children)&&x.children.includes(binding.owner));need(unions.length===1);const uid=unions[0].id;
  const union=await fixedRequest('GET',uid+'?only_ids=true',token);evidence.union=union.value;need(union.value.id===uid&&canonical(union.value.partners)===canonical([created])&&canonical(union.value.children)===canonical([binding.owner])&&(!union.value.adopted_children||union.value.adopted_children.length===0)&&(!union.value.foster_children||union.value.foster_children.length===0));
  // No VERIFIED claim until encrypted post-write evidence persistence is joined.
  await store.advance(binding,version,'uncertain',hash(canonical({profile:profile.hash,family:family.hash,union:union.hash})));return{phase:'consumed_readback_consistent_evidence_pending',created_id:created,private_evidence:evidence,post_write_evidence_durable:false,retry_allowed:false,production_enabled:false};
 }catch{
  try{await store.advance(binding,version,'uncertain',hash('uncertain:'+version+':'+(created??'unknown')));}catch{/* consumed state remains authoritative even if transition fails */}
  return{phase:'consumed_uncertain',created_id:created,private_evidence:evidence,post_write_evidence_durable:false,retry_allowed:false,production_enabled:false};
 }
}

export async function admitPostwriteReceipt(storage,binding,descriptor,immutable){
 exact(immutable,['source','descriptor']);
 need(immutable.descriptor&&['sha256','byte_length','stage','operation_binding','run_id','recipient'].every(k=>immutable.descriptor[k]===descriptor[k]));
 return storage.transaction(async tx=>{
  const intent=await tx.get('intent');need(intent&&canonical(intent.binding)===canonical(binding)&&intent.phase==='uncertain'&&intent.production_enabled===false);
  const reservation=await tx.get('postwrite-reservation');need(reservation&&reservation.phase==='reserved'&&canonical(reservation.binding)===canonical(binding)&&reservation.run_id===descriptor.run_id&&reservation.recipient===descriptor.recipient&&descriptor.byte_length<=reservation.byte_limit);
  const existing=await tx.get('evidence-ledger');need(existing&&existing.objects?.some(x=>x.stage==='pre_write')&&await tx.get('postwrite-receipt')===undefined&&descriptor.stage==='readback');
  need(existing.total_bytes===reservation.prior_total);
  const ledger=await accountEvidence({transaction:fn=>fn(tx)},binding,descriptor);
  const receipt={phase:'ciphertext_receipt_accounted_reconciliation_required',immutable:structuredClone(immutable),descriptor:structuredClone(descriptor),intent_version:intent.version,created_id:intent.created_id,ledger_total_bytes:ledger.total_bytes,intent_verified:false,retry_allowed:false,production_enabled:false};
  await tx.put('postwrite-reservation',{...reservation,phase:'accounted',sha256:descriptor.sha256,actual_bytes:descriptor.byte_length});await tx.put('postwrite-receipt',receipt);return receipt;
 });
}

/** Reserves the maximum ciphertext size before remote upload, not after it.
 * Same consumed intent/run/recipient; a failed upload leaves reservation intact.
 */
export async function reservePostwriteBudget(storage,binding,runId){
 return storage.transaction(async tx=>{
  const intent=await tx.get('intent'),ledger=await tx.get('evidence-ledger');
  need(intent&&canonical(intent.binding)===canonical(binding)&&intent.phase==='uncertain'&&intent.production_enabled===false&&ledger&&canonical(ledger.binding)===canonical(binding)&&ledger.run_id===runId&&Array.isArray(ledger.objects)&&ledger.objects.some(x=>x.stage==='pre_write'));
  need(ledger.objects.length>0&&ledger.objects.length<100&&ledger.objects.every(x=>x&&x.operation_binding===binding.plan&&x.run_id===runId&&x.recipient===ledger.recipient&&Number.isSafeInteger(x.byte_length)&&x.byte_length>0&&x.byte_length<=1048576&&/^[a-f0-9]{64}$/.test(x.sha256))&&new Set(ledger.objects.map(x=>x.sha256)).size===ledger.objects.length&&ledger.total_bytes===ledger.objects.reduce((n,x)=>n+x.byte_length,0)&&Number.isSafeInteger(ledger.total_bytes)&&ledger.total_bytes+1048576<=8388608&&await tx.get('postwrite-reservation')===undefined&&await tx.get('postwrite-receipt')===undefined);
  const reservation={binding:structuredClone(binding),run_id:runId,recipient:ledger.recipient,byte_limit:1048576,prior_total:ledger.total_bytes,phase:'reserved',production_enabled:false};
  await tx.put('postwrite-reservation',reservation);return{phase:'postwrite_ciphertext_budget_reserved',byte_limit:reservation.byte_limit,prior_total:reservation.prior_total,retry_allowed:false,production_enabled:false};
 });
}

/** Fixed read-only recovery of an existing consumed operation. A possible new
 * parent observed after lost acknowledgment is never assigned as created_id.
 * Returned evidence is private and still needs encryption/persistence.
 */
export async function collectDurableFatherRecovery(storage,binding,token){
 requireFatherRelease(); // unchanged unconditional production barrier
 const snapshot=await storage.transaction(async tx=>{
  const intent=await tx.get('intent');need(intent&&canonical(intent.binding)===canonical(binding)&&['consumed','acknowledged','uncertain'].includes(intent.phase)&&intent.production_enabled===false);
  return{intent,ledger:await tx.get('evidence-ledger'),receipt:await tx.get('postwrite-receipt')??null};
 });
 need(typeof token==='string'&&/^[A-Za-z0-9._~-]{8,4096}$/.test(token));
 const evidence={schema_version:1,mode:'private_read_only_recovery_evidence',binding:structuredClone(binding),intent:structuredClone(snapshot.intent),ledger:structuredClone(snapshot.ledger??null),receipt:structuredClone(snapshot.receipt),self:null,family:null,profile:null,union:null};
 let complete=false;
 try{
  const self=await fixedRequest('GET','profile?only_ids=true',token);evidence.self=self.value;need(self.value.id===binding.owner);
  const family=await fixedRequest('GET',binding.owner+'/immediate-family?only_ids=true',token);evidence.family=family.value;
  need(family.value.focus?.id===binding.owner&&family.value.nodes&&Object.getPrototypeOf(family.value.nodes)===Object.prototype&&Object.keys(family.value.nodes).length<=100);
  for(const[id,node]of Object.entries(family.value.nodes))need(node&&node.id===id&&/^(profile|union)-[1-9][0-9]{0,29}$/.test(id));
  const known=snapshot.intent.created_id;
  if(known!==null){
   need(typeof known==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(known)&&known!==binding.owner);
   const profile=await fixedRequest('GET',known+'?only_ids=true',token);evidence.profile=profile.value;need(profile.value.id===known);
   const unions=Object.values(family.value.nodes).filter(x=>/^union-[1-9][0-9]{0,29}$/.test(x?.id)&&Array.isArray(x.children)&&x.children.includes(binding.owner)&&Array.isArray(x.partners)&&x.partners.includes(known));
   if(unions.length===1){const union=await fixedRequest('GET',unions[0].id+'?only_ids=true',token);evidence.union=union.value;need(union.value.id===unions[0].id);}
  }
  complete=true;
 }catch{/* bounded partial read evidence remains private; never retries */}
 return{phase:complete?'consumed_read_only_observations_collected':'consumed_read_only_observations_partial',created_id:snapshot.intent.created_id,private_evidence:evidence,observation_complete:complete,identity_resolved:snapshot.intent.created_id!==null,intent_verified:false,retry_allowed:false,production_enabled:false};
}
