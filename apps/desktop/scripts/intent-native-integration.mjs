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
let dropNextAcceptanceResponse = false;
const transport = async (request) => {
  observed.push({
    method: request.method,
    path: request.path,
    body: request.body,
    idempotencyKey: request.idempotencyKey,
  });
  const result = await exchange(request);
  if (result.kind !== "response") throw new Error(result.code ?? "native supervisor rejected request");
  if (dropNextAcceptanceResponse && request.path === "/projects/intent/acceptances") {
    dropNextAcceptanceResponse = false;
    throw new Error("SIMULATED_ACCEPTANCE_RESPONSE_LOSS");
  }
  return result.response;
};
const client = createCoreApiClient(transport);
let project;
let accepted;
let policy;
let invalidRouteDenial;
let persistenceInspection;

try {
  const ready = await nextMessage();
  if (ready.kind !== "ready") throw new Error("native supervisor harness did not become ready");
  project = await client.createProject({
    parentDirectory,
    directoryName: "intent-native",
    displayName: "Intent native integration",
    primaryUseCase: "theory-synthesis",
    researchObjective: "Explain how evidence-first scholarly workflows preserve researcher authority.",
  });
  const root = project.root;
  await client.openProject({ root });
  const initialWorkspace = await client.intent({ root });
  if (initialWorkspace.current?.revision !== 1
    || initialWorkspace.current.primaryUseCase !== "theory-synthesis") {
    throw new Error("new project did not restore its atomic initial intent and workflow selection");
  }

  const impact = {
    root,
    expectedRevision: 1,
    primaryUseCase: "systematic-review",
    sourceKinds: ["peer-reviewed-article", "conference-paper"],
    evidenceTypes: ["empirical-study", "theoretical-work"],
    languageCodes: ["en"],
    startYear: 2015,
    endYear: 2026,
    includePrivateReports: false,
    noveltyStandard: "theoretical",
    autonomyLevel: "suggest",
    stoppingConditions: ["coverage-threshold"],
  };
  const preview = await client.previewIntent(impact);
  const draft = await client.saveIntentDraft({
    ...impact,
    researchObjective: "Explain how evidence-first scholarly workflows preserve researcher authority.",
    contributionIntent: "Develop a bounded conceptual synthesis.",
    phenomenon: "Evidence-first scholarly reasoning",
    unitOfAnalysis: "Scholarly workflow",
    levelOfAnalysis: "Conceptual system",
    noveltyRationale: "Compare explicit authority boundaries across workflow stages.",
    revisionRationale: "Create the initial decision-complete intent.",
    impactAcknowledgement: preview.acknowledgementToken,
  }, "0123456789abcdef0123456789abcdef");
  if (!draft.canRequestAcceptance || draft.revision !== 2) {
    throw new Error("persisted draft is not decision-complete revision 2");
  }

  const restarted = await exchange({ control: "restart" });
  if (restarted.kind !== "restarted") throw new Error("native supervisor did not restart");
  await client.openProject({ root });
  const restored = await client.intent({ root });
  if (restored.current?.revisionContentHash !== draft.revisionContentHash) {
    throw new Error("supervised Core did not restore the exact SQLite-backed draft");
  }

  const acceptanceCommand = {
    root,
    expectedRevision: draft.revision,
    expectedRevisionContentHash: draft.revisionContentHash,
    confirmed: true,
    decisionRationale: "This decision-complete intent governs the bounded integration check.",
  };
  const acceptanceKey = "abcdef0123456789abcdef0123456789";
  dropNextAcceptanceResponse = true;
  let ambiguousAcceptance = false;
  try {
    await client.acceptIntent(acceptanceCommand, acceptanceKey);
  } catch (error) {
    if (error instanceof Error && error.message === "SIMULATED_ACCEPTANCE_RESPONSE_LOSS") {
      ambiguousAcceptance = true;
    } else {
      throw error;
    }
  }
  if (!ambiguousAcceptance) throw new Error("acceptance response loss was not observed");

  const acceptanceRestart = await exchange({ control: "restart" });
  if (acceptanceRestart.kind !== "restarted") {
    throw new Error("native supervisor did not restart after ambiguous acceptance");
  }
  await client.openProject({ root });
  accepted = await client.acceptIntent(acceptanceCommand, acceptanceKey);
  if (accepted.status !== "accepted" || accepted.revision !== 3) {
    throw new Error("same-key acceptance reconciliation did not return the persisted revision");
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
  const invalidRouteRequest = {
    method: "POST",
    path: "/projects/intent/unapproved",
    body: JSON.stringify({ root }),
    ifMatch: null,
    idempotencyKey: null,
  };
  observed.push(invalidRouteRequest);
  invalidRouteDenial = await exchange(invalidRouteRequest);
  if (invalidRouteDenial.kind !== "error" || invalidRouteDenial.code !== "RO-CORE-API-REQUEST-INVALID") {
    throw new Error("native supervisor did not fail closed for an unapproved intent route");
  }
  await client.closeProject({ root });
  persistenceInspection = JSON.parse(execFileSync(
    basePython,
    [
      "-m", "native_integration_sidecar",
      "--profile-vault-root", vaultRoot,
      "--inspect-project-root", root,
      "--project-id", project.projectId,
    ],
    {
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: pythonPath },
    },
  ));
  const expectedEventCounts = {
    "intent.draft.saved": 2,
    "intent.accepted": 1,
    "intent.policy.evaluated": 1,
    "workflow.profile.activated": 1,
  };
  if (persistenceInspection.revisionRecords !== 3
    || Object.entries(expectedEventCounts).some(([eventType, count]) => (
      persistenceInspection.provenanceEvents?.[eventType]?.count !== count
      || persistenceInspection.provenanceEvents[eventType].actorBound !== true
    ))) {
    throw new Error("protected SQLite revision/provenance inspection did not match the vertical path");
  }
  await client.deleteProject({ root, confirmation: `delete:${project.projectId}` });
} finally {
  harness.stdin.end();
  const exitCode = await exit;
  lines.close();
  await rm(integrationRoot, { recursive: true, force: true });
  if (exitCode !== 0) throw new Error(`native supervisor harness failed (${exitCode}): ${stderr}`);
}

const acceptanceRequests = observed.filter(
  (request) => request.path === "/projects/intent/acceptances",
);
if (acceptanceRequests.length !== 2
  || !acceptanceRequests.every(
    (request) => request.idempotencyKey === "abcdef0123456789abcdef0123456789",
  )
  || new Set(acceptanceRequests.map((request) => request.body)).size !== 1) {
  throw new Error("ambiguous acceptance did not replay one byte-equivalent request with the same key");
}

const report = {
  schemaVersion: "1.0",
  documentType: "intent-native-integration-report",
  status: "passed",
  projectRevision: accepted.revision,
  policyOutcome: policy.outcome,
  routes: observed.map((request) => request.path),
  acceptanceReconciliation: {
    simulatedResponseLoss: true,
    attempts: acceptanceRequests.length,
    sameKey: true,
    byteEquivalentRequest: true,
  },
  invalidRouteDenial: invalidRouteDenial.code,
  persistenceInspection,
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
