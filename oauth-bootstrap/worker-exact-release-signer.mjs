// Dormant internal signing candidate. No route, authority or deployed key custody.
import{verifyWorkerFatherRelease}from'./worker-signed-father-release.mjs';
const fail=()=>{throw Error('worker release signing candidate blocked');};
const need=x=>{if(!x)fail();};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...keys].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
const bytes=s=>new TextEncoder().encode(s);
const base64=x=>btoa(String.fromCharCode(...x));
function checked(raw){
 need(typeof raw==='string'&&bytes(raw).length<=8192);const p=JSON.parse(raw);need(JSON.stringify(p)===raw);
 exact(p,['schema_version','mode','operation','max_post_count','binding','run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha','issued_at','expires_at','key_id','grant_id']);
 need(p.schema_version===1&&p.mode==='exact_single_father_release'&&p.operation==='single_father_add_parent'&&p.max_post_count===1&&p.run_attempt===1);
 exact(p.binding,['owner','connection','plan','payload','artifact','policy']);
 need(typeof p.binding.owner==='string'&&/^profile-[1-9][0-9]{0,29}(?![\s\S])/.test(p.binding.owner));
 need(typeof p.binding.connection==='string'&&/^[A-Za-z0-9_-]{1,100}(?![\s\S])/.test(p.binding.connection));
 for(const k of ['plan','payload','artifact','policy'])hex(p.binding[k],64);
 need(typeof p.run_id==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(p.run_id));hex(p.namespace_id,32);
 for(const k of ['service_sha','executor_sha','workflow_sha'])hex(p[k],40);hex(p.key_id,64);hex(p.grant_id,64);
 need(Number.isSafeInteger(p.issued_at)&&Number.isSafeInteger(p.expires_at)&&p.issued_at>=0&&p.expires_at<2**40&&p.expires_at>p.issued_at&&p.expires_at-p.issued_at<=900);
 return p;
}
const fresh=p=>{const now=Math.floor(Date.now()/1000);need(p.issued_at<=now&&now<p.expires_at);};
export async function signExactWorkerReleaseCandidate(privateKey,policyJson,verificationEnv){try{
 const p=checked(policyJson);exact(verificationEnv,['FATHER_RELEASE_PUBLIC_KEY_DER_BASE64','FATHER_RELEASE_KEY_ID']);
 const fixed={...verificationEnv};need(fixed.FATHER_RELEASE_KEY_ID===p.key_id);
 need(privateKey instanceof CryptoKey&&privateKey.type==='private'&&!privateKey.extractable&&privateKey.algorithm.name==='Ed25519'&&privateKey.usages.length===1&&privateKey.usages[0]==='sign');
 fresh(p);
 const signature=new Uint8Array(await crypto.subtle.sign('Ed25519',privateKey,bytes(policyJson)));
 fresh(p);need(signature.length===64);
 const envelope=JSON.stringify({policy:p,signature:base64(signature).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_')});
 const context=Object.fromEntries(['run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha'].map(k=>[k,p[k]]));
 const verified=await verifyWorkerFatherRelease({...fixed,FATHER_SIGNED_RELEASE_JSON:envelope},p.binding,context);
 fresh(p);need(verified.post_permitted===false&&verified.production_enabled===false);
 return Object.freeze({phase:'private_worker_signature_candidate_not_authority',private_signed_release_json:envelope,post_permitted:false,production_enabled:false});
}catch{fail();}}
