// Dormant release-policy verifier. Not wired to or a replacement for closed gate.
import{createHash,createPublicKey,verify}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('signed father release policy blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const fields=['owner','connection','plan','payload','artifact','policy'];
/** All env parameters are deployment-owned. No body-supplied key/config. A
 * signature proves key possession, not owner authority or deployment provenance.
 * Actual public key/source permissions and signed grant issuance need review.
 */
export function verifySignedFatherRelease(env,binding,context){
 exact(binding,fields);exact(context,['run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha']);
 const raw=env.FATHER_SIGNED_RELEASE_JSON;need(typeof raw==='string'&&Buffer.byteLength(raw)<=16384);
 const envelope=JSON.parse(raw);need(JSON.stringify(envelope)===raw);exact(envelope,['policy','signature']);
 const p=envelope.policy;exact(p,['schema_version','mode','operation','max_post_count','binding','run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha','issued_at','expires_at','key_id','grant_id']);
 need(p.schema_version===1&&p.mode==='exact_single_father_release'&&p.operation==='single_father_add_parent'&&p.max_post_count===1);
 exact(p.binding,fields);need(fields.every(k=>p.binding[k]===binding[k]));
 need(typeof binding.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(binding.owner)&&typeof binding.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(binding.connection));
 for(const k of ['plan','payload','artifact','policy'])need(typeof binding[k]==='string'&&/^[a-f0-9]{64}$/.test(binding[k]));
 need(context.run_attempt===1&&p.run_attempt===1&&typeof p.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(p.run_id));
 for(const k of ['run_id','namespace_id','service_sha','executor_sha','workflow_sha'])need(p[k]===context[k]);
 need(typeof p.namespace_id==='string'&&/^[a-f0-9]{32}$/.test(p.namespace_id));
 for(const k of ['service_sha','executor_sha','workflow_sha'])need(typeof p[k]==='string'&&/^[a-f0-9]{40}$/.test(p[k]));
 need(typeof p.grant_id==='string'&&/^[a-f0-9]{64}$/.test(p.grant_id)&&typeof p.key_id==='string'&&/^[a-f0-9]{64}$/.test(p.key_id));
 const now=Math.floor(Date.now()/1000);need(Number.isSafeInteger(p.issued_at)&&Number.isSafeInteger(p.expires_at)&&p.issued_at<=now&&now<p.expires_at&&p.expires_at-p.issued_at>0&&p.expires_at-p.issued_at<=900);
 const publicRaw=env.FATHER_RELEASE_PUBLIC_KEY_DER_BASE64;need(typeof publicRaw==='string'&&publicRaw.length<=256&&/^[A-Za-z0-9+/]+={0,2}$/.test(publicRaw));const der=Buffer.from(publicRaw,'base64');need(der.toString('base64')===publicRaw&&hash(der)===env.FATHER_RELEASE_KEY_ID&&p.key_id===env.FATHER_RELEASE_KEY_ID);
 const key=createPublicKey({key:der,format:'der',type:'spki'});need(key.asymmetricKeyType==='ed25519'&&key.export({format:'der',type:'spki'}).equals(der));
 need(typeof envelope.signature==='string'&&/^[A-Za-z0-9_-]{86}$/.test(envelope.signature));const signature=Buffer.from(envelope.signature,'base64url');need(signature.length===64&&signature.toString('base64url')===envelope.signature&&verify(null,Buffer.from(JSON.stringify(p)),key,signature));
 return Object.freeze({phase:'signed_exact_run_policy_verified',grant_id:p.grant_id,policy_sha256:hash(JSON.stringify(p)),namespace_id:p.namespace_id,run_id:p.run_id,post_permitted:false,production_enabled:false});
}
