// Protected-job private immutable approval writer. No installed caller or permit.
import{createHash}from'node:crypto';
import{staticPlanFingerprint}from'./live-protected-capture.mjs';
import{spawnSync}from'node:child_process';
const hash=(x,a='sha256')=>createHash(a).update(x).digest('hex');
const need=x=>{if(!x)throw Error('private approval writer blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
export async function persistPrivateApprovalRecord(env,recordBytes,onProgress){
 const ctl=new AbortController();let timer,active=true;const partial={blob:null,tree:null,commit:null,ref_update_attempted:false};
 try{
  need(recordBytes instanceof Uint8Array&&recordBytes.length>0&&recordBytes.length<=65536);const bytes=Buffer.from(recordBytes),record=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  // Require canonical writer bytes, so duplicate/hidden JSON keys cannot survive.
  need(JSON.stringify(record)===bytes.toString('utf8')&&record.schema_version===2&&record.production_enabled===false&&record.mode==='single_human_approval_content');
  // Reuse the full existing Python v2 validator in the protected Node job;
  // this module is never bundled into the Worker. No caller-selected command.
  const validation=spawnSync('python3',['-c','import json,sys;from single_human_approval_record import validate;validate(json.load(sys.stdin))'],{cwd:new URL('..',import.meta.url),input:bytes,timeout:5000,maxBuffer:65536,stdio:['pipe','pipe','pipe']});
  need(!validation.error&&validation.status===0);
  const raw=env.FATHER_APPROVAL_STORAGE_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_APPROVAL_STORAGE_SHA256);const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','repository_id','owner','repo','branch','parent_commit','path','plan_fingerprint','run_id']);
  need(c.mode==='unreleased_private_approval_writer'&&c.production_enabled===false&&staticPlanFingerprint(record)===c.plan_fingerprint&&record.pins.run_id===c.run_id&&record.pins.run_attempt===1);
  need(env.GITHUB_RUN_ID===c.run_id&&env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_REF==='refs/heads/master'&&env.GITHUB_EVENT_NAME==='workflow_dispatch');
  for(const k of['owner','repo','branch','path'])need(typeof c[k]==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(c[k])&&!['.','..'].includes(c[k]));need(/^[1-9][0-9]{0,19}$/.test(c.repository_id)&&/^[a-f0-9]{40}$/.test(c.parent_commit));
  const credential=env.PRIVATE_GIT_CREDENTIAL;need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}$/.test(credential)&&typeof onProgress==='function');const root='/repos/'+c.owner+'/'+c.repo;let n=0;
  const request=async(method,path,body)=>{
   need(active&&++n<=11);const r=await fetch('https://api.github.com'+path,{method,redirect:'manual',signal:ctl.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},...(body?{body:JSON.stringify(body)}:{})});
   need(active&&r.status===(method==='POST'?201:200)&&!r.redirected&&!r.headers.get('link')&&r.body);const len=r.headers.get('content-length');need(len===null||(/^[0-9]+$/.test(len)&&Number(len)<=1048576));const reader=r.body.getReader(),chunks=[];let size=0;try{for(;;){const x=await reader.read();if(x.done)break;size+=x.value.length;need(active&&size<=1048576);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));
  };
  const progress=()=>onProgress(Object.freeze({...partial}));
  const work=async()=>{
   const repo=await request('GET','/repositories/'+c.repository_id);need(String(repo.id)===c.repository_id&&repo.private===true&&repo.full_name===c.owner+'/'+c.repo);
   const ref=await request('GET',root+'/git/ref/heads/'+c.branch);need(ref.ref==='refs/heads/'+c.branch&&ref.object?.type==='commit'&&ref.object.sha===c.parent_commit);
   const parent=await request('GET',root+'/git/commits/'+c.parent_commit);need(parent.sha===c.parent_commit&&/^[a-f0-9]{40}$/.test(parent.tree?.sha));
   const old=await request('GET',root+'/git/trees/'+parent.tree.sha);need(old.sha===parent.tree.sha&&old.truncated===false&&Array.isArray(old.tree)&&old.tree.length<=1000&&!old.tree.some(e=>e.path===c.path));
   const blobId=hash(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1'),blob=await request('POST',root+'/git/blobs',{content:bytes.toString('base64'),encoding:'base64'});need(blob.sha===blobId);partial.blob=blob.sha;await progress();
   const tree=await request('POST',root+'/git/trees',{base_tree:parent.tree.sha,tree:[{path:c.path,mode:'100644',type:'blob',sha:blobId}]});need(/^[a-f0-9]{40}$/.test(tree.sha)&&tree.truncated===false&&Array.isArray(tree.tree)&&tree.tree.length===old.tree.length+1);const found=tree.tree.filter(e=>e.path===c.path);need(found.length===1&&found[0].sha===blobId&&found[0].mode==='100644'&&found[0].type==='blob');for(const e of old.tree){const match=tree.tree.filter(v=>v.path===e.path);need(match.length===1&&match[0].sha===e.sha&&match[0].mode===e.mode&&match[0].type===e.type);}partial.tree=tree.sha;await progress();
   const commit=await request('POST',root+'/git/commits',{message:'Persist private approval record',tree:tree.sha,parents:[c.parent_commit]});need(/^[a-f0-9]{40}$/.test(commit.sha)&&commit.tree?.sha===tree.sha&&commit.parents?.length===1&&commit.parents[0].sha===c.parent_commit);partial.commit=commit.sha;await progress();
   const check=await request('GET',root+'/git/commits/'+commit.sha);need(check.sha===commit.sha&&check.tree?.sha===tree.sha&&check.parents?.length===1&&check.parents[0].sha===c.parent_commit);
   partial.ref_update_attempted=true;await progress();const update=await request('PATCH',root+'/git/refs/heads/'+c.branch,{sha:commit.sha,force:false});need(update.ref==='refs/heads/'+c.branch&&update.object?.type==='commit'&&update.object.sha===commit.sha);
   const remote=await request('GET',root+'/git/blobs/'+blobId);need(remote.sha===blobId&&remote.encoding==='base64'&&remote.size===bytes.length&&typeof remote.content==='string');const encoded=remote.content.replace(/\n/g,''),read=Buffer.from(encoded,'base64');need(read.toString('base64')===encoded&&read.equals(bytes));
   const final=await request('GET',root+'/git/ref/heads/'+c.branch);need(final.ref==='refs/heads/'+c.branch&&final.object?.type==='commit'&&final.object.sha===commit.sha);
   return{phase:'private_approval_remote_bytes_verified',source:{repository_id:c.repository_id,owner:c.owner,repo:c.repo,commit:commit.sha,path:c.path,blob_sha:blobId,content_sha256:hash(bytes)},post_permitted:false,production_enabled:false};
  };
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('private approval writer blocked'));},10000);});return await Promise.race([work(),deadline]);
 }catch{const e=Error('private approval writer blocked');e.partial_receipt=Object.freeze({...partial});throw e;}finally{active=false;ctl.abort();clearTimeout(timer);}
}
