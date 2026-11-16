import test from'node:test';
import assert from'node:assert/strict';
import{mkdtempSync,writeFileSync,rmSync}from'node:fs';
import{tmpdir}from'node:os';
import{join}from'node:path';
import{execFileSync}from'node:child_process';
import{runIsolatedSuite}from'./isolated-test-runner.mjs';

test('deliberately failing isolated suite fails parent test process despite inherited child-v8',()=>{
 const dir=mkdtempSync(join(tmpdir(),'ZZ-isolated-regression-'));
 try{
  const bad=join(dir,'ZZ-bad.test.mjs'),parent=join(dir,'ZZ-parent.test.mjs');
  writeFileSync(bad,"import test from 'node:test';import assert from 'node:assert/strict';test('ZZ-must-fail',()=>assert.equal(1,2));");
  writeFileSync(parent,"import test from 'node:test';import{runIsolatedSuite}from "+JSON.stringify(new URL('./isolated-test-runner.mjs',import.meta.url).href)+";test('ZZ-parent',()=>runIsolatedSuite("+JSON.stringify(bad)+"));");
  const env={...process.env};delete env.NODE_TEST_CONTEXT;
  assert.throws(()=>execFileSync(process.execPath,['--test',parent],{env,stdio:'pipe',timeout:10000}),e=>{assert.equal(e.status,1);assert.match(e.stdout.toString(),/ZZ-parent/);return true;});
  // Exercise the helper under an explicitly inherited test-runner context too.
  const old=process.env.NODE_TEST_CONTEXT;process.env.NODE_TEST_CONTEXT='child-v8';
  try{assert.throws(()=>runIsolatedSuite(bad),e=>{assert.equal(e.status,1);assert.match(e.stdout.toString(),/ZZ-must-fail/);return true;});}
  finally{if(old===undefined)delete process.env.NODE_TEST_CONTEXT;else process.env.NODE_TEST_CONTEXT=old;}
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('isolated suite failure carries child stdout and stderr in the thrown message',()=>{
 const dir=mkdtempSync(join(tmpdir(),'ZZ-isolated-diagnostics-'));
 try{
  const bad=join(dir,'ZZ-diag.test.mjs'),parent=join(dir,'ZZ-diag-parent.test.mjs');
  writeFileSync(bad,"import test from 'node:test';import assert from 'node:assert/strict';test('ZZ-diag-case',()=>{console.error('ZZ-stderr-marker');assert.equal(1,2,'ZZ-assertion-marker');});");
  assert.throws(()=>runIsolatedSuite(bad),e=>{
   assert.equal(e.status,1);
   assert.match(e.message,/ZZ-diag-case/);
   assert.match(e.message,/ZZ-assertion-marker/);
   assert.match(e.message,/ZZ-stderr-marker/);
   assert.match(e.stdout.toString(),/ZZ-assertion-marker/);
   return true;
  });
  // What CI sees: the parent runner's own report includes the child's failing assertion.
  writeFileSync(parent,"import test from 'node:test';import{runIsolatedSuite}from "+JSON.stringify(new URL('./isolated-test-runner.mjs',import.meta.url).href)+";test('ZZ-diag-parent',()=>runIsolatedSuite("+JSON.stringify(bad)+"));");
  const env={...process.env};delete env.NODE_TEST_CONTEXT;
  assert.throws(()=>execFileSync(process.execPath,['--test',parent],{env,stdio:'pipe',timeout:20000}),e=>{assert.equal(e.status,1);assert.match(e.stdout.toString(),/ZZ-assertion-marker/);return true;});
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('passing isolated suite still returns the child stdout unchanged',()=>{
 const dir=mkdtempSync(join(tmpdir(),'ZZ-isolated-pass-'));
 try{
  const good=join(dir,'ZZ-good.test.mjs');
  writeFileSync(good,"import test from 'node:test';test('ZZ-pass-case',()=>{});");
  const out=runIsolatedSuite(good);
  assert.ok(Buffer.isBuffer(out));
  assert.match(out.toString(),/ZZ-pass-case/);
  assert.doesNotMatch(out.toString(),/child stdout|Isolated suite failed/);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
