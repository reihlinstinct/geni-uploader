import test from 'node:test';import assert from 'node:assert/strict';
import{checkCustodyContent,recheckCustodyAfterWait}from './scoped-custody-policy.mjs';
const encode=JSON.stringify;
function fixture(){
 const common={slot:'secondary',owner:'profile-999001',repository_id:'999002',environment:'ZZ-father',secret:'GENI_ZZ_CUSTODY'};
 const b={schema:1,...common,connection_id:'a'.repeat(64),generation:2,revocation_epoch:3,issued_at:100,provider_expires_at:1200,expires_at:900,access_token:'ZZ-ACCESS-SENTINEL',refresh_token:'ZZ-REFRESH-SENTINEL'};
 const p={schema:1,...common,max_lifetime_seconds:900,executor_sha:'b'.repeat(40),workflow_sha:'c'.repeat(40),run_id:'999003',run_attempt:1,approval_expires_at:800};
 const s={schema:1,slot:b.slot,owner:b.owner,connection_id:b.connection_id,generation:2,revocation_epoch:3,revoked:false};
 const c={...common,executor_sha:p.executor_sha,workflow_sha:p.workflow_sha,run_id:p.run_id,run_attempt:1};
 return {b,p,s,c,input:{bundleJson:encode(b),policyJson:encode(p),stateJson:encode(s),contextJson:encode(c),now:200}};
}
const refresh=f=>({...f.input,bundleJson:encode(f.b),policyJson:encode(f.p),stateJson:encode(f.s),contextJson:encode(f.c)});
const blocked=fn=>assert.throws(fn,e=>e.message==='credential custody blocked'&&!/SENTINEL/.test(String(e)));
test('current content is fixed descriptor only, never token or permission',()=>{const f=fixture(),r=checkCustodyContent(f.input);assert.equal(r.expires_at,800);assert.equal(r.write_permitted,false);assert.equal(r.authenticated,false);assert.ok(Object.isFrozen(r));assert.doesNotMatch(encode(r),/SENTINEL/);});
for(const target of ['b','p','s','c']){
 test('unknown/missing fields rejected '+target,()=>{for(const key of Object.keys(fixture()[target])){const f=fixture();delete f[target][key];blocked(()=>checkCustodyContent(refresh(f)));}const f=fixture();f[target].ZZ='ZZ-SENTINEL';blocked(()=>checkCustodyContent(refresh(f)));});
}
for(const key of ['slot','owner','repository_id','environment','secret']){
 for(const target of ['b','c'])test('wrong destination '+target+key,()=>{const f=fixture();f[target][key]='ZZ-wrong';blocked(()=>checkCustodyContent(refresh(f)));});
}
for(const [target,key,value]of [
 ['b','schema',true],['p','schema',true],['s','schema',true],['b','issued_at',201],['b','expires_at',200],['b','expires_at',1001],['b','provider_expires_at',150],['b','generation',1],['b','generation',true],['b','revocation_epoch',2],['b','connection_id','d'.repeat(64)],['b','access_token','ZZ\nTOKEN'],['b','refresh_token',''],['s','revoked',true],['s','revoked',0],['s','generation',3],['s','revocation_epoch',4],['s','owner','profile-999004'],['p','max_lifetime_seconds',901],['p','max_lifetime_seconds',0],['p','run_attempt',2],['p','approval_expires_at',200],['c','executor_sha','d'.repeat(40)],['c','workflow_sha','d'.repeat(40)],['c','run_id','999004'],['c','run_attempt',2],
])test('reject mutation '+target+key+String(value),()=>{const f=fixture();f[target][key]=value;blocked(()=>checkCustodyContent(refresh(f)));});
for(const value of [-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER,true,'200'])test('invalid clock '+String(value),()=>{const f=fixture();blocked(()=>checkCustodyContent({...f.input,now:value}));});
test('exact expiry boundaries fail and one second before succeeds',()=>{const f=fixture();assert.equal(checkCustodyContent({...f.input,now:799}).write_permitted,false);blocked(()=>checkCustodyContent({...f.input,now:800}));f.p.approval_expires_at=1300;blocked(()=>checkCustodyContent({...refresh(f),now:900}));});
test('duplicate JSON keys and noncanonical/unsafe numeric values rejected',()=>{const f=fixture();for(const raw of [f.input.bundleJson.replace('"schema":1','"schema":1,"schema":1'),' '+f.input.bundleJson,f.input.bundleJson.replace('"generation":2','"generation":9007199254740993')])blocked(()=>checkCustodyContent({...f.input,bundleJson:raw}));});
test('revocation/rotation/expiry while awaiting stops, no retry or token result',async()=>{for(const kind of ['revoke','rotate','expire','error']){const f=fixture(),{now,...input}=f.input;let t=now,calls=0;await assert.rejects(recheckCustodyAfterWait(input,async()=>{calls++;if(kind==='revoke')f.s.revoked=true;if(kind==='rotate')f.s.generation++;if(kind==='expire')t=800;if(kind==='error')throw Error('ZZ-SENTINEL');return encode(f.s);},()=>t),/^Error: credential custody blocked$/);assert.equal(calls,1);}});
test('detached strings survive caller mutation across await; state remains exact',async()=>{const f=fixture(),{now,...input}=f.input;const r=await recheckCustodyAfterWait(input,async()=>{input.bundleJson='ZZ-MUTATED';return f.input.stateJson;},()=>now);assert.equal(r.authenticated,false);assert.equal(r.write_permitted,false);});
test('invalid initial content never calls reader',async()=>{const f=fixture(),{now,...input}=f.input;input.bundleJson='{}';let calls=0;await assert.rejects(recheckCustodyAfterWait(input,async()=>{calls++;return f.input.stateJson;},()=>now));assert.equal(calls,0);});

test('final newline in all pinned identifiers is rejected',()=>{for(const key of ['slot','owner','repository_id','environment','secret','executor_sha','workflow_sha','run_id']){const f=fixture();for(const target of ['b','p','s','c'])if(Object.hasOwn(f[target],key))f[target][key]+='\n';blocked(()=>checkCustodyContent(refresh(f)));}});
