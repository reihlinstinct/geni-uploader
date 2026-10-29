// Fake-only composition seams. No route, network default, or authority claim.
import{checkCustodyContent}from'./scoped-custody-policy.mjs';
import{beginCredentialGeneration,commitCredentialGeneration,inspectCredentialGeneration}from'./credential-custody-state.mjs';
const fail=()=>{throw Error('fake custody persistence blocked');};
const need=x=>{if(!x)fail();};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const parse=raw=>{need(typeof raw==='string'&&raw.length<=49152);const x=JSON.parse(raw);need(JSON.stringify(x)===raw);return x;};
const hash=async raw=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))),b=>b.toString(16).padStart(2,'0')).join('');
// Internal test-only orchestrator. persist is an injected fake adapter seam, not
// a truthy permission callback. No token is returned, printed or released.
export function createFakeCredentialPersistence(config,storage,persist,clock){
 exact(config,['policyJson','contextJson']);const constructor=Object.freeze({...config});
 need(typeof persist==='function'&&typeof clock==='function');
 return async function rehearseCredentialPersistence(input){try{
 exact(input,['bundleJson','expectedGeneration','expectedEpoch']);
 const fixed=Object.freeze({...input,...constructor});
 const bundle=parse(fixed.bundleJson),policy=parse(fixed.policyJson),context=parse(fixed.contextJson);
 need(Number.isSafeInteger(fixed.expectedGeneration)&&fixed.expectedGeneration>=0&&Number.isSafeInteger(fixed.expectedEpoch)&&fixed.expectedEpoch>=0);
 need(bundle.generation===fixed.expectedGeneration+1&&bundle.revocation_epoch===fixed.expectedEpoch);
 const pinsJson=JSON.stringify({owner:policy.owner,slot:policy.slot});
 const state={schema:1,slot:bundle.slot,owner:bundle.owner,connection_id:bundle.connection_id,generation:bundle.generation,revocation_epoch:bundle.revocation_epoch,revoked:false};
 const check=()=>checkCustodyContent({bundleJson:fixed.bundleJson,policyJson:fixed.policyJson,contextJson:fixed.contextJson,stateJson:JSON.stringify(state),now:clock()});
 const guarded={transaction:callback=>storage.transaction(async tx=>{
  check();const wrapped={get:async key=>{check();const value=await tx.get(key);check();return value;},put:async(key,value)=>{check();await tx.put(key,value);check();}};
  const result=await callback(wrapped);check();return result;
 })};
 check();const digest=await hash(fixed.bundleJson);check();
 await beginCredentialGeneration(guarded,pinsJson,JSON.stringify({expected_generation:fixed.expectedGeneration,expected_epoch:fixed.expectedEpoch,connection_id:bundle.connection_id,bundle_sha256:digest}));
 // Any failure from here leaves the reservation unavailable. Never auto-retry,
 // erase, rollback to an old credential or infer a remote success from timeout.
 check();
 const pending=await inspectCredentialGeneration(guarded,pinsJson);
 need(JSON.stringify(pending)===JSON.stringify({...state,revoked:true}));check();
 const result=await persist(Object.freeze({bundleJson:fixed.bundleJson,policyJson:fixed.policyJson,contextJson:fixed.contextJson,bundle_sha256:digest}));
 exact(result,['phase','bundle_sha256']);need(result.phase==='fake_environment_bundle_persisted'&&result.bundle_sha256===digest);check();
 const current=await inspectCredentialGeneration(guarded,pinsJson);
 need(JSON.stringify(current)===JSON.stringify({...state,revoked:true}));check();
 await commitCredentialGeneration(guarded,pinsJson,JSON.stringify({generation:bundle.generation,revocation_epoch:bundle.revocation_epoch,connection_id:bundle.connection_id,bundle_sha256:digest}));
 const active=await inspectCredentialGeneration(guarded,pinsJson);
 need(JSON.stringify(active)===JSON.stringify(state));check();
 return Object.freeze({phase:'fake_credential_persistence_rehearsed',authenticated:false,write_permitted:false});
}catch{fail();}};
}
