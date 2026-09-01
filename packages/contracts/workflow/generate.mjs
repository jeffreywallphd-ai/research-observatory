#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "workflow-contract.schema.json");
const templates = {
  typescript: resolve(root, "workflow-contract.template.ts.txt"),
  python: resolve(root, "workflow-contract.template.py.txt"),
};
const outputs = {
  typescript: resolve(root, "generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/workflow_contracts.py"),
};
const canonicalText = (value) => value.toString("utf8").replace(/\r\n?/g, "\n");
const schemaText = canonicalText(readFileSync(schemaPath));
const schema = JSON.parse(schemaText);
const schemaSha256 = createHash("sha256").update(schemaText).digest("hex");
const assert = (condition, message) => {
  if (!condition) throw new Error(`workflow contract source invalid: ${message}`);
};

const expectedRules = [
  "definition-step-keys-are-unique",
  "definition-dependencies-close-and-are-acyclic",
  "step-shape-matches-kind",
  "progress-shape-is-consistent",
  "snapshot-binds-exact-definition",
  "references-close-over-snapshot",
  "identities-are-unique",
  "history-sequence-is-contiguous",
  "history-transition-is-allowed",
  "history-reconstructs-current-state",
  "attempt-progress-is-monotonic",
  "attempt-numbers-are-contiguous",
  "job-has-at-most-one-succeeded-attempt",
  "job-idempotency-binds-command-fingerprint",
  "checkpoint-order-and-owner-are-consistent",
  "succeeded-output-artifacts-are-committed",
  "unsuccessful-attempt-has-no-accepted-output",
  "completed-human-task-binds-decision",
  "human-decision-is-audit-bound",
  "security-lock-does-not-auto-resume",
];
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(schema.$defs?.WorkflowDefinition?.properties?.documentType?.const === "research-observatory-workflow-definition", "definition root");
assert(schema.$defs?.WorkflowSnapshot?.properties?.documentType?.const === "research-observatory-workflow-snapshot", "snapshot root");
assert(schema.$defs?.LegacyOperationBridge?.properties?.documentType?.const === "research-observatory-legacy-operation-bridge", "legacy bridge root");
assert(JSON.stringify(schema["x-research-observatory-semanticRules"]) === JSON.stringify(expectedRules), "semantic rule inventory");

const replacements = new Map([
  ["@@SCHEMA_SHA256@@", schemaSha256],
  ["@@SCHEMA_JSON@@", JSON.stringify(schemaText)],
  ["@@SCHEMA_TEXT@@", schemaText],
]);
const render = (templatePath) => {
  let output = canonicalText(readFileSync(templatePath));
  for (const [marker, value] of replacements) output = output.replaceAll(marker, value);
  assert(!output.includes("@@"), `${templatePath} retains a marker`);
  return output;
};

let drift = false;
for (const key of Object.keys(outputs)) {
  const output = render(templates[key]);
  if (process.argv.includes("--check")) {
    let current = "";
    try {
      current = canonicalText(readFileSync(outputs[key]));
    } catch {
      drift = true;
      continue;
    }
    if (current !== output) drift = true;
  } else {
    writeFileSync(outputs[key], output, "utf8");
  }
}
if (drift) {
  console.error("workflow generated contracts are stale; run node packages/contracts/workflow/generate.mjs");
  process.exit(1);
}
if (!process.argv.includes("--check")) console.log(`generated workflow contracts ${schemaSha256}`);
