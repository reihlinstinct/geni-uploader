// Dormant private Node issuer. No deployed caller or service-config adapter.
import crypto,{createHash,createPrivateKey,createPublicKey,randomBytes}from'node:crypto';
import fs from'node:fs/promises';
import{constants}from'node:fs';
import{spawnSync}from'node:child_process';
import{inspectLiveProtectedCapture}from'./live-protected-capture.mjs';
import{reservePrivateIssuanceAttempt}from'./private-issuance-journal.mjs';
import{verifySignedFatherRelease}from'./signed-father-release-policy.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('private release issuer blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
function fresh(p){const now=Math.floor(Date.now()/1000);need(Number.isSafeInteger(p.issued_at)&&Number.isSafeInteger(p.expires_at)&&p.issued_at<=now&&now<p.expires_at);}
async function readPrivateKey(path){
 need(typeof path==='string'&&path.startsWith('/')&&typeof process.getuid==='function');
 const fd=await fs.open(path,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);const bytes=Buffer.alloc(4097);
 try{
  const st=await fd.stat();need(st.isFile()&&st.uid===process.getuid()&&(st.mode&0o7777)===0o600&&st.size>0&&st.size<=4096);
  let size=0;for(;;){const r=await fd.read(bytes,size,bytes.length-size,null);size+=r.bytesRead;need(size<=4096);if(r.bytesRead===0)break;}
  need(size===st.size);const key=createPrivateKey(bytes.subarray(0,size));need(key.asymmetricKeyType==='ed25519');return key;
 }finally{bytes.fill(0);await fd.close();}
}
export async function issuePrivateFatherRelease(env,approvalBytes){
 try{
  const raw=env.FATHER_ISSUER_CONFIG_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_ISSUER_CONFIG_SHA256);const c=JSON.parse(raw);need(JSON.stringify(c)===raw);
  exact(c,['mode','production_enabled','binding','run_id','namespace_id','service_sha','executor_sha','workflow_sha','issuer_sha','key_id','public_key_der_base64','validity_seconds']);need(c.mode==='private_exact_father_release_issuer'&&c.production_enabled===false&&Number.isSafeInteger(c.validity_seconds)&&c.validity_seconds>0&&c.validity_seconds<=900);
  exact(c.binding,['owner','connection','plan','payload','artifact','policy']);need(typeof c.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(c.run_id));need(/^[a-f0-9]{32}$/.test(c.namespace_id));for(const k of ['service_sha','executor_sha','workflow_sha','issuer_sha'])need(typeof c[k]==='string'&&/^[a-f0-9]{40}$/.test(c[k]));
  const journalRaw=env.FATHER_ISSUANCE_JOURNAL_JSON;need(typeof journalRaw==='string'&&hash(journalRaw)===env.FATHER_ISSUANCE_JOURNAL_SHA256);const journal=JSON.parse(journalRaw);need(JSON.stringify(journal.binding)===JSON.stringify(c.binding)&&journal.run_id===c.run_id&&journal.issuer_sha===c.issuer_sha);
  need(approvalBytes instanceof Uint8Array&&approvalBytes.length>0&&approvalBytes.length<=65536);const bytes=Buffer.from(approvalBytes),record=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));need(JSON.stringify(record)===bytes.toString('utf8'));
  const validation=spawnSync('python3',['-c','import json,sys;from single_human_approval_record import validate;validate(json.load(sys.stdin))'],{cwd:new URL('..',import.meta.url),input:bytes,timeout:5000,maxBuffer:65536,stdio:['pipe','pipe','pipe']});need(!validation.error&&validation.status===0);
  const p=record.pins;need(p.owner===c.binding.owner&&p.connection_id===c.binding.connection&&p.payload_hash===c.binding.payload&&p.artifact_hash===c.binding.artifact&&p.policy_hash===c.binding.policy&&p.run_id===c.run_id&&p.run_attempt===1&&p.service_sha===c.service_sha&&p.executor_sha===c.executor_sha&&p.workflow_sha===c.workflow_sha);
  // Only a separately provisioned exclusive-purpose 0600 key file, not caller bytes.
  fresh(p);const key=await readPrivateKey(env.FATHER_RELEASE_PRIVATE_KEY_PATH);const der=createPublicKey(key).export({type:'spki',format:'der'});need(der.toString('base64')===c.public_key_der_base64&&hash(der)===c.key_id);
  const approval=await inspectLiveProtectedCapture(env,record,{...c.binding,run_id:c.run_id});need(approval.api_capture_correlated===true&&approval.static_plan_bound===true);
  fresh(p);const reservation=await reservePrivateIssuanceAttempt(env);need(reservation.phase==='private_issuance_attempt_reserved_bytes_verified');
  fresh(p);const now=Math.floor(Date.now()/1000),policy={schema_version:1,mode:'exact_single_father_release',operation:'single_father_add_parent',max_post_count:1,binding:c.binding,run_id:c.run_id,run_attempt:1,namespace_id:c.namespace_id,service_sha:c.service_sha,executor_sha:c.executor_sha,workflow_sha:c.workflow_sha,issued_at:now,expires_at:Math.min(now+c.validity_seconds,p.expires_at),key_id:c.key_id,grant_id:randomBytes(32).toString('hex')};
  const envelope=JSON.stringify({policy,signature:crypto.sign(null,Buffer.from(JSON.stringify(policy)),key).toString('base64url')});verifySignedFatherRelease({FATHER_SIGNED_RELEASE_JSON:envelope,FATHER_RELEASE_PUBLIC_KEY_DER_BASE64:c.public_key_der_base64,FATHER_RELEASE_KEY_ID:c.key_id},c.binding,{run_id:c.run_id,run_attempt:1,namespace_id:c.namespace_id,service_sha:c.service_sha,executor_sha:c.executor_sha,workflow_sha:c.workflow_sha});
  return{phase:'private_signed_release_pending_installed_config_verification',private_signed_release_json:envelope,issuance_receipt:reservation.receipt,post_permitted:false,production_enabled:false};
 }catch{throw Error('private release issuer stopped; inspect issuance slot before any new attempt');}
}
