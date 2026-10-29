import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPair, SignJWT } from 'jose';
import { PIN_CLAIMS, verifyOfflineWorkload as verify } from './intent-workload-verifier.mjs';
const { publicKey, privateKey } = await generateKeyPair('RS256');
const other = await generateKeyPair('RS256');
const now = 2000000000;
const pins = { iss: 'https://token.actions.githubusercontent.com', aud: 'ZZ-intent', sub: 'ZZ-reviewed-subject',
  repository: 'ZZ-org/ZZ-repo', repository_id: '999001', repository_owner_id: '999002',
  workflow_ref: 'ZZ-org/ZZ-repo/.github/workflows/ZZ.yml@refs/heads/master',
  workflow_sha: 'a'.repeat(40), sha: 'b'.repeat(40), ref: 'refs/heads/master',
  environment: 'ZZ-protected', event_name: 'workflow_dispatch', actor_id: '999003', run_id: '999004',
  run_attempt: '1', runner_environment: 'github-hosted', kid: 'ZZ-key' };
const claims = () => ({ ...Object.fromEntries(PIN_CLAIMS.map(k => [k, pins[k]])),
  iat: now - 10, nbf: now - 10, exp: now + 60, jti: 'ZZ-unique' });
const sign = async (body = claims(), header = {}, key = privateKey) =>
  new SignJWT(body).setProtectedHeader({ alg: 'RS256', typ: 'JWT', kid: pins.kid, ...header }).sign(key);
test('valid signature gives workload identity only, NOT authority/replay protection', async () => {
  assert.deepEqual(await verify(await sign(), publicKey, pins, now), {
    mode: 'offline_workload_identity_only', workload_verified: true,
    owner_approval_verified: false, replay_protection_provided: false, production_enabled: false });
});
for (const key of PIN_CLAIMS) {
  test(`each exact claim ${key} mismatch and missing reject`, async () => {
    const body = claims(); body[key] = 'ZZ-wrong';
    await assert.rejects(verify(await sign(body), publicKey, pins, now));
    delete body[key]; await assert.rejects(verify(await sign(body), publicKey, pins, now));
  });
}
for (const [key, value] of [['exp', now], ['iat', now + 1], ['nbf', now + 1],
  ['iat', now - 301], ['exp', now + 1000], ['exp', true], ['jti', 'https://ZZ.invalid'],
  ['aud', [pins.aud]], ['job_workflow_ref', 'ZZ-reusable'], ['unexpected', 'ZZ-extra']]) {
  test(`reject bad time/type/extra ${key}:${value}`, async () => {
    await assert.rejects(verify(await sign({ ...claims(), [key]: value }), publicKey, pins, now));
  });
}
test('wrong key header kid URL and algorithm rejected without diagnostic echo', async () => {
  for (const token of [await sign(claims(), {}, other.privateKey), await sign(claims(), { kid: 'ZZ-other' }),
    await sign(claims(), { jku: 'https://ZZ.invalid' }), await sign(claims(), { typ: 'ZZ-other' }),
    'eyJhbGciOiJub25lIn0.e30.', 'ZZ-token', 'Z'.repeat(16385)]) {
    await assert.rejects(verify(token, publicKey, pins, now), { message: 'offline workload identity rejected' });
  }
});
test('bad pins private key and invalid clock rejected', async () => {
  const token = await sign();
  for (const changed of [{ ...pins, ref: 'refs/heads/ZZ-other' }, { ...pins, run_attempt: '2' },
    { ...pins, repository_id: '01' }, { ...pins, extra: true }])
    await assert.rejects(verify(token, publicKey, changed, now));
  await assert.rejects(verify(token, privateKey, pins, now));
  await assert.rejects(verify(token, publicKey, pins, true));
});
test('duplicate signed claims/header and signature tampering rejected', async () => {
  const { sign: rsaSign } = await import('node:crypto');
  function manual(header, body) {
    const prefix = Buffer.from(header).toString('base64url') + '.' + Buffer.from(body).toString('base64url');
    return prefix + '.' + rsaSign('RSA-SHA256', Buffer.from(prefix), privateKey).toString('base64url');
  }
  const head = JSON.stringify({ alg: 'RS256', typ: 'JWT', kid: pins.kid });
  const raw = JSON.stringify(claims());
  const duplicatePayload = raw.slice(0, -1) + ',"run_attempt":"1"}';
  const duplicateHeader = head.slice(0, -1) + ',"alg":"RS256"}';
  for (const token of [manual(head, duplicatePayload), manual(duplicateHeader, raw),
    (() => { const parts = manual(head, raw).split('.');
      parts[2] = (parts[2][0] === 'A' ? 'B' : 'A') + parts[2].slice(1);
      return parts.join('.'); })()]) {
    await assert.rejects(verify(token, publicKey, pins, now));
  }
});
test('HS256 ES256 and detached-untrusted headers are rejected', async () => {
  const { generateSecret } = await import('jose');
  const secret = await generateSecret('HS256');
  const ec = await generateKeyPair('ES256');
  for (const token of [await new SignJWT(claims()).setProtectedHeader({ alg: 'HS256', kid: pins.kid, typ: 'JWT' }).sign(secret),
    await new SignJWT(claims()).setProtectedHeader({ alg: 'ES256', kid: pins.kid, typ: 'JWT' }).sign(ec.privateKey),
    await sign(claims(), { x5u: 'https://ZZ.invalid/key' })])
    await assert.rejects(verify(token, publicKey, pins, now));
});
test('each time claim missing and noninteger rejects', async () => {
  for (const field of ['iat', 'nbf', 'exp']) {
    const body = claims(); delete body[field];
    await assert.rejects(verify(await sign(body), publicKey, pins, now));
    body[field] = now - 0.5;
    await assert.rejects(verify(await sign(body), publicKey, pins, now));
  }
});


