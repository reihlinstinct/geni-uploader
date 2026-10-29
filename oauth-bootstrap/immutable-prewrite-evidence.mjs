// Immutable private pre-write evidence readback. No create permission or decrypt.
import{createHash}from'node:crypto';
const hash=(b,a='sha256')=>createHash(a).update(b).digest('hex');
const need=x=>{if(!x)throw Error('immutable prewrite evidence blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
async function verifyImmutableEvidence(env,expectedBinding,stage){
 const ctl=new AbortController();let timer,active=true;
 try{
  const raw=env.FATHER_PREWRITE_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_PREWRITE_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','source','descriptor','credential_sha256','binding']);
  exact(c.binding,['owner','connection','plan','payload','artifact','policy','run_id']);
  exact(expectedBinding,Object.keys(c.binding));need(Object.keys(c.binding).every(k=>c.binding[k]===expectedBinding[k]));
  need(c.mode===(stage==='pre_write'?'unreleased_private_prewrite_admission':'unreleased_private_postwrite_admission')&&c.production_enabled===false);
  const s=c.source,d=c.descriptor;need(d.operation_binding===c.binding.plan&&d.run_id===c.binding.run_id);exact(s,['repository_id','owner','repo','commit','path']);
  need(typeof s.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(s.repository_id));for(const k of['owner','repo','path'])need(typeof s[k]==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(s[k])&&!['.','..'].includes(s[k]));hex(s.commit,40);
  exact(d,['schema_version','mode','production_enabled','schema','stage','sha256','byte_length','recipient','operation_binding','run_id','run_attempt','blob_id','commit']);
  need(d.schema_version===1&&d.mode==='offline_ciphertext_descriptor'&&d.production_enabled===false&&d.schema==='geni-evidence-ciphertext-v1'&&d.stage===stage&&d.run_attempt===1&&d.commit===s.commit);
  for(const k of['sha256','recipient','operation_binding'])hex(d[k],64);hex(d.blob_id,40);hex(c.credential_sha256,64);
  need(Number.isSafeInteger(d.byte_length)&&d.byte_length>22&&d.byte_length<=1048576&&typeof d.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(d.run_id));
  need(typeof env.GENI_SECONDARY_ACCESS_TOKEN==='string'&&env.GENI_SECONDARY_ACCESS_TOKEN.length>0&&hash(env.GENI_SECONDARY_ACCESS_TOKEN)===c.credential_sha256);
  const credential=env.PRIVATE_GIT_CREDENTIAL;need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(credential));
  const root='/repos/'+s.owner+'/'+s.repo;let calls=0;
  const get=async route=>{
   need(active&&++calls<=4);const r=await fetch('https://api.github.com'+route,{redirect:'manual',signal:ctl.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'X-GitHub-Api-Version':'2022-11-28'}});
   need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const len=r.headers.get('content-length');need(len===null||(/^[0-9]+$/.test(len)&&Number(len)<=2097152));
   const reader=r.body.getReader(),chunks=[];let n=0;try{for(;;){const x=await reader.read();if(x.done)break;n+=x.value.length;need(active&&n<=2097152);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));
   // Canonical duplicate rejection, independent of whitespace and key ordering.
   const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];
   for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const k=JSON.parse(t),set=stack.at(-1);need(set instanceof Set&&!set.has(k));set.add(k);}need(stack.length<=12);}
   return JSON.parse(text);
  };
  const work=async()=>{
   const repo=await get('/repositories/'+s.repository_id);need(String(repo.id)===s.repository_id&&repo.private===true&&repo.full_name===s.owner+'/'+s.repo);
   const commit=await get(root+'/git/commits/'+s.commit);need(commit.sha===s.commit);hex(commit.tree?.sha,40);
   const tree=await get(root+'/git/trees/'+commit.tree.sha);need(tree.sha===commit.tree.sha&&tree.truncated===false&&Array.isArray(tree.tree)&&tree.tree.length<=1000);
   const matches=tree.tree.filter(e=>e.path===s.path);need(matches.length===1&&matches[0].type==='blob'&&matches[0].mode==='100644'&&matches[0].sha===d.blob_id);
   const b=await get(root+'/git/blobs/'+d.blob_id);need(b.sha===d.blob_id&&b.encoding==='base64'&&b.size===d.byte_length&&typeof b.content==='string');
   const encoded=b.content.replace(/\n/g,'');need(/^[A-Za-z0-9+/]*={0,2}$/.test(encoded));const bytes=Buffer.from(encoded,'base64');need(bytes.toString('base64')===encoded&&bytes.length===d.byte_length&&hash(bytes)===d.sha256&&hash(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1')===d.blob_id);
   need(bytes.subarray(0,22).equals(Buffer.from('age-encryption.org/v1\n')));
   return{phase:stage==='pre_write'?'immutable_private_prewrite_bytes_verified':'immutable_private_postwrite_bytes_verified',descriptor:structuredClone(d),credential_binding_verified:true,age_header_present:true,encryption_provenance_verified:false,recipient_decryptability_verified:false,post_permitted:false,production_enabled:false};
  };
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('immutable prewrite evidence blocked'));},10000);});
  return await Promise.race([work(),deadline]);
 }catch{throw Error('immutable prewrite evidence blocked');}finally{active=false;ctl.abort();clearTimeout(timer);}
}

export function verifyImmutablePrewriteEvidence(env,binding){return verifyImmutableEvidence(env,binding,'pre_write');}
// Same bounded immutable byte checks, but a separate deployment-owned stage.
export function verifyImmutablePostwriteEvidence(env,binding){return verifyImmutableEvidence({...env,FATHER_PREWRITE_RELEASE_JSON:env.FATHER_POSTWRITE_RELEASE_JSON,FATHER_PREWRITE_RELEASE_SHA256:env.FATHER_POSTWRITE_RELEASE_SHA256},binding,'readback');}
