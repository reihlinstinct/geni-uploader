// Strict bounded binary multipart candidate. No provider transport or authority.
const need=x=>{if(!x)throw Error('fake module readback blocked');};
const bytes=s=>new TextEncoder().encode(s);
const ascii=b=>{need(b.every(x=>x>=32&&x<=126||x===13||x===10));return String.fromCharCode(...b);};
const equal=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
const hash=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),x=>x.toString(16).padStart(2,'0')).join('');
function positions(all,needle){const found=[];for(let i=0;i<=all.length-needle.length;i++){if(all[i]===needle[0]&&needle.every((x,j)=>all[i+j]===x))found.push(i);}return found;}
export async function checkFakeMultipartModules(response,expected,etag){
 need(response&&response.status===200&&response.redirected===false&&response.body&&response.type!=='opaqueredirect'&&!response.headers.get('link'));
 need(response.headers.get('etag')==='"'+etag+'"');
 const contentType=response.headers.get('content-type'),match=typeof contentType==='string'&&/^multipart\/form-data; boundary=([A-Za-z0-9_-]{1,70})(?![\s\S])/.exec(contentType);need(match);const delimiter=bytes('--'+match[1]);
 const reader=response.body.getReader(),chunks=[];let size=0;try{for(;;){const x=await reader.read();if(x.done)break;need(x.value instanceof Uint8Array);size+=x.value.length;need(size<=2097152);chunks.push(x.value);}}finally{reader.cancel().catch(()=>{});reader.releaseLock();}
 const all=new Uint8Array(size);let offset=0;for(const b of chunks){all.set(b,offset);offset+=b.length;}
 need(equal(all.slice(0,delimiter.length),delimiter));const split=positions(all,bytes('\r\n--'+match[1]));need(split.length===expected.length&&split.length<=16);let start=delimiter.length+2;need(equal(all.slice(delimiter.length,start),bytes('\r\n')));const seen=new Set(),descriptors=[];
 for(let i=0;i<split.length;i++){
  const end=split[i];need(end>=start);const part=all.slice(start,end),separators=positions(part,bytes('\r\n\r\n'));need(separators.length>=1&&separators[0]<=4096);const cut=separators[0],headers=ascii(part.slice(0,cut)).split('\r\n');need(headers.length===2);
  const disposition=/^Content-Disposition: form-data; name="([A-Za-z0-9_.-]{1,100})"; filename="([A-Za-z0-9_.-]{1,100})"(?![\s\S])/.exec(headers[0]),type=/^Content-Type: ([a-z0-9.+-]+\/[a-z0-9.+-]+)(?![\s\S])/.exec(headers[1]);need(disposition&&type&&disposition[1]===disposition[2]);const name=disposition[1];need(name!=='.'&&name!=='..'&&!seen.has(name));seen.add(name);
  const spec=expected.find(x=>x.name===name);need(spec&&spec.type===type[1]);const body=part.slice(cut+4);need(body.length===spec.byte_length&&await hash(body)===spec.sha256);descriptors.push({name,type:type[1],byte_length:body.length,sha256:spec.sha256});
  start=end+2+delimiter.length;const last=i===split.length-1;
  if(last)need(equal(all.slice(start),bytes('--\r\n')));else{need(equal(all.slice(start,start+2),bytes('\r\n')));start+=2;}
 }
 need(seen.size===expected.length);return descriptors.sort((a,b)=>a.name.localeCompare(b.name));
}
