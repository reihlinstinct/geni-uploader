// Dormant verification only. No issuer, route or replacement for the closed gate.
const need=x=>{if(!x)throw Error('worker signed release blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const fields=['owner','connection','plan','payload','artifact','policy'];
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
const bytes=s=>new TextEncoder().encode(s);
const base64=b=>btoa(String.fromCharCode(...b));
function decode(s){return Uint8Array.from(atob(s),x=>x.charCodeAt(0));}
export async function verifyWorkerFatherRelease(env,binding,context){try{
 exact(binding,fields);exact(context,['run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha']);
 const raw=env.FATHER_SIGNED_RELEASE_JSON;need(typeof raw==='string'&&bytes(raw).length<=16384);
 const envelope=JSON.parse(raw);need(JSON.stringify(envelope)===raw);exact(envelope,['policy','signature']);
 const p=envelope.policy;exact(p,['schema_version','mode','operation','max_post_count','binding','run_id','run_attempt','namespace_id','service_sha','executor_sha','workflow_sha','issued_at','expires_at','key_id','grant_id']);
 need(p.schema_version===1&&p.mode==='exact_single_father_release'&&p.operation==='single_father_add_parent'&&p.max_post_count===1);
 exact(p.binding,fields);need(fields.every(k=>p.binding[k]===binding[k]));
 need(typeof binding.owner==='string'&&/^profile-[1-9][0-9]{0,29}(?![\s\S])/.test(binding.owner)&&typeof binding.connection==='string'&&/^[A-Za-z0-9_-]{1,100}(?![\s\S])/.test(binding.connection));
 for(const k of ['plan','payload','artifact','policy'])hex(binding[k],64);
 need(context.run_attempt===1&&p.run_attempt===1&&typeof p.run_id==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(p.run_id));
 for(const k of ['run_id','namespace_id','service_sha','executor_sha','workflow_sha'])need(p[k]===context[k]);
 hex(p.namespace_id,32);for(const k of ['service_sha','executor_sha','workflow_sha'])hex(p[k],40);hex(p.grant_id,64);hex(p.key_id,64);
 const now=Math.floor(Date.now()/1000);need(Number.isSafeInteger(p.issued_at)&&Number.isSafeInteger(p.expires_at)&&p.issued_at<=now&&now<p.expires_at&&p.expires_at-p.issued_at>0&&p.expires_at-p.issued_at<=900);
 const publicRaw=env.FATHER_RELEASE_PUBLIC_KEY_DER_BASE64;need(typeof publicRaw==='string'&&publicRaw.length<=256&&/^[A-Za-z0-9+/]+={0,2}(?![\s\S])/.test(publicRaw));const der=decode(publicRaw);need(base64(der)===publicRaw&&await sha(der)===env.FATHER_RELEASE_KEY_ID&&p.key_id===env.FATHER_RELEASE_KEY_ID);
 // RFC8410 Ed25519 SPKI: fixed algorithm identifier, no parameters,32-byte key.
 const prefix=[48,42,48,5,6,3,43,101,112,3,33,0];need(der.length===44&&prefix.every((x,i)=>der[i]===x));
 const key=await crypto.subtle.importKey('spki',der,{name:'Ed25519'},false,['verify']);need(key.type==='public'&&!key.extractable&&key.algorithm.name==='Ed25519'&&key.usages.length===1&&key.usages[0]==='verify');
 need(typeof envelope.signature==='string'&&/^[A-Za-z0-9_-]{86}(?![\s\S])/.test(envelope.signature));const signature=decode(envelope.signature.replace(/-/g,'+').replace(/_/g,'/')+'==');need(signature.length===64&&base64(signature).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_')===envelope.signature&&await crypto.subtle.verify('Ed25519',key,signature,bytes(JSON.stringify(p))));
 // Crypto awaits must not turn a pre-expiry check into an expired acceptance.
 const policy_sha256=await sha(bytes(JSON.stringify(p)));
 const end=Math.floor(Date.now()/1000);need(p.issued_at<=end&&end<p.expires_at);
 return Object.freeze({phase:'signed_exact_run_policy_verified',grant_id:p.grant_id,policy_sha256,namespace_id:p.namespace_id,run_id:p.run_id,post_permitted:false,production_enabled:false});
}catch{throw Error('worker signed release blocked');}}
