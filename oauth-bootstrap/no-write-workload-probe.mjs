// No create-entrypoint/executor/service imports. Actual dispatch needs approval.
import{requestBoundedWorkloadToken}from'./bounded-workload-acquisition.mjs';
import{verifyTrustedWorkload}from'./trusted-workload-jwks.mjs';
import{createHash}from'node:crypto';
import{open,lstat}from'node:fs/promises';
import{resolve,join}from'node:path';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('no-write compatibility probe blocked');};
function config(env){
 const raw=env.FATHER_PROBE_CONFIG_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_PROBE_CONFIG_SHA256);
 const c=JSON.parse(raw);need(JSON.stringify(c)===raw&&c&&Object.getPrototypeOf(c)===Object.prototype&&Object.keys(c).sort().join(',')==='mode,private_receipt_directory,production_enabled,workload_audience,workload_pins,workload_request_origin');
 need(c.mode==='no_write_workload_compatibility_probe'&&c.production_enabled===false);
 const p=c.workload_pins;need(p&&p.run_id===env.GITHUB_RUN_ID&&p.run_attempt==='1'&&env.GITHUB_RUN_ATTEMPT==='1'&&env.GITHUB_REF==='refs/heads/master'&&env.GITHUB_EVENT_NAME==='workflow_dispatch'&&p.aud===c.workload_audience);
 need(p.repository===env.GITHUB_REPOSITORY&&p.sha===env.GITHUB_SHA&&p.workflow_sha===env.GITHUB_WORKFLOW_SHA);
 need(typeof c.private_receipt_directory==='string'&&c.private_receipt_directory.startsWith('/')&&resolve(c.private_receipt_directory)===c.private_receipt_directory&&c.private_receipt_directory!=='/'&&c.private_receipt_directory.length<=512);
 need(typeof p.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(p.run_id));return c;
}
export async function runNoWriteWorkloadProbe(env){
 const c=config(env),st=await lstat(c.private_receipt_directory);need(st.isDirectory()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o700);
 // Exclusive reservation before HTTP. Failure leaves file and requires inspection.
 const path=join(c.private_receipt_directory,'workload-probe-'+c.workload_pins.run_id+'-attempt-1.json'),file=await open(path,'wx',0o600);
 try{
  const token=await requestBoundedWorkloadToken(env,c.workload_request_origin,c.workload_audience);
  const verified=await verifyTrustedWorkload(token,c.workload_pins);need(verified.workload_verified===true&&verified.production_enabled===false);
  const receipt={schema_version:1,mode:'private_no_write_workload_compatibility_receipt',config_sha256:env.FATHER_PROBE_CONFIG_SHA256,workload_request_origin:c.workload_request_origin,workload_pins:c.workload_pins,workload_verified:true,owner_approval_verified:false,geni_calls:0,post_permitted:false,production_enabled:false};
  await file.writeFile(JSON.stringify(receipt)+'\n');await file.sync();const dir=await open(c.private_receipt_directory,'r');try{await dir.sync();}finally{await dir.close();}
  return{phase:'no_write_workload_compatibility_verified',post_permitted:false,production_enabled:false};
 }finally{await file.close();}
}
