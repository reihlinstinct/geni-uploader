// A Node test child must not inherit the parent's internal child-v8 context.
import{execFileSync}from'node:child_process';
const text=b=>b==null?'':Buffer.isBuffer(b)?b.toString('utf8'):String(b);
export function runIsolatedSuite(suite,cwd=new URL('.',import.meta.url)){
 const env={...process.env};delete env.NODE_TEST_CONTEXT;
 try{return execFileSync(process.execPath,['--test',suite],{cwd,env,timeout:60000,stdio:'pipe'});}
 catch(e){
  // Failure only: carry the child's captured output so CI shows the failing assertion (#323).
  const failure=new Error(`Isolated suite failed: ${suite} (status ${e.status??'none'}, signal ${e.signal??'none'})\n--- child stdout ---\n${text(e.stdout)}\n--- child stderr ---\n${text(e.stderr)}`,{cause:e});
  for(const k of['status','signal','code','stdout','stderr'])failure[k]=e[k];
  throw failure;
 }
}
