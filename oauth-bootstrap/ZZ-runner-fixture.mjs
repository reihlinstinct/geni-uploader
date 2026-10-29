import assert from'node:assert/strict';import{createHash}from'node:crypto';import{execFileSync}from'node:child_process';import{setup}from'./ZZ-approval-fixture.mjs';import{staticPlanFingerprint}from'./live-protected-capture.mjs';import{runProtectedFatherJob}from'./protected-father-runner.mjs';
const sha=(x,a='sha256')=>createHash(a).update(x).digest('hex');
const key=process.env.ZZ_TEST_AGE_KEY,recipient=key?execFileSync('age-keygen',['-y',key],{encoding:'utf8'}).trim():null;
function fixture(recordOverride){
 const record=recordOverride??setup().c.expected_record;record.pins.recipient=sha(recipient);const plan=staticPlanFingerprint(record),b={owner:record.pins.owner,connection:record.pins.connection_id,plan,payload:record.pins.payload_hash,artifact:record.pins.artifact_hash,policy:record.pins.policy_hash};
 const approvalBytes=Buffer.from(JSON.stringify(record)),prewriteBytes=Buffer.from(JSON.stringify({binding:b,ZZ:'synthetic prewrite'}));
 const a={mode:'unreleased_private_approval_writer',production_enabled:false,repository_id:'999001',owner:'ZZ-owner',repo:'ZZ-private',branch:'ZZ-main',parent_commit:'a'.repeat(40),path:'ZZ-approval.json',plan_fingerprint:plan,run_id:record.pins.run_id};
 const storage=(stage,path)=>({mode:'unreleased_protected_job_evidence',production_enabled:false,recipient,storage:{repository_id:a.repository_id,owner:a.owner,repo:a.repo,branch:a.branch,parent_commit:a.parent_commit,path,recipient:sha(recipient),operation_binding:plan,run_id:a.run_id,stage,existing_total_bytes:0}});
 const config={mode:'unreleased_protected_father_runner',production_enabled:false,service_origin:'https://zz-service.invalid',binding:{...b,run_id:a.run_id},prewrite_sha256:sha(prewriteBytes),prewrite_storage:storage('pre_write','ZZ-pre.age'),postwrite_storage:storage('readback','ZZ-post.age')};
 const env={PRIVATE_GIT_CREDENTIAL:'ZZprivate',FATHER_WORKLOAD_TOKEN:'ZZsigned',GITHUB_RUN_ID:a.run_id,GITHUB_RUN_ATTEMPT:'1',GITHUB_REF:'refs/heads/master',GITHUB_EVENT_NAME:'workflow_dispatch'};
 for(const [k,v]of [['FATHER_APPROVAL_STORAGE',a],['FATHER_POSTWRITE_BINDING',b],['FATHER_RUNNER_RELEASE',config]]){env[k+'_JSON']=JSON.stringify(v);env[k+'_SHA256']=sha(env[k+'_JSON']);}
 const id='profile-999009',result={phase:'consumed_readback_consistent_evidence_pending',created_id:id,private_evidence:{schema_version:1,mode:'private_post_write_evidence',binding:b,acknowledgment:{id},profile:{id,public:false},family:{focus:{id:b.owner}},union:{id:'union-999010'}},retry_allowed:false,post_write_evidence_durable:false,production_enabled:false};
 return{env,config,approvalBytes,prewriteBytes,result};
}
function mockGitAndService(t,f,fault,serviceOverride,externalOverride){
 let head='a'.repeat(40),tree='b'.repeat(40),pendingTree,pendingCommit,serial=10,execute=0,complete=0,requests=0;const blobs=new Map(),trees=new Map([[tree,[]]]),commits=new Map([[head,{sha:head,tree:{sha:tree},parents:[]}]]),root='https://api.github.com/repos/ZZ-owner/ZZ-private';
 t.mock.method(globalThis,'fetch',async(u,o)=>{
  requests++;assert.equal(o.redirect,'manual');let body;
  if(externalOverride){const out=await externalOverride(u,o);if(out!==undefined)return out;}
  if(u.startsWith('https://zz-service.invalid')){
   if(serviceOverride)return serviceOverride(u,o);
   const r=JSON.parse(o.body);assert.equal(r.workload_token,f.env.FATHER_WORKLOAD_TOKEN);assert.equal(r.plan_hash,f.config.binding.plan);
   if(u.endsWith('/execute')){execute++;assert.equal(execute,1);assert.ok(r.uploads.approval.commit);assert.equal(r.uploads.prewrite.stage,'pre_write');if(fault==='execute')throw Error('ZZlost');return Response.json(f.result);}
   if(u.endsWith('/reserve')){if(fault==='reserve')throw Error('ZZlost');const entry=trees.get(tree).find(x=>x.path==='ZZ-pre.age');return Response.json({phase:'postwrite_ciphertext_budget_reserved',byte_limit:1048576,prior_total:blobs.get(entry.sha).length,retry_allowed:false,production_enabled:false});}
   assert.equal(u,'https://zz-service.invalid/complete');complete++;assert.equal(r.descriptor.stage,'readback');if(fault==='complete')throw Error('ZZlost');return Response.json({phase:'ciphertext_receipt_accounted_reconciliation_required',intent_verified:false,retry_allowed:false,production_enabled:false});
  }
  assert.equal(o.headers.Authorization,'Bearer ZZprivate');const data=o.body?JSON.parse(o.body):null;
  if(u==='https://api.github.com/repositories/999001')body={id:999001,private:true,full_name:'ZZ-owner/ZZ-private'};
  else if(u===root+'/git/ref/heads/ZZ-main')body={ref:'refs/heads/ZZ-main',object:{type:'commit',sha:head}};
  else if(u.startsWith(root+'/git/commits/'))body=commits.get(u.split('/').at(-1));
  else if(u===root+'/git/blobs'){
   const bytes=Buffer.from(data.content,'base64'),id=sha(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes]),'sha1');blobs.set(id,bytes);body={sha:id};if(fault==='postupload'&&execute===1)throw Error('ZZlost');
  }
  else if(u===root+'/git/trees'){
   assert.equal(data.base_tree,tree);pendingTree=(++serial).toString(16).padStart(40,'0');trees.set(pendingTree,[...trees.get(tree),...data.tree]);body={sha:pendingTree,truncated:false,tree:trees.get(pendingTree)};
  }
  else if(u.startsWith(root+'/git/trees/')){const id=u.split('/').at(-1);body={sha:id,truncated:false,tree:trees.get(id)};}
  else if(u===root+'/git/commits'){assert.deepEqual(data.parents,[head]);pendingCommit=(++serial).toString(16).padStart(40,'0');body={sha:pendingCommit,tree:{sha:data.tree},parents:[{sha:head}]};commits.set(pendingCommit,body);}
  else if(u===root+'/git/refs/heads/ZZ-main'){assert.equal(data.force,false);assert.equal(data.sha,pendingCommit);head=pendingCommit;tree=pendingTree;body={ref:'refs/heads/ZZ-main',object:{type:'commit',sha:head}};}
  else if(u.startsWith(root+'/git/blobs/')){const id=u.split('/').at(-1),bytes=blobs.get(id);body={sha:id,encoding:'base64',size:bytes.length,content:bytes.toString('base64')};}
  else throw Error('unexpected route');assert.ok(body);return Response.json(body,{status:o.method==='POST'?201:200});
 });return()=>({execute,complete,requests,blobs,trees,tree});
}

export{fixture,mockGitAndService,key,sha};
