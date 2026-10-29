// A Node test child must not inherit the parent's internal child-v8 context.
import{execFileSync}from'node:child_process';
export function runIsolatedSuite(suite,cwd=new URL('.',import.meta.url)){
 const env={...process.env};delete env.NODE_TEST_CONTEXT;
 return execFileSync(process.execPath,['--test',suite],{cwd,env,timeout:60000,stdio:'pipe'});
}
