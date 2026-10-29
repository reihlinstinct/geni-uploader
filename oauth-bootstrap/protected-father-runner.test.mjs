import test from'node:test';import assert from'node:assert/strict';import{execFileSync}from'node:child_process';import{runProtectedFatherJob}from'./protected-father-runner.mjs';import{fixture,mockGitAndService,key}from'./ZZ-runner-fixture.mjs';
test('protected runner joins real private approval + age uploads + service execute/receipt',{skip:!key},async t=>{
 const f=fixture(),state=mockGitAndService(t,f),events=[],r=await runProtectedFatherJob(f.env,f.approvalBytes,f.prewriteBytes,x=>events.push(x));
 const s=state();assert.equal(s.execute,1);assert.equal(s.complete,1);assert.equal(s.requests,36);assert.equal(r.intent_verified,false);assert.equal(events.length,14);
 const entries=s.trees.get(s.tree),pre=s.blobs.get(entries.find(e=>e.path==='ZZ-pre.age').sha),post=s.blobs.get(entries.find(e=>e.path==='ZZ-post.age').sha);
 assert.deepEqual(execFileSync('age',['-d','-i',key],{input:pre}),f.prewriteBytes);assert.deepEqual(JSON.parse(execFileSync('age',['-d','-i',key],{input:post})),{result_phase:f.result.phase,created_id:f.result.created_id,evidence:f.result.private_evidence});
});
for(const fault of ['execute','reserve','postupload','complete'])test('runner response loss '+fault+' never retries create',{skip:!key},async t=>{const f=fixture(),state=mockGitAndService(t,f,fault);await assert.rejects(runProtectedFatherJob(f.env,f.approvalBytes,f.prewriteBytes,()=>{}),e=>e.execute_attempted===true);assert.equal(state().execute,1);});
test('runner invalid config stops before write',async t=>{let n=0;t.mock.method(globalThis,'fetch',()=>n++);await assert.rejects(runProtectedFatherJob({},new Uint8Array([1]),new Uint8Array([2]),()=>{}),e=>e.execute_attempted===false);assert.equal(n,0);});

test('journaled actual runner records private progress and disallows replay',{skip:!key},async t=>{
 const{mkdtemp,rm}=await import('node:fs/promises'),{join}=await import('node:path'),{tmpdir}=await import('node:os');
 const{runJournaledFatherJob}=await import('./journaled-father-job.mjs'),{inspectPrivateRunJournal}=await import('./private-run-journal.mjs');
 const root=await mkdtemp(join(tmpdir(),'ZZ-journaled-runner-'));try{
  const f=fixture();f.env.FATHER_PRIVATE_JOURNAL_DIRECTORY=join(root,'ZZ-private');const state=mockGitAndService(t,f);
  await runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes);const journal=await inspectPrivateRunJournal(f.env);assert.equal(journal.events.length,16);assert.equal(journal.events.at(-1).stage,'completed');assert.equal(journal.events.at(-1).receipt.execute_attempted,true);assert.equal(journal.retry_allowed,false);
  await assert.rejects(runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes));assert.equal(state().execute,1);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('remote journal failure stops journaled job before execute without retry',{skip:!key},async t=>{
 const{mkdtemp,rm}=await import('node:fs/promises'),{join}=await import('node:path'),{tmpdir}=await import('node:os'),{runJournaledFatherJob}=await import('./journaled-father-job.mjs');const root=await mkdtemp(join(tmpdir(),'ZZ-remote-journal-'));
 try{const f=fixture();f.env.FATHER_PRIVATE_JOURNAL_DIRECTORY=join(root,'ZZ-private');let requests=0;t.mock.method(globalThis,'fetch',async u=>{requests++;assert.equal(u,'https://zz-service.invalid/journal');throw Error('ZZlost');});await assert.rejects(runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes));assert.equal(requests,1);}finally{await rm(root,{recursive:true,force:true});}
});

test('synthetic transport rejects look-alike service URLs without entering service override',async t=>{let serviceCalls=0;mockGitAndService(t,{},undefined,()=>{serviceCalls++;return Response.json({ZZ:true});});for(const url of ['https://zz-service.invalid.attacker.invalid/execute','https://zz-service.invalid@attacker.invalid/execute','https://user@zz-service.invalid/execute','https://zz-service.invalid:444/execute','http://zz-service.invalid/execute','https://zz-service.invalid/unknown','https://zz-service.invalid/execute?ZZ=1','https://zz-service.invalid/execute#ZZ'])await assert.rejects(fetch(url,{redirect:'manual',headers:{}}));assert.equal(serviceCalls,0);});
test('synthetic transport accepts exact supported service origin',async t=>{let calls=0;mockGitAndService(t,{},undefined,()=>{calls++;return Response.json({ZZ:true});});await fetch('https://zz-service.invalid/execute',{redirect:'manual'});assert.equal(calls,1);});
