// Child of the test-only Rust supervisor module. No Core port, capability,
// Native session or arbitrary fixture setup operation is received by this code.
import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";

const fixture=process.argv[2];
const {createCoreApiClient,CoreApiClientError}=await import(pathToFileURL(path.join(fixture,"client/client.mjs")).href);
const reportPath=path.join(fixture,"client-report.json");
const report={documentType:"populated-native-search-client",status:"RUNNING",calls:[],denials:[],boundaries:[],identities:{},
  limits:["Fixed wholly synthetic metadata source; no scientific gold or full-text/Reader proof.",
    "Test-private actual corpus/rights setup is separate from public renderer admission.",
    "Source Core and Native fixture session; no installed packaging, sign-in or file picker proof.",
    "One item is not scale, throughput or resource qualification."]};
await writeFile(reportPath,JSON.stringify(report,null,2)+"\n",{flag:"wx"});
const lines=createInterface({input:process.stdin});
const waiting=[];let closed=false;
lines.on("line",line=>{const next=waiting.shift();if(!next)throw Error("Unsolicited supervisor reply");next.resolve(JSON.parse(line));});
lines.on("close",()=>{closed=true;while(waiting.length)waiting.shift().reject(Error("Supervisor IPC closed"));});
const exchange=async value=>{
  if(closed)throw Error("Supervisor IPC closed");
  let timer;
  const response=new Promise((resolve,reject)=>{
    waiting.push({resolve,reject});
    timer=setTimeout(()=>reject(Error("Fixed child IPC deadline exceeded")),30000);
    process.stdout.write(JSON.stringify(value)+"\n",error=>{if(error)reject(error);});
  });
  try{return await response;}finally{clearTimeout(timer);}
};
const control=async name=>{
  const reply=await exchange({control:name});
  assert.equal(reply.kind,"fixture",reply.code??"Fixed fixture operation failed");return reply.value;
};
const transport=async request=>{
  const start=performance.now(),reply=await exchange(request);
  report.calls.push({path:request.path,elapsedMs:performance.now()-start,kind:reply.kind,status:reply.response?.status??null,
    nativeCode:reply.kind==="error"?reply.code:null});
  if(reply.kind!=="response")throw Error(reply.code??"Native denied");return reply.response;
};
const client=createCoreApiClient(transport);
const id=n=>`01900000-0000-7000-8000-${String(n).padStart(12,"0")}`;
const waitFor=async (read,terminal,limit=60000)=>{
  const deadline=performance.now()+limit;let value;
  do {
    value=await read();
    assert.ok(performance.now()<deadline,"Original bounded operation deadline exceeded");
    if(terminal(value))return value;
    await new Promise(resolve=>setTimeout(resolve,100));
  } while(true);
};
const awaitSearch=address=>waitFor(()=>client.inspectLexicalSearch(address),value=>["succeeded","failed","cancelled"].includes(value.state));
const expectSearchDenied=async (label,read)=>{
  await assert.rejects(read,error=>{
    assert.ok(error instanceof CoreApiClientError,"Transport/IPC/decoder failure cannot prove denial");
    assert.equal(error.problem.status,409);assert.equal(error.problem.code,"RO-CORE-SEARCH-DENIED");
    report.denials.push({label,status:error.problem.status,code:error.problem.code,traceId:error.problem.traceId});return true;
  });
};
let failure;
try {
  const project=await client.createProject({parentDirectory:path.join(fixture,"projects"),directoryName:"search",
    displayName:"Synthetic populated search Native proof",primaryUseCase:"theory-synthesis",
    researchObjective:"Synthetic local populated lexical API boundary proof."});
  const root=project.root,projectId=project.projectId;
  report.identities.projectId=projectId;
  await client.openProject({root});
  const impact={root,expectedRevision:1,primaryUseCase:"systematic-review",sourceKinds:["peer-reviewed-article","conference-paper"],
    evidenceTypes:["empirical-study","theoretical-work"],languageCodes:["en"],startYear:2015,endYear:2026,includePrivateReports:false,
    noveltyStandard:"theoretical",autonomyLevel:"suggest",stoppingConditions:["coverage-threshold"]};
  const preview=await client.previewIntent(impact);
  const draft=await client.saveIntentDraft({...impact,researchObjective:"Synthetic local populated lexical API boundary proof.",
    contributionIntent:"Verify bounded local lookup against one declared synthetic source.",phenomenon:"Synthetic lookup",
    unitOfAnalysis:"Synthetic record",levelOfAnalysis:"Technical fixture",noveltyRationale:"No scholarly novelty claim.",
    revisionRationale:"Isolated populated Native proof.",impactAcknowledgement:preview.acknowledgementToken},"0123456789abcdef0123456789abcdef");
  await client.acceptIntent({root,expectedRevision:draft.revision,expectedRevisionContentHash:draft.revisionContentHash,confirmed:true,
    decisionRationale:"Synthetic fixture confirmation only."},"abcdef0123456789abcdef0123456789");
  report.boundaries.push("actual Native principal and accepted protected Intent");
  const seed=await control("seed-import");
  report.identities.sourceSha256=seed.sourceSha256;
  const previewId=seed.previewId;
  const parsed=await waitFor(()=>client.importPreviewStatus({root,previewId}),value=>["parse-completed","failed","cancelled","security-interrupted"].includes(value.state));
  assert.equal(parsed.state,"parse-completed");
  const review=await client.beginImportReview({root,previewId});
  const prepared=await client.prepareImportCommit({root,previewId,revision:review.revision,previousManifestRevisionId:null});
  await client.startImportCommit({root,previewId,revision:review.revision,requestId:prepared.requestId,previousManifestRevisionId:null});
  const committed=await waitFor(()=>client.importCommitStatus({root,previewId,requestId:prepared.requestId}),value=>["succeeded","failed","cancelled"].includes(value.jobState));
  assert.equal(committed.jobState,"succeeded");
  const manifest=await client.importManifest({root,previewId,revisionId:null});assert.ok(manifest);
  const members=await client.importManifestMembers({root,previewId,revisionId:manifest.revisionId,after:0,limit:10});
  const member=members.records.find(value=>value.included&&value.sourceRecordRevisionId!==null);assert.ok(member);
  const source={kind:"import-member",contextId:previewId,revisionId:manifest.revisionId,ordinal:member.ordinal,recordKey:member.recordKey};
  const work=await client.reconcileScholarlySource({root,commandId:id(100),source});
  assert.ok(work.workId&&work.workRevisionId&&work.assertionRevisionId);
  const seeded=await control("create-corpus"),item=seeded.item;
  assert.equal(item.workId,work.workId);
  assert.ok(seeded.rights.policy.revisionId);
  report.identities={...report.identities,previewId,manifestRevisionId:manifest.revisionId,
    assertionRevisionId:work.assertionRevisionId,workId:work.workId,workRevisionId:work.workRevisionId,
    itemId:item.itemId,initialRightsRevisionId:seeded.rights.policy.revisionId};
  report.boundaries.push("actual Native import and generated public review/commit/manifest/reconciliation",
    "fixed private corpus and six-permission rights setup through actual Core operations");
  const query="title:synthetic AND identifiers:native-lexical-fixture";
  assert.equal((await client.validateLexicalQuery({query})).valid,true);
  const request={root,projectId,commandId:id(101),query,filters:{yearFrom:2024,yearTo:2024}};
  const job=await client.executeLexicalSearch(request),replay=await client.executeLexicalSearch(request);
  assert.equal(job.jobId,replay.jobId);assert.equal(job.workflowRunId,replay.workflowRunId);
  const address={root,projectId,jobId:job.jobId};
  assert.equal((await awaitSearch(address)).state,"succeeded");
  const pageRequest={...address,after:null,limit:50};
  const page=await client.pageLexicalSearch(pageRequest),again=await client.pageLexicalSearch(pageRequest);
  assert.equal(page.execution.resultCount,1);assert.equal(page.startPosition,0);assert.equal(page.afterCursor,null);assert.equal(page.nextCursor,null);
  assert.equal(page.execution.semanticState,"unqualified");assert.equal(page.execution.rerankState,"not-run");
  assert.deepEqual(page.hits,again.hits);assert.equal(page.execution.resultSha256,again.execution.resultSha256);
  const hit=page.hits[0];assert.equal(hit.position,1);assert.equal(hit.itemId,item.itemId);
  assert.equal(hit.workId,work.workId);assert.equal(hit.workRevisionId,work.workRevisionId);
  assert.equal(hit.title,"Synthetic observatory lookup");assert.equal(hit.year,2024);assert.equal(hit.source,null);
  assert.ok(hit.snippet);assert.ok(hit.snippet.highlights.length>0);
  const explanation=await client.explainLexicalSearch({...address,itemId:item.itemId});
  assert.equal(explanation.score,hit.score);
  assert.ok(explanation.components.some(value=>value.field==="title"));
  assert.ok(explanation.components.some(value=>value.field==="identifiers"));
  report.identities.searchRunId=page.execution.searchRunId;report.identities.searchRunRevisionId=page.execution.revisionId;
  report.boundaries.push("populated protected field/filter/ranking/snippet/explanation with canonical IDs and stable replay");
  const excluded=await client.executeLexicalSearch({...request,commandId:id(102),filters:{yearFrom:2000,yearTo:2000}});
  const excludedAddress={root,projectId,jobId:excluded.jobId};assert.equal((await awaitSearch(excludedAddress)).state,"succeeded");
  assert.equal((await client.pageLexicalSearch({...excludedAddress,after:null,limit:50})).execution.resultCount,0);
  for(const body of [{...request,actorId:id(103)},{...request,sessionId:"f".repeat(32)}]) {
    const reply=await exchange({method:"POST",path:"/projects/search/run",body:JSON.stringify(body),ifMatch:null,idempotencyKey:null});
    assert.equal(reply.kind,"error");assert.equal(reply.code,"RO-CORE-API-REQUEST-INVALID");
  }
  for(const route of ["/projects/search/sql","/native/imports/context","/projects/corpus/create","/projects/corpus/rights/current"]) {
    const reply=await exchange({method:"POST",path:route,body:JSON.stringify({root,projectId}),ifMatch:null,idempotencyKey:null});
    assert.equal(reply.kind,"error");assert.equal(reply.code,"RO-CORE-API-REQUEST-INVALID");
  }
  report.boundaries.push("ordinary Native admission still denies claimed identity and private or unknown routes");
  const denied=await control("rights-deny");
  assert.notEqual(denied.policy.revisionId,seeded.rights.policy.revisionId);
  await expectSearchDenied("rights-page",()=>client.pageLexicalSearch(pageRequest));
  await expectSearchDenied("rights-status",()=>client.inspectLexicalSearch(address));
  const restored=await control("rights-restore");assert.notEqual(restored.policy.revisionId,denied.policy.revisionId);
  report.identities.deniedRightsRevisionId=denied.policy.revisionId;report.identities.restoredRightsRevisionId=restored.policy.revisionId;
  report.boundaries.push("actual rights successors invalidate old public page and status");
  await client.closeProject({root});await expectSearchDenied("closed-project-page",()=>client.pageLexicalSearch(pageRequest));
  assert.equal((await control("restart")).restarted,true);
  await client.openProject({root});await expectSearchDenied("fresh-session-old-page",()=>client.pageLexicalSearch(pageRequest));
  const fresh=await client.executeLexicalSearch({...request,commandId:id(104)});
  const freshAddress={root,projectId,jobId:fresh.jobId};assert.equal((await awaitSearch(freshAddress)).state,"succeeded");
  assert.equal((await client.pageLexicalSearch({...freshAddress,after:null,limit:50})).hits[0].itemId,item.itemId);
  const cancelling=await client.executeLexicalSearch({...request,commandId:id(105)}),cancelAddress={root,projectId,jobId:cancelling.jobId};
  await client.cancelLexicalSearch(cancelAddress);const terminal=await awaitSearch(cancelAddress);
  assert.ok(["succeeded","cancelled"].includes(terminal.state));
  report.cancellation={terminalState:terminal.state,cancellationWon:terminal.state==="cancelled",
    limit:"A won completion race is retained; deterministic running-cancel/late acceptance is separate Core phase-barrier proof."};
  await client.closeProject({root});
  report.boundaries.push("actual close/restart denies old run and current restored source remains searchable; cancellation outcome retained");
  report.status="PASS";
} catch(error) {
  failure=error;report.status="FAIL";report.failureType=error?.constructor?.name??"Unknown";
  report.failureCode=error?.problem?.code??null;
} finally {
  await writeFile(reportPath,JSON.stringify(report,null,2)+"\n");
  process.stdout.write(JSON.stringify({kind:"finished",status:report.status})+"\n");
  lines.close();
}
if(failure)process.exitCode=1;
