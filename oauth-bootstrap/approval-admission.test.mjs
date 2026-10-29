import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fetchPrivateApproval,admitApproval} from './approval-admission.mjs';
const hash=(x,alg='sha256')=>createHash(alg).update(x).digest('hex');
const now=()=>Math.floor(Date.now()/1000);
const pins=()=>({owner:'profile-999001',connection_id:'ZZ-secondary',operation:'single_father_add_parent',payload_hash:'a'.repeat(64),graph_hash:'b'.repeat(64),data_hash:'c'.repeat(64),executor_sha:'d'.repeat(40),workflow_sha:'e'.repeat(40),artifact_hash:'f'.repeat(64),service_sha:'1'.repeat(40),policy_hash:'2'.repeat(64),recipient:'3'.repeat(64),run_id:'999002',run_attempt:1,nonce:'4'.repeat(64),issued_at:now()-1,expires_at:now()+300});
const approvals={owner:{approver_ref:'5'.repeat(64),evidence_ref:'6'.repeat(64)},human_reviewer:{approver_ref:'7'.repeat(64),evidence_ref:'8'.repeat(64)}};
const excluded=['add_child','add_mother','add_partner','delete','fact_cite','marriage','merge','profile_update','retry','source_upload','tag','union_update'];
function fixture(change=()=>{},rawChange=x=>x){
 const record={schema_version:1,mode:'offline_approval_record',production_enabled:false,pins:pins(),exclusions:[...excluded],approvals:Object.entries(approvals).map(([role,x])=>({role,...x}))};change(record);
 const bytes=Buffer.from(rawChange(JSON.stringify(record))),sha=hash(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1');
 const source={repository_id:'999003',owner:'ZZ-owner',repo:'ZZ-private',commit:'9'.repeat(40),path:'ZZ-approval.json',blob_sha:sha,content_sha256:hash(bytes)};
 const root='/repos/ZZ-owner/ZZ-private';const paths=['/repositories/999003',root+'/git/commits/'+source.commit,root+'/git/trees/'+'a'.repeat(40),root+'/git/blobs/'+sha];
 const bodies=[{id:999003,private:true,full_name:'ZZ-owner/ZZ-private'},{sha:source.commit,tree:{sha:'a'.repeat(40)}},{sha:'a'.repeat(40),truncated:false,tree:[{path:source.path,type:'blob',mode:'100644',sha}]},{sha,size:bytes.length,encoding:'base64',content:bytes.toString('base64')}];
 return {record,bytes,source,paths,bodies};
}
function mock(t,f,alter=(b)=>b,options={}){
 let count=0;t.mock.method(globalThis,'fetch',async(url,opts)=>{
  assert.equal(url,'https://api.github.com'+f.paths[count]);assert.equal(opts.redirect,'error');assert.ok(opts.signal instanceof AbortSignal);
  assert.equal(opts.headers.Authorization,'Bearer ZZsynthetic');assert.equal(opts.headers.Accept,'application/vnd.github+json');
  const b=structuredClone(f.bodies[count]);const index=count++;return Response.json(alter(b,index),options);
 });return()=>count;
}
async function get(f){return fetchPrivateApproval({source:f.source,credential:'ZZsynthetic'});}
function admit(f,r,changes={}){return admitApproval({approvalBytes:f.bytes,expectedPins:f.record.pins,authenticatedRecord:r,expectedApprovals:approvals,nowUnix:now(),...changes});}
test('fixed source provenance plus exact content is never consent',async t=>{
 const f=fixture(),count=mock(t,f),r=await get(f);assert.equal(count(),4);assert.equal(r.owner_approval_verified,false);
 const a=admit(f,r);assert.equal(a.content_consistent,true);assert.equal(a.record_provenance_verified,true);assert.equal(a.owner_approval_verified,false);assert.equal(a.review_provenance_verified,false);assert.equal(a.production_enabled,false);assert.equal(a.post_permitted,false);assert.equal(a.release_gaps.length,3);
 assert.throws(()=>admit(f,{...r}),{message:'approval admission blocked'}); // No forgeable flag envelope.
 f.bytes[0]=0;assert.throws(()=>admit(f,r));
});
for(const field of Object.keys(pins()))test('pin mismatch '+field,async t=>{
 const f=fixture();mock(t,f);const r=await get(f),p=structuredClone(f.record.pins);p[field]=typeof p[field]==='number'?p[field]+1:p[field]+'Z';assert.throws(()=>admit(f,r,{expectedPins:p}));
});
for(const [label,change]of [
 ['public',b=>b.private=false],['wrong repository',b=>b.id=999004],['wrong name',b=>b.full_name='ZZ-other/ZZ-private'],
 ['commit',(_,i,f)=>f.bodies[1].sha='b'.repeat(40)],
])test(label+' refuses remote source',async t=>{
 const f=fixture();if(label==='commit')change(null,null,f);mock(t,f,(b,i)=>{if(i===0&&label!=='commit')change(b);return b;});await assert.rejects(get(f),{message:'approval admission blocked'});
});
for(const [label,idx,key,value]of [
 ['truncated',2,'truncated',true],['tree identity',2,'sha','b'.repeat(40)],['wrong blob identity',3,'sha','b'.repeat(40)],['encoding',3,'encoding','utf8'],['size',3,'size',65537],['bytes size',3,'size',1],['bad base64',3,'content','!!!!'],
])test(label,async t=>{const f=fixture();mock(t,f,(b,i)=>{if(i===idx)b[key]=value;return b;});await assert.rejects(get(f));});
for(const [label,alter]of [
 ['symlink',b=>b.tree[0].mode='120000'],['wrong path',b=>b.tree[0].path='ZZ-other.json'],['duplicate path',b=>b.tree.push({...b.tree[0]})],['wrong leaf',b=>b.tree[0].sha='b'.repeat(40)],['wrong type',b=>b.tree[0].type='tree'],
])test(label,async t=>{const f=fixture();mock(t,f,(b,i)=>{if(i===2)alter(b);return b;});await assert.rejects(get(f));});
for(const [label,change]of [
 ['expired',r=>{r.pins.issued_at=now()-100;r.pins.expires_at=now()-1;}],['future',r=>{r.pins.issued_at=now()+10;r.pins.expires_at=now()+100;}],['window',r=>r.pins.expires_at=now()+901],['self review',r=>r.approvals[1].approver_ref=r.approvals[0].approver_ref],['same evidence',r=>r.approvals[1].evidence_ref=r.approvals[0].evidence_ref],['exclusion',r=>r.exclusions.pop()],['role order',r=>r.approvals.reverse()],['attempt',r=>r.pins.run_attempt=2],['extra',r=>r.fake=true],['mode',r=>r.mode='authenticated'],['enabled',r=>r.production_enabled=true],['schema',r=>r.schema_version=2],
])test(label+' content cannot admit',async t=>{const f=fixture(change);mock(t,f);const r=await get(f);assert.throws(()=>admit(f,r));});
for(const [label,change]of [
 ['duplicate',s=>s.replace('"mode":','"mode":"ZZ","mode":')],['depth',()=>JSON.stringify({x:[[[[[[[[[]]]]]]]]]})],['invalid',()=>'{ZZ'],['nonutf8',()=>String.fromCharCode(0)],
])test(label+' JSON rejected',async t=>{const f=fixture(()=>{},change);mock(t,f);await assert.rejects(get(f),{message:'approval admission blocked'});});
test('redirect, pagination, non200 rejected without retry',async t=>{
 for(const opts of [{status:302},{headers:{Link:'ZZnext'}},{status:401}]){const f=fixture(),count=mock(t,f,b=>b,opts);await assert.rejects(get(f));assert.equal(count(),1);}
});
test('deadline bounded despite ignored abort',async t=>{
 const real=setTimeout;t.mock.method(globalThis,'setTimeout',(fn,ms)=>{assert.equal(ms,5000);return real(fn,5)});t.mock.method(globalThis,'fetch',()=>new Promise(()=>{}));await assert.rejects(get(fixture()));
});
test('receipt freshness and caller time do not create authority',async t=>{
 const f=fixture();mock(t,f);const r=await get(f),old=Date.now;t.mock.method(Date,'now',()=>old()+31000);assert.throws(()=>admit(f,r));assert.throws(()=>admit(f,r,{nowUnix:1}));
});

test('declared cap is independent of valid small body',async t=>{const f=fixture();mock(t,f,b=>b,{headers:{'Content-Length':'131073'}});await assert.rejects(get(f));});
test('stream cap with valid large JSON and no length header',async t=>{const f=fixture();t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(f.bodies[0])+' '.repeat(131073)));await assert.rejects(get(f));});
test('blob digest and content digest independently pinned',async t=>{
 for(const field of ['blob_sha','content_sha256']){
  const f=fixture();if(field==='blob_sha')f.bodies[3].content=Buffer.from(f.bytes.toString().replace('profile-999001','profile-999009')).toString('base64');
  else f.source.content_sha256='0'.repeat(64);
  mock(t,f);await assert.rejects(get(f));
 }
});
test('source and credential validation precede network',async t=>{
 let count=0;t.mock.method(globalThis,'fetch',async()=>{count++;throw Error('ZZ');});
 for(const change of [s=>s.path='../ZZ',s=>s.owner='ZZ/escape',s=>s.repo='ZZ?escape',s=>s.commit='ZZ',s=>s.repository_id='0']){const f=fixture();change(f.source);await assert.rejects(get(f));}
 await assert.rejects(fetchPrivateApproval({source:fixture().source,credential:'ZZ\nsecret'}));assert.equal(count,0);
});
test('nested ordinary tree traversal is exact and bounded',async t=>{
 const f=fixture();f.source.path='ZZ-dir/'+f.source.path;
 f.paths.splice(3,0,'/repos/ZZ-owner/ZZ-private/git/trees/'+'b'.repeat(40));
 f.bodies.splice(2,0,{sha:'a'.repeat(40),truncated:false,tree:[{path:'ZZ-dir',type:'tree',mode:'040000',sha:'b'.repeat(40)}]});
 f.bodies[3].sha='b'.repeat(40);mock(t,f);assert.ok(await get(f));
});

