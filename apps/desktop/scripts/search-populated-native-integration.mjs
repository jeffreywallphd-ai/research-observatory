// Explicit real-principal slice trial. The Rust test owns the child client and
// supervisor; this driver owns only the confined fixture and compiler process.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, lstat, realpath, rm, writeFile, open } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const appRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const repo=path.resolve(appRoot,"../..");
const scratch=await realpath(path.join(repo,"artifacts/tmp"));
const argument=process.argv.indexOf("--report");
assert.ok(argument>=0&&process.argv[argument+1],"Explicit confined report required");
const reportPath=path.resolve(repo,process.argv[argument+1]);
assert.equal(path.dirname(reportPath),scratch);assert.ok(path.basename(reportPath).startsWith("CAP-06.S01."));
const report={documentType:"populated-native-search-integration",status:"RUNNING",startedAtUtc:new Date().toISOString(),
  limits:["Source Core, explicitly synthetic Native session/Intent/source/rights confirmations.",
    "Actual fixed fixture setup does not establish renderer corpus/rights editing or file picker/sign-in.",
    "Single metadata item; no full text, 100k, scientific gold, installed packaging or full-profile PASS.",
    "Selected source/runtime hashes only; qualifying execution additionally needs the full frozen-input recorder. No complete installed-runtime/OS attestation or reuse authority."]};
