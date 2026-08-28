#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "model-task.schema.json");
const templates = {
  typescript: resolve(root, "model-task.template.ts.txt"),
  python: resolve(root, "model-task.template.py.txt"),
};
const outputs = {
  typescript: resolve(root, "generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/model_gateway_contracts.py"),
};

const canonicalText = (value) => value.toString("utf8").replace(/\r\n?/g, "\n");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const schemaText = canonicalText(readFileSync(schemaPath));
const schema = JSON.parse(schemaText);
const assert = (condition, message) => {
  if (!condition) throw new Error(`model gateway contract source invalid: ${message}`);
};

assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(Array.isArray(schema.oneOf) && schema.oneOf.length === 2, "task/result root union");
assert(typeof schema.$defs === "object" && schema.$defs !== null, "schema definitions");
assert(schema.$defs.ModelTaskSpec?.properties?.documentType?.const === "research-observatory-model-task", "task discriminator");
assert(schema.$defs.ModelResultEnvelope?.properties?.documentType?.const === "research-observatory-model-result", "result discriminator");
assert(JSON.stringify(schema.$defs.TaskKind?.enum) === JSON.stringify([
  "embedding",
  "reranking",
  "classification",
  "nli",
  "structured-extraction",
  "generation",
  "moderation",
  "tool-call",
]), "task-kind catalog");
assert(JSON.stringify(schema["x-research-observatory-semanticRules"]) === JSON.stringify([
  "task-input-kind-matches-task-kind",
  "reranking-top-k-within-candidate-count",
  "successful-result-output-kind-matches-task-kind",
  "successful-result-requires-selected-route-and-accepted-validation",
  "non-success-result-carries-no-output",
  "reported-token-total-equals-input-plus-output",
  "reported-usage-within-task-bounds",
  "successful-result-within-task-deadline",
  "validation-state-and-output-hash-consistent",
  "supplied-citations-close-over-task-input-references",
  "required-citations-are-supplied",
  "citation-status-matches-task-requirement",
  "pinned-execution-route-matches-result-route",
  "indexed-output-closes-over-task-inputs",
  "unsupported-required-features-fail-explicitly",
]), "semantic-rule catalog");

const replacements = {
  "@@SCHEMA_SHA256@@": sha256(Buffer.from(schemaText, "utf8")),
  "@@SCHEMA_JSON@@": JSON.stringify(schema, null, 2),
};
const render = (path) => {
  let value = canonicalText(readFileSync(path));
  for (const [token, replacement] of Object.entries(replacements)) value = value.replaceAll(token, replacement);
  assert(!value.includes("@@"), `unresolved template token in ${path}`);
  return value;
};

const check = process.argv.includes("--check");
let changed = false;
for (const language of ["typescript", "python"]) {
  const expected = render(templates[language]);
  let actual = null;
  try {
    actual = canonicalText(readFileSync(outputs[language]));
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (actual === expected) continue;
  if (check) throw new Error(`${outputs[language].slice(repo.length + 1)} is stale; run node packages/contracts/model-gateway/generate.mjs`);
  writeFileSync(outputs[language], expected, "utf8");
  changed = true;
}

console.log(changed ? "Model gateway contracts: UPDATED" : "Model gateway contracts: PASS");
