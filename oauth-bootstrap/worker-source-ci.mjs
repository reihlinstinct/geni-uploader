// Dormant GitHub evidence correlation. Not independent review or a release grant.
import{createWorkerEvidenceTransport}from'./worker-evidence-transport.mjs';
const need=x=>{if(!x)throw Error('worker source CI blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Object.keys(x).sort().join(',')===[...ks].sort().join(','));
const hash=async x=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(x))),b=>b.toString(16).padStart(2,'0')).join('');
const id=x=>need(typeof x==='string'&&/^[1-9][0-9]{0,19}(?![\s\S])/.test(x));
export async function inspectWorkerSourceCI(env,fetcher=fetch){let transport;try{
 const raw=env.FATHER_SOURCE_CI_JSON;need(typeof raw==='string'&&raw.length<=16384&&await hash(raw)===env.FATHER_SOURCE_CI_SHA256);
 const c=JSON.parse(raw);need(JSON.stringify(c)===raw);exact(c,['mode','production_enabled','owner','repo','source_sha','checks']);
 need(c.mode==='unreleased_exact_source_ci'&&c.production_enabled===false);
 for(const k of ['owner','repo'])need(typeof c[k]==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,99}(?![\s\S])/.test(c[k]));
 need(typeof c.source_sha==='string'&&/^[a-f0-9]{40}(?![\s\S])/.test(c.source_sha));
 need(Array.isArray(c.checks)&&c.checks.length>0&&c.checks.length<=16);const names=new Set();
 for(const check of c.checks){exact(check,['name','app_id']);need(typeof check.name==='string'&&/^[A-Za-z0-9 ()_.-]{1,100}(?![\s\S])/.test(check.name)&&!names.has(check.name));names.add(check.name);id(check.app_id);}
 const root='/repos/'+c.owner+'/'+c.repo,commit=root+'/commits/'+c.source_sha,checks=commit+'/check-runs?filter=all&per_page=100';
 transport=createWorkerEvidenceTransport({routes:[commit,checks],credential:env.PRIVATE_GIT_CREDENTIAL},fetcher);
 const source=await transport.get(commit);need(source.sha===c.source_sha&&source.commit?.verification?.verified===true&&source.commit.verification.reason==='valid');
 const result=await transport.get(checks);need(Number.isSafeInteger(result.total_count)&&result.total_count===c.checks.length&&Array.isArray(result.check_runs)&&result.check_runs.length===c.checks.length);
 const seen=new Set();for(const check of result.check_runs){need(typeof check.name==='string'&&!seen.has(check.name));seen.add(check.name);const pin=c.checks.find(x=>x.name===check.name);need(pin&&check.head_sha===c.source_sha&&check.status==='completed'&&check.conclusion==='success'&&Number.isSafeInteger(check.app?.id)&&check.app.id>0&&String(check.app.id)===pin.app_id);}
 need(seen.size===names.size&&[...names].every(x=>seen.has(x)));
 return Object.freeze({phase:'exact_source_ci_github_correlated',source_sha:c.source_sha,github_signature_verified:true,exact_checks_correlated:true,pinned_signing_key_verified:false,independent_review_verified:false,merge_path_verified:false,installed_bundle_verified:false,post_permitted:false,production_enabled:false});
}catch{throw Error('worker source CI blocked');}finally{transport?.close();}}
