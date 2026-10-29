// Fixed GET-only preflight. No POST, refresh, redirect, retry or graph absence proof.
import{createHash}from'node:crypto';
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('owner preflight blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
export async function verifyOwnerPreflight(env,binding,approvedGraphHash){
 const ctl=new AbortController();let timer,active=true;
 try{
  const raw=env.FATHER_PREFLIGHT_RELEASE_JSON;need(typeof raw==='string'&&raw.length<=16384&&hash(raw)===env.FATHER_PREFLIGHT_RELEASE_SHA256);
  const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','owner','connection','plan','graph_hash','allow_unknown_merge','unknown_parent_risk_accepted']);
  need(c.mode==='unreleased_secondary_owner_preflight'&&c.production_enabled===false&&c.owner===binding.owner&&c.connection===binding.connection&&c.plan===binding.plan&&c.graph_hash===approvedGraphHash&&/^profile-[1-9][0-9]{0,29}$/.test(c.owner)&&/^[a-f0-9]{64}$/.test(c.graph_hash)&&typeof c.allow_unknown_merge==='boolean'&&c.unknown_parent_risk_accepted===true);
  const token=env.GENI_SECONDARY_ACCESS_TOKEN;need(typeof token==='string'&&/^[A-Za-z0-9._~-]{8,4096}$/.test(token));
  let calls=0;const fields='id,first_name,middle_name,last_name,maiden_name,names,gender,public,is_alive,merge_pending,merged_into,unions';
  async function get(route,family=false){
   need(active&&++calls<=3);const url='https://www.geni.com/api/'+route+'?only_ids=true'+(family?'':'&fields='+fields);
   const r=await fetch(url,{method:'GET',redirect:'manual',signal:ctl.signal,headers:{Accept:'application/json',Authorization:'Bearer '+token}});
   need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const len=r.headers.get('content-length');need(len===null||(/^[0-9]+$/.test(len)&&Number(len)<=1048576));
   const reader=r.body.getReader(),chunks=[];let size=0;try{for(;;){const x=await reader.read();if(x.done)break;size+=x.value.length;need(active&&size<=1048576);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks));const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];
   for(let i=0;i<tokens.length;i++){const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();else if(t[0]==='"'&&tokens[i+1]===':'){const s=stack.at(-1),k=JSON.parse(t);need(s instanceof Set&&!s.has(k));s.add(k);}need(stack.length<=16);}
   const value=JSON.parse(text);need(value&&typeof value==='object'&&!Array.isArray(value)&&!['error','results','paging','pagination','next_page','redacted'].some(k=>k in value));return value;
  }
  function owner(p){
   need(p&&p.id===c.owner&&!['error','redacted','deleted','is_merged'].some(k=>k in p));
   const unknown=!('merge_pending'in p)&&!('merged_into'in p);
   need((unknown&&c.allow_unknown_merge)||(p.merge_pending===false&&(!('merged_into'in p)||p.merged_into===null)));
   if('unions'in p)need(Array.isArray(p.unions)&&p.unions.length<=20&&new Set(p.unions).size===p.unions.length&&p.unions.every(x=>/^union-[1-9][0-9]{0,29}$/.test(x)));
   return unknown?'UNKNOWN':'explicit_false';
  }
  async function work(){
   const self=await get('profile'),profile=await get(c.owner),family=await get(c.owner+'/immediate-family',true);
   const statuses=[owner(self),owner(profile)];exact(family,['focus','nodes']);statuses.push(owner(family.focus));need(family.nodes&&Object.getPrototypeOf(family.nodes)===Object.prototype&&Object.keys(family.nodes).length<=100);
   for(const [id,node]of Object.entries(family.nodes)){
    need(/^(profile|union)-[1-9][0-9]{0,29}$/.test(id)&&node&&node.id===id&&!['error','redacted','deleted','paging','pagination','next_page'].some(k=>k in node));
    if(id.startsWith('union-')){
     need(Array.isArray(node.partners)&&Array.isArray(node.children)&&node.partners.length<=100&&node.children.length<=100);
     for(const edge of[...node.partners,...node.children])need(typeof edge==='string'&&/^profile-[1-9][0-9]{0,29}$/.test(edge)&&Object.hasOwn(family.nodes,edge));
     // Known parent union is adverse. Zero observed parents remains UNKNOWN.
     need(!node.children.includes(c.owner));
    }
   }
   const graphHash=hash(canonical({self,profile,family}));need(graphHash===c.graph_hash);
   return{phase:'secondary_owner_current_graph_consistent',token_self_owner_verified:true,graph_hash:graphHash,merge_status:statuses.includes('UNKNOWN')?'UNKNOWN':'explicit_false',hidden_parent_completeness_proved:false,unknown_parent_risk_preserved:true,checked_at:Math.floor(Date.now()/1000),post_permitted:false,production_enabled:false};
  }
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('owner preflight blocked'));},10000);});return await Promise.race([work(),deadline]);
 }catch{throw Error('owner preflight blocked');}finally{active=false;ctl.abort();clearTimeout(timer);}
}
