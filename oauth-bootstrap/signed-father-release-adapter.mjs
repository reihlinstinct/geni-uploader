// Dormant adapter. The shipped father-release-gate does NOT import this module.
import{verifySignedFatherRelease}from'./signed-father-release-policy.mjs';
/** Only a reviewed deployed DO may supply env and approvedRun. These arguments
 * are not proof of deployment provenance; never populate them from a request.
 * Namespace ID must be independently checked against the installed DO binding.
 */
export async function requireSignedFatherRelease(env,binding,approvedRun,storage,operation){
 if(!env||typeof approvedRun!=='string')throw Error('father release context blocked');
 const context={run_id:approvedRun,run_attempt:1,namespace_id:env.FATHER_REVIEWED_NAMESPACE_ID,service_sha:env.FATHER_REVIEWED_SERVICE_SHA,executor_sha:env.FATHER_REVIEWED_EXECUTOR_SHA,workflow_sha:env.FATHER_REVIEWED_WORKFLOW_SHA};
 const verified=verifySignedFatherRelease(env,binding,context);
 if(!storage||typeof storage.transaction!=='function'||!['execute','recover'].includes(operation))throw Error('father release consumption blocked');
 // One permanent slot in the canonical owner DO. Neither a new grant ID nor a
 // new run may erase a prior execution attempt. No automatic retry after loss.
 const record={grant_id:verified.grant_id,run_id:approvedRun,policy_sha256:verified.policy_sha256,binding};
 await storage.transaction(async tx=>{
  const prior=await tx.get('signed-release-consumption');
  if(operation==='execute'){
   if(prior!==undefined)throw Error('father release already consumed');
   await tx.put('signed-release-consumption',structuredClone(record));
  }else if(!prior||JSON.stringify(prior)!==JSON.stringify(record))throw Error('father recovery release mismatch');
 });
 return verified;
}
