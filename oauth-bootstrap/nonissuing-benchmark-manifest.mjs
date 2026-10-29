// Dormant local manifest check. Not an installer or evidence authenticator.
const need=x=>{if(!x)throw Error('non-issuing benchmark manifest blocked');};
const exact=(x,keys)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Reflect.ownKeys(x).length===keys.length&&keys.every(k=>Object.hasOwn(x,k)));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
function jsonTree(value,depth=0,budget={n:0}){
 need(depth<=8&&++budget.n<=256);
 if(value===null||typeof value==='string'||typeof value==='boolean'||typeof value==='number'){need(typeof value!=='number'||Number.isFinite(value));return;}
 need(value&&typeof value==='object'&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===Array.prototype));
 const keys=Reflect.ownKeys(value);need(keys.every(k=>typeof k==='string'));
 if(Array.isArray(value))need(keys.length===value.length+1&&keys.includes('length'));
 for(const k of keys){if(Array.isArray(value)&&k==='length')continue;const d=Object.getOwnPropertyDescriptor(value,k);need(d.enumerable&&Object.hasOwn(d,'value'));jsonTree(d.value,depth+1,budget);}
}
export function validateNonissuingBenchmarkManifest(input){try{
 jsonTree(input);
 exact(input,['schema_version','mode','account_id','source','plan','targets','limits','exposure','effects','provider_outputs']);
 // Snapshot before validation; return only independently checked JSON data.
 const p=structuredClone(input);
 need(p.schema_version===1&&p.mode==='synthetic_nonissuing_benchmark');hex(p.account_id,32);
 exact(p.source,['commit_sha','bundle_sha256','modules_sha256','review_sha256','ci_sha256','compatibility_date','compatibility_flags']);
 hex(p.source.commit_sha,40);for(const k of ['bundle_sha256','modules_sha256','review_sha256','ci_sha256'])hex(p.source[k],64);
 need(p.source.compatibility_date==='2026-10-01'&&Array.isArray(p.source.compatibility_flags)&&p.source.compatibility_flags.length===1&&p.source.compatibility_flags[0]==='nodejs_compat');
 exact(p.plan,['workers','durable_objects_backend','evidence_sha256','observed_at','expires_at']);
 need(p.plan.workers==='free'&&p.plan.durable_objects_backend==='sqlite');hex(p.plan.evidence_sha256,64);
 for(const k of ['observed_at','expires_at'])need(Number.isSafeInteger(p.plan[k])&&p.plan[k]>0);
 need(p.plan.expires_at>p.plan.observed_at&&p.plan.expires_at-p.plan.observed_at<=300);
 exact(p.targets,['issuer_script','father_script','owner_class']);
 for(const k of ['issuer_script','father_script'])need(typeof p.targets[k]==='string'&&/^ZZ-benchmark-[a-z0-9-]{1,40}(?![\s\S])/.test(p.targets[k]));
 need(p.targets.issuer_script!==p.targets.father_script&&p.targets.owner_class==='ZZBenchmarkOwner');
 exact(p.limits,['cost_usd','requests','subrequests_per_request','wall_ms','cpu_measurement']);
 need(p.limits.cost_usd===0&&p.limits.requests===1&&p.limits.subrequests_per_request===0&&p.limits.wall_ms===10000&&p.limits.cpu_measurement==='provider_required_not_local_wall');
 exact(p.exposure,['workers_dev','routes','custom_domains','public_ingress']);
 need(p.exposure.workers_dev===false&&p.exposure.public_ingress===false&&Array.isArray(p.exposure.routes)&&p.exposure.routes.length===0&&Array.isArray(p.exposure.custom_domains)&&p.exposure.custom_domains.length===0);
 exact(p.effects,['geni','signing','real_key','existing_namespace','oauth','settings_change','upgrade','deletion']);
 need(Object.values(p.effects).every(x=>x===false));
 exact(p.provider_outputs,['issuer_version','father_version','namespace_id']);need(Object.values(p.provider_outputs).every(x=>x===null));
 return {manifest:p,manifest_shape_checked:true,provider_evidence_verified:false,approval_verified:false,executable:false,production_enabled:false,post_permitted:false};
}catch{throw Error('non-issuing benchmark manifest blocked');}}
