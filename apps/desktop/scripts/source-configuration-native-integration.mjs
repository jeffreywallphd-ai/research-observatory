// Real native supervisor/Core/DPAPI boundary; no dialog or provider-network claim.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { createCoreApiClient, sourceTestCommand } = await import(pathToFileURL(path.join(repo, "packages/contracts/core-api/generated.ts")));
const temporary = path.join(repo, "artifacts/tmp");
await mkdir(temporary, { recursive: true });
const fixture = await mkdtemp(path.join(temporary, "source-native-"));
const vault = path.join(fixture, "vault");
const projects = path.join(fixture, "projects");
const session = path.join(fixture, "session");
await mkdir(vault); await mkdir(projects); await mkdir(session);
const python = execFileSync(path.join(repo, ".venv/Scripts/python.exe"), ["-c", "import sys; print(sys._base_executable)"], { encoding: "utf8" }).trim();
const pythonPath = ["tests/service/fixtures", "services/core-api/src", ".venv/Lib/site-packages"].map((item) => path.join(repo, item)).join(path.delimiter);
const harness = spawn("cargo", ["run", "--quiet", "--locked", "--offline", "--features", "integration-harness", "--example", "supervised_core_harness", "--", python, repo, pythonPath, vault, session], {
  cwd: path.join(repo, "apps/desktop/src-tauri"), stdio: ["pipe", "pipe", "pipe"],
});
const reader = createInterface({ input: harness.stdout });
const buffered = []; const waiters = []; const output = [];
let closed = false; let diagnostics = "";
reader.on("line", (line) => {
  output.push(line);
  try {
    const message = JSON.parse(line);
    if (waiters.length) waiters.shift().resolve(message); else buffered.push(message);
  } catch { while (waiters.length) waiters.shift().reject(Error("Invalid harness reply")); }
});
harness.stderr.setEncoding("utf8");
harness.stderr.on("data", (chunk) => { diagnostics = (diagnostics + chunk).slice(-32768); });
const exit = new Promise((resolve) => {
  harness.on("error", () => { while (waiters.length) waiters.shift().reject(Error("Harness launch failed")); });
  harness.on("close", (code) => {
    closed = true;
    while (waiters.length) waiters.shift().reject(Error("Harness closed before reply"));
    resolve(code);
  });
});
function next() {
  if (buffered.length) return Promise.resolve(buffered.shift());
  if (closed) return Promise.reject(Error("Harness already closed"));
  return new Promise((resolve, reject) => waiters.push({ resolve, reject }));
}
async function exchange(value) {
  const reply = next(); harness.stdin.write(`${JSON.stringify(value)}\n`); return reply;
}
const publicRequests = [];
const client = createCoreApiClient(async (request) => {
  publicRequests.push(request);
  const reply = await exchange(request);
  assert.equal(reply.kind, "response", "public route must return a bounded response");
  return reply.response;
});
const deadline = setTimeout(() => { harness.stdin.end(); harness.kill(); }, 180_000);
let result;
try {
  assert.equal((await next()).kind, "ready");
  const project = await client.createProject({ parentDirectory: projects, directoryName: "source-proof", displayName: "Synthetic source configuration", primaryUseCase: "theory-synthesis", researchObjective: "Verify private source configuration without provider network access." });
  await client.openProject({ root: project.root });
  const command = { control: "connector-configuration-fixture", root: project.root, projectId: project.projectId, write: false, expectedVersion: null };
  const status = async (changes = {}) => {
    const reply = await exchange({ ...command, ...changes });
    assert.equal(reply.kind, "response");
    return { status: reply.response.status, body: JSON.parse(reply.response.body) };
  };
  const fresh = await status();
  assert.equal(fresh.status, 200);
  assert.equal(fresh.body.configuration, "not-configured");
  assert.equal(fresh.body.version, null);
  const saved = await status({ write: true });
  assert.equal(saved.status, 200);
  assert.equal(saved.body.contactConfigured, true);
  assert.equal(saved.body.keyConfigured, false);
  assert.match(saved.body.version, /^[0-9a-f]{32}$/);
  assert.equal((await client.connectorCapabilities()).items.find((item) => item.providerId === "unpaywall").configuration, "ready");
  const conflict = await status({ write: true });
  assert.equal(conflict.status, 409);
  assert.equal(conflict.body.code, "RO-CORE-CONNECTOR-CONFIGURATION-CONFLICT");
  assert.deepEqual((await status()).body, saved.body);
  assert.equal((await exchange({ control: "restart" })).kind, "restarted");
  await client.openProject({ root: project.root });
  assert.deepEqual((await status()).body, saved.body, "protected settings survive actual Core restart");
  const replaced = await status({ write: true, expectedVersion: saved.body.version });
  assert.equal(replaced.status, 200);
  assert.notEqual(replaced.body.version, saved.body.version);
  const wrong = await exchange({ ...command, projectId: "018f6b91-7c00-7000-8000-000000000099" });
  assert.equal(wrong.kind, "error");
  for (const endpoint of ["status", "replace"]) {
    const denial = await exchange({ method: "POST", path: `/native/connectors/configuration/${endpoint}`, body: JSON.stringify(command), ifMatch: null, idempotencyKey: null });
    assert.equal(denial.kind, "error");
    assert.equal(denial.code, "RO-CORE-API-REQUEST-INVALID");
  }
  // The ordinary generated-client/native/Core permission path, not a seeded
  // accepted Intent. Previews below are local-only; no confirmation is sent.
  const provider = (await client.connectorCapabilities()).items.find((item) => item.providerId === "unpaywall");
  const sourceRequest = sourceTestCommand(project.root, project.projectId, provider, "10.99999/synthetic", "01900000-0000-7000-8000-000000000071");
  await assert.rejects(client.previewSourceTest(sourceRequest));
  const current = (await client.intent({ root: project.root })).current;
  const scope = { root: project.root, expectedRevision: current.revision, primaryUseCase: "theory-synthesis", sourceKinds: ["peer-reviewed-article"], evidenceTypes: ["theoretical-work"], languageCodes: ["en"], startYear: 2020, endYear: 2026, includePrivateReports: false, noveltyStandard: "theoretical", autonomyLevel: "suggest", stoppingConditions: ["interpretive-saturation"], egressPolicy: { mode: "approved-content", approvedDestinationIds: ["unpaywall"] } };
  const impact = await client.previewIntent(scope);
  const draft = await client.saveIntentDraft({ ...scope, researchObjective: "Verify explicit source authority in a synthetic project.", contributionIntent: "Bounded conceptual synthesis.", phenomenon: "Research workflow", unitOfAnalysis: "Scholarly workflow", levelOfAnalysis: "Conceptual system", noveltyRationale: "Compare explicit authority boundaries.", revisionRationale: "Authorize one named scholarly source with exact confirmation.", impactAcknowledgement: impact.acknowledgementToken }, "a".repeat(32));
  assert.deepEqual(draft.egressPolicy, scope.egressPolicy);
  await assert.rejects(client.previewSourceTest(sourceRequest), "a draft never grants egress");
  const accepted = await client.acceptIntent({ root: project.root, expectedRevision: draft.revision, expectedRevisionContentHash: draft.revisionContentHash, confirmed: true, decisionRationale: "Synthetic researcher acceptance of the exact provider scope." }, "b".repeat(32));
  assert.deepEqual(accepted.egressPolicy, scope.egressPolicy);
  await assert.rejects(client.previewSourceTest(sourceRequest), "accepted Intent cannot bypass offline privacy");
  const privacy = await client.privacy({ root: project.root });
  const privacyCommand = { root: project.root, expectedRevision: privacy.revision, networkPolicy: "approved-providers", egressConsentToken: "acknowledge-egress-preview-v1", remoteModelApproval: privacy.remoteModelApproval, telemetryMode: privacy.telemetryMode, logRetentionDays: privacy.logRetentionDays, documentRetention: privacy.documentRetention, cacheRetentionDays: privacy.cacheRetentionDays };
  const permittedPrivacy = await client.updatePrivacy(privacyCommand);
  const preview = await client.previewSourceTest(sourceRequest);
  // Decoder deliberately creates null-prototype records. Compare exact wire
  // content without requiring JavaScript prototype identity across the boundary.
  assert.deepEqual(JSON.parse(JSON.stringify(preview.request)), sourceRequest.request);
  assert.equal(preview.intentSha256, accepted.revisionContentHash);
  assert.equal((await client.recentSourceRequests({ root: project.root })).items.length, 0);
  assert.equal(await client.inspectSourceRequest({ root: project.root, previewId: preview.previewId, recordOffset: 0 }), null, "a local preview alone is not a submitted job");
  await client.updatePrivacy({ ...privacyCommand, expectedRevision: permittedPrivacy.revision, networkPolicy: "offline", egressConsentToken: null });
  await assert.rejects(client.previewSourceTest(sourceRequest), "revoked privacy must deny another preview");
  await client.closeProject({ root: project.root });
  assert.equal((await exchange(command)).kind, "error", "closed project cannot access private configuration");
  assert.equal(publicRequests.some((request) => request.path.includes("/confirmations")), false);
  result = { status: "passed", scope: "Native supervisor, normal Core, isolated Windows DPAPI vault and SQLCipher project; no UI or provider-network proof", freshMissing: true, privateSave: true, restartPersistence: true, staleWriterDenied: true, currentWriterReplaces: true, wrongProjectDenied: true, closedProjectDenied: true, rendererPrivateRoutesDenied: true, ordinaryIntentImpactDraftAcceptance: true, draftAndOfflineDenial: true, exactLocalPreview: true, revokedPrivacyDenial: true, noProviderConfirmation: true };
} finally {
  harness.stdin.end();
  const code = await exit; clearTimeout(deadline); reader.close();
  assert.equal(code, 0, "native harness must exit cleanly");
}
const forbidden = Buffer.from("synthetic-native@example.invalid");
assert.equal(Buffer.from(output.join("\n") + diagnostics + JSON.stringify(publicRequests)).includes(forbidden), false, "private input must not appear in public requests or diagnostic/output projection");
async function checkProtected(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) await checkProtected(target);
    else assert.equal((await readFile(target)).includes(forbidden), false, "retained fixture bytes must not contain plaintext private configuration");
  }
}
await checkProtected(fixture);
result.noPlaintextInRetainedFilesOrPublicOutputs = true;
result.fixture = path.relative(repo, fixture).replaceAll("\\", "/");
const reportIndex = process.argv.indexOf("--report");
if (reportIndex !== -1) await writeFile(path.resolve(process.argv[reportIndex + 1]), `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result));
