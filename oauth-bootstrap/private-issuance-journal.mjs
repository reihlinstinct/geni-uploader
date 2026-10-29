// Dormant private issuer exclusion. No signing, deploy, vendor or reset import.
import{createHash}from'node:crypto';
const hash=(x,a='sha256')=>createHash(a).update(x).digest('hex');
const need=x=>{if(!x)throw Error('private issuance journal blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
function config(env){
 const raw=env.FATHER_ISSUANCE_JOURNAL_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_ISSUANCE_JOURNAL_SHA256);const c=JSON.parse(raw);need(JSON.stringify(c)===raw);
 exact(c,['mode','production_enabled','repository_id','owner','repo','binding','run_id','issuer_sha']);need(c.mode==='private_issuance_attempt_journal'&&c.production_enabled===false);
 for(const k of ['owner','repo'])need(typeof c[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(c[k]));
 for(const k of ['repository_id','run_id'])need(typeof c[k]==='string'&&/^[1-9][0-9]{0,19}$/.test(c[k]));hex(c.issuer_sha,40);
 const b=c.binding;exact(b,['owner','connection','plan','payload','artifact','policy']);need(typeof b.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(b.owner)&&typeof b.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(b.connection));for(const k of ['plan','payload','artifact','policy'])hex(b[k],64);
 need(typeof env.PRIVATE_ISSUER_GIT_CREDENTIAL==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(env.PRIVATE_ISSUER_GIT_CREDENTIAL));return c;
}
function unique(text){const value=JSON.parse(text),tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const key=JSON.parse(t),set=stack.at(-1);need(set instanceof Set&&!set.has(key));set.add(key);}need(stack.length<=12);}return value;}
export async function reservePrivateIssuanceAttempt(env){
 const partial={blob:null,tree:null,commit:null,ref_create_attempted:false};const ctl=new AbortController();let active=true,timer;
 try{
  const c=config(env),root='/repos/'+c.owner+'/'+c.repo,ref='refs/heads/father-issuance-'+hash(c.binding.owner),record={schema_version:1,mode:'private_issuance_attempt_reserved',binding:c.binding,run_id:c.run_id,issuer_sha:c.issuer_sha,signing_attempted:false,service_config_attempted:false,post_permitted:false,production_enabled:false},bytes=Buffer.from(JSON.stringify(record)),blobId=hash(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1');let calls=0;
  async function request(method,path,body,absent=false){
   need(active&&++calls<=10);const r=await fetch('https://api.github.com'+path,{method,redirect:'manual',signal:ctl.signal,headers:{Authorization:'Bearer '+env.PRIVATE_ISSUER_GIT_CREDENTIAL,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},...(body?{body:JSON.stringify(body)}:{})});need(active&&!r.redirected&&!r.headers.get('link'));
   if(absent&&r.status===404){await r.body?.cancel();return null;}need(r.status===(method==='POST'?201:200)&&r.body);const declared=r.headers.get('content-length');need(declared===null||(/^[0-9]+$/.test(declared)&&Number(declared)<=65536));const reader=r.body.getReader(),chunks=[];let size=0;try{for(;;){const x=await reader.read();if(x.done)break;size+=x.value.length;need(active&&size<=65536);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}return unique(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));
  }
  const work=async()=>{
   const repo=await request('GET','/repositories/'+c.repository_id);need(String(repo.id)===c.repository_id&&repo.private===true&&repo.full_name===c.owner+'/'+c.repo);
   need(await request('GET',root+'/git/ref/'+ref.slice(5),undefined,true)===null);
   const blob=await request('POST',root+'/git/blobs',{content:bytes.toString('base64'),encoding:'base64'});need(blob.sha===blobId);partial.blob=blobId;
   const entry={path:'issuance-attempt.json',mode:'100644',type:'blob',sha:blobId},tree=await request('POST',root+'/git/trees',{tree:[entry]});hex(tree.sha,40);need(tree.truncated===false&&tree.tree?.length===1);const e=tree.tree[0];for(const k of Object.keys(entry))need(e[k]===entry[k]);partial.tree=tree.sha;
   const commit=await request('POST',root+'/git/commits',{message:'Reserve private issuance attempt',tree:tree.sha,parents:[]});hex(commit.sha,40);need(commit.tree?.sha===tree.sha&&commit.parents?.length===0);partial.commit=commit.sha;
   const check=await request('GET',root+'/git/commits/'+commit.sha);need(check.sha===commit.sha&&check.tree?.sha===tree.sha&&check.parents?.length===0);
   // Only create, never update/delete/force. Concurrent creates get one winner.
   partial.ref_create_attempted=true;const created=await request('POST',root+'/git/refs',{ref,sha:commit.sha});need(created.ref===ref&&created.object?.type==='commit'&&created.object.sha===commit.sha);
   const remote=await request('GET',root+'/git/blobs/'+blobId);need(remote.sha===blobId&&remote.encoding==='base64'&&remote.size===bytes.length&&typeof remote.content==='string');const encoded=remote.content.replace(/\n/g,''),read=Buffer.from(encoded,'base64');need(read.toString('base64')===encoded&&read.equals(bytes));
   const final=await request('GET',root+'/git/ref/'+ref.slice(5));need(final.ref===ref&&final.object?.type==='commit'&&final.object.sha===commit.sha);
   return{phase:'private_issuance_attempt_reserved_bytes_verified',receipt:{...partial},post_permitted:false,production_enabled:false};
  };
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('private issuance journal blocked'));},10000);});return await Promise.race([work(),deadline]);
 }catch{const e=Error('private issuance journal blocked; inspect private slot before any new issuance');e.partial_receipt=Object.freeze({...partial});throw e;}finally{active=false;ctl.abort();clearTimeout(timer);}
}