await writeFile(reportPath,JSON.stringify(report,null,2)+"\n",{flag:"wx"});
const fixture=await realpath(await mkdtemp(path.join(scratch,"search-populated-native-")));
const python=path.join(repo,".venv/Scripts/python.exe");
const pythonPath=[path.join(repo,"tests/service/fixtures"),path.join(repo,"services/core-api/src"),path.join(repo,".venv/Lib/site-packages")].join(path.delimiter);
const sha=async filename=>createHash("sha256").update(await readFile(filename)).digest("hex");
const stamp=performance.now();let failure;
try {
  report.candidateCommit=execFileSync("git",["rev-parse","HEAD"],{cwd:repo,encoding:"utf8"}).trim();
  report.inputSha256={};
  for(const relative of ["apps/desktop/scripts/search-populated-native-integration.mjs",
    "apps/desktop/scripts/search-populated-native-client.mjs","apps/desktop/src-tauri/src/supervisor.rs",
    "apps/desktop/src-tauri/src/supervisor/populated_search_integration.rs",
    "apps/desktop/src-tauri/src/supervisor/native_stop_proof.rs",
    "tests/service/fixtures/native_integration_sidecar.py","packages/contracts/core-api/generated.ts",
    "tests/search/populated_native_owner.py","tests/service/test_native_project_contract.py","workers/windows/lpac_launcher.py"])
    report.inputSha256[relative]=await sha(path.join(repo,relative));
  report.nodeSha256=await sha(process.execPath);report.pythonSha256=await sha(python);
  const basePython=execFileSync(python,["-B","-c","import sys; print(sys._base_executable)"],{encoding:"utf8"}).trim();
  report.basePythonSha256=await sha(basePython);
  await mkdir(path.join(fixture,"projects"));await mkdir(path.join(fixture,"session"));await mkdir(path.join(fixture,"temp"));
  execFileSync(python,["-B","-c","from pathlib import Path; import sys; from research_observatory_core.windows_credentials import WindowsCredentialStore; WindowsCredentialStore(Path(sys.argv[1]),audit_sink=lambda event:None)._ensure_root()",path.join(fixture,"vault")],
    {cwd:repo,env:{...process.env,PYTHONPATH:pythonPath,PYTHONDONTWRITEBYTECODE:"1",TEMP:path.join(fixture,"temp"),TMP:path.join(fixture,"temp")},encoding:"utf8"});
  await build({configFile:false,root:repo,logLevel:"error",build:{ssr:path.join(repo,"packages/contracts/core-api/generated.ts"),
    outDir:path.join(fixture,"client"),emptyOutDir:false,rollupOptions:{output:{entryFileNames:"client.mjs",format:"es"}}}});
  report.generatedClientBundleSha256=await sha(path.join(fixture,"client/client.mjs"));
  report.childSettings={pythonNoBytecode:true,tempRoot:"owned-fixture/temp",nativeResponseDeadlineSeconds:2,
    rustChildDeadlineSeconds:180,nodeIpcDeadlineSeconds:30,operationDeadlineSeconds:60,
    compilerDeadlineSeconds:360,ownedTestDeadlineSeconds:240,outerOwnerDeadlineSeconds:900,
    fixtureSession:"actual Native WorkflowSessionAuthority in isolated session directory"};
  const rawPath=reportPath.replace(/\.json$/u,".owner.log");
  assert.notEqual(rawPath,reportPath);
  const raw=await open(rawPath,"wx");
  try {
    const cargo=execFileSync(python,["-B","-c","import shutil; print(shutil.which('cargo') or '')"],{encoding:"utf8"}).trim();
    assert.ok(cargo,"actual Cargo executable required");
    execFileSync(python,["-B",path.join(repo,"tests/search/populated_native_owner.py"),fixture,cargo],{cwd:repo,stdio:["ignore",raw.fd,raw.fd],
      env:{...process.env,PYTHONDONTWRITEBYTECODE:"1",TEMP:path.join(fixture,"temp"),TMP:path.join(fixture,"temp"),RO_SEARCH_POPULATED_FIXTURE:fixture,
        RO_SEARCH_POPULATED_PYTHON:basePython,RO_SEARCH_POPULATED_NODE:process.execPath},timeout:900000});
    report.ownerExitCode=0;
  } catch(error) {
    report.ownerExitCode=Number.isInteger(error.status)?error.status:null;
    report.outerWatchdogExpired=error.code==="ETIMEDOUT";throw error;
  } finally { await raw.close();report.rawOutput=path.relative(repo,rawPath).split(path.sep).join("/");report.rawOutputSha256=await sha(rawPath); }
  report.client=JSON.parse(await readFile(path.join(fixture,"client-report.json"),"utf8"));
  report.native=JSON.parse(await readFile(path.join(fixture,"native-proof.json"),"utf8"));
  report.owner=JSON.parse(await readFile(path.join(fixture,"owner-report.json"),"utf8"));
  assert.equal(report.owner.status,"PASS");assert.equal(report.owner.runs.length,2);
  for(const run of report.owner.runs){
    assert.equal(run.status,"PASS");assert.equal(run.forcedTermination,false);
    assert.equal(run.naturalDrainObservation.active,0);assert.equal(run.binaryReaderCompleted,true);
  }
  report.lifetimeStops=[];
  for(const stage of ["restart","final"]){
    const stop=JSON.parse(await readFile(path.join(fixture,`native-stop-${stage}.json`),"utf8"));
    assert.equal(stop.kind,"actual-native-inner-core-stop-observation");
    assert.equal(stop.stage,stage);
    assert.equal(stop.coreNormalContainedDrain,true);
    assert.equal(stop.boundedJourneyNormalLifetime,true);
    assert.equal(stop.attemptMatches,true);
    assert.equal(stop.ownedZeroRolesIndependentlyChecked,true);
    assert.equal(stop.record.normalEntries,1);
    for(const key of ["immediateEntries","terminateInvocations","directKillInvocations"])
      assert.equal(stop.record[key],0);
    assert.equal(stop.record.closeAttempts,1);assert.equal(stop.record.closeResults,1);
    assert.equal(stop.record.closeSucceeded,true);
    const before=stop.record.beforeClose;
    for(const key of ["accountingQueryOk","processListQueryOk","completeProcessList"])
      assert.equal(before[key],true);
    for(const key of ["activeProcesses","totalTerminatedProcesses","assignedProcesses","returnedProcesses"])
      assert.equal(before[key],0);
    assert.deepEqual(before.processIds,[]);
    assert.equal(stop.waitResult,0);assert.equal(stop.exitCodeKnown,true);assert.equal(stop.exitCode,0);
    assert.equal(stop.identityEqual,true);assert.equal(stop.observerHandleClosed,true);
    assert.deepEqual(stop.identityAfter,stop.record.identity);
    const identity=stop.record.identity;
    assert.ok(Number.isSafeInteger(identity.process_id)&&identity.process_id>0&&identity.process_id<=0xffffffff);
    assert.match(identity.creation_filetime,/^[0-9a-f]{16}$/u);
    assert.match(identity.executable_identity,/^[0-9a-f]{64}$/u);
    const name=`core-owned-roles-${identity.process_id}-${identity.creation_filetime}.json`;
    const roles=JSON.parse(await readFile(path.join(fixture,"core-owned-role-proof",name),"utf8"));
    assert.deepEqual(roles,stop.ownedRoleReceipt);
    assert.deepEqual(roles.coreIdentity,identity);
    assert.equal(roles.kind,"test-only-core-owned-role-zero-observation");
    for(const key of ["installedBeforeRuntimeComposition","runtimeReturned","finalizedBeforeCoreExit",
      "aliasesRetainedUntilFinalization","sourcePinsEqualAfter","observedZeroRoleAttempts"])
      assert.equal(roles[key],true);
    assert.equal(roles.coverage.aliasesMatchedAtInstall,true);assert.equal(roles.coverage.observerError,false);
    assert.deepEqual(roles.unexpectedLiveThreads,[]);
    assert.equal(roles.positiveWorkerGuardianDrain,"NOT_OBSERVED");
    assert.deepEqual(Object.keys(roles.roles).sort(),["acl-utility","connector-worker","guardian","lpac-worker"]);
    for(const counts of Object.values(roles.roles))
      assert.deepEqual(counts,{attempts:0,returns:0,errors:0,inflight:0});
    report.lifetimeStops.push({stage,coreIdentity:identity,roleReceiptName:name,
      coreNormalContainedDrain:true,observedZeroRoleAttempts:true,boundedJourneyNormalLifetime:true});
  }
  assert.notDeepEqual(
    [report.lifetimeStops[0].coreIdentity.process_id,report.lifetimeStops[0].coreIdentity.creation_filetime],
    [report.lifetimeStops[1].coreIdentity.process_id,report.lifetimeStops[1].coreIdentity.creation_filetime],
    "restart must produce a distinct actual Core incarnation");
  assert.deepEqual(report.native.lifetimeReceiptPaths,["native-stop-restart.json","native-stop-final.json"]);
  assert.equal(report.client.status,"PASS");
  assert.equal(report.native.normalChildExit,true);assert.equal(report.native.childReaped,true);assert.equal(report.native.supervisorStopped,true);
  assert.equal(await sha(path.join(fixture,"client/client.mjs")),report.generatedClientBundleSha256);
  assert.equal(await sha(process.execPath),report.nodeSha256);assert.equal(await sha(python),report.pythonSha256);
  assert.equal(await sha(basePython),report.basePythonSha256);
  for(const [relative,digest] of Object.entries(report.inputSha256))assert.equal(await sha(path.join(repo,relative)),digest);
  assert.equal(execFileSync("git",["rev-parse","HEAD"],{cwd:repo,encoding:"utf8"}).trim(),report.candidateCommit);
  report.inputEqualityAfter=true;report.status="PASS";
} catch(error) {
  failure=error;report.status="FAIL";report.failureType=error?.constructor?.name??"Unknown";
} finally {
  report.beforeCleanupSeconds=(performance.now()-stamp)/1000;
  try {
    const retained=reportPath.replace(/\.json$/u,"-receipts");assert.notEqual(retained,reportPath);
    await mkdir(retained);report.receipts=[];
    for(const name of ["client-report.json","native-proof.json","owner-report.json","node-stderr.log",
      "native-stop-restart.json","native-stop-final.json",
      "compiler.stdout.log","compiler.stderr.log","native-test.stdout.log","native-test.stderr.log"]){
      const source=path.join(fixture,name);
      let bytes;
      try{bytes=await readFile(source);}catch(error){if(error.code==="ENOENT"&&report.status!=="PASS")continue;throw error;}
      const digest=createHash("sha256").update(bytes).digest("hex");
      const target=path.join(retained,name);await writeFile(target,bytes,{flag:"wx"});
      assert.equal(await sha(source),digest);assert.equal(await sha(target),digest);
      report.receipts.push({path:path.relative(repo,target).split(path.sep).join("/"),sha256:digest,bytes:bytes.length});
    }
    const roleRoot=path.join(fixture,"core-owned-role-proof");
    let entries=[];
    try{entries=await readdir(roleRoot,{withFileTypes:true});}
    catch(error){if(error.code!=="ENOENT"||report.status==="PASS")throw error;}
    assert.ok(entries.length<=8,"fixed fixture role receipt bound");
    if(entries.length){
      await mkdir(path.join(retained,"core-owned-role-proof"));
      for(const entry of entries.sort((a,b)=>a.name.localeCompare(b.name))){
        assert.ok(entry.isFile()&&!entry.isSymbolicLink());
        assert.match(entry.name,/^core-owned-roles-[1-9][0-9]{0,9}-[0-9a-f]{16}\.json$/u);
        const source=path.join(roleRoot,entry.name);
        const metadata=await lstat(source);
        assert.ok(metadata.isFile()&&!metadata.isSymbolicLink()&&metadata.size<=131072);
        const bytes=await readFile(source);assert.ok(bytes.length<=131072);
        const digest=createHash("sha256").update(bytes).digest("hex");
        const target=path.join(retained,"core-owned-role-proof",entry.name);
        await writeFile(target,bytes,{flag:"wx"});
        assert.equal(await sha(source),digest);assert.equal(await sha(target),digest);
        report.receipts.push({path:path.relative(repo,target).split(path.sep).join("/"),sha256:digest,bytes:bytes.length});
      }
    }
    if(report.status==="PASS"){
      assert.equal(entries.length,2);
      assert.deepEqual(entries.map(entry=>entry.name).sort(),report.lifetimeStops.map(stop=>stop.roleReceiptName).sort());
    }
  }catch(error){report.status="FAIL";failure??=error;report.receiptFailureType=error.constructor.name;}
  if(report.status==="PASS") {
    try{
      const resolved=await realpath(fixture);assert.equal(path.dirname(resolved),scratch);
      assert.ok(path.basename(resolved).startsWith("search-populated-native-"));
      await rm(resolved,{recursive:true,force:false});report.ownedFixtureCleanup="complete";
    }
    catch(error){report.status="FAIL";failure??=error;report.failureType=error.constructor.name;report.ownedFixtureCleanup="failed";report.retainedFixture=fixture;}
  } else {report.ownedFixtureCleanup="retained-for-diagnosis-no-normal-drain-inferred";report.retainedFixture=fixture;}
  report.elapsedSeconds=(performance.now()-stamp)/1000;report.completedAtUtc=new Date().toISOString();
  await writeFile(reportPath,JSON.stringify(report,null,2)+"\n");
}
console.log(JSON.stringify({status:report.status,elapsedSeconds:report.elapsedSeconds,ownerExitCode:report.ownerExitCode,
  boundaries:report.client?.boundaries??[],ownedFixtureCleanup:report.ownedFixtureCleanup}));
if(failure)process.exitCode=1;
