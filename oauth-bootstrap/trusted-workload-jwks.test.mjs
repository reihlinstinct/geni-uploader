import test from 'node:test';
import {generateKeyPairSync} from 'node:crypto';
import assert from 'node:assert/strict';
import {generateKeyPair,exportJWK,SignJWT} from 'jose';
import {PIN_CLAIMS} from './intent-workload-verifier.mjs';
import {verifyTrustedWorkload as verify} from './trusted-workload-jwks.mjs';
const pair=await generateKeyPair('RS256');const jwk={...await exportJWK(pair.publicKey),kid:'ZZ-key',alg:'RS256',use:'sig'};
const now=Math.floor(Date.now()/1000);
const pins={iss:'https://token.actions.githubusercontent.com',aud:'ZZ-intent',sub:'ZZ-reviewed',repository:'ZZ-org/ZZ-repo',repository_id:'999001',repository_owner_id:'999002',workflow_ref:'ZZ-org/ZZ-repo/.github/workflows/ZZ.yml@refs/heads/master',workflow_sha:'a'.repeat(40),sha:'b'.repeat(40),ref:'refs/heads/master',environment:'ZZ-protected',event_name:'workflow_dispatch',actor_id:'999003',run_id:'999004',run_attempt:'1',runner_environment:'github-hosted',kid:'ZZ-key'};
const claims={...Object.fromEntries(PIN_CLAIMS.map(k=>[k,pins[k]])),iat:now-1,nbf:now-1,exp:now+60,jti:'ZZ-test'};
const token=await new SignJWT(claims).setProtectedHeader({alg:'RS256',typ:'JWT',kid:pins.kid}).sign(pair.privateKey);
test('fixed issuer key verifies only workload, no authority',async t=>{
  let calls=0;t.mock.method(globalThis,'fetch',async(url,options)=>{
    calls++;assert.equal(url,'https://token.actions.githubusercontent.com/.well-known/jwks');
    assert.equal(options.redirect,'error');assert.ok(options.signal instanceof AbortSignal);
    assert.equal(options.headers.Accept,'application/json');return Response.json({keys:[jwk]});});
  const result=await verify(token,pins);assert.equal(calls,1);assert.equal(result.workload_verified,true);
  assert.equal(result.production_enabled,false);assert.equal(result.owner_approval_verified,false);
});
for(const [label,raw] of [
 ['duplicate-kid',JSON.stringify({keys:[jwk,jwk]})],['unknown-kid',JSON.stringify({keys:[{...jwk,kid:'ZZ-other'}]})],
 ['wrong-alg',JSON.stringify({keys:[{...jwk,alg:'HS256'}]})],['private-key',JSON.stringify({keys:[{...jwk,d:'ZZSECRET'}]})],
 ['duplicate-json',JSON.stringify({keys:[jwk]}).replace('"keys":','"keys":[],"keys":')],
 ['empty','{"keys":[]}'],['oversize','x'.repeat(65537)],['invalid-json','ZZSECRET'],
 ['key-count',JSON.stringify({keys:Array.from({length:17},(_,i)=>({...jwk,kid:'ZZ-'+i}))})],
 ['small-modulus',JSON.stringify({keys:[{...jwk,n:'AAAA'}]})],['wrong-use',JSON.stringify({keys:[{...jwk,use:'enc'}]})],
 ['wrong-ops',JSON.stringify({keys:[{...jwk,key_ops:['sign']}]})]]) {
 test(label+' fails value-free without retry',async t=>{let calls=0;
  t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response(raw);});
  await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});assert.equal(calls,1);
 });
}
test('redirect error and non200 are never followed/retried',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response(JSON.stringify({keys:[jwk]}),{status:302,headers:{Location:'https://zz.invalid'}});});
 await assert.rejects(verify(token,pins));assert.equal(calls,1);
});
test('malformed header rejected before network',async t=>{let calls=0;
 t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('ZZSECRET');});
 await assert.rejects(verify('ZZ.bad.token',pins));assert.equal(calls,0);
});

test('nonsettling fetch is bounded even if mock ignores abort',async t=>{
 const real=globalThis.setTimeout;
 t.mock.method(globalThis,'setTimeout',(fn,ms)=>{assert.equal(ms,5000);return real(fn,5);});
 t.mock.method(globalThis,'fetch',async()=>new Promise(()=>{}));
 await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});
});
test('stream over cap without content-length is refused',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(new ReadableStream({start(c){
   c.enqueue(new Uint8Array(40000));c.enqueue(new Uint8Array(30000));c.close();}})));
 await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});
});
test('malformed JSON header and declared size produce fixed errors',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('{}',{
   headers:{'content-length':'65537'}});});
 await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});
 const bad=Buffer.from('ZZSECRET').toString('base64url')+'.e30.AA';
 await assert.rejects(verify(bad,pins),{message:'trusted workload verification blocked'});
 assert.equal(calls,1);
});

// Every fixture is otherwise valid and keeps the pinned key, so adjacent
// parsing/lookup/type guards cannot mask removal of these exact bounds.
const validOversize=JSON.stringify({keys:[jwk]})+' '.repeat(65537);
for(const [label,body,options] of [
 ['declared valid JSON byte cap',JSON.stringify({keys:[jwk]}),{headers:{'content-length':'65537'}}],
 ['streamed valid JSON byte cap',validOversize,{}],
])test(label,async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(body,options));
 await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});
});
for(const [label,modulusLength,publicExponent] of [
 ['large modulus',4608,65537], ['wrong exponent',2048,3],
])test(label+' rejects even when token signature matches that key',async t=>{
 const custom=generateKeyPairSync('rsa',{modulusLength,publicExponent});
 const key={...custom.publicKey.export({format:'jwk'}),kid:pins.kid,alg:'RS256',use:'sig'};
 const customToken=await new SignJWT(claims).setProtectedHeader({alg:'RS256',typ:'JWT',kid:pins.kid}).sign(custom.privateKey);
 t.mock.method(globalThis,'fetch',async()=>Response.json({keys:[key]}));
 await assert.rejects(verify(customToken,pins),{message:'trusted workload verification blocked'});
});
test('key count retains pinned valid key and isolates set cap',async t=>{
 const keys=[jwk,...Array.from({length:16},(_,i)=>({...jwk,kid:'ZZ-extra-'+i}))];
 t.mock.method(globalThis,'fetch',async()=>Response.json({keys}));
 await assert.rejects(verify(token,pins),{message:'trusted workload verification blocked'});
});
