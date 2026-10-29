// Dormant content/freshness checks only. Not authentication or Geni permission.
const fail=()=>{throw Error('credential custody blocked');};
const need=x=>{if(!x)fail();};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const integer=x=>need(Number.isSafeInteger(x)&&x>=0&&x<2**40);
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
const credential=x=>need(typeof x==='string'&&x.length>0&&x.length<=16384&&!/[\s\x00-\x1f\x7f]/.test(x));
// Canonical input transport rejects duplicate keys, whitespace variants, unsafe
// numbers, inherited properties and getters before any policy decision.
const parse=raw=>{
 need(typeof raw==='string'&&raw.length>0&&raw.length<=49152);
 let value;try{value=JSON.parse(raw);}catch{fail();}
 need(JSON.stringify(value)===raw);return value;
};
const bundleKeys=['schema','slot','owner','repository_id','environment','secret','connection_id','generation','revocation_epoch','issued_at','provider_expires_at','expires_at','access_token','refresh_token'];
const policyKeys=['schema','slot','owner','repository_id','environment','secret','max_lifetime_seconds','executor_sha','workflow_sha','run_id','run_attempt','approval_expires_at'];
const stateKeys=['schema','slot','owner','connection_id','generation','revocation_epoch','revoked'];
const contextKeys=['slot','owner','repository_id','environment','secret','executor_sha','workflow_sha','run_id','run_attempt'];
const destinationKeys=['slot','owner','repository_id','environment','secret'];
function validate(bundle,policy,state,context,now){
 exact(bundle,bundleKeys);exact(policy,policyKeys);exact(state,stateKeys);exact(context,contextKeys);
 need(bundle.schema===1&&policy.schema===1&&state.schema===1);
 need(policy.slot==='secondary'&&typeof policy.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(policy.owner));
 need(typeof policy.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(policy.repository_id));
 need(typeof policy.environment==='string'&&/^[A-Za-z0-9_-]{1,80}$/.test(policy.environment));
 need(typeof policy.secret==='string'&&/^GENI_[A-Z0-9_]{1,80}$/.test(policy.secret));
 for(const key of destinationKeys)need(bundle[key]===policy[key]&&context[key]===policy[key]);
 need(state.slot===policy.slot&&state.owner===policy.owner);
 for(const key of ['executor_sha','workflow_sha']){hex(policy[key],40);need(context[key]===policy[key]);}
 need(typeof policy.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(policy.run_id));
 need(policy.run_attempt===1&&context.run_attempt===1&&context.run_id===policy.run_id);
 integer(now);integer(policy.max_lifetime_seconds);integer(policy.approval_expires_at);
 // Maximum accepted lifetime is a reviewed candidate, never a native Secret TTL.
 need(policy.max_lifetime_seconds>0&&policy.max_lifetime_seconds<=900&&now<policy.approval_expires_at);
 for(const key of ['issued_at','provider_expires_at','expires_at','generation','revocation_epoch'])integer(bundle[key]);
 for(const key of ['generation','revocation_epoch'])integer(state[key]);
 need(bundle.generation>0&&state.generation===bundle.generation&&state.revocation_epoch===bundle.revocation_epoch);
 hex(bundle.connection_id,64);need(state.connection_id===bundle.connection_id&&state.revoked===false);
 need(bundle.issued_at<=now&&bundle.expires_at>bundle.issued_at&&bundle.provider_expires_at>bundle.issued_at);
 need(bundle.expires_at<=bundle.provider_expires_at&&bundle.expires_at-bundle.issued_at<=policy.max_lifetime_seconds);
 need(now<bundle.expires_at&&now<bundle.provider_expires_at);
 credential(bundle.access_token);credential(bundle.refresh_token);
 return Object.freeze({phase:'credential_content_current_not_permission',connection_id:bundle.connection_id,
  generation:bundle.generation,revocation_epoch:bundle.revocation_epoch,
  expires_at:Math.min(bundle.expires_at,bundle.provider_expires_at,policy.approval_expires_at),
  authenticated:false,write_permitted:false});
}
export function checkCustodyContent({bundleJson,policyJson,stateJson,contextJson,now}){
 try{return validate(parse(bundleJson),parse(policyJson),parse(stateJson),parse(contextJson),now);}catch{fail();}
}
// Revalidate a fresh external revocation/generation snapshot after every awaited
// dependency. Frozen source strings cannot be changed while the read is pending.
// The reader is a dependency seam, not proof that its state is authoritative.
export async function recheckCustodyAfterWait(input,readState,clock){
 try{
  exact(input,['bundleJson','policyJson','stateJson','contextJson']);
  const snapshot=Object.freeze({...input});
  need(typeof readState==='function'&&typeof clock==='function');
  checkCustodyContent({...snapshot,now:clock()});
  const current=await readState();
  const descriptor=checkCustodyContent({...snapshot,stateJson:current,now:clock()});
  need(current===snapshot.stateJson); // Any concurrent state change stops, never refreshes/retries.
  return descriptor;
 }catch{fail();}
}
