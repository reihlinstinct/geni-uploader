// Node protected-job boundary only. No workflow installation, dispatch or Geni.
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {persistCiphertext} from './ciphertext-private-writer.mjs';
const sha=(b,alg='sha256')=>createHash(alg).update(b).digest('hex');
const need=x=>{if(!x)throw Error('protected job evidence blocked');};
function encrypt(recipient,bytes){return new Promise((resolve,reject)=>{
 const child=spawn('age',['-r',recipient],{stdio:['pipe','pipe','pipe'],env:{...process.env}});
 const chunks=[];let n=0,active=true;const fail=()=>{if(!active)return;active=false;child.kill('SIGKILL');reject(Error('protected job encryption blocked'));};
 const timer=setTimeout(fail,30000);
 child.on('error',()=>{clearTimeout(timer);fail();});child.stdin.on('error',fail);child.stderr.resume();
 child.stdout.on('data',v=>{if(!active)return;n+=v.length;if(n>1048576)fail();else chunks.push(v);});
 child.on('close',code=>{clearTimeout(timer);if(!active)return;active=false;
  const output=Buffer.concat(chunks);if(code!==0||!output.subarray(0,22).equals(Buffer.from('age-encryption.org/v1\n'))){reject(Error('protected job encryption blocked'));return;}resolve(output);
 });
 child.stdin.end(bytes);
});}
/** Only deployment/job environment, no caller-selected destination/credential.
 * Uses the already reviewed age CLI and existing Git writer, not a new cipher.
 * The returned opaque descriptor is NOT authority for a service POST.
 */
export async function persistProtectedJobEvidence(env,plaintext,onProgress){
 try{
  need(plaintext instanceof Uint8Array&&plaintext.length>0&&plaintext.length<=1048000);
  const raw=env.FATHER_EVIDENCE_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&sha(raw)===env.FATHER_EVIDENCE_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw&&Object.keys(c).sort().join(',')==='mode,production_enabled,recipient,storage');
  need(c.mode==='unreleased_protected_job_evidence'&&c.production_enabled===false&&typeof c.recipient==='string'&&/^age1[0-9a-z]{58}$/.test(c.recipient));
  need(env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_REF==='refs/heads/master'&&env.GITHUB_EVENT_NAME==='workflow_dispatch'&&env.GITHUB_RUN_ID===c.storage.run_id);
  need(c.storage.recipient===sha(c.recipient));
  need(typeof env.PRIVATE_GIT_CREDENTIAL==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(env.PRIVATE_GIT_CREDENTIAL)&&typeof onProgress==='function');
  const bytes=await encrypt(c.recipient,Buffer.from(plaintext));
  const d={schema_version:1,mode:'offline_ciphertext_descriptor',production_enabled:false,schema:'geni-evidence-ciphertext-v1',stage:c.storage.stage,sha256:sha(bytes),byte_length:bytes.length,recipient:c.storage.recipient,operation_binding:c.storage.operation_binding,run_id:c.storage.run_id,run_attempt:1,blob_id:sha(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1')};
  const result=await persistCiphertext({bytes,descriptor:d,storagePins:c.storage,credential:env.PRIVATE_GIT_CREDENTIAL,onProgress});
  return{...result,age_encryption_performed:true,post_permitted:false};
 }catch(error){const blocked=Error('protected job evidence blocked');if(error?.partial_receipt)blocked.partial_receipt=error.partial_receipt;throw blocked;}
}
