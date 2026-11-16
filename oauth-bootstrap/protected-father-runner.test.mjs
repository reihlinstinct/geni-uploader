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
// #359: reservation fails after the one consumed /execute response, before any postwrite ciphertext.
for(const failure of['response_lost','rejected'])test('journaled runner reservation '+failure+' after consumed execute response stops without postwrite ciphertext and refuses replay',{skip:!key},async t=>{
 const{mkdtemp,rm}=await import('node:fs/promises'),{join}=await import('node:path'),{tmpdir}=await import('node:os');
 const{runJournaledFatherJob}=await import('./journaled-father-job.mjs'),{inspectPrivateRunJournal}=await import('./private-run-journal.mjs');
 const root=await mkdtemp(join(tmpdir(),'ZZ-reservation-failure-runner-'));try{
  const f=fixture();f.env.FATHER_PRIVATE_JOURNAL_DIRECTORY=join(root,'ZZ-private');let reserves=0;
  const rejected=u=>{if(String(u).endsWith('/reserve')){reserves++;if(failure==='rejected')return Response.json({phase:'blocked_or_already_consumed',production_enabled:false,retry_allowed:false},{status:409});}};
  const state=mockGitAndService(t,f,failure==='response_lost'?'reserve':undefined,undefined,rejected);
  await assert.rejects(runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes),{message:'journaled father job stopped; inspect only, never replay create'});
  let s=state();assert.equal(s.execute,1);assert.equal(s.complete,0);assert.equal(reserves,1);
  assert.equal(s.trees.get(s.tree).some(e=>e.path==='ZZ-post.age'),false);
  const journal=await inspectPrivateRunJournal(f.env),stages=journal.events.map(e=>e.stage);assert.equal(journal.retry_allowed,false);
  assert.deepEqual(stages.slice(-2),['execute_attempt','stopped']);assert.equal(stages.includes('readback'),false);assert.equal(stages.includes('completed'),false);
  assert.deepEqual(journal.events.at(-1).receipt,{execute_attempted:true,retry_allowed:false});
  assert.equal(journal.events.some(e=>'created_id' in e.receipt),false);
  // A fresh invocation is refused before any service or storage request.
  const requests=s.requests;await assert.rejects(runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes));
  s=state();assert.equal(s.requests,requests);assert.equal(s.execute,1);assert.equal(reserves,1);
  assert.deepEqual((await inspectPrivateRunJournal(f.env)).events,journal.events);
 }finally{await rm(root,{recursive:true,force:true});}
});
// #808 finding 3: characterization tests that pin a CURRENT gap on purpose. At this
// failure point the created ID reaches the runner only in the consumed /execute response;
// neither the thrown error nor any journal carries it. Service-side counterpart:
// oauth-bootstrap/consumed-readonly-recovery.test.mjs. A future fix must flip these deliberately.
const reservationFailure808=(failure,onReserve)=>u=>{if(String(u).endsWith('/reserve')){onReserve();if(failure==='rejected')return Response.json({phase:'blocked_or_already_consumed',production_enabled:false,retry_allowed:false},{status:409});}};
for(const failure of['response_lost','rejected'])test('pins current gap (#808 finding 3): runner reservation '+failure+' drops the created ID from its thrown error and progress receipts',{skip:!key},async t=>{
 const f=fixture(),id=f.result.created_id,events=[];let reserves=0;
 const state=mockGitAndService(t,f,failure==='response_lost'?'reserve':undefined,undefined,reservationFailure808(failure,()=>reserves++));
 let error;await assert.rejects(runProtectedFatherJob(f.env,f.approvalBytes,f.prewriteBytes,x=>events.push(x)),e=>{error=e;return true;});
 assert.equal(state().execute,1);assert.equal(reserves,1);assert.equal(typeof id,'string');
 assert.deepEqual(Object.keys(error),['execute_attempted']);assert.equal(error.execute_attempted,true);assert.equal('created_id' in error,false);assert.equal(error.cause,undefined);
 assert.equal(String(error.message).includes(id),false);assert.equal(String(error.stack).includes(id),false);
 assert.equal(events.map(e=>e.stage).at(-1),'execute_attempt');assert.equal(JSON.stringify(events).includes(id),false);
});
for(const failure of['response_lost','rejected'])test('pins current gap (#808 finding 3): journaled runner reservation '+failure+' keeps the created ID out of its journals and error',{skip:!key},async t=>{
 const{mkdtemp,rm,readdir,readFile}=await import('node:fs/promises'),{join}=await import('node:path'),{tmpdir}=await import('node:os');
 const{runJournaledFatherJob}=await import('./journaled-father-job.mjs'),{inspectPrivateRunJournal}=await import('./private-run-journal.mjs');
 const root=await mkdtemp(join(tmpdir(),'ZZ-reservation-808-'));try{
  const f=fixture(),id=f.result.created_id,remote=[];f.env.FATHER_PRIVATE_JOURNAL_DIRECTORY=join(root,'ZZ-private');let reserves=0;
  const onReserve=reservationFailure808(failure,()=>reserves++),external=(u,o)=>{if(String(u).endsWith('/journal'))remote.push(String(o.body));return onReserve(u);};
  const state=mockGitAndService(t,f,failure==='response_lost'?'reserve':undefined,undefined,external);
  let error;await assert.rejects(runJournaledFatherJob(f.env,f.approvalBytes,f.prewriteBytes),e=>{error=e;return true;});
  assert.equal(state().execute,1);assert.equal(reserves,1);assert.equal(typeof id,'string');
  assert.equal(error.message,'journaled father job stopped; inspect only, never replay create');assert.deepEqual(Object.keys(error),[]);assert.equal(error.cause,undefined);assert.equal(String(error.stack).includes(id),false);
  const journal=await inspectPrivateRunJournal(f.env);assert.equal(journal.events.at(-1).stage,'stopped');assert.equal(JSON.stringify(journal).includes(id),false);
  const files=[];const walk=async d=>{for(const e of await readdir(d,{withFileTypes:true})){const x=join(d,e.name);if(e.isDirectory())await walk(x);else files.push(await readFile(x,'utf8'));}};await walk(root);
  assert.ok(files.length>0);assert.equal(files.some(x=>x.includes(id)),false);
  assert.ok(remote.length>0);assert.equal(remote.some(x=>x.includes(id)),false);
 }finally{await rm(root,{recursive:true,force:true});}
});
