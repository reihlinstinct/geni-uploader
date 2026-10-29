// Synthetic fixed GET preflight only. No live profile or credential.
import{createHash}from'node:crypto';
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(x).digest('hex');
export function ownerFixture(binding){
 const self={id:binding.owner,first_name:'ZZChild',public:false,is_alive:true},profile={...self},family={focus:{...self},nodes:{[binding.owner]:{...self}}};
 const graph_hash=hash(canonical({self,profile,family})),c={mode:'unreleased_secondary_owner_preflight',production_enabled:false,owner:binding.owner,connection:binding.connection,plan:binding.plan,graph_hash,allow_unknown_merge:true,unknown_parent_risk_accepted:true},raw=JSON.stringify(c);
 const fields='id,first_name,middle_name,last_name,maiden_name,names,gender,public,is_alive,merge_pending,merged_into,unions';return{graph_hash,env:{GENI_SECONDARY_ACCESS_TOKEN:'ZZtoken123',FATHER_PREFLIGHT_RELEASE_JSON:raw,FATHER_PREFLIGHT_RELEASE_SHA256:hash(raw)},urls:['https://www.geni.com/api/profile?only_ids=true&fields='+fields,'https://www.geni.com/api/'+binding.owner+'?only_ids=true&fields='+fields,'https://www.geni.com/api/'+binding.owner+'/immediate-family?only_ids=true'],bodies:[self,profile,family]};
}
