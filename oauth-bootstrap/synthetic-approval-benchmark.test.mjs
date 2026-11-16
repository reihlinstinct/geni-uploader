import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';
import { buildSyntheticBenchmark } from './build-synthetic-benchmark.mjs';
import { checkWorkerApprovalContent } from './worker-single-human-approval.mjs';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdtemp, mkdir, cp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

// Deliberate reviewed constants, not derived from the implementation under test.
// A source/compiler change requires explaining and reviewing each changed pin.
const EXPECTED_INPUTS = {
  'synthetic-approval-benchmark.mjs': '390639315697fada15c796caef71418625f3c703d7b699c5ec30f34c5dc5c645',
  'worker-approval-synthetic.json': '39e071e7a2f56d6db090d3f206dcaa7f9fb1b3b1d12d7956a5da88b126651d82',
  'worker-single-human-approval.mjs': '210278c4058a7170b8936e866f7204cb4092316e934a2bea5012754bcbe79a80',
};
const EXPECTED_BUNDLE = 'a2484fe2cc913b670ccd934587f5e344bcd8a450bd6800030389ea85dc46ce17';
const EXPECTED_RECORD = 'f481fbdeade50afd58dad3ab0b27a5fadadc5db9ad165a1fd5402bd384242ce8';

function assertKnownPackage(inventory) {
  assert.deepEqual(inventory.inputs, EXPECTED_INPUTS);
  assert.equal(inventory.bundle_sha256, EXPECTED_BUNDLE);
}

test('known package constants reject an altered module or bundle', () => {
  const good = { inputs: structuredClone(EXPECTED_INPUTS), bundle_sha256: EXPECTED_BUNDLE };
  assertKnownPackage(good);
  for (const name of Object.keys(EXPECTED_INPUTS)) {
    const changed = structuredClone(good);
    changed.inputs[name] = '0'.repeat(64);
    assert.throws(() => assertKnownPackage(changed));
  }
  assert.throws(() => assertKnownPackage({ ...good, bundle_sha256: '0'.repeat(64) }));
});

test('altered valid fixture has a different known content hash', async () => {
  const fixture = JSON.parse(await readFile(new URL('./worker-approval-synthetic.json', import.meta.url)));
  const original = JSON.stringify(fixture);
  const baseline = await checkWorkerApprovalContent(original, original, 100);
  assert.equal(baseline.record_hash, EXPECTED_RECORD);
  fixture.pins.nonce = 'e'.repeat(64);
  const changed = JSON.stringify(fixture);
  const result = await checkWorkerApprovalContent(changed, changed, 100);
  assert.notEqual(result.record_hash, EXPECTED_RECORD);
  assert.equal(result.owner_approval_verified, false);
  await assert.rejects(checkWorkerApprovalContent(changed, original, 100));
});

test('closed known build, actual workerd RPC and denied public ingress', { timeout: 45000 }, async () => {
  const a = await buildSyntheticBenchmark();
  const b = await buildSyntheticBenchmark();
  assertKnownPackage(a.inventory);
  assert.ok(a.bytes.equals(b.bytes));
  assert.deepEqual(a.inventory, b.inventory);
  assert.equal(a.inventory.bundle_sha256, createHash('sha256').update(a.bytes).digest('hex'));
  assert.deepEqual(a.inventory.runtime_bindings, []);
  assert.equal(a.inventory.executable, false);

  // Test-only caller: no dispatcher is part of the deployed package.
  const driver = `export default {
    async fetch(request, env) {
      try { return Response.json(await env.BENCH.run(...await request.json())); }
      catch { return new Response('Blocked', {status:403}); }
    }
  }`;
  const mf = new Miniflare(convertV4MiniflareOptions({ workers: [
    {
      name: 'ZZ-rpc-test-driver', modules: true, script: driver,
      compatibilityDate: '2026-10-01',
      serviceBindings: { BENCH: { name: 'ZZ-benchmark', entrypoint: 'ZZApprovalBenchmark' } },
    },
    {
      name: 'ZZ-benchmark', modules: true, script: a.bytes.toString(),
      compatibilityDate: '2026-10-01', compatibilityFlags: ['nodejs_compat'],
    },
  ] }));
  try {
    const target = await mf.getWorker('ZZ-benchmark');
    for (const method of ['GET', 'POST', 'PUT', 'DELETE']) {
      const response = await target.fetch('https://zz.invalid/run', { method });
      assert.equal(response.status, 403);
      assert.equal(await response.text(), 'Blocked');
    }
    const call = async args => mf.dispatchFetch('https://zz.invalid', {
      method: 'POST', body: JSON.stringify(args),
    });
    const response = await call([]);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.phase, 'synthetic_content_microbenchmark_only');
    assert.equal(result.provider_cpu_verified, false);
    assert.equal(result.owner_approval_verified, false);
    assert.equal(result.geni_calls, 0);
    assert.equal(result.post_permitted, false);
    assert.equal(result.record_hash, EXPECTED_RECORD);
    assert.deepEqual(await (await call([])).json(), result);
    assert.equal((await call([{ real_input: true }])).status, 403);
  } finally {
    await mf.dispose();
  }
});

