// Fixed deployment-binding boundary. Not a production route or deployed grant.
import {createHash} from 'node:crypto';
import {fetchPrivateApproval} from './approval-admission.mjs';
import {persistCiphertext} from './ciphertext-private-writer.mjs';
const fail=()=>{throw Error('reviewed release boundary blocked');};const need=x=>{if(!x)fail();};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hash=s=>createHash('sha256').update(s).digest('hex');
const hex=(s,n)=>need(typeof s==='string'&&new RegExp('^[0-9a-f]{'+n+'}$').test(s));
function configuration(raw,pin){
 need(typeof raw==='string'&&Buffer.byteLength(raw)>0&&Buffer.byteLength(raw)<=16384);hex(pin,64);need(hash(raw)===pin);
 // Canonical serialization rejects duplicate keys, whitespace and hidden extras.
 const c=JSON.parse(raw);need(JSON.stringify(c)===raw);
 exact(c,['schema_version','production_enabled','approval_source','storage','expected','operation','run_id','stage','recipient']);
 need(c.schema_version===1&&c.production_enabled===false);
 exact(c.approval_source,['repository_id','owner','repo','commit','path','blob_sha','content_sha256']);
 exact(c.storage,['repository_id','owner','repo','branch','parent_commit','path','existing_total_bytes']);
 exact(c.expected,['service_sha','policy_hash','artifact_hash','payload_hash','owner']);
 for(const k of ['service_sha'])hex(c.expected[k],40);for(const k of ['policy_hash','artifact_hash','payload_hash'])hex(c.expected[k],64);
 need(typeof c.expected.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(c.expected.owner));
 for(const dest of [c.approval_source,c.storage]){
  need(typeof dest.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(dest.repository_id));
  for(const k of ['owner','repo'])need(typeof dest[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(dest[k]));
 }
 need(c.approval_source.repository_id===c.storage.repository_id&&c.approval_source.owner===c.storage.owner&&c.approval_source.repo===c.storage.repo);
 hex(c.approval_source.commit,40);hex(c.approval_source.blob_sha,40);hex(c.approval_source.content_sha256,64);hex(c.storage.parent_commit,40);
 for(const path of [c.approval_source.path,c.storage.path])need(typeof path==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(path));
 need(c.approval_source.path!==c.storage.path&&typeof c.storage.branch==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(c.storage.branch));
 need(Number.isSafeInteger(c.storage.existing_total_bytes)&&c.storage.existing_total_bytes>=0&&c.storage.existing_total_bytes<=8388608);
 hex(c.operation,64);hex(c.recipient,64);need(typeof c.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(c.run_id));need(['pre_write','acknowledgment','readback','reconciliation'].includes(c.stage));
 return structuredClone(c);
}
/** Called by a FUTURE reviewed Worker entrypoint with its platform env, NEVER
 * request JSON. No entrypoint currently imports this. Caller already executing
 * code can supply fake env, so this function is not itself a secure sandbox.
 * Pin and config provenance must be audited at deployment, not inferred here.
 */
export function bindReviewedRelease(env){
 try{
  exact(env,['REVIEWED_RELEASE_JSON','REVIEWED_RELEASE_SHA256','PRIVATE_GIT_CREDENTIAL']);
  const c=configuration(env.REVIEWED_RELEASE_JSON,env.REVIEWED_RELEASE_SHA256);
  need(typeof env.PRIVATE_GIT_CREDENTIAL==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(env.PRIVATE_GIT_CREDENTIAL));
  const credential=env.PRIVATE_GIT_CREDENTIAL;
  return Object.freeze({
   production_enabled:false,
   async fetchApproval(request){
    exact(request,['payload_hash','owner','service_sha','policy_hash','artifact_hash','run_id']);
    for(const k of Object.keys(c.expected))need(request[k]===c.expected[k]);need(request.run_id===c.run_id);
    return fetchPrivateApproval({source:structuredClone(c.approval_source),credential});
   },
   async persistEvidence(request){
    exact(request,['bytes','descriptor','onProgress']);
    const storagePins={...c.storage,recipient:c.recipient,operation_binding:c.operation,run_id:c.run_id,stage:c.stage};
    return persistCiphertext({bytes:request.bytes,descriptor:request.descriptor,storagePins,credential,onProgress:request.onProgress});
   }
  });
 }catch{fail();}
}
