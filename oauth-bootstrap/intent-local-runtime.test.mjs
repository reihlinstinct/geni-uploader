// Local workerd SQLite rehearsal only. No deployment, credentials or Geni.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { Miniflare, convertV4MiniflareOptions } from 'miniflare';

const H = c => c.repeat(64);
const binding = () => ({ owner: 'profile-999001', connection: 'ZZ-secondary',
  plan: H('1'), payload: H('2'), artifact: H('3'), policy: H('4') });
const here = dirname(fileURLToPath(import.meta.url));

// TEST-ONLY wrapper: no production auth or owner routing. Outbound fetch denied.
const fixture = `
import {OfflineCreateIntentCandidate as Candidate} from './create-intent-candidate.mjs';
export class ZZIntent {
  constructor(ctx) {this.ctx=ctx;this.c=new Candidate(ctx.storage,'profile-999001');}
  async fetch(request) {
    try {
      const body=await request.json();
      let result;
      if(body.action==='consume') result=await this.c.consume(body.binding,0);
      else if(body.action==='advance') result=await this.c.advance(body.binding,
        body.version,body.event,body.evidence,body.createdId??null);
      else if(body.action==='inspect') {
        result={intent:await this.ctx.storage.get('intent'),
          events:[...await this.ctx.storage.list({prefix:'event:'})].map(([k,v])=>[k,v])};
      } else throw Error('ZZ unsupported');
      return Response.json(result);
    } catch {return new Response('ZZ blocked',{status:409});}
  }
}
export default {fetch(request,env) {
  return env.ZZ.get(env.ZZ.idFromName('ZZ-fixed-owner')).fetch(request);
}};
`;

test('local SQLite DO consumes once across concurrency and runtime restart',
  { timeout: 45000 }, async () => {
    const dir = await mkdtemp(join(tmpdir(), 'zz-intent-rehearsal-'));
    const bundle = await build({ stdin: { contents: fixture, resolveDir: here,
      sourcefile: 'ZZ-local-only.mjs' }, bundle: true, format: 'esm', write: false });
    let mf;
    let outbound = 0;
    const start = () => new Miniflare({ ...convertV4MiniflareOptions({ name: 'ZZ-local', modules: true, script: bundle.outputFiles[0].text,
      compatibilityDate: '2026-10-01',
      durableObjects: { ZZ: { className: 'ZZIntent', useSQLite: true } },
      outboundService: () => { outbound++; throw Error('ZZ external network denied'); } }), resourcePersistencePath: dir, isolatedResourcePersistencePath: dir });
    const send = async body => {
      const r = await mf.dispatchFetch('https://zz.invalid/', {
        method: 'POST', body: JSON.stringify(body) });
      return {status:r.status, value: r.status===200 ? await r.json() : await r.text()};
    };
    try {
      mf = start();
      const results = await Promise.all(Array.from({length:20}, (_, n) =>
        send({action:'consume', binding:{...binding(), connection:'ZZ-'+n,
          plan:n.toString(16).padStart(64,'0')}})));
      assert.equal(results.filter(r=>r.status===200).length,1);
      assert.equal(results.filter(r=>r.status===409).length,19);
      const winner=results.find(r=>r.status===200).value;
      assert.equal(winner.phase,'consumed');
      assert.equal(winner.production_enabled,false);
      const snapshot=(await send({action:'inspect'})).value;
      assert.equal(snapshot.events.length,1);
      assert.deepEqual(snapshot.intent,winner);
      assert.deepEqual(snapshot.events[0],['event:1',winner]);
      await mf.dispose(); mf=start();
      assert.deepEqual((await send({action:'inspect'})).value,snapshot);
      assert.equal((await send({action:'consume',binding:binding()})).status,409);
      const common={action:'advance', binding:winner.binding};
      assert.equal((await send({...common,version:1,event:'uncertain',evidence:H('a')})).status,200);
      // No create/acknowledge replay from uncertainty, even after restart.
      assert.equal((await send({...common,version:2,event:'acknowledge',evidence:H('b'),
        createdId:'profile-999002'})).status,409);
      assert.equal((await send({...common,version:2,event:'reconcile_verified',evidence:H('b'),
        createdId:'profile-999002'})).status,200);
      const done=(await send({action:'inspect'})).value;
      assert.equal(done.intent.phase,'verified');
      assert.equal(done.intent.production_enabled,false);
      assert.equal(done.events.length,3);
      await mf.dispose(); mf=start();
      assert.deepEqual((await send({action:'inspect'})).value,done);
      assert.equal((await send({action:'consume',binding:binding()})).status,409);
      assert.equal(outbound,0);
    } finally {if(mf) await mf.dispose();await rm(dir,{recursive:true,force:true});}
  });
