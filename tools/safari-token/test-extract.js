const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(__dirname+'/extract-token.js','utf8');
const token='ZZsyntheticToken1234567890';
const base='https://www.geni.com/platform/oauth/auth_success';
let count=0;
function test(url,expected,clearThrows=false){
 let result,cleared,calls=0; const order=[];
 const context={URL,Map,Set,decodeURIComponent,window:{location:{href:url},history:{replaceState(a,b,path){order.push('clear');if(clearThrows)throw Error('ZZunexpected secret in exception');cleared=path;}}},completion(v){calls++;order.push('complete');result=v;}};
 if(expected){vm.runInNewContext(code,context);assert.equal(result,expected);assert.equal(cleared,'/platform/oauth/auth_success');assert.equal(calls,1);assert.deepEqual(order,['clear','complete']);}
 else {let error;try{vm.runInNewContext(code,context);}catch(e){error=e;}assert(error);assert(error.message.startsWith('Stop: '));assert(!error.message.includes('ZZunexpected'));assert.equal(result,undefined);assert.equal(calls,0);assert.equal(cleared,undefined);}
 count++;
}
test(base+'#access_token='+token,token);
test(base+'#access_token='+token+'&expires_in=86400&token_type=bearer&scope=read_profile&state=ZZstate',token);
test(base+'#access_token='+token+'%2B',token+'+');
test(base+'#access_token='+'Z'.repeat(20),'Z'.repeat(20));
test(base+'#access_token='+'Z'.repeat(4096),'Z'.repeat(4096));
for(const url of [base,base+'?access_token='+token,base+'?#access_token='+token,base+'?x=1#access_token='+token,base+'#?access_token='+token,base+'#access_token='+token+'&',base+'#access_token='+token+'&&state=ZZ',base+'#access_token='+token+'&state',base+'#access_token='+token+'&=ZZ',base+'#access_token='+token+'&state=%ZZ',base+'#access_token='+token+'&state=%E0%A4%A',base+'#access_token='+token+'&%61ccess_token='+token,base+'#access_token='+token+'+',base+'#access_token='+token+'=',base+'#access_token='+token+'%3D',base+'#access_token='+'Z'.repeat(19),base+'#access_token='+'Z'.repeat(4097),base+'#access_token=',base+'#access_token=%0A'+token,base+'#access_token=%3Cscript%3E'+token,base+'#access_token='+token+'&error=ZZerror',base+'#access_token='+token+'&expires_in=1&expires_in=2',base+'#access_token='+token+'#ZZsuffix',base+'#access_token='+token+'%09',base+'#code=ZZcode','http://www.geni.com/platform/oauth/auth_success#access_token='+token,'https://www.geni.com.evil.invalid/platform/oauth/auth_success#access_token='+token,'https://www.geni.com:444/platform/oauth/auth_success#access_token='+token,'https://ZZuser@www.geni.com/platform/oauth/auth_success#access_token='+token,'https://www.geni.com/platform/oauth/other#access_token='+token])test(url,false);
test(base+'#access_token='+token,false,true);
// Source-level smoke check only, not proof of all possible program behavior.
for(const bad of ['fetch(', 'XMLHttpRequest', 'sendBeacon','localStorage','sessionStorage','document.','console.','alert(', 'navigator.'])assert(!code.includes(bad),bad);
console.log(count+' synthetic cases PASS; forbidden-primitives smoke check PASS');
