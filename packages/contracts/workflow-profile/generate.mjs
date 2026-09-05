#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "workflow-profile.schema.json");
// Presentation versions may change without rewriting persisted scholarly meaning.
// Fixed approved pins below remain authority, not the adjacent provenance record.
const workflowCatalogPath = resolve(root, "source/academic-minimal-1.5/WORKFLOW_CATALOG.json");
const pageContractsPath = resolve(root, "source/academic-minimal-1.5/CAPABILITY_COVERAGE.json");
const expectedWorkflowCatalogSha256 = "2f9f27334e38e090088551433ff5f156257f02f8fd0545a5c735fed8762c39ca";
const expectedPageContractsSha256 = "d0a86f107ac288a04ab47e5126f9a6cd2b82ce5c5d370e6d2963c76ae04d971d";
const canonicalText = (value) => value.toString("utf8").replace(/\r\n?/g, "\n");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const stableJson = (value) => {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
};
const pythonBase64Literal = (value) => {
  const encoded = Buffer.from(JSON.stringify(value), "utf8").toString("base64");
  const chunks = encoded.match(/.{1,88}/g) ?? [];
  return chunks.map((chunk) => JSON.stringify(chunk)).join("\n        ");
};
const assert = (condition, message) => {
  if (!condition) throw new Error(`workflow profile contract source invalid: ${message}`);
};

const schemaText = canonicalText(readFileSync(schemaPath));
const schema = JSON.parse(schemaText);
const schemaSha256 = sha256(schemaText);
const rawWorkflowCatalog = canonicalText(readFileSync(workflowCatalogPath));
const workflowCatalog = JSON.parse(rawWorkflowCatalog);
const rawPageContracts = canonicalText(readFileSync(pageContractsPath));
const pageContracts = JSON.parse(rawPageContracts);
assert(sha256(rawWorkflowCatalog) === expectedWorkflowCatalogSha256, "governed workflow catalog hash");
assert(sha256(rawPageContracts) === expectedPageContractsSha256, "governed page-contract catalog hash");
assert(workflowCatalog.reference_id === "RO-UI-ACADEMIC-MINIMAL-1.5", "governed reference ID");
assert(workflowCatalog.version === "1.5", "governed reference version");
assert(pageContracts.reference_id === workflowCatalog.reference_id, "page-contract reference ID");
assert(pageContracts.version === workflowCatalog.version, "page-contract reference version");
const expectedProfileIds = schema.$defs.WorkflowProfileId.enum;
assert(JSON.stringify(Object.keys(workflowCatalog.workflows)) === JSON.stringify(expectedProfileIds), "profile identity and order");
const registeredToolPageContractIds = Object.keys(pageContracts.page_contracts);
assert(registeredToolPageContractIds.length === pageContracts.product_page_count, "registered tool page-contract count");

