import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import sodium from 'libsodium-wrappers';
test('fixed bridge sealer interoperates with independent sodium',async()=>{
  await sodium.ready;
  const keys=sodium.crypto_box_keypair();
  const run=spawnSync(process.execPath,['source-slot-seal.mjs'],{
    cwd:new URL('.',import.meta.url),
    input:JSON.stringify({value:'ZZ-synthetic-source',public:Buffer.from(keys.publicKey).toString('base64')})});
  assert.equal(run.status,0);
  const plain=sodium.crypto_box_seal_open(Buffer.from(run.stdout.toString(),'base64'),keys.publicKey,keys.privateKey);
  assert.equal(sodium.to_string(plain),'ZZ-synthetic-source');
  assert.equal(run.stderr.length,0);
});
