// Actual Rust supervisor -> authenticated Core -> DPAPI/SQLCipher -> generated
// client. The empty lawful corpus isolates the transport/persistence boundary;
// populated ranking/rights and frozen known-item quality are separate checks.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "vite";

const appRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const repoRoot=path.resolve(appRoot,"../..");
const scratch=await realpath(path.join(repoRoot,"artifacts/tmp"));
const argument=process.argv.indexOf("--report");
if(argument<0||!process.argv[argument+1])throw Error("Confined ignored report path required");
const reportPath=path.resolve(repoRoot,process.argv[argument+1]);
if(path.dirname(reportPath)!==scratch||!path.basename(reportPath).startsWith("CAP-06.S01.T03."))throw Error("Report path invalid");
const report={documentType:"search-native-integration",status:"RUNNING",boundaries:[],calls:[],
  limits:["Source Core integration harness; no packaged installer proof.","Empty lawful corpus; populated ranking/rights and known-item quality are separate checks."]};
await writeFile(reportPath,JSON.stringify(report,null,2)+"\n",{flag:"wx"});
const fixture=await mkdtemp(path.join(scratch,"search-native-"));
const vaultRoot=path.join(fixture,"vault"), parentDirectory=path.join(fixture,"projects"),sessionRoot=path.join(fixture,"session");
// Core creates its own private vault with the existing Windows protection/ACL
// policy. Precreating that directory with Node's inherited ACLs is not safe.
await mkdir(parentDirectory);await mkdir(sessionRoot);
const python=path.join(repoRoot,".venv/Scripts/python.exe");
const basePython=execFileSync(python,["-B","-c","import sys; print(sys._base_executable)"],{encoding:"utf8"}).trim();
const pythonPath=[path.join(repoRoot,"tests/service/fixtures"),path.join(repoRoot,"services/core-api/src"),path.join(repoRoot,".venv/Lib/site-packages")].join(path.delimiter);
// The existing harness requires the vault path to exist before startup. Use
// the real Core store initializer (Windows mode0700), never an inherited ACL.
execFileSync(python,["-B","-c","from pathlib import Path; import sys; from research_observatory_core.windows_credentials import WindowsCredentialStore; WindowsCredentialStore(Path(sys.argv[1]),audit_sink=lambda event:None)._ensure_root()",vaultRoot],
  {env:{...process.env,PYTHONPATH:pythonPath},encoding:"utf8"});
let createCoreApiClient;
try {
  await build({configFile:false,root:repoRoot,logLevel:"error",build:{
    ssr:path.join(repoRoot,"packages/contracts/core-api/generated.ts"),outDir:path.join(fixture,"client"),emptyOutDir:false,
    rollupOptions:{output:{entryFileNames:"client.mjs",format:"es"}},
  }});
  ({createCoreApiClient}=await import(pathToFileURL(path.join(fixture,"client/client.mjs")).href));
} catch(error) {
  report.status="FAIL";report.failureType=error?.constructor?.name??"Unknown";
  await writeFile(reportPath,JSON.stringify(report,null,2)+"\n");
  const resolved=await realpath(fixture);
  assert.equal(path.dirname(resolved),scratch);assert.ok(path.basename(resolved).startsWith("search-native-"));
  await rm(resolved,{recursive:true,force:false});throw error;
}
const harness=spawn("cargo",["run","--quiet","--locked","--features","integration-harness","--example","supervised_core_harness","--",
  basePython,repoRoot,pythonPath,vaultRoot,sessionRoot],{cwd:path.join(appRoot,"src-tauri"),stdio:["pipe","pipe","pipe"],env:{...process.env,PYTHONDONTWRITEBYTECODE:"1"}});