test('Git blob hash alone rejects claimed ID despite valid content SHA256',async t=>{
 const f=fixture();f.source.blob_sha='c'.repeat(40);f.bodies[2].tree[0].sha=f.source.blob_sha;f.bodies[3].sha=f.source.blob_sha;f.paths[3]='/repos/ZZ-owner/ZZ-private/git/blobs/'+f.source.blob_sha;mock(t,f);await assert.rejects(get(f));
});
for(const field of ['approver_ref','evidence_ref'])test('distinct '+field+' even if expected approvals agree',async t=>{
 const f=fixture(r=>r.approvals[1][field]=r.approvals[0][field]);mock(t,f);const r=await get(f);const want=structuredClone(approvals);want.human_reviewer[field]=want.owner[field];assert.throws(()=>admit(f,r,{expectedApprovals:want}));
});
test('retrieved bytes cannot be replaced with equivalent valid JSON',async t=>{
 const f=fixture();mock(t,f);const r=await get(f);assert.throws(()=>admit(f,r,{approvalBytes:Buffer.from(f.bytes.toString()+' ')}));
});
test('stream cap stops reading immediately before a subsequent stalled read',async t=>{
 const f=fixture();let reads=0,cancelled=false;
 t.mock.method(globalThis,'fetch',async()=>({status:200,redirected:false,headers:new Headers(),body:{getReader:()=>({read:async()=>{reads++;if(reads===1)return{done:false,value:new Uint8Array(131073)};return new Promise(()=>{});},cancel:async()=>{cancelled=true;},releaseLock:()=>{}})}}));
 const real=setTimeout;t.mock.method(globalThis,'setTimeout',(fn,ms)=>real(fn,10));await assert.rejects(get(f));assert.equal(reads,1);assert.equal(cancelled,true);
});

