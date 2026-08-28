#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "research-intent.schema.json");
const templates = {
  typescript: resolve(root, "research-intent.template.ts.txt"),
  python: resolve(root, "research-intent.template.py.txt"),
};
const outputs = {
  typescript: resolve(root, "generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/research_intent_contracts.py"),
};
const canonicalText = (value) => value.toString("utf8").replace(/\r\n?/g, "\n");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const schemaText = canonicalText(readFileSync(schemaPath));
const schema = JSON.parse(schemaText);
const assert = (condition, message) => {
  if (!condition) throw new Error(`research intent contract source invalid: ${message}`);
};
const semanticRules = [
  "revision-identities-are-distinct",
  "revision-lineage-is-immediate",
  "decision-status-is-consistent",
  "decision-not-before-created",
  "mode-requirements-match-epistemic-mode",
  "primary-use-case-matches-epistemic-mode",
  "accepted-revision-is-decision-complete",
  "intent-acceptance-is-human",
  "autonomy-retains-researcher-authority",
  "autonomy-actions-match-level",
  "stopping-rule-matches-epistemic-mode",
  "source-temporal-range-is-ordered",
  "egress-policy-is-consistent",
];
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(schema.$ref === "#/$defs/ResearchIntentRevision", "revision root");
assert(schema.$defs?.ResearchIntentRevision?.properties?.documentType?.const === "research-observatory-research-intent-revision", "revision discriminator");
assert(schema.$defs?.ResearchIntentReference?.properties?.documentType?.const === "research-observatory-research-intent-reference", "reference discriminator");
assert(JSON.stringify(schema["x-research-observatory-semanticRules"]) === JSON.stringify(semanticRules), "semantic-rule catalog");
assert(JSON.stringify(schema.$defs.ResearchIntentRevision.properties.epistemicMode.enum) === JSON.stringify(["systematic", "theory", "technical", "hermeneutic", "critical", "novelty", "empirical"]), "epistemic-mode catalog");

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
  if (check) throw new Error(`${outputs[language].slice(repo.length + 1)} is stale; run node packages/contracts/intent/generate.mjs`);
  writeFileSync(outputs[language], expected, "utf8");
  changed = true;
}
console.log(changed ? "Research intent contracts: UPDATED" : "Research intent contracts: PASS");
