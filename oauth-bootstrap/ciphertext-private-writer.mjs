// Unconnected private Git evidence writer. No credential lookup or live route.
import {createHash} from 'node:crypto';
const fail=()=>{throw Error('private evidence persistence blocked');};const need=x=>{if(!x)fail();};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(x));
const sha=(x,alg='sha256')=>createHash(alg).update(x).digest('hex');
const blob=x=>sha(Buffer.concat([Buffer.from('blob '+x.length+'\0'),x]),'sha1');
const STAGES=['pre_write','acknowledgment','readback','reconciliation'];
function validate(bytes,d,p){
 need(bytes instanceof Uint8Array&&bytes.length>0&&bytes.length<=1048576);
 exact(d,['schema_version','mode','production_enabled','schema','stage','sha256','byte_length','recipient','operation_binding','run_id','run_attempt','blob_id']);
 need(d.schema_version===1&&d.mode==='offline_ciphertext_descriptor'&&d.production_enabled===false&&d.schema==='geni-evidence-ciphertext-v1'&&STAGES.includes(d.stage));
 for(const k of ['sha256','recipient','operation_binding'])hex(d[k],64);hex(d.blob_id,40);
 need(d.byte_length===bytes.length&&d.sha256===sha(bytes)&&d.blob_id===blob(Buffer.from(bytes)));
 need(typeof d.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(d.run_id)&&d.run_attempt===1);
 // Screening is NOT encryption proof. Approved encryption boundary remains external.
 const b=Buffer.from(bytes);need(!['{','[','<','-----BEGIN','%PDF','PK\x03\x04','\ufeff'].some(s=>b.subarray(0,Buffer.byteLength(s)).equals(Buffer.from(s))));
 try{const s=new TextDecoder('utf-8',{fatal:true}).decode(b);let printable=0;for(const c of s)if(/[\P{C}\n\r\t]/u.test(c))printable++;need(printable<0.95*[...s].length);}catch(e){if(e?.message==='private evidence persistence blocked')throw e;}
 exact(p,['repository_id','owner','repo','branch','parent_commit','path','recipient','operation_binding','run_id','stage','existing_total_bytes']);
 need(typeof p.repository_id==='string'&&/^[1-9][0-9]{0,19}$/.test(p.repository_id));
 for(const k of ['owner','repo','branch'])need(typeof p[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/.test(p[k]));hex(p.parent_commit,40);
 // One ordinary root filename only. Directory/tree traversal is deliberately excluded.
 need(typeof p.path==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(p.path)&&!['.','..'].includes(p.path));
 for(const k of ['recipient','operation_binding','run_id','stage'])need(d[k]===p[k]);
 need(Number.isSafeInteger(p.existing_total_bytes)&&p.existing_total_bytes>=0&&p.existing_total_bytes+bytes.length<=8388608);
}
function decode(raw){
 const s=new TextDecoder('utf-8',{fatal:true}).decode(raw),value=JSON.parse(s),tokens=s.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];
 for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const set=stack.at(-1),key=JSON.parse(t);need(set instanceof Set&&!set.has(key));set.add(key);}need(stack.length<=12);}
 return value;
}
/** This candidate accepts only reviewed release config and already-encrypted bytes.
 * No production caller imports it. It does not authenticate either input's origin.
 * Journal partial IDs via the callback without clearing consumed create intent.
 */
