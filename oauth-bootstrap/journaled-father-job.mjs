// No CLI or workflow. A journal already present blocks a fresh invocation.
import{createPrivateRunJournal}from'./private-run-journal.mjs';
import{createHash}from'node:crypto';
import{protectedRunnerConfig,protectedRunnerService,runProtectedFatherJob}from'./protected-father-runner.mjs';
export async function runJournaledFatherJob(env,approvalBytes,prewriteBytes){
 const c=protectedRunnerConfig(env);const journal=await createPrivateRunJournal(env);let attempted=false,sequence=0,previous='0'.repeat(64);
 const remote=async event=>{const entry={sequence:++sequence,previous,event};const expected=createHash('sha256').update(JSON.stringify(entry)).digest('hex');const r=await protectedRunnerService(env,c,'/journal',{entry});if(r.phase!=='opaque_progress_durable'||r.sequence!==sequence||r.sha256!==expected||r.retry_allowed!==false||r.production_enabled!==false)throw Error('remote journal blocked');previous=r.sha256;};
 try{
  await remote({stage:'start',receipt:{execute_attempted:false}});
  const result=await runProtectedFatherJob(env,approvalBytes,prewriteBytes,async event=>{await journal.append(event);await remote(event);if(event.stage==='execute_attempt'&&event.receipt.execute_attempted)attempted=true;});
  const completed={stage:'completed',receipt:{execute_attempted:attempted,intent_verified:false,created_id:result.created_id,retry_allowed:false}};await journal.append(completed);await remote(completed);return result;
 }catch{
  try{await journal.append({stage:'stopped',receipt:{execute_attempted:attempted,retry_allowed:false}});}catch{/* existing fsynced events remain; no replay */}
  throw Error(attempted?'journaled father job stopped; inspect only, never replay create':'journaled father job stopped; inspect before a new plan');
 }finally{await journal.close();}
}
