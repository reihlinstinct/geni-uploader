// Unreleased authenticated service composition. No Geni endpoint or deployment.
import {verifyUploadedPostwrite} from './postwrite-ledger-admission.mjs';
import {executeDurableFather,admitPostwriteReceipt} from './durable-father-executor.mjs';
import {OfflineCreateIntentCandidate} from './create-intent-candidate.mjs';
import {verifyTrustedWorkload} from './trusted-workload-jwks.mjs';
import {verifyOwnerPreflight} from './owner-preflight.mjs';
import {bindUploadedDescriptors} from './bounded-upload-descriptors.mjs';
import {verifyProtectedApprovalContent} from './protected-approval-service.mjs';
const need=x=>{if(!x)throw Error('father intent service blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
function config(env){
 need(typeof env.FATHER_INTENT_CONFIG==='string'&&env.FATHER_INTENT_CONFIG.length<=16384);
 const c=JSON.parse(env.FATHER_INTENT_CONFIG);need(JSON.stringify(c)===env.FATHER_INTENT_CONFIG);
 exact(c,['mode','production_enabled','workload_pins','owner','connection','plan','payload','artifact','policy','expires_at','approved_run']);
 need(c.mode==='unreleased_father_intent_service'&&c.production_enabled===false);
 need(typeof c.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(c.owner));
 need(typeof c.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(c.connection));
 for(const k of ['plan','payload','artifact','policy'])hex(c[k],64);
 need(Number.isSafeInteger(c.expires_at)&&c.expires_at>0);
 need(c.approved_run===c.workload_pins.run_id&&c.workload_pins.run_attempt==='1');
 return c;
}
function binding(c){return{owner:c.owner,connection:c.connection,plan:c.plan,payload:c.payload,artifact:c.artifact,policy:c.policy};}
/** Entry route verifies real issuer signature, then routes to ONE canonical owner
 * name independent of run/plan/connection. No Geni write is exposed here.
 * Binding deployment/config namespace provenance is still a release requirement.
 */
export default {async fetch(request,env){
 try{
  const c=config(env),route=new URL(request.url).pathname;need(request.method==='POST'&&['/consume','/execute','/complete'].includes(route));
  // This module cannot be released by setting a request bool. Its existing mode
  // is consumed only by local workerd rehearsal; production route stays closed.
  need(env.FATHER_SERVICE_LOCAL_REHEARSAL==='local-only-no-geni');
  const declared=request.headers.get('content-length');if(declared!==null)need(/^[0-9]+$/.test(declared)&&Number(declared)<=32768);
  const reader=request.body?.getReader();need(reader);const chunks=[];let size=0;
  try{for(;;){const v=await reader.read();if(v.done)break;size+=v.value.length;need(size<=32768);chunks.push(v.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
  const body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));
  exact(body,route==='/complete'?['workload_token','plan_hash','descriptor']:['workload_token','plan_hash','uploads']);need(body.plan_hash===c.plan);
  need(Math.floor(Date.now()/1000)<c.expires_at);
  await verifyTrustedWorkload(body.workload_token,c.workload_pins);
  need(Math.floor(Date.now()/1000)<c.expires_at);
  const approvedBinding={...binding(c),run_id:c.approved_run};
  if(route==='/complete'){
   const verified=await verifyUploadedPostwrite(env,approvedBinding,body.descriptor);need(Math.floor(Date.now()/1000)<c.expires_at);
   need(env.FATHER_OWNER_INTENTS&&typeof env.FATHER_OWNER_INTENTS.idFromName==='function');
   const stub=env.FATHER_OWNER_INTENTS.get(env.FATHER_OWNER_INTENTS.idFromName('father-owner:'+c.owner));
   return stub.fetch(new Request('https://owner-intent.invalid/complete',{method:'POST',body:JSON.stringify({binding:binding(c),descriptor:verified.descriptor,source:verified.source})}));
  }
  const readbackEnv=bindUploadedDescriptors(env,body.uploads,approvedBinding);
  const approval=await verifyProtectedApprovalContent(readbackEnv,approvedBinding);
  await verifyOwnerPreflight(readbackEnv,approvedBinding,approval.approved_graph_hash);
  need(Math.floor(Date.now()/1000)<c.expires_at);
  need(env.FATHER_OWNER_INTENTS&&typeof env.FATHER_OWNER_INTENTS.idFromName==='function');
  const stub=env.FATHER_OWNER_INTENTS.get(env.FATHER_OWNER_INTENTS.idFromName('father-owner:'+c.owner));
  return await stub.fetch(new Request('https://owner-intent.invalid'+route,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(route==='/execute'?{binding:binding(c),prewrite:approval.evidence.descriptor}:{binding:binding(c)})}));
 }catch{return Response.json({phase:'blocked',production_enabled:false,retry_allowed:false},{status:403});}
}};
/** Real SQLite-backed DO wrapper. No public namespace route beyond service fetch.
 * The platform namespace is required; caller-selected namespaces are forbidden.
 * DO constructor obtains the same fixed release config, never body owner.
 */
export class FatherOwnerIntent {
 constructor(ctx,env){this.ctx=ctx;this.env=env;}
 async fetch(request){
  try{
   const c=config(this.env);need(this.env.FATHER_SERVICE_LOCAL_REHEARSAL==='local-only-no-geni');
   const route=new URL(request.url).pathname;need(request.method==='POST'&&['/consume','/execute','/complete'].includes(route));
   const text=await request.text();need(text.length<=4096);const body=JSON.parse(text);exact(body,route==='/complete'?['binding','descriptor','source']:route==='/execute'?['binding','prewrite']:['binding']);
   need(JSON.stringify(body.binding)===JSON.stringify(binding(c)));
   if(route==='/complete'){
    const d=body.descriptor;need(d&&d.run_id===c.approved_run);
    return Response.json(await admitPostwriteReceipt(this.ctx.storage,binding(c),{sha256:d.sha256,byte_length:d.byte_length,stage:d.stage,operation_binding:d.operation_binding,run_id:d.run_id,recipient:d.recipient},{source:body.source,descriptor:d}));
   }
   if(route==='/execute'){
    // Payload and credential are deployment owned, never request fields.
    need(typeof this.env.FATHER_EXECUTOR_PAYLOAD_JSON==='string'&&this.env.FATHER_EXECUTOR_PAYLOAD_JSON.length<=65536);
    const payload=JSON.parse(this.env.FATHER_EXECUTOR_PAYLOAD_JSON);need(JSON.stringify(payload)===this.env.FATHER_EXECUTOR_PAYLOAD_JSON);
    const d=body.prewrite;need(d&&d.stage==='pre_write');
    return Response.json(await executeDurableFather(this.ctx.storage,binding(c),payload,this.env.GENI_SECONDARY_ACCESS_TOKEN,{sha256:d.sha256,byte_length:d.byte_length,stage:d.stage,operation_binding:d.operation_binding,run_id:d.run_id,recipient:d.recipient},{source:body.source,descriptor:d}));
   }
   const store=new OfflineCreateIntentCandidate(this.ctx.storage,c.owner);
   const value=await store.consume(binding(c),0);
   return Response.json({phase:value.phase,version:value.version,production_enabled:false,post_permitted:false});
  }catch{return Response.json({phase:'blocked_or_already_consumed',production_enabled:false,retry_allowed:false},{status:409});}
 }
}
