// Offline fixed build. Never imports wrangler, deploys or writes an account.
import{build,version}from'esbuild';
import{readFile,lstat}from'node:fs/promises';
import{execFileSync}from'node:child_process';
import{createHash}from'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const need=x=>{if(!x)throw Error('closed father build blocked');};
export async function buildClosedFatherWorker(){
 const root=new URL('..',import.meta.url).pathname,dir=new URL('.',import.meta.url).pathname;
 const git=(args)=>execFileSync('git',args,{cwd:root,encoding:'utf8',stdio:['ignore','pipe','pipe']});
 const source=git(['rev-parse','HEAD']).trim();need(/^[a-f0-9]{40}$/.test(source));
 const packageBytes=await readFile(new URL('./package.json',import.meta.url)),lockBytes=await readFile(new URL('./package-lock.json',import.meta.url)),p=JSON.parse(packageBytes),lock=JSON.parse(lockBytes);
 need(version==='0.28.2'&&p.devDependencies.esbuild===version&&lock.lockfileVersion===3&&lock.packages['node_modules/esbuild'].version===version&&p.dependencies.jose==='6.1.0'&&lock.packages['node_modules/jose'].version==='6.1.0');
 const gate=await readFile(new URL('./father-release-gate.mjs',import.meta.url),'utf8');
 need(gate===`// A code merge or an environment flag cannot release a vendor write.\nexport function requireFatherRelease(){throw Error('father live executor unreleased');}\n`);
 // No caller options, plugins, injected aliases, defines or source replacement.
 const result=await build({absWorkingDir:dir,entryPoints:['father-intent-service.mjs'],bundle:true,format:'esm',platform:'browser',target:'es2022',conditions:['workerd','browser'],external:['node:crypto'],write:false,metafile:true,legalComments:'none',charset:'utf8',logLevel:'silent'});
 const inputs=Object.keys(result.metafile.inputs).sort(),inventory={};
 for(const input of inputs){
  need(!input.startsWith('/')&&!input.split('/').includes('..')&&!/ZZ-|\.test\.|wrangler|build-closed|private-release-issuer|no-write-workload-probe|protected-job-entrypoint/.test(input));
  const path=new URL(input,new URL('.',import.meta.url));
  const st=await lstat(path);need(st.isFile()&&!st.isSymbolicLink()&&st.size<=2097152);
  inventory[input]=hash(await readFile(path));
  for(const edge of result.metafile.inputs[input].imports)if(edge.external)need(edge.path==='node:crypto');
 }
 const tracked=['oauth-bootstrap/package.json','oauth-bootstrap/package-lock.json',...inputs.filter(x=>!x.startsWith('node_modules/')).map(x=>'oauth-bootstrap/'+x)];
 git(['diff','--exit-code',source,'--',...tracked]);
 const actual=git(['ls-files','-z','--',...tracked]).split('\0').filter(Boolean);need(actual.length===tracked.length);
 need(inputs.includes('father-release-gate.mjs')&&inputs.includes('durable-father-executor.mjs')&&inputs.includes('father-intent-service.mjs'));
 need(result.outputFiles.length===1);const bytes=Buffer.from(result.outputFiles[0].contents);need(bytes.length>0&&bytes.length<=2097152&&bytes.includes(Buffer.from('father live executor unreleased'))&&!bytes.includes(Buffer.from('ZZ-test-only-release')));
 return{bytes,inventory:{schema_version:1,mode:'offline_closed_father_bundle',source_sha:source,esbuild_version:version,compatibility_date:'2026-10-01',compatibility_flags:['nodejs_compat'],package_sha256:hash(packageBytes),lockfile_sha256:hash(lockBytes),inputs:inventory,bundle_sha256:hash(bytes),production_enabled:false,post_permitted:false}};
}