const lines=createInterface({input:harness.stdout}), waiting=[], buffered=[];
let stderr="", closed=false;
harness.stderr.setEncoding("utf8");harness.stderr.on("data",chunk=>{stderr=(stderr+chunk).slice(-16000);});
lines.on("line",line=>{const value=JSON.parse(line);const next=waiting.shift();if(next)next.resolve(value);else buffered.push(value);});
const exit=new Promise(resolve=>harness.on("close",code=>{closed=true;while(waiting.length)waiting.shift().reject(Error(`Harness closed (${code})`));resolve(code);}));
harness.on("error",()=>{while(waiting.length)waiting.shift().reject(Error("Native harness could not start"));});
const receive=()=>buffered.length?Promise.resolve(buffered.shift()):new Promise((resolve,reject)=>waiting.push({resolve,reject}));
const exchange=async value=>{const reply=receive();harness.stdin.write(JSON.stringify(value)+"\n");return await reply;};
const transport=async request=>{
  const start=performance.now();const reply=await exchange(request);
  report.calls.push({path:request.path,elapsedMs:performance.now()-start,kind:reply.kind,status:reply.response?.status??null});
  if(reply.kind!=="response")throw Error(reply.code??"Native request denied");
  return reply.response;
};
const client=createCoreApiClient(transport);
const id=n=>`01900000-0000-7000-8000-${String(n).padStart(12,"0")}`;
let failure=null;
try{
  assert.equal((await receive()).kind,"ready");
  const project=await client.createProject({parentDirectory,directoryName:"search",displayName:"Synthetic search Native proof",
    primaryUseCase:"theory-synthesis",researchObjective:"Synthetic local search transport and immutable run proof."});
  const root=project.root;await client.openProject({root});
  const impact={root,expectedRevision:1,primaryUseCase:"systematic-review",sourceKinds:["peer-reviewed-article","conference-paper"],
    evidenceTypes:["empirical-study","theoretical-work"],languageCodes:["en"],startYear:2015,endYear:2026,includePrivateReports:false,
    noveltyStandard:"theoretical",autonomyLevel:"suggest",stoppingConditions:["coverage-threshold"]};
  const preview=await client.previewIntent(impact);
  const draft=await client.saveIntentDraft({...impact,researchObjective:"Synthetic local lexical API boundary proof.",
    contributionIntent:"Verify the bounded local search interface.",phenomenon:"Synthetic lookup",unitOfAnalysis:"Synthetic record",
    levelOfAnalysis:"Technical fixture",noveltyRationale:"No scholarly novelty claim.",revisionRationale:"Isolated Native proof.",
    impactAcknowledgement:preview.acknowledgementToken},"0123456789abcdef0123456789abcdef");
  await client.acceptIntent({root,expectedRevision:draft.revision,expectedRevisionContentHash:draft.revisionContentHash,
    confirmed:true,decisionRationale:"Synthetic confirmation in an isolated fixture only."},"abcdef0123456789abcdef0123456789");
  report.boundaries.push("actual Rust Native principal and accepted protected Intent");
  const validation=await client.validateLexicalQuery({query:"title:synthetic"});assert.equal(validation.valid,true);
  const request={root,projectId:project.projectId,commandId:id(1),query:"title:synthetic",filters:{yearFrom:null,yearTo:null}};
  const job=await client.executeLexicalSearch(request), replay=await client.executeLexicalSearch(request);
  assert.equal(job.jobId,replay.jobId);assert.equal(job.workflowRunId,replay.workflowRunId);
  const address={root,projectId:project.projectId,jobId:job.jobId};
  let status=job;const deadline=performance.now()+60000;
  while(!["succeeded","failed","cancelled"].includes(status.state)&&performance.now()<deadline){
    await new Promise(resolve=>setTimeout(resolve,100));status=await client.inspectLexicalSearch(address);
  }
  assert.equal(status.state,"succeeded");
  const page=await client.pageLexicalSearch({...address,after:null,limit:50});
  assert.equal(page.execution.resultCount,0);assert.deepEqual(page.hits,[]);assert.equal(page.nextCursor,null);
  assert.equal(page.execution.semanticState,"unqualified");assert.equal(page.execution.rerankState,"not-run");
  report.boundaries.push("existing admitted durable worker, protected selected generation and strict canonical SearchRun","generated typed run/status/page replies","same-command replay returns the same queue job");
  for(const body of [{...request,actorId:id(2)},{...request,sessionId:"f".repeat(32)}]){
    const reply=await exchange({method:"POST",path:"/projects/search/run",body:JSON.stringify(body),ifMatch:null,idempotencyKey:null});
    assert.equal(reply.kind,"error");assert.equal(reply.code,"RO-CORE-API-REQUEST-INVALID");
  }
  const bad=await exchange({method:"POST",path:"/projects/search/sql",body:JSON.stringify(request),ifMatch:null,idempotencyKey:null});
  assert.equal(bad.kind,"error");assert.equal(bad.code,"RO-CORE-API-REQUEST-INVALID");
  report.boundaries.push("Native rejects claimed actor/session and unknown search routes");
  await client.closeProject({root});
  await assert.rejects(()=>client.pageLexicalSearch({...address,after:null,limit:50}));
  assert.equal((await exchange({control:"restart"})).kind,"restarted");
  await client.openProject({root});
  await assert.rejects(()=>client.pageLexicalSearch({...address,after:null,limit:50}));
  const fresh=await client.executeLexicalSearch({...request,commandId:id(3)});
  assert.notEqual(job.jobId,fresh.jobId);
  await client.cancelLexicalSearch({...address,jobId:fresh.jobId});
  await client.closeProject({root});
  report.boundaries.push("project close and fresh-session restart reject an old result; fresh command and cancellation remain available");
  report.status="PASS";
}catch(error){failure=error;report.status="FAIL";report.failureType=error?.constructor?.name??"Unknown";report.failureCode=error?.problem?.code??null;}
finally{
  if(!closed)harness.stdin.end();
  const code=await exit;lines.close();
  report.harnessExitCode=code;
  report.diagnostics=stderr.split(/\r?\n/u).flatMap(line=>{
    try {const value=JSON.parse(line);return typeof value.event==="string"&&value.event.includes("unavailable")
      ? [{event:value.event,reasonCode:value.reasonCode??null}] : [];}
    catch{return [];}
  });
  if(code!==0){report.status="FAIL";failure??=Error("Harness did not drain cleanly");}
  const resolved=await realpath(fixture);
  assert.equal(path.dirname(resolved),scratch);assert.ok(path.basename(resolved).startsWith("search-native-"));
  await rm(resolved,{recursive:true,force:false});report.ownedFixtureCleanup="complete";
  await writeFile(reportPath,JSON.stringify(report,null,2)+"\n");
}
console.log(JSON.stringify({status:report.status,boundaries:report.boundaries,calls:report.calls,harnessExitCode:report.harnessExitCode}));
if(failure){console.error(failure);if(report.harnessExitCode!==0)console.error(stderr);process.exitCode=1;}
