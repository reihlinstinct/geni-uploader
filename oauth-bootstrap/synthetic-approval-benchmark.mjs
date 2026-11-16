// Synthetic microbenchmark only. No runtime bindings or source authentication.
import{WorkerEntrypoint}from'cloudflare:workers';
import fixture from'./worker-approval-synthetic.json';
import{checkWorkerApprovalContent}from'./worker-single-human-approval.mjs';
const raw=JSON.stringify(fixture);
export class ZZApprovalBenchmark extends WorkerEntrypoint{
 async run(){
  if(arguments.length!==0)throw Error('synthetic benchmark blocked');
  const r=await checkWorkerApprovalContent(raw,raw,fixture.pins.issued_at);
  if(r.content_consistent!==true||r.post_permitted!==false||r.owner_approval_verified!==false)throw Error('synthetic benchmark blocked');
  return{schema_version:1,phase:'synthetic_content_microbenchmark_only',record_hash:r.record_hash,provider_cpu_verified:false,owner_approval_verified:false,geni_calls:0,production_enabled:false,post_permitted:false};
 }
}
export default{fetch(){return new Response('Blocked',{status:403});}};
