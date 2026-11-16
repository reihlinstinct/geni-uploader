import test from'node:test';import assert from'node:assert/strict';import{build}from'esbuild';import{Miniflare,convertV4MiniflareOptions}from'miniflare';import{mkdtemp,rm}from'node:fs/promises';import{join}from'node:path';import{tmpdir}from'node:os';import{collectDurableFatherRecovery}from'./durable-father-executor.mjs';
const b={owner:'profile-999001',connection:'ZZ-secondary',plan:'1'.repeat(64),payload:'2'.repeat(64),artifact:'3'.repeat(64),policy:'4'.repeat(64)};
test('shipped recovery gate blocks before storage or vendor request',async t=>{let n=0;t.mock.method(globalThis,'fetch',()=>n++);await assert.rejects(collectDurableFatherRecovery({transaction:()=>n++},b,'ZZtoken123'));assert.equal(n,0);});
for(const known of [null,'profile-999003'])test('real SQLite consumed recovery known='+known+' does GET only and preserves intent',{timeout:45000},async()=>{
 const entry=`import{collectDurableFatherRecovery}from'./durable-father-executor.mjs';import{OfflineCreateIntentCandidate}from'./create-intent-candidate.mjs';export class ZZ{constructor(ctx){this.s=ctx.storage;}async fetch(r){const x=await r.json();if(x.seed){const st=new OfflineCreateIntentCandidate(this.s,x.binding.owner);await st.consume(x.binding,0);if(x.known)await st.advance(x.binding,1,'acknowledge','a'.repeat(64),x.known);return Response.json({ok:true});}if(x.inspect)return Response.json(await this.s.get('intent'));return Response.json(await collectDurableFatherRecovery(this.s,x.binding,'ZZtoken123'));}}export default{fetch(r,e){return e.ZZ.get(e.ZZ.idFromName('ZZ-owner')).fetch(r)}};`;
 const bundle=await build({stdin:{contents:entry,resolveDir:new URL('.',import.meta.url).pathname,sourcefile:'ZZ-recovery.mjs'},bundle:true,format:'esm',platform:'browser',external:['node:crypto'],write:false,plugins:[{name:'ZZ-test-only-release',setup(build){build.onLoad({filter:/father-release-gate\.mjs$/},()=>({contents:'export function requireFatherRelease(){}',loader:'js'}));}}]});
 const dir=await mkdtemp(join(tmpdir(),'ZZ-recovery-'));let mf;const seen=[],uid='union-999004';const start=()=>new Miniflare({...convertV4MiniflareOptions({name:'ZZ-recovery',modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-10-01',compatibilityFlags:['nodejs_compat'],durableObjects:{ZZ:{className:'ZZ',useSQLite:true}},outboundService:r=>{assert.equal(r.method,'GET');seen.push(r.url);if(r.url.endsWith('/profile?only_ids=true'))return Response.json({id:b.owner});if(r.url.includes('/immediate-family'))return Response.json({focus:{id:b.owner},nodes:{[b.owner]:{id:b.owner},'profile-999003':{id:'profile-999003'},[uid]:{id:uid,partners:['profile-999003'],children:[b.owner]}}});if(r.url.includes('/union-'))return Response.json({id:uid,partners:['profile-999003'],children:[b.owner]});return Response.json({id:known,public:false});}}),resourcePersistencePath:dir,isolatedResourcePersistencePath:dir});
 const send=x=>mf.dispatchFetch('https://zz.invalid/',{method:'POST',body:JSON.stringify(x)});
 try{mf=start();await send({seed:true,binding:b,known});const before=await(await send({inspect:true})).json();const out=await(await send({binding:b})).json();assert.equal(out.created_id,known);assert.equal(out.identity_resolved,known!==null);assert.equal(out.intent_verified,false);assert.equal(out.observation_complete,true);assert.equal(seen.length,known?4:2);assert.deepEqual(await(await send({inspect:true})).json(),before);await mf.dispose();mf=start();assert.deepEqual(await(await send({inspect:true})).json(),before);}finally{if(mf)await mf.dispose();await rm(dir,{recursive:true,force:true});}
});
// #808: characterization tests. Each pins a CURRENT recovery gap on purpose, so the
// gap stays explicit; a future change that removes one must flip its test deliberately.
import{createHash}from'node:crypto';
const canonical808=x=>Array.isArray(x)?'['+x.map(canonical808).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical808(x[k])).join(',')+'}':JSON.stringify(x);
const p808={names:{he:{first_name:'ZZאב'},en:{first_name:'ZZFather'}},first_name:'ZZFather',gender:'male',is_alive:true,public:false};
const b808={...b,payload:createHash('sha256').update(canonical808(p808)).digest('hex')},d808={sha256:'5'.repeat(64),byte_length:100,stage:'pre_write',operation_binding:b808.plan,run_id:'999021',recipient:'6'.repeat(64)};
// Saved acknowledgment, then /reserve either never runs or commits with its response lost.
async function reservation808(reserve){
 const entry=`import{executeDurableFather,reservePostwriteBudget,collectDurableFatherRecovery}from'./durable-father-executor.mjs';export class ZZ{constructor(ctx){this.s=ctx.storage;}async fetch(r){const v=await r.json(),s=this.s;try{if(v.action==='inspect')return Response.json({intent:await s.get('intent')??null,ledger:await s.get('evidence-ledger')??null,reservation:await s.get('postwrite-reservation')??null,receipt:await s.get('postwrite-receipt')??null});if(v.action==='reserve')return Response.json(await reservePostwriteBudget(s,v.binding,v.run_id));if(v.action==='recover')return Response.json(await collectDurableFatherRecovery(s,v.binding,'ZZtoken123'));return Response.json(await executeDurableFather(s,v.binding,v.payload,'ZZtoken123',v.prewrite));}catch{return Response.json({phase:'blocked'},{status:409});}}}export default{fetch(r,e){return e.ZZ.get(e.ZZ.idFromName('ZZ-owner-808')).fetch(r)}};`;
 const bundle=await build({stdin:{contents:entry,resolveDir:new URL('.',import.meta.url).pathname,sourcefile:'ZZ-recovery-808.mjs'},bundle:true,format:'esm',platform:'browser',external:['node:crypto'],write:false,plugins:[{name:'ZZ-test-only-release',setup(build){build.onLoad({filter:/father-release-gate\.mjs$/},()=>({contents:'export function requireFatherRelease(){}',loader:'js'}));}}]});
 const id='profile-'+(999000+22),uid='union-'+(999000+23),api='https://www.geni.com/api/',profile={...p808,id},union={id:uid,partners:[id],children:[b.owner]};
 const family={focus:{id:b.owner},nodes:{[b.owner]:{id:b.owner},[id]:{...profile},[uid]:{...union}}};
 const dir=await mkdtemp(join(tmpdir(),'ZZ-recovery-808-'));let mf;const seen=[];
 const outbound=r=>{seen.push(r.method+' '+r.url);if(r.method==='POST'){assert.equal(r.url,api+b.owner+'/add-parent');return Response.json(profile);}assert.equal(r.method,'GET');
  if(r.url===api+'profile?only_ids=true')return Response.json({id:b.owner});if(r.url===api+b.owner+'/immediate-family?only_ids=true')return Response.json(family);
  if(r.url===api+id+'?only_ids=true')return Response.json(profile);if(r.url===api+uid+'?only_ids=true')return Response.json(union);throw Error('ZZ unexpected '+r.url);};
 const start=()=>new Miniflare({...convertV4MiniflareOptions({name:'ZZ-recovery-808',modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-10-01',compatibilityFlags:['nodejs_compat'],durableObjects:{ZZ:{className:'ZZ',useSQLite:true}},outboundService:outbound}),resourcePersistencePath:dir,isolatedResourcePersistencePath:dir});
 const send=x=>mf.dispatchFetch('https://zz.invalid/',{method:'POST',body:JSON.stringify(x)}),inspect=async()=>(await send({action:'inspect'})).json();
 try{
  mf=start();const executed=await(await send({binding:b808,payload:p808,prewrite:d808})).json();
  assert.equal(executed.phase,'consumed_readback_consistent_evidence_pending');assert.equal(executed.created_id,id);
  if(reserve==='committed'){const lost=await send({action:'reserve',binding:b808,run_id:d808.run_id});assert.equal(lost.status,200);await lost.body.cancel();}
  await mf.dispose();mf=start();const state=await inspect();
  const recovered=await send({action:'recover',binding:b808});assert.equal(recovered.status,200);
  return{id,state,recovery:await recovered.json(),posts:seen.filter(x=>x.startsWith('POST ')).length};
 }finally{if(mf)await mf.dispose();await rm(dir,{recursive:true,force:true});}
}
test('pins current gap (#808 finding 1): recovery snapshot omits a committed postwrite reservation',{timeout:90000},async()=>{
 // A future fix that adds the reservation to the recovery snapshot must flip this test on purpose.
 const none=await reservation808('none'),committed=await reservation808('committed');
 assert.equal(none.state.reservation,null);
 assert.equal(committed.state.reservation.phase,'reserved');assert.equal(committed.state.reservation.prior_total,d808.byte_length);
 for(const x of[none,committed]){
  assert.equal(x.posts,1);assert.equal(x.state.receipt,null);
  assert.deepEqual(Object.keys(x.recovery.private_evidence).sort(),['binding','family','intent','ledger','mode','profile','receipt','schema_version','self','union']);
  assert.equal('reservation' in x.recovery,false);assert.equal(x.recovery.private_evidence.receipt,null);
  assert.equal(JSON.stringify(x.recovery).includes('prior_total'),false);assert.equal(JSON.stringify(x.recovery).includes('byte_limit'),false);
 }
 // Gap: recovery evidence cannot tell a committed reservation (response lost) from none at all.
 assert.deepEqual(committed.recovery,none.recovery);
});
test('pins current gap (#808 finding 3): only the service-side durable intent retains the created ID after reservation response loss',{timeout:45000},async()=>{
 // Runner-side counterpart: oauth-bootstrap/protected-father-runner.test.mjs (#808 finding 3). A future fix must flip both on purpose.
 const x=await reservation808('committed');
 assert.equal(x.state.intent.phase,'uncertain');assert.equal(x.state.intent.created_id,x.id);assert.equal(x.state.reservation.phase,'reserved');assert.equal(x.state.receipt,null);
 assert.equal(x.recovery.created_id,x.id);assert.equal(x.recovery.identity_resolved,true);assert.equal(x.recovery.private_evidence.intent.created_id,x.id);
});
