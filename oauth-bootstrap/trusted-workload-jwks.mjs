// Fixed-issuer network trust boundary. No owner consent, replay store or permit.
import { importJWK } from 'jose';
import { verifyOfflineWorkload } from './intent-workload-verifier.mjs';
const URL = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const fail = () => { throw new Error('trusted workload verification blocked'); };
const check = value => { if (!value) fail(); };
function parseUnique(raw) {
  const result = JSON.parse(raw);
  const stack = [];
  const tokens = raw.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g) || [];
  for (let n=0;n<tokens.length;n++) {
    const t=tokens[n];
    if(t==='{') {stack.push(new Set());check(stack.length<=8);}
    else if(t==='[') {stack.push(null);check(stack.length<=8);}
    else if(t==='}'||t===']') stack.pop();
    else if(t[0]==='"'&&tokens[n+1]===':') {
      const keys=stack.at(-1);check(keys instanceof Set);
      const key=JSON.parse(t);check(!keys.has(key));keys.add(key);
    }
  }
  return result;
}
function headerKid(token) {
  check(typeof token==='string'&&token.length<=16384);
  const parts=token.split('.');check(parts.length===3);
  check(/^[A-Za-z0-9_-]+$/.test(parts[0]));
  const bytes=Buffer.from(parts[0],'base64url');
  check(bytes.toString('base64url')===parts[0]);
  const h=parseUnique(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  check(h&&Object.keys(h).sort().join(',')==='alg,kid,typ');
  check(h.alg==='RS256'&&h.typ==='JWT'&&typeof h.kid==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(h.kid));
  return h.kid;
}
async function bounded(response) {
  check(response.status===200&&!response.redirected&&response.body);
  const declared=response.headers.get('content-length');
  if(declared!==null) check(/^[0-9]+$/.test(declared)&&Number(declared)<=65536);
  const reader=response.body.getReader();const chunks=[];let total=0;
  try {
    while(true) {const {done,value}=await reader.read();if(done)break;
      total+=value.byteLength;check(total<=65536);chunks.push(value);}
    check(total>0);
    const bytes=new Uint8Array(total);let offset=0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    return new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  } finally {await reader.cancel().catch(()=>{});reader.releaseLock();}
}
export async function verifyTrustedWorkload(token, pins) {
  // System/server clock, never a caller-supplied approval timestamp.
  const controller=new AbortController();
  let timer;
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();
    reject(new Error('trusted workload verification blocked'));},5000);});
  const operation=async()=>{
    const kid=headerKid(token);
    check(pins&&pins.kid===kid);
    const response=await fetch(URL,{redirect:'error',signal:controller.signal,
      headers:{Accept:'application/json'}});
    const jwks=parseUnique(await bounded(response));
    check(jwks&&Object.keys(jwks).join(',')==='keys'&&Array.isArray(jwks.keys)
      &&jwks.keys.length>0&&jwks.keys.length<=16);
    const seen=new Set();
    for(const key of jwks.keys) {
      check(key&&typeof key==='object'&&!Array.isArray(key)&&typeof key.kid==='string'
        &&/^[A-Za-z0-9_-]{1,100}$/.test(key.kid)&&!seen.has(key.kid));seen.add(key.kid);
      check(!['d','p','q','dp','dq','qi','oth','jku','x5u'].some(k=>k in key));
    }
    const key=jwks.keys.find(k=>k.kid===kid);check(key);
    check(key.kty==='RSA'&&key.alg==='RS256'&&key.use==='sig'
      &&typeof key.n==='string'&&/^[A-Za-z0-9_-]+$/.test(key.n)
      &&Buffer.from(key.n,'base64url').toString('base64url')===key.n
      &&Buffer.from(key.n,'base64url').length>=256&&Buffer.from(key.n,'base64url').length<=512
      &&key.e==='AQAB');
    if('key_ops' in key) check(Array.isArray(key.key_ops)&&key.key_ops.length===1&&key.key_ops[0]==='verify');
    const publicKey=await importJWK(key,'RS256');
    return await verifyOfflineWorkload(token,publicKey,pins,Math.floor(Date.now()/1000));
  };
  try {return await Promise.race([operation(),deadline]);}
  catch {fail();} finally {controller.abort();clearTimeout(timer);}
}
