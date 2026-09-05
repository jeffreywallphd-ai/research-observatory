// Actual generated client -> compiled async native supervisor -> disposable Core.
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const coreInputs = execFileSync("git", ["ls-files", "--", "services/core-api/src"], { cwd: repo, encoding: "utf8" }).trim().split(/\r?\n/);
const inputs = ["Cargo.toml", "Cargo.lock", "apps/desktop/src-tauri/Cargo.toml", "apps/desktop/src-tauri/src/lib.rs", "apps/desktop/src-tauri/src/supervisor.rs", "apps/desktop/src-tauri/examples/project_contract_probe.rs", "packages/contracts/core-api/generated.ts", "tests/service/fixtures/native_integration_sidecar.py", "tests/service/test_native_project_contract.py", "tests/service/test_provenance.py", "artifacts/evidence/W1.A09.T02.native-check-01.mjs", "target/debug/examples/project_contract_probe.exe", ...coreInputs];
async function hashes() {
  return Object.fromEntries(await Promise.all(inputs.map(async relative => [relative, createHash("sha256").update(await readFile(path.join(repo, relative))).digest("hex")])));
}
const sourceHashes = await hashes();
const { createCoreApiClient } = await import(pathToFileURL(path.join(repo, "packages/contracts/core-api/generated.ts")).href);
const temporary = await mkdtemp(path.join(repo, "artifacts/tmp/project-native-contract-"));
const vault = path.join(temporary, "vault");
const parentDirectory = path.join(temporary, "projects");
await mkdir(vault);
await mkdir(parentDirectory);
const python = execFileSync(path.join(repo, ".venv/Scripts/python.exe"), ["-c", "import sys; print(sys._base_executable)"], { encoding: "utf8" }).trim();
const pythonPath = ["tests/service/fixtures", "services/core-api/src", ".venv/Lib/site-packages"].map(value => path.join(repo, value)).join(path.delimiter);
const probe = spawn(path.join(repo, "target/debug/examples/project_contract_probe.exe"), [python, repo, pythonPath, vault], { cwd: repo, stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
const lines = createInterface({ input: probe.stdout });
const queued = [];
const waiting = [];
let ended = false;
let stderrBytes = 0;
let exitCode = null;
probe.stderr.on("data", chunk => { stderrBytes += chunk.length; });
lines.on("line", line => {
  let value;
  try { value = JSON.parse(line); } catch { value = { kind: "invalid-probe-output" }; }
  if (waiting.length) waiting.shift().resolve(value); else queued.push(value);
});
const exited = new Promise(resolve => {
  probe.once("close", code => {
    ended = true; exitCode = code;
    while (waiting.length) waiting.shift().reject(new Error("native-probe-closed"));
    resolve(code);
  });
});
probe.on("error", () => {
  while (waiting.length) waiting.shift().reject(new Error("native-probe-spawn-failed"));
});
function nextMessage() {
  if (queued.length) return Promise.resolve(queued.shift());
  if (ended) return Promise.reject(new Error("native-probe-closed"));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("native-probe-response-timeout")), 45000);
    waiting.push({ resolve: value => { clearTimeout(timer); resolve(value); }, reject: error => { clearTimeout(timer); reject(error); } });
  });
}
async function exchange(value) {
  const next = nextMessage();
  probe.stdin.write(`${JSON.stringify(value)}\n`);
  return await next;
}
const requests = [];
const transport = async request => {
  requests.push({ method: request.method, path: request.path });
  const result = await exchange(request);
  if (result.kind !== "response") throw new Error(result.code ?? "native-probe-response-invalid");
  return result.response;
};
const client = createCoreApiClient(transport);
const statuses = [];
async function waitReady() {
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) {
    const result = await exchange({ control: "status" });
    assert.equal(result.kind, "snapshot");
    statuses.push(result.snapshot.state);
    if (result.snapshot.state === "ready") return result.snapshot;
    assert.ok(["starting", "stopped"].includes(result.snapshot.state), "actual Core startup failed");
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  throw new Error("actual-core-readiness-timeout");
}
const outcomes = {};
try {
  const initial = await nextMessage();
  assert.equal(initial.kind, "initialized");
  assert.equal(initial.snapshot.state, "stopped");
  await assert.rejects(client.workflowProfileCatalog(), /RO-CORE-API-UNAVAILABLE/);
  outcomes.notReadyDenied = true;
  const catalogRequest = { method: "GET", path: "/workflow-profiles/catalog", body: null, ifMatch: null, idempotencyKey: null };
  for (const request of [
    { ...catalogRequest, method: "POST" }, { ...catalogRequest, path: "/workflow-profiles/catalog?limit=1" },
    { ...catalogRequest, body: "{}" }, { ...catalogRequest, ifMatch: "\"one\"" },
    { ...catalogRequest, idempotencyKey: "a".repeat(32) }, { ...catalogRequest, path: "/unapproved" },
  ]) assert.deepEqual(await exchange(request), { kind: "error", code: "RO-CORE-API-REQUEST-INVALID" });
  outcomes.preReadinessSubstitutionsDenied = 6;
  await exchange({ control: "start" });
  const ready = await waitReady();
  assert.equal(ready.attempt, 1);
  assert.ok(statuses.includes("starting"), "actual async starting state was not observed");
  await exchange({ control: "start" });
  assert.equal((await waitReady()).attempt, 1, "duplicate start consumed restart budget");
  const catalog = await client.workflowProfileCatalog();
  assert.equal(catalog.referenceId, "RO-UI-ACADEMIC-MINIMAL-1.5");
  assert.equal(catalog.profiles.length, 14);
  outcomes.authenticatedCatalogProfiles = catalog.profiles.length;
  const researchObjective = "Explain bounded evidence.\nPreserve line two.\r\nRetain\ttab context.";
  const project = await client.createProject({ parentDirectory, directoryName: "native-study", displayName: "Native contract study", primaryUseCase: "theory-synthesis", researchObjective });
  await client.openProject({ root: project.root });
  const original = await client.intent({ root: project.root });
  assert.equal(original.current.researchObjective, researchObjective);
  const progressBefore = await client.workflowProgress({ root: project.root });
  assert.equal(progressBefore.profileId, "theory-synthesis");
  outcomes.multilineCreatedExactly = true;
  const impact = { root: project.root, expectedRevision: 1, primaryUseCase: "theory-synthesis", sourceKinds: ["peer-reviewed-article"], evidenceTypes: ["theoretical-work"], languageCodes: ["en"], startYear: 2015, endYear: 2026, includePrivateReports: false, noveltyStandard: "theoretical", autonomyLevel: "suggest", stoppingConditions: ["interpretive-saturation"] };
  const preview = await client.previewIntent(impact);
  const draft = await client.saveIntentDraft({ ...impact, researchObjective, contributionIntent: "Bounded synthetic contract proof.", phenomenon: "Scholarly workflows", unitOfAnalysis: "Workflow", levelOfAnalysis: "System", noveltyRationale: "Compare explicit authority boundaries.", revisionRationale: "Retain exact lineage to the prior draft.", impactAcknowledgement: preview.acknowledgementToken }, randomUUID().replaceAll("-", ""));
  await client.closeProject({ root: project.root });
  const seed = JSON.parse(execFileSync(python, [path.join(repo, "tests/service/test_native_project_contract.py"), "--seed-lineage", project.root, vault], {
    encoding: "utf8", env: { ...process.env, PYTHONPATH: pythonPath }, windowsHide: true,
  }));
  await client.openProject({ root: project.root });
  const query = { root: project.root, revisionId: seed.secondRevisionId, direction: "ancestors", cursor: 0, pageSize: 50, maxDepth: 8 };
  const lineage = await client.lineage(query);
  assert.equal(lineage.revisionId, seed.secondRevisionId);
  assert.ok(lineage.items.some(item => item.depth > 0 && item.revisionId === seed.firstRevisionId), "retained predecessor relation missing");
  outcomes.retainedLineageNodes = lineage.items.length;
  const lineageRequest = { method: "POST", path: "/projects/provenance/lineage", body: JSON.stringify(query), ifMatch: null, idempotencyKey: null };
  for (const request of [
    { ...lineageRequest, method: "GET" }, { ...lineageRequest, path: `${lineageRequest.path}/` },
    { ...lineageRequest, path: `${lineageRequest.path}?cursor=0` }, { ...lineageRequest, ifMatch: "\"one\"" },
    { ...lineageRequest, idempotencyKey: "a".repeat(32) },
    { ...lineageRequest, body: JSON.stringify({ ...query, cursor: true }) },
    { ...lineageRequest, body: JSON.stringify({ ...query, extra: null }) },
    { ...lineageRequest, body: lineageRequest.body.replace("{", "{\"cursor\":0,") },
  ]) assert.deepEqual(await exchange(request), { kind: "error", code: "RO-CORE-API-REQUEST-INVALID" });
  outcomes.liveLineageSubstitutionsDenied = 8;
  const unknown = await client.lineage({ ...query, revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099" });
  assert.equal(unknown.items.length, 0);
  assert.equal(unknown.integrityState, "integrity-review");
  assert.equal(unknown.exportAllowed, false);
  assert.ok(unknown.missingRevisionIds.includes("018f47a2-4d6b-7f78-9f2e-7fb76c86d099"));
  outcomes.unknownRevisionFailsClosed = true;
  await client.closeProject({ root: project.root });
  await client.openProject({ root: project.root });
  const reopened = await client.intent({ root: project.root });
  assert.equal(reopened.current.revisionContentHash, draft.revisionContentHash);
  const retainedProgress = await client.workflowProgress({ root: project.root });
  assert.equal(retainedProgress.selectionRevisionId, progressBefore.selectionRevisionId);
  assert.equal(retainedProgress.selectionRevisionContentHash, progressBefore.selectionRevisionContentHash);
  const second = await client.createProject({ parentDirectory, directoryName: "other-study", displayName: "Other isolated study", primaryUseCase: "theory-synthesis", researchObjective: "Separate project authority." });
  await client.openProject({ root: second.root });
  const wrongProject = await client.lineage({ ...query, root: second.root });
  assert.equal(wrongProject.items.length, 0);
  assert.equal(wrongProject.integrityState, "integrity-review");
  assert.equal(wrongProject.exportAllowed, false);
  assert.ok(wrongProject.missingRevisionIds.includes(seed.secondRevisionId));
  outcomes.wrongProjectFailsClosed = true;
  await client.closeProject({ root: second.root });
  await client.closeProject({ root: project.root });
  const stopped = await exchange({ control: "stop" });
  assert.equal(stopped.snapshot.state, "stopped");
  const creationCount = requests.filter(request => request.path === "/projects").length;
  await assert.rejects(client.workflowProfileCatalog(), /RO-CORE-API-UNAVAILABLE/);
  await exchange({ control: "start" });
  assert.equal((await waitReady()).attempt, 2);
  await client.workflowProfileCatalog();
  assert.equal(requests.filter(request => request.path === "/projects").length, creationCount);
  await client.openProject({ root: project.root });
  const restarted = await client.intent({ root: project.root });
  assert.equal(restarted.current.revisionContentHash, draft.revisionContentHash);
  assert.equal(restarted.current.researchObjective, researchObjective);
  const afterRestart = await client.workflowProgress({ root: project.root });
  assert.equal(afterRestart.selectionRevisionContentHash, retainedProgress.selectionRevisionContentHash);
  assert.ok((await client.lineage(query)).items.some(item => item.revisionId === seed.firstRevisionId && item.depth > 0));
  outcomes.restartPreservedIntentWorkflowAndLineage = true;
  outcomes.readRetryCreatedNothing = true;
  await client.closeProject({ root: project.root });
} finally {
  probe.stdin.end();
  const timer = setTimeout(() => { if (!ended) probe.kill(); }, 15000);
  await exited;
  clearTimeout(timer);
  lines.close();
}
assert.equal(exitCode, 0, "native probe did not shut down normally");
assert.deepEqual(await hashes(), sourceHashes, "native probe inputs changed during verification");
const report = { schemaVersion: "1.0", taskId: "W1.A09.T02", ok: true, boundary: "generated TypeScript client through actual async native dispatch/supervisor, per-launch authenticated Core and isolated Windows DPAPI/SQLCipher project persistence; canonical lineage fixture appended through real unit-of-work while closed; not Tauri IPC or packaged no-fallback qualification", outcomes, observedRuntimeStates: [...new Set(statuses)], normalProbeExit: exitCode, stderrBytes, sourceHashes, fixtureDirectory: path.relative(repo, temporary).replaceAll("\\", "/"), fixturesRetained: true };
const rendered = JSON.stringify(report, null, 2);
await writeFile(path.join(temporary, "report.json"), `${rendered}\n`, { flag: "wx" });
console.log(rendered);
