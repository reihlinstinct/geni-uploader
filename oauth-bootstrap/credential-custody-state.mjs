// Dormant credential-only CAS primitive. No token, public route or identity proof.
const fail=()=>{throw Error('credential custody state blocked');};
const need=x=>{if(!x)fail();};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const number=x=>need(Number.isSafeInteger(x)&&x>=0&&x<2**40);
const hex=x=>need(typeof x==='string'&&/^[a-f0-9]{64}(?![\s\S])/.test(x));
const key='credential-generation-state-v1';
const fields=['schema','owner','slot','generation','revocation_epoch','phase','connection_id','bundle_sha256'];
function pins(raw){
 need(typeof raw==='string'&&raw.length<1024);const p=JSON.parse(raw);need(JSON.stringify(p)===raw);
 exact(p,['owner','slot']);need(p.slot==='secondary'&&typeof p.owner==='string'&&/^profile-[1-9][0-9]{0,29}(?![\s\S])/.test(p.owner));return p;
}
function checked(record,p){
 exact(record,fields);need(record.schema===1&&record.owner===p.owner&&record.slot===p.slot);
 number(record.generation);number(record.revocation_epoch);need(record.generation>0);
 need(['pending','active','revoked'].includes(record.phase));hex(record.connection_id);hex(record.bundle_sha256);return record;
}
const descriptor=r=>Object.freeze({schema:1,slot:r.slot,owner:r.owner,connection_id:r.connection_id,
 generation:r.generation,revocation_epoch:r.revocation_epoch,revoked:r.phase!=='active'});
async function tx(storage,raw,callback){
 const p=pins(raw);need(storage&&typeof storage.transaction==='function');
 return storage.transaction(async t=>callback(t,p));
}
export async function beginCredentialGeneration(storage,pinsJson,requestJson){try{
 need(typeof requestJson==='string'&&requestJson.length<1024);const r=JSON.parse(requestJson);need(JSON.stringify(r)===requestJson);
 exact(r,['expected_generation','expected_epoch','connection_id','bundle_sha256']);
 number(r.expected_generation);number(r.expected_epoch);need(r.expected_generation<2**40-1);hex(r.connection_id);hex(r.bundle_sha256);
 return await tx(storage,pinsJson,async(t,p)=>{
  const old=await t.get(key);
  if(old===undefined)need(r.expected_generation===0&&r.expected_epoch===0);
  else{checked(old,p);need(old.phase!=='pending'&&old.generation===r.expected_generation&&old.revocation_epoch===r.expected_epoch&&old.connection_id!==r.connection_id);}
  const next={schema:1,...p,generation:r.expected_generation+1,revocation_epoch:r.expected_epoch,
   phase:'pending',connection_id:r.connection_id,bundle_sha256:r.bundle_sha256};
  await t.put(key,next);return Object.freeze({phase:'credential_persistence_reserved',...descriptor(next),bundle_sha256:next.bundle_sha256,write_permitted:false});
 });
}catch{fail();}}
export async function commitCredentialGeneration(storage,pinsJson,requestJson){try{
 need(typeof requestJson==='string'&&requestJson.length<1024);const r=JSON.parse(requestJson);need(JSON.stringify(r)===requestJson);
 exact(r,['generation','revocation_epoch','connection_id','bundle_sha256']);number(r.generation);number(r.revocation_epoch);hex(r.connection_id);hex(r.bundle_sha256);
 return await tx(storage,pinsJson,async(t,p)=>{
  const old=checked(await t.get(key),p);need(old.phase==='pending');
  for(const field of ['generation','revocation_epoch','connection_id','bundle_sha256'])need(old[field]===r[field]);
  const next={...old,phase:'active'};await t.put(key,next);
  return Object.freeze({phase:'credential_persistence_committed_not_authority',...descriptor(next),write_permitted:false});
 });
}catch{fail();}}
export async function revokeCredentialGeneration(storage,pinsJson,requestJson){try{
 need(typeof requestJson==='string'&&requestJson.length<512);const r=JSON.parse(requestJson);need(JSON.stringify(r)===requestJson);
 exact(r,['expected_generation','expected_epoch']);number(r.expected_generation);number(r.expected_epoch);
 return await tx(storage,pinsJson,async(t,p)=>{
  const old=checked(await t.get(key),p);need(old.generation===r.expected_generation&&old.revocation_epoch===r.expected_epoch&&old.phase!=='revoked'&&old.revocation_epoch<2**40-1);
  const next={...old,phase:'revoked',revocation_epoch:old.revocation_epoch+1};await t.put(key,next);
  return Object.freeze({phase:'local_credential_revoked_not_provider_erasure',...descriptor(next),write_permitted:false});
 });
}catch{fail();}}
export async function inspectCredentialGeneration(storage,pinsJson){try{
 return await tx(storage,pinsJson,async(t,p)=>descriptor(checked(await t.get(key),p)));
}catch{fail();}}
