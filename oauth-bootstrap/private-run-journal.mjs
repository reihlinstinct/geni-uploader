// Protected Node job private local journal. No vendor calls or replay command.
import{open,mkdir,readFile,lstat}from'node:fs/promises';
import{resolve,join}from'node:path';
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('private run journal blocked');};
function pins(env){
 const root=env.FATHER_PRIVATE_JOURNAL_DIRECTORY;need(typeof root==='string'&&root.startsWith('/')&&resolve(root)===root&&root!=='/'&&root.length<=512);
 const run=env.GITHUB_RUN_ID;need(typeof run==='string'&&/^[1-9][0-9]{0,19}$/.test(run)&&env.GITHUB_RUN_ATTEMPT==='1');
 const raw=env.FATHER_RUNNER_RELEASE_JSON;need(typeof raw==='string'&&hash(raw)===env.FATHER_RUNNER_RELEASE_SHA256);
 return{root,file:join(root,'run-'+run+'-attempt-1.jsonl'),run,config_sha256:hash(raw)};
}
/** Exclusive creation: a second process/run invocation cannot quietly reuse it.
 * Path is protected-job environment only. Contents are private synthetic opaque
 * receipts/status, never raw approval/provider bytes or a workload credential.
 */
export async function createPrivateRunJournal(env){
 const p=pins(env);await mkdir(p.root,{mode:0o700,recursive:false});
 const st=await lstat(p.root);need(st.isDirectory()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o700);
 const f=await open(p.file,'wx',0o600);let sequence=0,previous='0'.repeat(64),closed=false,queue=Promise.resolve();
 const append=event=>{
  need(!closed);const snapshot=structuredClone(event);
  queue=queue.then(async()=>{
   need(snapshot&&Object.getPrototypeOf(snapshot)===Object.prototype&&Object.keys(snapshot).sort().join(',')==='receipt,stage');
   need(['approval','pre_write','readback','execute_attempt','completion_attempt','stopped','completed'].includes(snapshot.stage));
   const receipt=snapshot.receipt;need(receipt&&Object.getPrototypeOf(receipt)===Object.prototype);
   for(const [k,v]of Object.entries(receipt))need(['blob','tree','commit','ref_update_attempted','execute_attempted','intent_verified','created_id','retry_allowed'].includes(k)&&(v===null||typeof v==='boolean'||(typeof v==='string'&&(/^[a-f0-9]{40}$/.test(v)||/^profile-[1-9][0-9]{0,29}$/.test(v)))));
   const value={sequence:++sequence,previous,run_id:p.run,config_sha256:p.config_sha256,event:snapshot},raw=JSON.stringify(value);need(Buffer.byteLength(raw)<=4096&&sequence<=100);const entry={...value,sha256:hash(raw)};await f.write(JSON.stringify(entry)+'\n');await f.sync();previous=entry.sha256;
  });return queue;
 };
 await append({stage:'execute_attempt',receipt:{execute_attempted:false}});
 return{append,async close(){closed=true;try{await queue;}finally{await f.close();}},path:p.file};
}
/** Read-only inspection is not permission to resume or retry a create. */
export async function inspectPrivateRunJournal(env){
 const p=pins(env),st=await lstat(p.file);need(st.isFile()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o600&&st.size<=409600);
 const raw=await readFile(p.file,'utf8');need(raw.endsWith('\n'));let previous='0'.repeat(64),sequence=0;const events=[];
 for(const line of raw.trimEnd().split('\n')){const e=JSON.parse(line),{sha256,...value}=e;need(e.sequence===++sequence&&e.previous===previous&&e.run_id===p.run&&e.config_sha256===p.config_sha256&&hash(JSON.stringify(value))===sha256);previous=sha256;events.push(e.event);}
 return{phase:'private_journal_read_only',events,retry_allowed:false,production_enabled:false};
}
