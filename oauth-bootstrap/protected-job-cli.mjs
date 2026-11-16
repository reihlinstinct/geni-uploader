#!/usr/bin/env node
// One-shot protected job CLI. No argument-controlled scope or destination.
import{pathToFileURL}from'node:url';
import{runProtectedJobEntrypoint}from'./protected-job-entrypoint.mjs';
export async function protectedJobCli(args=process.argv.slice(2),env=process.env){
 try{
  if(args.length!==0)throw Error('arguments forbidden');
  const result=await runProtectedJobEntrypoint(env);
  if(result?.phase!=='protected_job_receipt_accounted_reconciliation_required'||result.intent_verified!==false||result.retry_allowed!==false||result.production_enabled!==false)throw Error('unexpected result');
  // Public stdout is deliberately value-free. Full opaque receipts and known
  // profile identity are already in private storage, never CI output.
  process.stdout.write(JSON.stringify({phase:'receipt_accounted_reconciliation_required',intent_verified:false,retry_allowed:false,production_enabled:false})+'\n');
  return 0;
 }catch{
  process.stderr.write('Protected job stopped. Inspect private receipts; do not replay create.\n');return 1;
 }
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)process.exitCode=await protectedJobCli();