test('deadline duration is inspected outside rejection assertion',async t=>{
 const durations=[],real=setTimeout;t.mock.method(globalThis,'setTimeout',(fn,ms)=>{durations.push(ms);return real(fn,5);});t.mock.method(globalThis,'fetch',()=>new Promise(()=>{}));
 await assert.rejects(get(fixture()));assert.deepEqual(durations,[5000]);
});
test('caller clock skew alone rejects a fresh valid receipt',async t=>{
 const f=fixture();mock(t,f);const r=await get(f);assert.throws(()=>admit(f,r,{nowUnix:now()+6}));
});
test('operation policy rejects even with matching expected pins',async t=>{
 const f=fixture(r=>r.pins.operation='ZZ_other_operation');mock(t,f);const r=await get(f);assert.throws(()=>admit(f,r));
});
test('role must match semantic slot even with matching hashes',async t=>{
 const f=fixture(r=>r.approvals[0].role='ZZ_not_owner');mock(t,f);const r=await get(f);assert.throws(()=>admit(f,r));
});
test('actual invalid UTF8 bytes reject before replacement-character parsing',async t=>{
 const f=fixture();const text=f.bytes.toString().replace('offline_approval_record','offline_approval_recorX');
 const bytes=Buffer.from(text);bytes[bytes.indexOf('recorX')+5]=0xff;
 const sha=hash(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1');f.bytes=bytes;f.source.blob_sha=sha;f.source.content_sha256=hash(bytes);f.paths[3]='/repos/ZZ-owner/ZZ-private/git/blobs/'+sha;f.bodies[2].tree[0].sha=sha;f.bodies[3]={sha,size:bytes.length,encoding:'base64',content:bytes.toString('base64')};mock(t,f);await assert.rejects(get(f));
});
for(const [field,value]of [['type','blob'],['mode','100644']])test('intermediate directory '+field+' rejects independently',async t=>{
 const f=fixture();f.source.path='ZZ-dir/'+f.source.path;f.paths.splice(3,0,'/repos/ZZ-owner/ZZ-private/git/trees/'+'b'.repeat(40));
 f.bodies.splice(2,0,{sha:'a'.repeat(40),truncated:false,tree:[{path:'ZZ-dir',type:'tree',mode:'040000',sha:'b'.repeat(40)}]});f.bodies[3].sha='b'.repeat(40);f.bodies[2].tree[0][field]=value;mock(t,f);await assert.rejects(get(f));
});
