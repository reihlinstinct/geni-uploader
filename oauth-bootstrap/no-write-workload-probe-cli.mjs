#!/usr/bin/env node
import{pathToFileURL}from'node:url';
import{runNoWriteWorkloadProbe}from'./no-write-workload-probe.mjs';
export async function noWriteWorkloadProbeCli(args=process.argv.slice(2),env=process.env){
 try{if(args.length)throw Error('arguments forbidden');await runNoWriteWorkloadProbe(env);process.stdout.write('No-write workload compatibility verified. No execution permit.\n');return 0;}
 catch{process.stderr.write('No-write workload probe stopped. Inspect private receipt.\n');return 1;}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)process.exitCode=await noWriteWorkloadProbeCli();