async function temporarySource() {
  const dir = await mkdtemp(join(tmpdir(), 'ZZ-benchmark-copy-'));
  const root = new URL('..', import.meta.url).pathname;
  const files = [
    'build-synthetic-benchmark.mjs', 'synthetic-approval-benchmark.mjs',
    'worker-single-human-approval.mjs', 'worker-approval-synthetic.json',
    'package.json', 'package-lock.json',
  ];
  for (const file of files) {
    const relative = 'oauth-bootstrap/' + file;
    const target = join(dir, relative);
    await mkdir(join(target, '..'), { recursive: true });
    await cp(join(root, relative), target);
  }
  await cp(new URL('./node_modules', import.meta.url), join(dir, 'oauth-bootstrap/node_modules'), {
    recursive: true, dereference: true,
  });
  const git = args => execFileSync('git', args, { cwd: dir, stdio: 'ignore' });
  const commit = () => {
    git(['add', '.']);
    git(['-c', 'commit.gpgsign=false', '-c', 'user.name=ZZ', '-c',
      'user.email=zz@example.invalid', 'commit', '-qm', 'ZZ fixture']);
  };
  git(['init', '-q']);
  commit();
  return { dir, commit };
}

for (const mode of ['uncommitted', 'extra-import', 'fixture', 'compiler']) {
  test('fail closed ' + mode, async () => {
    const source = await temporarySource();
    try {
      const file = mode === 'fixture' ? 'worker-approval-synthetic.json'
        : mode === 'compiler' ? 'package-lock.json' : 'synthetic-approval-benchmark.mjs';
      const path = join(source.dir, 'oauth-bootstrap', file);
      let raw = await readFile(path, 'utf8');
      if (mode === 'fixture') {
        const fixture = JSON.parse(raw);
        fixture.pins.owner = 'profile-123';
        raw = JSON.stringify(fixture);
      } else if (mode === 'compiler') {
        const lock = JSON.parse(raw);
        lock.packages['node_modules/esbuild'].version = '0.0.0';
        raw = JSON.stringify(lock);
      } else if (mode === 'extra-import') {
        await writeFile(join(source.dir, 'oauth-bootstrap/ZZ-extra.mjs'), 'export const value=1;');
        raw = "import{value}from'./ZZ-extra.mjs';console.log(value);\n" + raw;
      } else {
        raw += '\n// ZZ dirty\n';
      }
      await writeFile(path, raw);
      if (mode !== 'uncommitted') source.commit();
      const module = await import(new URL('file://' + join(source.dir, 'oauth-bootstrap/build-synthetic-benchmark.mjs')));
      await assert.rejects(module.buildSyntheticBenchmark(), /^Error: synthetic benchmark build blocked$/);
    } finally {
      await rm(source.dir, { recursive: true, force: true });
    }
  });
}
