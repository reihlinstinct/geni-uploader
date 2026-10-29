// Dormant transport only. Deployment-owned plan/credential are NOT authorization.
const message='worker evidence read blocked';
const need=x=>{if(!x)throw Error(message);};
function parse(text){
 const tokens=text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g)||[],stack=[];
 for(let i=0;i<tokens.length;i++){
  const t=tokens[i];if(t==='{')stack.push(new Set());else if(t==='[')stack.push(null);else if(t==='}'||t===']')stack.pop();
  else if(t[0]==='"'&&tokens[i+1]===':'){const key=JSON.parse(t),s=stack.at(-1);need(s instanceof Set&&!s.has(key));s.add(key);}
  need(stack.length<=16);
 }
 return JSON.parse(text);
}
export function createWorkerEvidenceTransport({routes,credential},fetcher=fetch){
 try{
  need(Array.isArray(routes)&&routes.length>0&&routes.length<=16&&new Set(routes).size===routes.length);
  // Exact deployment-owned routes; reject URL normalization/host override tricks.
  for(const path of routes)need(typeof path==='string'&&path.length<=512&&/^\/repos\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+\/[A-Za-z0-9_/?=&.-]+(?![\s\S])/.test(path)&&!path.includes('..')&&!path.includes('//')&&!path.includes('#')&&new URL('https://api.github.com'+path).pathname+new URL('https://api.github.com'+path).search===path);
  need(typeof credential==='string'&&/^[A-Za-z0-9_]{1,4096}(?![\s\S])/.test(credential)&&typeof fetcher==='function');
  const allowed=new Set(routes),controller=new AbortController(),readers=new Set();let count=0,total=0,active=true,rejectStop;
  const stopped=new Promise((_,reject)=>{rejectStop=reject;});stopped.catch(()=>{});
  const close=()=>{if(!active)return;active=false;clearTimeout(timer);controller.abort();for(const r of readers)Promise.resolve(r.cancel()).catch(()=>{});rejectStop(Error(message));};
  const timer=setTimeout(close,10000);
  async function get(path){
   try{
    need(active&&allowed.has(path)&&++count<=16);
    const work=(async()=>{
     const r=await fetcher('https://api.github.com'+path,{method:'GET',redirect:'manual',signal:controller.signal,headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+credential,'X-GitHub-Api-Version':'2022-11-28'}});
     need(active&&r.status===200&&!r.redirected&&!r.headers.has('link')&&r.body);
     const declared=r.headers.get('content-length');need(declared===null||(/^[0-9]+(?![\s\S])/.test(declared)&&Number(declared)<=262144));
     const reader=r.body.getReader();readers.add(reader);let size=0;const chunks=[];
     try{for(;;){const x=await reader.read();need(active);if(x.done)break;need(x.value instanceof Uint8Array);size+=x.value.byteLength;total+=x.value.byteLength;need(size<=262144&&total<=1048576);chunks.push(x.value);}}
     finally{readers.delete(reader);await reader.cancel().catch(()=>{});reader.releaseLock();}
     need(active);const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
     return parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
    })();
    return await Promise.race([work,stopped]);
   }catch{close();throw Error(message);}
  }
  return Object.freeze({get,close});
 }catch{throw Error(message);}
}
