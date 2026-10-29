// Synthetic local-only full content/capture fixture. No live sources.
import{createHash}from'node:crypto';import{setup}from'./ZZ-approval-fixture.mjs';import{fixture as capture}from'./ZZ-capture-fixture.mjs';
const hash=(x,a='sha256')=>createHash(a).update(x).digest('hex');
export function joinedSetup(){
 const x=setup(),f=capture(),r=f.r;
 x.f.binding=f.b;x.c.expected_record=r;x.c.plan_fingerprint=f.b.plan;
 x.f.c.binding=f.b;x.f.c.descriptor.operation_binding=f.b.plan;
 const recordBytes=Buffer.from(JSON.stringify(r)),blob=hash(Buffer.concat([Buffer.from('blob '+recordBytes.length+'\0'),recordBytes]),'sha1');
 x.c.source.blob_sha=blob;x.c.source.content_sha256=hash(recordBytes);delete x.c.expected_record;
 const raw=JSON.stringify(x.c);x.env.FATHER_APPROVAL_RELEASE_JSON=raw;x.env.FATHER_APPROVAL_RELEASE_SHA256=hash(raw);
 const evidenceRaw=JSON.stringify(x.f.c);x.env.FATHER_PREWRITE_RELEASE_JSON=evidenceRaw;x.env.FATHER_PREWRITE_RELEASE_SHA256=hash(evidenceRaw);
 Object.assign(x.env,f.env);x.env.FATHER_REVIEWED_WORKFLOW_SHA=r.pins.workflow_sha;
 x.urls[3]=x.urls[3].replace(/[^/]+$/,blob);x.bodies[2].tree[0].sha=blob;x.bodies[3]={sha:blob,encoding:'base64',size:recordBytes.length,content:recordBytes.toString('base64')};
 x.urls.splice(4,0,...f.urls);x.bodies.splice(4,0,...f.bodies);
 return x;
}
