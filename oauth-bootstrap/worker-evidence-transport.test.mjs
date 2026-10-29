import test from'node:test';import assert from'node:assert/strict';import{build}from'esbuild';import{Miniflare,convertV4MiniflareOptions}from'miniflare';
test('workerd evidence budgets, streams, cancellation and hostile responses',{timeout:45000},async()=>{
 const entry=`import{createWorkerEvidenceTransport as make}from'./worker-evidence-transport.mjs';export default{async fetch(){
 const out=[],route='/repos/ZZ/ZZ/actions/runs/999001',key='ZZ_token';let calls=0;
 const fixed=e=>{if(e.message!=='worker evidence read blocked'||e.cause!==undefined)throw Error('ZZ-error-leak');};
 async function blocked(name,fn){try{await fn();throw Error('ZZ-unexpected-pass:'+name);}catch(e){fixed(e);out.push(name);}}
 const good=async(url,options)=>{calls++;if(url!=='https://api.github.com'+route||options.method!=='GET'||options.redirect!=='manual'||options.headers.Authorization!=='Bearer '+key)throw Error('ZZ-request');return Response.json({ok:true});};
 let t=make({routes:[route],credential:key},good);for(let i=0;i<16;i++)await t.get(route);await blocked('request-cap',()=>t.get(route));if(calls!==16)throw Error('ZZ-budget');
 t=make({routes:[route],credential:key},good);await blocked('unlisted',()=>t.get(route+'?ZZ=1'));await blocked('closed-after-failure',()=>t.get(route));
 for(const [name,response] of [
 ['redirect',()=>new Response('',{status:302,headers:{location:'https://zz.invalid'}})],
 ['pagination',()=>new Response('{}',{headers:{link:'<https://zz.invalid>; rel=next'}})],
 ['declared-large',()=>new Response('{}',{headers:{'content-length':'262145'}})],
 ['chunked-large',()=>new Response(new Uint8Array(262145))],
 ['duplicate',()=>new Response('{"ZZ":1,"\\\\u005aZ":2}')],
 ['nested',()=>new Response('['.repeat(17)+'0'+']'.repeat(17))],
 ['utf8',()=>new Response(new Uint8Array([255]))],
 ['malformed',()=>new Response('{')],
 ['fetch-error',()=>{throw Error('ZZ-sensitive-token-provider');}],
 ]){t=make({routes:[route],credential:key},async()=>response());await blocked(name,()=>t.get(route));}
 const big=JSON.stringify({ZZ:'a'.repeat(230000)});t=make({routes:[route],credential:key},async()=>new Response(big));for(let i=0;i<4;i++)await t.get(route);await blocked('aggregate',()=>t.get(route));
 t=make({routes:[route],credential:key},async()=>new Response(big));const concurrent=await Promise.allSettled(Array.from({length:6},()=>t.get(route)));if(concurrent.every(x=>x.status==='fulfilled'))throw Error('ZZ-concurrent-cap');t.close();out.push('concurrent');
 let cancelled=false;t=make({routes:[route],credential:key},async()=>new Response(new ReadableStream({cancel(){cancelled=true;}})));const pending=t.get(route);await new Promise(r=>setTimeout(r,5));t.close();await blocked('close-stalled',()=>pending);if(!cancelled)throw Error('ZZ-not-cancelled');
 t=make({routes:[route],credential:key},()=>new Promise(()=>{}));const start=Date.now();await blocked('deadline-fetch',()=>t.get(route));if(Date.now()-start<9000||Date.now()-start>12000)throw Error('ZZ-deadline');
 t=make({routes:[route],credential:key},async()=>new Response(new ReadableStream()));await blocked('deadline-stream',()=>t.get(route));
 t=make({routes:[route],credential:key},good);t.close();await blocked('explicit-close',()=>t.get(route));
 t=make({routes:[route],credential:key},good);const requests=await Promise.allSettled(Array.from({length:17},()=>t.get(route)));if(calls>32||requests.every(x=>x.status==='fulfilled'))throw Error('ZZ-concurrent-request-cap');out.push('concurrent-request-cap');
 const dotRoute='/repos/ZZ/ZZ.tool/actions/runs/999001';t=make({routes:[dotRoute],credential:key},async()=>Response.json({ok:true}));await t.get(dotRoute);t.close();out.push('safe-dot');
 for(const bad of ['/repos/ZZ/.ZZ/actions','/repos/ZZ/./actions','/repos/ZZ/../actions','//zz.invalid','/repos/ZZ/ZZ/../ZZ','/repos/ZZ/ZZ/actions#ZZ','/repos/ZZ/ZZ/actions\\n'])await blocked('bad-route',()=>make({routes:[bad],credential:key},good));
 return Response.json(out);}}`;
 const bundle=await build({stdin:{contents:entry,resolveDir:new URL('.',import.meta.url).pathname,sourcefile:'ZZ-transport.mjs'},bundle:true,platform:'browser',format:'esm',write:false,metafile:true});assert.deepEqual(Object.keys(bundle.metafile.inputs).sort(),['ZZ-transport.mjs','worker-evidence-transport.mjs']);
 const mf=new Miniflare(convertV4MiniflareOptions({name:'ZZ-evidence-transport',modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-10-01'}));try{const r=await mf.dispatchFetch('https://zz.invalid');assert.equal(r.status,200,await r.clone().text());const results=await r.json();assert.ok(results.includes('deadline-fetch'));assert.ok(results.includes('duplicate'));}finally{await mf.dispose();}
});
