import{requestBoundedWorkloadToken}from'./bounded-workload-acquisition.mjs';
// Dormant protected Node entrypoint. No CLI auto-run or installed workflow.
import{spawnSync}from'node:child_process';
import{readFile,lstat}from'node:fs/promises';
import{resolve,join}from'node:path';
import{createHash}from'node:crypto';
import{runJournaledFatherJob}from'./journaled-father-job.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('protected job entrypoint blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
function config(env){
 const raw=env.FATHER_ENTRYPOINT_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_ENTRYPOINT_RELEASE_SHA256);
 const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','workload_request_origin','workload_audience','private_input_directory','prewrite_filename','run_id']);
 need(c.mode==='unreleased_protected_job_entrypoint'&&c.production_enabled===false&&c.run_id===env.GITHUB_RUN_ID&&env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_REF==='refs/heads/master'&&env.GITHUB_EVENT_NAME==='workflow_dispatch');
 const u=new URL(c.workload_request_origin);need(u.protocol==='https:'&&u.origin===c.workload_request_origin&&!u.port&&!u.username&&!u.password);
 need(typeof c.workload_audience==='string'&&/^[A-Za-z0-9_.:/-]{1,200}$/.test(c.workload_audience));
 need(typeof c.private_input_directory==='string'&&resolve(c.private_input_directory)===c.private_input_directory&&c.private_input_directory.startsWith('/')&&c.private_input_directory!=='/');
 need(typeof c.prewrite_filename==='string'&&/^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$/.test(c.prewrite_filename)&&!['.','..'].includes(c.prewrite_filename));return c;
}
/** Request URL/token are platform environment values, not caller JSON. Exact
 * reviewed origin and audience are required. Origin consistency is not proof
 * that the deployed environment was provisioned correctly. Never logs tokens.
 */
export async function acquireProtectedWorkloadToken(env){const c=config(env);return requestBoundedWorkloadToken(env,c.workload_request_origin,c.workload_audience);}
async function privateFile(path,max){const st=await lstat(path);need(st.isFile()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o600&&st.size>0&&st.size<=max);const b=await readFile(path);need(b.length===st.size);return b;}
/** Future reviewed workflow calls this exactly once. Collector creates one
 * exclusive 0600 approval file. Prewrite is an existing reviewed private file.
 * No raw collector output/provider bytes/token are printed or returned.
 */
export async function runProtectedJobEntrypoint(env){
 try{
  const c=config(env),dir=await lstat(c.private_input_directory);need(dir.isDirectory()&&!dir.isSymbolicLink()&&(dir.mode&0o777)===0o700);
  const prewrite=await privateFile(join(c.private_input_directory,c.prewrite_filename),1048000);
  const capture=join(c.private_input_directory,'approval-run-'+c.run_id+'-attempt-1.json');need(c.prewrite_filename!==capture.split('/').at(-1));
  // Fixed program and cwd. No caller-selected script/command or shell.
  const collected=spawnSync('python3',['-c','import sys;from protected_father_job import collect_from_environment;collect_from_environment(sys.argv[1])',capture],{cwd:new URL('..',import.meta.url),env:{...env},timeout:20000,maxBuffer:65536,stdio:['ignore','pipe','pipe']});
  need(!collected.error&&collected.status===0&&collected.stdout.length===0);
  const approval=await privateFile(capture,65536),token=await acquireProtectedWorkloadToken(env);
  return await runJournaledFatherJob({...env,FATHER_WORKLOAD_TOKEN:token},approval,prewrite);
 }catch{throw Error('protected job entrypoint stopped; inspect private receipts before any new run');}
}