const checkpoint = {
  state: "unknown",
  rationale: "No stage-specific checkpoint authority is declared by governed reference 1.5; execution must not infer completion authority.",
};
const profiles = Object.entries(workflowCatalog.workflows).map(([profileId, workflow]) => {
  const occurrences = new Map();
  const stages = workflow.steps.map((pageContractId, index) => {
    const slug = pageContractId.replace(/\.html$/, "");
    const occurrence = (occurrences.get(slug) ?? 0) + 1;
    occurrences.set(slug, occurrence);
    const page = pageContracts.page_contracts[pageContractId];
    assert(page !== undefined, `missing page contract ${pageContractId}`);
    return {
      stageKey: `${slug}-${occurrence}`,
      order: index + 1,
      pageContractId,
      role: "primary",
      optional: false,
      rationale: page.purpose,
      checkpoint,
    };
  });
  return {
    profileId,
    profileVersion: workflowCatalog.version,
    profileRevision: 1,
    sourceWorkflowHash: `sha256:${sha256(stableJson(workflow))}`,
    title: workflow.title,
    purpose: workflow.purpose,
    expectedOutputs: [workflow.output],
    cyclePolicy: workflow.cyclical ? "revisitable" : "linear",
    stages,
    supportingToolPolicy: {
      allRegisteredToolsAccessible: true,
      returnBehavior: "return-to-current-primary-stage",
    },
  };
});
const catalog = {
  schemaVersion: "1.0",
  documentType: "research-observatory-workflow-profile-catalog",
  contractVersion: "1.0.0",
  profileCatalogVersion: "1.0.0",
  governedReference: {
    referenceId: workflowCatalog.reference_id,
    referenceVersion: workflowCatalog.version,
    workflowCatalogHash: `sha256:${expectedWorkflowCatalogSha256}`,
    pageContractsHash: `sha256:${expectedPageContractsSha256}`,
  },
  registeredToolPageContractIds,
  profiles,
};
const profileCatalogHash = `sha256:${sha256(stableJson(catalog))}`;
const profileById = new Map(profiles.map((profile) => [profile.profileId, profile]));
const profileReference = (profileId) => {
  const profile = profileById.get(profileId);
  assert(profile !== undefined, `unknown fixture profile ${profileId}`);
  return {
    referenceId: workflowCatalog.reference_id,
    referenceVersion: workflowCatalog.version,
    workflowCatalogHash: `sha256:${expectedWorkflowCatalogSha256}`,
    pageContractsHash: `sha256:${expectedPageContractsSha256}`,
    profileCatalogVersion: catalog.profileCatalogVersion,
    profileCatalogHash,
    profileId: profile.profileId,
    profileVersion: profile.profileVersion,
    profileRevision: profile.profileRevision,
    sourceWorkflowHash: profile.sourceWorkflowHash,
  };
};
const actor = { actorType: "human", actorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d030" };
const researchIntent = {
  schemaVersion: "1.0",
  documentType: "research-observatory-research-intent-reference",
  contractVersion: "1.0.0",
  intentId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d020",
  revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d021",
  revision: 1,
  revisionContentHash: `sha256:${"1".repeat(64)}`,
};
const revisedResearchIntent = {
  ...researchIntent,
  revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d022",
  revision: 2,
  revisionContentHash: `sha256:${"2".repeat(64)}`,
};
const migrationAcceptance = {
  decisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d060",
  decisionContentHash: `sha256:${"d".repeat(64)}`,
  decision: "accepted",
  decidedAt: "2026-09-03T19:05:00Z",
  decidedBy: actor,
};
const migrationAcceptanceReference = {
  migrationId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d050",
  migrationContentHash: `sha256:${"e".repeat(64)}`,
  fromProfile: profileReference("systematic-review"),
  toProfile: profileReference("living-review"),
  priorResearchIntent: researchIntent,
  targetResearchIntent: revisedResearchIntent,
  acceptance: migrationAcceptance,
};
const initialSelection = {
  schemaVersion: "1.0",
  documentType: "research-observatory-project-workflow-selection",
  contractVersion: "1.0.0",
  selectionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d010",
  selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
  projectId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d001",
  revision: 1,
  revisionContentHash: `sha256:${"a".repeat(64)}`,
  createdAt: "2026-09-03T19:00:00Z",
  selectedBy: actor,
  researchIntent,
  profile: profileReference("systematic-review"),
  parentSelection: null,
  impactPreview: null,
  acceptedMigration: null,
};
const parentSelection = {
  selectionId: initialSelection.selectionId,
  selectionRevisionId: initialSelection.selectionRevisionId,
  revision: initialSelection.revision,
  revisionContentHash: initialSelection.revisionContentHash,
  researchIntent: initialSelection.researchIntent,
  profile: initialSelection.profile,
};
const changedSelection = {
  ...initialSelection,
  selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d012",
  revision: 2,
  revisionContentHash: `sha256:${"b".repeat(64)}`,
  createdAt: "2026-09-03T19:05:00Z",
  researchIntent: revisedResearchIntent,
  profile: profileReference("living-review"),
  parentSelection,
  impactPreview: {
    priorSelection: parentSelection,
    targetProfile: profileReference("living-review"),
    historyPolicy: "preserve",
    priorStageStates: [
      {
        stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d040",
        stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
        stageStateRevision: 1,
        stageStateRevisionContentHash: `sha256:${"c".repeat(64)}`,
        fromStageKey: "intent-contract-1",
        disposition: "retain",
        targetStageKey: "intent-contract-1",
        rationale: "The accepted intent stage remains applicable and its prior state remains immutable.",
      },
    ],
    summary: "Preview the move to living review while retaining the prior selection and stage-state history.",
  },
  acceptedMigration: migrationAcceptanceReference,
};
const stageState = {
  schemaVersion: "1.0",
  documentType: "research-observatory-workflow-stage-state",
  contractVersion: "1.0.0",
  stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d040",
  stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
  revision: 1,
  revisionContentHash: `sha256:${"c".repeat(64)}`,
  projectId: initialSelection.projectId,
  selection: {
    selectionId: initialSelection.selectionId,
    selectionRevisionId: initialSelection.selectionRevisionId,
    revision: initialSelection.revision,
    revisionContentHash: initialSelection.revisionContentHash,
  },
  profile: initialSelection.profile,
  stageKey: "intent-contract-1",
  pageContractId: "intent-contract.html",
  navigationRole: "primary",
  passNumber: 1,
  status: "current",
  completionEvidenceIds: [],
  attention: null,
  staleCauses: [],
  skipRationale: null,
  supportReturn: null,
  parentState: null,
  updatedAt: "2026-09-03T19:00:00Z",
  updatedBy: actor,
};
const fromProfile = profileById.get("systematic-review");
const toProfile = profileById.get("living-review");
const toStagesByPage = new Map(toProfile.stages.map((stage) => [stage.pageContractId, stage.stageKey]));
const migration = {
  schemaVersion: "1.0",
  documentType: "research-observatory-workflow-profile-migration",
  contractVersion: "1.0.0",
  ...migrationAcceptanceReference,
  createdAt: "2026-09-03T19:04:00Z",
  createdBy: actor,
  historyPolicy: "preserve",
  requiresHumanAcceptance: true,
  stageMappings: fromProfile.stages.map((stage) => {
    const targetStageKey = toStagesByPage.get(stage.pageContractId) ?? null;
    return {
      fromStageKey: stage.stageKey,
      disposition: targetStageKey === null ? "requires-review" : "retain",
      targetStageKey,
      rationale: targetStageKey === null
        ? "The target profile has no equivalent primary stage; retain history and require researcher review."
        : "The governed target profile retains the same page-contract stage; retain immutable prior history.",
    };
  }),
};

assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(schema.$defs.WorkflowProfileCatalog.properties.documentType.const === "research-observatory-workflow-profile-catalog", "catalog root");
assert(schema.$defs.ProjectWorkflowSelection.properties.documentType.const === "research-observatory-project-workflow-selection", "selection root");
assert(schema.$defs.WorkflowStageState.properties.documentType.const === "research-observatory-workflow-stage-state", "stage-state root");
assert(schema.$defs.WorkflowProfileMigration.properties.documentType.const === "research-observatory-workflow-profile-migration", "migration root");

const replacements = new Map([
  ["@@SCHEMA_SHA256@@", schemaSha256],
  ["@@SCHEMA_JSON@@", JSON.stringify(schema)],
  ["@@SCHEMA_JSON_BASE64@@", pythonBase64Literal(schema)],
  ["@@GOVERNED_WORKFLOW_CATALOG_SHA256@@", `sha256:${expectedWorkflowCatalogSha256}`],
  ["@@PROFILE_CATALOG_SHA256@@", profileCatalogHash],
  ["@@APPROVED_CATALOG_JSON@@", JSON.stringify(catalog)],
  ["@@APPROVED_CATALOG_JSON_BASE64@@", pythonBase64Literal(catalog)],
]);
const render = (templatePath) => {
  let output = canonicalText(readFileSync(templatePath));
  for (const [marker, value] of replacements) output = output.replaceAll(marker, value);
  assert(!output.includes("@@"), `${templatePath} retains a marker`);
  return output;
};
const jsonOutput = (value) => `${JSON.stringify(value, null, 2)}\n`;
const outputs = new Map([
  [resolve(root, "generated.ts"), render(resolve(root, "workflow-profile.template.ts.txt"))],
  [resolve(repo, "services/core-api/src/research_observatory_core/workflow_profile_contracts.py"), render(resolve(root, "workflow-profile.template.py.txt"))],
  [resolve(root, "fixtures/approved-workflow-profile-catalog.v1.json"), jsonOutput(catalog)],
  [resolve(root, "fixtures/valid-project-workflow-selection.v1.json"), jsonOutput(initialSelection)],
  [resolve(root, "fixtures/valid-project-workflow-selection-change.v1.json"), jsonOutput(changedSelection)],
  [resolve(root, "fixtures/valid-workflow-stage-state.v1.json"), jsonOutput(stageState)],
  [resolve(root, "fixtures/valid-workflow-profile-migration.v1.json"), jsonOutput(migration)],
]);

let drift = false;
for (const [path, output] of outputs) {
  if (process.argv.includes("--check")) {
    let current = "";
    try {
      current = canonicalText(readFileSync(path));
    } catch {
      drift = true;
      continue;
    }
    if (current !== output) drift = true;
  } else {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, output, "utf8");
  }
}
if (drift) {
  console.error("workflow profile generated contracts or fixtures are stale; run node packages/contracts/workflow-profile/generate.mjs");
  process.exit(1);
}
if (!process.argv.includes("--check")) console.log(`generated workflow profile contracts ${schemaSha256}`);