export async function persistCiphertext({bytes,descriptor,storagePins,credential,onProgress}){
 const ctl=new AbortController();let timer;let active=true;const partial={blob:null,tree:null,commit:null,ref_update_attempted:false};
 try{
  validate(bytes,descriptor,storagePins);need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(credential));need(typeof onProgress==='function');
  // Freeze a copy before the first await. Callers cannot mutate what is uploaded.
  bytes=Buffer.from(bytes);descriptor=structuredClone(descriptor);storagePins=structuredClone(storagePins);
  const p=storagePins,root='/repos/'+p.owner+'/'+p.repo;let requests=0;
  const request=async(method,route,body)=>{
   need(active&&!ctl.signal.aborted&&++requests<=12);const r=await fetch('https://api.github.com'+route,{method,redirect:'manual',signal:ctl.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},...(body?{body:JSON.stringify(body)}:{})});
   need(active&&!ctl.signal.aborted);need(r.status===(method==='POST'?201:200)&&!r.redirected&&!r.headers.get('link')&&r.body);
   const h=r.headers.get('content-length');if(h!==null)need(/^[0-9]+$/.test(h)&&Number(h)<=2097152);
   const reader=r.body.getReader(),chunks=[];let total=0;try{for(;;){const {done,value}=await reader.read();if(done)break;total+=value.length;need(total<=2097152);chunks.push(value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   return decode(Buffer.concat(chunks));
  };
  const progress=async()=>{await onProgress(Object.freeze({...partial}));};
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('private evidence persistence blocked'));},10000);});
  const work=async()=>{
   const repo=await request('GET','/repositories/'+p.repository_id);need(String(repo.id)===p.repository_id&&repo.private===true&&repo.full_name===p.owner+'/'+p.repo);
   const ref=await request('GET',root+'/git/ref/heads/'+p.branch);need(ref.ref==='refs/heads/'+p.branch&&ref.object?.type==='commit'&&ref.object.sha===p.parent_commit);
   const parent=await request('GET',root+'/git/commits/'+p.parent_commit);need(parent.sha===p.parent_commit);hex(parent.tree?.sha,40);
   const oldTree=await request('GET',root+'/git/trees/'+parent.tree.sha);need(oldTree.sha===parent.tree.sha&&oldTree.truncated===false&&Array.isArray(oldTree.tree)&&oldTree.tree.length<=1000&&!oldTree.tree.some(x=>x.path===p.path));
   const b=await request('POST',root+'/git/blobs',{content:bytes.toString('base64'),encoding:'base64'});need(b.sha===descriptor.blob_id);partial.blob=b.sha;await progress();
   const tree=await request('POST',root+'/git/trees',{base_tree:parent.tree.sha,tree:[{path:p.path,mode:'100644',type:'blob',sha:b.sha}]});hex(tree.sha,40);need(tree.truncated===false&&Array.isArray(tree.tree));
   const entries=tree.tree.filter(x=>x.path===p.path);need(entries.length===1&&entries[0].sha===b.sha&&entries[0].type==='blob'&&entries[0].mode==='100644');need(tree.tree.length===oldTree.tree.length+1);for(const prior of oldTree.tree){const same=tree.tree.filter(x=>x.path===prior.path);need(same.length===1&&same[0].sha===prior.sha&&same[0].mode===prior.mode&&same[0].type===prior.type);}
   partial.tree=tree.sha;await progress();
   // Fixed value-free commit message; no raw family fields or approval context.
   const commit=await request('POST',root+'/git/commits',{message:'Persist encrypted evidence',tree:tree.sha,parents:[p.parent_commit]});hex(commit.sha,40);need(commit.tree?.sha===tree.sha&&Array.isArray(commit.parents)&&commit.parents.length===1&&commit.parents[0].sha===p.parent_commit);partial.commit=commit.sha;await progress();
   // Inspect the immutable created commit before changing the branch ref.
   const checkCommit=await request('GET',root+'/git/commits/'+commit.sha);need(checkCommit.sha===commit.sha&&checkCommit.tree?.sha===tree.sha&&Array.isArray(checkCommit.parents)&&checkCommit.parents.length===1&&checkCommit.parents[0].sha===p.parent_commit);
   partial.ref_update_attempted=true;await progress();const updated=await request('PATCH',root+'/git/refs/heads/'+p.branch,{sha:commit.sha,force:false});need(updated.ref==='refs/heads/'+p.branch&&updated.object?.type==='commit'&&updated.object.sha===commit.sha);
   const remote=await request('GET',root+'/git/blobs/'+b.sha);need(remote.sha===b.sha&&remote.encoding==='base64'&&remote.size===bytes.length&&typeof remote.content==='string');const encoded=remote.content.replace(/\n/g,'');need(/^[A-Za-z0-9+/]*={0,2}$/.test(encoded));const rb=Buffer.from(encoded,'base64');need(rb.toString('base64')===encoded&&rb.equals(bytes)&&blob(rb)===b.sha&&sha(rb)===descriptor.sha256);
   const finalRef=await request('GET',root+'/git/ref/heads/'+p.branch);need(finalRef.ref==='refs/heads/'+p.branch&&finalRef.object?.type==='commit'&&finalRef.object.sha===commit.sha);
   return {phase:'private_ciphertext_remote_bytes_verified',descriptor:{...descriptor,commit:commit.sha},receipt:{...partial},production_enabled:false,ciphertext_proved:false,authority:false,retention_proved:false};
  };
  return await Promise.race([work(),deadline]);
 }catch{const e=Error('private evidence persistence blocked');e.partial_receipt=Object.freeze({...partial});throw e;}finally{active=false;ctl.abort();clearTimeout(timer);}
}
