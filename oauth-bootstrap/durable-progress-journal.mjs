// Canonical owner SQLite receipt journal, no create permission or reset route.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('durable progress journal blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const fields=['owner','connection','plan','payload','artifact','policy'];
function binding(b){exact(b,fields);need(typeof b.owner==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(b.owner)&&typeof b.connection==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(b.connection));for(const k of ['plan','payload','artifact','policy'])need(typeof b[k]==='string'&&/^[a-f0-9]{64}$/.test(b[k]));}
function event(e){
 exact(e,['stage','receipt']);need(['start','approval','pre_write','readback','execute_attempt','completion_attempt','stopped','completed'].includes(e.stage));
 need(e.receipt&&Object.getPrototypeOf(e.receipt)===Object.prototype&&Object.keys(e.receipt).length<=8);
 for(const[k,v]of Object.entries(e.receipt))need(['blob','tree','commit','ref_update_attempted','execute_attempted','intent_verified','created_id','retry_allowed'].includes(k)&&(v===null||typeof v==='boolean'||(typeof v==='string'&&(/^[a-f0-9]{40}$/.test(v)||/^profile-[1-9][0-9]{0,29}$/.test(v)))));
 need(e.receipt.retry_allowed!==true&&e.receipt.intent_verified!==true);
 for(const[k,v]of Object.entries(e.receipt)){if(['blob','tree','commit'].includes(k))need(v===null||(typeof v==='string'&&/^[a-f0-9]{40}$/.test(v)));else if(k==='created_id')need(v===null||(typeof v==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(v)));else need(typeof v==='boolean');}
}
function validate(j,b,run){
 exact(j,['binding','run_id','entries','production_enabled']);binding(j.binding);need(fields.every(k=>j.binding[k]===b[k])&&j.run_id===run&&j.production_enabled===false&&Array.isArray(j.entries)&&j.entries.length<=100);
 let previous='0'.repeat(64),sequence=0;for(const e of j.entries){exact(e,['sequence','previous','event','sha256']);event(e.event);need(Buffer.byteLength(JSON.stringify(e))<=4200);need(e.sequence===++sequence&&e.previous===previous&&e.sha256===hash(JSON.stringify({sequence:e.sequence,previous:e.previous,event:e.event})));previous=e.sha256;}
}
export async function appendDurableProgress(storage,b,run,entry){
 binding(b);need(typeof run==='string'&&/^[1-9][0-9]{0,19}$/.test(run));exact(entry,['sequence','previous','event']);need(Buffer.byteLength(JSON.stringify(entry))<=4096);event(entry.event);
 return storage.transaction(async tx=>{
  let j=await tx.get('progress-journal');if(j===undefined){need(entry.sequence===1&&entry.event.stage==='start'&&entry.event.receipt.execute_attempted===false);j={binding:structuredClone(b),run_id:run,entries:[],production_enabled:false};}
  validate(j,b,run);const last=j.entries.at(-1);need(j.entries.length<100&&entry.sequence===j.entries.length+1&&entry.previous===(last?.sha256??'0'.repeat(64)));
  need(entry.sequence===1||entry.event.stage!=='start');const v={...structuredClone(entry),sha256:hash(JSON.stringify(entry))};j.entries.push(v);await tx.put('progress-journal',j);
  return{phase:'opaque_progress_durable',sequence:v.sequence,sha256:v.sha256,retry_allowed:false,production_enabled:false};
 });
}
export async function inspectDurableProgress(storage,b,run){binding(b);return storage.transaction(async tx=>{const j=await tx.get('progress-journal');need(j!==undefined);validate(j,b,run);return{phase:'opaque_progress_read_only',journal:structuredClone(j),retry_allowed:false,production_enabled:false};});}
