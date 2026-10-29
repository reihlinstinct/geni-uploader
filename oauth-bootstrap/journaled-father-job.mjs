// No CLI or workflow. A journal already present blocks a fresh invocation.
import{createPrivateRunJournal}from'./private-run-journal.mjs';
import{runProtectedFatherJob}from'./protected-father-runner.mjs';
export async function runJournaledFatherJob(env,approvalBytes,prewriteBytes){
 const journal=await createPrivateRunJournal(env);let attempted=false;
 try{
  const result=await runProtectedFatherJob(env,approvalBytes,prewriteBytes,async event=>{await journal.append(event);if(event.stage==='execute_attempt'&&event.receipt.execute_attempted)attempted=true;});
  await journal.append({stage:'completed',receipt:{execute_attempted:attempted,intent_verified:false,created_id:result.created_id,retry_allowed:false}});return result;
 }catch{
  try{await journal.append({stage:'stopped',receipt:{execute_attempted:attempted,retry_allowed:false}});}catch{/* existing fsynced events remain; no replay */}
  throw Error(attempted?'journaled father job stopped; inspect only, never replay create':'journaled father job stopped; inspect before a new plan');
 }finally{await journal.close();}
}