test('noncanonical signature padding bits rejected even with identical decoded bytes', async () => {
  const token = await sign(); const parts = token.split('.');
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const last = alphabet.indexOf(parts[2].at(-1));
  assert.equal(last % 16, 0); // RS256 2048-bit key yields 256 bytes.
  parts[2] = parts[2].slice(0, -1) + alphabet[last + 1];
  assert.deepEqual(Buffer.from(parts[2], 'base64url'), Buffer.from(token.split('.')[2], 'base64url'));
  await assert.rejects(verify(parts.join('.'), publicKey, pins, now));
});
function officialShape(){
 const p={...pins,sub:'repo:ZZ-org@999002/ZZ-repo@999001:environment:ZZ-protected',job_workflow_ref:'ZZ-org/ZZ-automation/.github/workflows/ZZ.yml@refs/heads/master',job_workflow_sha:'c'.repeat(40)};
 const body={...claims(),sub:p.sub,job_workflow_ref:p.job_workflow_ref,job_workflow_sha:p.job_workflow_sha,repository_owner:'ZZ-org',actor:'ZZ-actor',repository_visibility:'public',run_number:'10',workflow:'ZZ-workflow',head_ref:'',base_ref:'',ref_type:'branch',check_run_id:'999005',repo_property_workspace_id:'ZZ-workspace'};
 return{p,body};
}
test('documented GitHub-shaped x5t and informational extras with ID-bound subject and pinned reusable workflow',async()=>{
 const{p,body}=officialShape();const out=await verify(await sign(body,{x5t:'ZZ-thumbprint'}),publicKey,p,now);assert.equal(out.workload_verified,true);assert.equal(out.owner_approval_verified,false);
});
for(const k of ['sub','job_workflow_ref','job_workflow_sha'])test('official-shaped load-bearing '+k+' missing/mismatch rejected',async()=>{
 for(const missing of[true,false]){const{p,body}=officialShape();if(missing)delete body[k];else body[k]='ZZ-wrong';await assert.rejects(verify(await sign(body,{x5t:'ZZ-thumbprint'}),publicKey,p,now));}
});
test('unreviewed reusable workflow claims reject instead of silently treating as extras',async()=>{const{body}=officialShape();await assert.rejects(verify(await sign(body),publicKey,{...pins,sub:body.sub},now));});
for(const [label,change]of[['unknown',b=>b.ZZ_unknown='ZZ'],['nested',b=>b.actor={id:'ZZ'}],['extra cap',b=>b.actor='Z'.repeat(501)],['empty required',b=>b.repository_id=''],['old name-only subject',b=>b.sub='repo:ZZ-org/ZZ-repo:environment:ZZ-protected']])test('official-shaped '+label+' rejected',async()=>{const{p,body}=officialShape();change(body);await assert.rejects(verify(await sign(body),publicKey,p,now));});
