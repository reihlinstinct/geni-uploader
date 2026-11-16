// Dormant plan only. Never calls an API or treats digest pins as authorization.
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');const need=x=>{if(!x)throw Error('benchmark dry-run plan blocked');};
const exact=(x,ks)=>need(x&&Object.getPrototypeOf(x)===Object.prototype&&Reflect.ownKeys(x).length===ks.length&&ks.every(k=>Object.hasOwn(x,k)&&Object.getOwnPropertyDescriptor(x,k).enumerable&&Object.hasOwn(Object.getOwnPropertyDescriptor(x,k),'value')));
const hex=(x,n)=>need(typeof x==='string'&&new RegExp('^[a-f0-9]{'+n+'}(?![\\s\\S])').test(x));
export function planBenchmarkProvisioning(input){try{
 exact(input,['account_id','script','source_sha','bundle_sha256','bundle_bytes','review_sha256','ci_sha256']);
 hex(input.account_id,32);hex(input.source_sha,40);for(const k of ['bundle_sha256','review_sha256','ci_sha256'])hex(input[k],64);
 need(typeof input.script==='string'&&/^ZZ-benchmark-[a-z0-9-]{1,40}(?![\s\S])/.test(input.script));
 need(input.bundle_bytes instanceof Uint8Array&&input.bundle_bytes.length>0&&input.bundle_bytes.length<=65536);
 const bytes=Buffer.from(input.bundle_bytes);need(hash(bytes)===input.bundle_sha256);
 const prefix='/accounts/'+input.account_id+'/workers/scripts/'+input.script;
 const metadata={main_module:'benchmark.mjs',compatibility_date:'2026-10-01',compatibility_flags:['nodejs_compat'],bindings:[],keep_bindings:[],logpush:false,observability:{enabled:false}};
 const metadata_json=JSON.stringify(metadata),subdomain_json=JSON.stringify({enabled:false,previews_enabled:false});
 // Multipart boundary/wire bytes are NOT fixed here. Do not mislabel this hash.
 const upload_descriptor={metadata_sha256:hash(metadata_json),module_name:'benchmark.mjs',module_content_type:'application/javascript+module',module_sha256:hash(bytes),module_byte_length:bytes.length};
 return{schema_version:1,mode:'blocked_dry_run_microbenchmark_provisioning_plan',account_id:input.account_id,script:input.script,source_sha:input.source_sha,bundle_sha256:input.bundle_sha256,review_sha256:input.review_sha256,ci_sha256:input.ci_sha256,metadata_json,upload_descriptor,
 proposed_writes:[{method:'PUT',path:prefix,body_kind:'multipart_descriptor_not_wire_body',descriptor_sha256:hash(JSON.stringify(upload_descriptor))},{method:'POST',path:prefix+'/subdomain',body_kind:'application/json',body_json:subdomain_json,body_sha256:hash(subdomain_json)}],
 candidate_write_count:2,existing_target_update_permitted:false,migrations:[],secret_writes:0,namespace_writes:0,account_setting_writes:0,delete_permitted:false,cost_ceiling_usd:0,
 required_before_write:['authenticated_target_absence_not_403','authenticated_free_product_and_capacity','exact_head_review_and_ci','closed_upload_wire_bytes','initial_no_public_exposure_guarantee','bootstrap_custody_and_revocation','private_evidence_and_readback'],
 required_after_write:['independent_full_bundle_config_active_version_readback','subdomain_and_preview_disabled_routes_and_domains_absent','supported_internal_invocation_no_public_dispatcher','exact_invocation_cpu_and_version_evidence','private_receipt_durability_and_stop_procedure'],
 blocking:['no_live_installer','no_authenticated_entitlement_capacity','no_initial_exposure_guarantee','no_internal_invoker','no_exact_cpu_readback','no_verified_private_evidence_route','no_owner_approval'],
 executable:false,approval_verified:false,provider_evidence_verified:false,provider_cpu_verified:false,production_enabled:false,post_permitted:false};
}catch{throw Error('benchmark dry-run plan blocked');}}
