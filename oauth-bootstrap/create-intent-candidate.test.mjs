import { test } from 'node:test';
import assert from 'node:assert/strict';
import { OfflineCreateIntentCandidate as Candidate } from './create-intent-candidate.mjs';
const H = c => c.repeat(64);
const bind = () => ({ owner: 'profile-999001', connection: 'ZZ-secondary',
  plan: H('1'), payload: H('2'), artifact: H('3'), policy: H('4') });
class FakeStorage {
  rows = new Map(); queue = Promise.resolve(); fail = 0; puts = 0;
  transaction(fn) {
    const run = this.queue.then(async () => {
      const copy = structuredClone(this.rows); this.puts = 0;
      const tx = { get: async k => structuredClone(copy.get(k)),
        put: async (k, v) => { if (++this.puts === this.fail) throw Error('ZZ crash');
          copy.set(k, structuredClone(v)); } };
      const result = await fn(tx); this.rows = copy; return result;
    });
    this.queue = run.catch(() => {}); return run;
  }
}
const setup = () => { const store = new FakeStorage();
  return [store, new Candidate(store, 'profile-999001')]; };
test('synthetic CAS excludes variants and fresh instances sharing owner storage', async () => {
  const [store] = setup();
  const runs = Array.from({ length: 20 }, (_, n) => {
    const b = bind(); b.connection = `ZZ-${n}`; b.plan = n.toString(16).padStart(64, '0');
    return new Candidate(store, b.owner).consume(b, 0);
  });
  const results = await Promise.allSettled(runs);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  assert.equal(store.rows.size, 2);
});
test('transaction rollback after first or second write never leaves partial record', async () => {
  for (const fail of [1, 2]) {
    const [store, c] = setup(); store.fail = fail;
    await assert.rejects(c.consume(bind(), 0)); assert.equal(store.rows.size, 0);
    store.fail = 0; await c.consume(bind(), 0);
    const before = structuredClone(store.rows); store.fail = fail;
    await assert.rejects(c.advance(bind(), 1, 'acknowledge', H('a'), 'profile-999002'));
    assert.deepEqual(store.rows, before);
  }
});
test('consumed survives lost acknowledgment and cannot be replayed', async () => {
  const [store, c] = setup(); await c.consume(bind(), 0);
  await assert.rejects(new Candidate(store, bind().owner).consume(bind(), 0));
  const s = await c.advance(bind(), 1, 'uncertain', H('a'));
  assert.equal(s.phase, 'uncertain');
  assert.equal((await c.advance(bind(), 2, 'reconcile_verified', H('b'),
    'profile-999002')).production_enabled, false);
});
for (const shape of ['consumed', 'acknowledged', 'unknown', 'known', 'verified']) {
  for (const event of ['acknowledge', 'uncertain', 'verify', 'reconcile_verified', 'reset', 'retry', 'delete']) {
    test(`independent matrix ${shape}/${event}`, async () => {
      const [store, c] = setup(); await c.consume(bind(), 0);
      if (['acknowledged', 'known', 'verified'].includes(shape))
        await c.advance(bind(), 1, 'acknowledge', H('a'), 'profile-999002');
      if (shape === 'unknown') await c.advance(bind(), 1, 'uncertain', H('a'));
      if (shape === 'known') await c.advance(bind(), 2, 'uncertain', H('b'));
      if (shape === 'verified') await c.advance(bind(), 2, 'verify', H('b'));
      const allowed = { consumed: ['acknowledge', 'uncertain'], acknowledged: ['verify', 'uncertain'],
        unknown: ['reconcile_verified'], known: ['reconcile_verified'], verified: [] };
      const before = structuredClone(store.rows); const prev = before.get('intent');
      const id = ['acknowledge', 'reconcile_verified'].includes(event) ? 'profile-999002' : null;
      const promise = c.advance(bind(), prev.version, event, H('c'), id);
      if (allowed[shape].includes(event)) {
        const result = await promise; assert.equal(result.version, prev.version + 1);
        assert.deepEqual(store.rows.get(`event:${prev.version}`), prev);
        assert.equal(result.production_enabled, false);
      } else { await assert.rejects(promise); assert.deepEqual(store.rows, before); }
    });
  }
}
test('bad binding stale version duplicated evidence wrong IDs fail without changing state', async () => {
  const [store, c] = setup(); await c.consume(bind(), 0);
  for (const b of [{ ...bind(), owner: 'profile-999003' }, { ...bind(), plan: H('a') },
    { ...bind(), extra: true }, { ...bind(), owner: 'profile-01' }]) {
    await assert.rejects(c.advance(b, 1, 'uncertain', H('b')));
  }
  await assert.rejects(c.advance(bind(), 0, 'uncertain', H('a')));
  await assert.rejects(c.advance(bind(), true, 'uncertain', H('a')));
  await assert.rejects(c.advance(bind(), 1, 'acknowledge', H('a'), bind().owner));
  await assert.rejects(c.advance(bind(), 1, 'uncertain', 'https://ZZ.invalid'));
  await c.advance(bind(), 1, 'acknowledge', H('a'), 'profile-999002');
  const before = structuredClone(store.rows);
  await assert.rejects(c.advance(bind(), 2, 'verify', H('a')));
  await c.advance(bind(), 2, 'uncertain', H('b'));
  await assert.rejects(c.advance(bind(), 3, 'reconcile_verified', H('c'), 'profile-999003'));
  assert.equal(store.rows.get('intent').created_id, 'profile-999002');
  assert.deepEqual(store.rows.get('event:2'), before.get('event:2'));
});
test('committed response lost preserves permanent consumption', async () => {
  const [store] = setup(); const transaction = store.transaction.bind(store);
  let lose = true;
  store.transaction = async fn => { const value = await transaction(fn);
    if (lose) { lose = false; throw Error('ZZ lost response after commit'); } return value; };
  const c = new Candidate(store, bind().owner);
  await assert.rejects(c.consume(bind(), 0));
  assert.equal(store.rows.get('intent').phase, 'consumed');
  await assert.rejects(new Candidate(store, bind().owner).consume(bind(), 0));
  assert.equal(store.rows.size, 2);
});
test('changed stored schema and preexisting history slot reject atomically', async () => {
  for (const change of [s => { s.version = true; }, s => { s.phase = 'retry'; },
    s => { s.extra = true; }, s => { s.production_enabled = true; },
    s => { s.binding.owner = 'profile-999003'; }, s => { s.created_id = bind().owner; }]) {
    const [store, c] = setup(); await c.consume(bind(), 0);
    const s = store.rows.get('intent'); change(s); const before = structuredClone(store.rows);
    await assert.rejects(c.advance(bind(), 1, 'uncertain', H('a')));
    assert.deepEqual(store.rows, before);
  }
  const [store, c] = setup(); await c.consume(bind(), 0);
  store.rows.set('event:2', { ZZ: 'occupied' }); const before = structuredClone(store.rows);
  await assert.rejects(c.advance(bind(), 1, 'uncertain', H('a')));
  assert.deepEqual(store.rows, before);
});
for (const key of ['owner', 'connection', 'plan', 'payload', 'artifact', 'policy']) {
  test(`immutable binding rejects changed ${key} before state/history mutation`, async () => {
    const [store, c] = setup(); await c.consume(bind(), 0);
    const before = structuredClone(store.rows); const changed = bind();
    changed[key] = key === 'owner' ? 'profile-999003' : key === 'connection' ? 'ZZ-other' : H('f');
    await assert.rejects(c.advance(changed, 1, 'uncertain', H('a')));
    assert.deepEqual(store.rows, before);
  });
}
test('two concurrent same-version advances yield exactly one atomic winner', async () => {
  const [store, c] = setup(); await c.consume(bind(), 0);
  const results = await Promise.allSettled([
    c.advance(bind(), 1, 'acknowledge', H('a'), 'profile-999002'),
    new Candidate(store, bind().owner).advance(bind(), 1, 'uncertain', H('b')),
  ]);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  assert.equal(results.filter(r => r.status === 'rejected').length, 1);
  const winner = results.find(r => r.status === 'fulfilled').value;
  assert.equal(winner.version, 2); assert.equal(store.rows.size, 3);
  assert.deepEqual(store.rows.get('intent'), winner);
  assert.deepEqual(store.rows.get('event:2'), winner);
  assert.equal(store.rows.get('event:1').phase, 'consumed');
});
test('occupied first history slot without intent blocks consume without overwrite', async () => {
  const [store, c] = setup(); store.rows.set('event:1', { ZZ: 'preserve-history' });
  const before = structuredClone(store.rows);
  await assert.rejects(c.consume(bind(), 0));
  assert.deepEqual(store.rows, before);
});
