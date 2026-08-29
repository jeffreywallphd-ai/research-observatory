import { execFileSync, spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "../..");

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const reportPath = argument("--report");
const generatedUrl = pathToFileURL(path.join(repoRoot, "packages", "contracts", "core-api", "generated.ts"));
const { createCoreApiClient } = await import(generatedUrl.href);
const temporaryRoot = path.join(repoRoot, "artifacts", "tmp");
await mkdir(temporaryRoot, { recursive: true });
const integrationRoot = await mkdtemp(path.join(temporaryRoot, "intent-native-integration-"));
const vaultRoot = path.join(integrationRoot, "vault");
const parentDirectory = path.join(integrationRoot, "projects");
await mkdir(vaultRoot);
await mkdir(parentDirectory);
const virtualEnvironmentPython = path.join(repoRoot, ".venv", "Scripts", "python.exe");
const basePython = execFileSync(
  virtualEnvironmentPython,
  ["-c", "import sys; print(sys._base_executable)"],
  { encoding: "utf8" },
).trim();
const pythonPath = [
  path.join(repoRoot, "tests", "service", "fixtures"),
  path.join(repoRoot, "services", "core-api", "src"),
  path.join(repoRoot, ".venv", "Lib", "site-packages"),
].join(path.delimiter);

const harness = spawn(
  "cargo",
  [
    "run", "--quiet", "--locked", "--features", "integration-harness",
    "--example", "supervised_core_harness", "--",
    basePython,
    repoRoot,
    pythonPath,
    vaultRoot,
  ],
  { cwd: path.join(appRoot, "src-tauri"), stdio: ["pipe", "pipe", "pipe"] },
);
const lines = createInterface({ input: harness.stdout });
const pending = [];
let stderr = "";
harness.stderr.setEncoding("utf8");
harness.stderr.on("data", (chunk) => { stderr += chunk; });
lines.on("line", (line) => pending.shift()?.resolve(JSON.parse(line)));
const exit = new Promise((resolve) => {
  harness.on("close", (code) => {
    const failure = new Error(`native supervisor harness closed (${code}): ${stderr}`);
    while (pending.length) pending.shift().reject(failure);
    resolve(code);
  });
});
harness.on("error", (error) => {
  while (pending.length) pending.shift().reject(error);
});

function nextMessage() {
  return new Promise((resolve, reject) => pending.push({ resolve, reject }));
}

async function exchange(value) {
  const message = nextMessage();
  harness.stdin.write(`${JSON.stringify(value)}\n`);
  return await message;
}

const observed = [];
const transport = async (request) => {
  observed.push({ method: request.method, path: request.path, idempotencyKey: request.idempotencyKey });
  const result = await exchange(request);
  if (result.kind !== "response") throw new Error(result.code ?? "native supervisor rejected request");
  return result.response;
};
const client = createCoreApiClient(transport);
let project;
let accepted;
let policy;

try {
  const ready = await nextMessage();
  if (ready.kind !== "ready") throw new Error("native supervisor harness did not become ready");
  project = await client.createProject({
    parentDirectory,
    directoryName: "intent-native",
    displayName: "Intent native integration",
    templateId: "theory-synthesis",
  });
  const root = project.root;
  await client.openProject({ root });
  const emptyWorkspace = await client.intent({ root });
  if (emptyWorkspace.current !== null) throw new Error("new project unexpectedly has an intent");

  const impact = {
    root,
    expectedRevision: 0,
    primaryUseCase: "theory-synthesis",
    sourceKinds: ["peer-reviewed-article", "conference-paper"],
    languageCodes: ["en"],
    startYear: 2015,
    endYear: 2026,
    includePrivateReports: false,
    noveltyStandard: "theoretical",
  };
  const preview = await client.previewIntent(impact);
  const draft = await client.saveIntentDraft({
    ...impact,
    researchObjective: "Explain how evidence-first scholarly workflows preserve researcher authority.",
    contributionIntent: "Develop a bounded conceptual synthesis.",
    phenomenon: "Evidence-first scholarly reasoning",
    unitOfAnalysis: "Scholarly workflow",
    levelOfAnalysis: "Conceptual system",
    evidenceTypes: ["empirical-study", "theoretical-work"],
    noveltyRationale: "Compare explicit authority boundaries across workflow stages.",
    autonomyLevel: "suggest",
    stoppingConditions: ["interpretive-saturation"],
    revisionRationale: "Create the initial decision-complete intent.",
    impactAcknowledgement: preview.acknowledgementToken,
  }, "0123456789abcdef0123456789abcdef");
  if (!draft.canRequestAcceptance || draft.revision !== 1) {
    throw new Error("persisted draft is not decision-complete revision 1");
  }

  const restarted = await exchange({ control: "restart" });
  if (restarted.kind !== "restarted") throw new Error("native supervisor did not restart");
  await client.openProject({ root });
  const restored = await client.intent({ root });
  if (restored.current?.revisionContentHash !== draft.revisionContentHash) {
    throw new Error("supervised Core did not restore the exact SQLite-backed draft");
  }

  accepted = await client.acceptIntent({
    root,
    expectedRevision: draft.revision,
    expectedRevisionContentHash: draft.revisionContentHash,
    confirmed: true,
    decisionRationale: "This decision-complete intent governs the bounded integration check.",
  }, "abcdef0123456789abcdef0123456789");
  if (accepted.status !== "accepted" || accepted.revision !== 2) {
    throw new Error("accepted governing revision was not persisted");
  }
  policy = await client.evaluateIntentPolicy({
    root,
    action: "execute-approved-query",
    subjectType: "system",
    stoppingCondition: null,
  });
  if (policy.governingIntent?.revisionContentHash !== accepted.revisionContentHash) {
    throw new Error("policy decision is not bound to the accepted revision");
  }
  await client.closeProject({ root });
  await client.deleteProject({ root, confirmation: `delete:${project.projectId}` });
} finally {
  harness.stdin.end();
  const exitCode = await exit;
  lines.close();
  await rm(integrationRoot, { recursive: true, force: true });
  if (exitCode !== 0) throw new Error(`native supervisor harness failed (${exitCode}): ${stderr}`);
}

const report = {
  schemaVersion: "1.0",
  documentType: "intent-native-integration-report",
  status: "passed",
  projectRevision: accepted.revision,
  policyOutcome: policy.outcome,
  routes: observed.map((request) => request.path),
  idempotencyKeys: observed
    .filter((request) => request.idempotencyKey !== null)
    .map((request) => ({ path: request.path, canonical: /^[0-9a-f]{32}$/.test(request.idempotencyKey) })),
};
if (reportPath) {
  const target = path.resolve(reportPath);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(report, null, 2)}\n`, "utf8");
}
console.log(JSON.stringify(report));
