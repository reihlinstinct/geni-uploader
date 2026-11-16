// Standalone bounded OIDC request. No create, service, journal or executor import.
const need=x=>{if(!x)throw Error('bounded workload acquisition blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
export async function requestBoundedWorkloadToken(env,origin,audience){
 const o=new URL(origin);need(o.protocol==='https:'&&o.origin===origin&&!o.port&&!o.username&&!o.password);need(typeof audience==='string'&&/^[A-Za-z0-9_.:/-]{1,200}$/.test(audience));
 const u=new URL(env.ACTIONS_ID_TOKEN_REQUEST_URL);need(u.origin===origin&&u.protocol==='https:'&&!u.username&&!u.password&&!u.hash&&u.pathname.length<=512&&u.search.length<=2048);
 need(!u.searchParams.has('audience'));u.searchParams.set('audience',audience);
 const credential=env.ACTIONS_ID_TOKEN_REQUEST_TOKEN;need(typeof credential==='string'&&credential.length>0&&credential.length<=16384&&!/[\r\n]/.test(credential));
 const ctl=new AbortController();let timer,active=true;
 try{
  const work=async()=>{const r=await fetch(u.href,{method:'GET',redirect:'manual',signal:ctl.signal,headers:{Authorization:'Bearer '+credential,Accept:'application/json'}});need(active&&r.status===200&&!r.redirected&&!r.headers.get('link')&&r.body);const reader=r.body.getReader(),chunks=[];let n=0;try{for(;;){const x=await reader.read();if(x.done)break;n+=x.value.length;need(active&&n<=32768);chunks.push(x.value);}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}const text=new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)),v=JSON.parse(text);exact(v,['value']);need((text.match(/"(?:[^"\\]|\\.)*"\s*:/g)||[]).length===1&&typeof v.value==='string'&&v.value.length<=16384&&/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(v.value));return v.value;};
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{active=false;ctl.abort();reject(Error('workload token request blocked'));},10000);});return await Promise.race([work(),deadline]);
 }finally{active=false;ctl.abort();clearTimeout(timer);}
}
