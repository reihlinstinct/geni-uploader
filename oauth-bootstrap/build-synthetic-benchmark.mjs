// Local offline build only. No wrangler, upload, execution or provider access.
import{build,version}from'esbuild';import{readFile,lstat}from'node:fs/promises';import{execFileSync}from'node:child_process';import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');const need=x=>{if(!x)throw Error('synthetic benchmark build blocked');};
const inputs=['synthetic-approval-benchmark.mjs','worker-approval-synthetic.json','worker-single-human-approval.mjs'];
export async function buildSyntheticBenchmark(){try{
 const root=new URL('..',import.meta.url).pathname,dir=new URL('.',import.meta.url).pathname;
 const git=args=>execFileSync('git',args,{cwd:root,encoding:'utf8',stdio:['ignore','pipe','pipe']});
 const source=git(['rev-parse','HEAD']).trim();need(/^[a-f0-9]{40}$/.test(source));
 const packageBytes=await readFile(new URL('./package.json',import.meta.url)),lockBytes=await readFile(new URL('./package-lock.json',import.meta.url)),p=JSON.parse(packageBytes),lock=JSON.parse(lockBytes);
 need(version==='0.28.2'&&p.devDependencies.esbuild===version&&lock.lockfileVersion===3&&lock.packages['node_modules/esbuild'].version===version);
 const expected=[...inputs].sort(),inventory={};
 const tracked=['build-synthetic-benchmark.mjs','package.json','package-lock.json',...expected].map(x=>'oauth-bootstrap/'+x);
 git(['diff','--exit-code',source,'--',...tracked]);need(git(['ls-files','-z','--',...tracked]).split('\0').filter(Boolean).length===tracked.length);
 for(const input of expected){const path=new URL(input,import.meta.url),st=await lstat(path);need(st.isFile()&&!st.isSymbolicLink()&&st.size<=65536);inventory[input]=hash(await readFile(path));}
 const f=JSON.parse(await readFile(new URL('./worker-approval-synthetic.json',import.meta.url)));need(f.pins.owner==='profile-999001'&&f.pins.connection_id==='ZZ-secondary'&&f.production_enabled===false);
 const result=await build({absWorkingDir:dir,entryPoints:['synthetic-approval-benchmark.mjs'],bundle:true,format:'esm',platform:'browser',target:'es2022',conditions:['workerd','browser'],external:['cloudflare:workers'],write:false,metafile:true,legalComments:'none',charset:'utf8',logLevel:'silent'});
 need(JSON.stringify(Object.keys(result.metafile.inputs).sort())===JSON.stringify(expected));
 for(const v of Object.values(result.metafile.inputs))for(const e of v.imports)if(e.external)need(e.path==='cloudflare:workers');
 need(result.outputFiles.length===1);const bytes=Buffer.from(result.outputFiles[0].contents);need(bytes.length>0&&bytes.length<=65536);
 return{bytes,inventory:{schema_version:1,mode:'offline_synthetic_content_microbenchmark',source_sha:source,esbuild_version:version,builder_sha256:hash(await readFile(new URL('./build-synthetic-benchmark.mjs',import.meta.url))),package_sha256:hash(packageBytes),lockfile_sha256:hash(lockBytes),inputs:inventory,bundle_sha256:hash(bytes),compatibility_date:'2026-10-01',compatibility_flags:['nodejs_compat'],internal_entrypoint:'ZZApprovalBenchmark',public_fetch:'deny_all',runtime_bindings:[],provider_cpu_verified:false,executable:false,production_enabled:false,post_permitted:false}};
}catch{throw Error('synthetic benchmark build blocked');}}
