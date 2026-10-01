#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "corpus-membership.schema.json");
const schemaBytes = readFileSync(schemaPath);
const schema = JSON.parse(schemaBytes.toString("utf8"));
const sha256 = createHash("sha256").update(schemaBytes).digest("hex");
const assert = (condition, reason) => {
  if (!condition) throw new Error(`corpus contract source invalid: ${reason}`);
};
const documents = {
  CorpusItemRevision: "research-observatory-corpus-item-revision",
  DiscoveryPath: "research-observatory-discovery-path",
  CorpusDecision: "research-observatory-corpus-decision",
};
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "draft");
assert(JSON.stringify(schema.oneOf) === JSON.stringify(Object.keys(documents).map((name) => ({ $ref: `#/$defs/${name}` }))), "document union");
const semanticRules = [
  "identity-and-revision-distinct", "initial-candidate-pending-with-unknown-availability-no-duplicate-or-decision",
  "later-revision-requires-decision",
  "discovery-path-ids-sorted-unique", "discovery-kind-has-exact-typed-source",
  "discovery-edge-direction-time-and-predecessor",
  "decision-identities-and-values-distinct", "decision-evidence-sorted-unique",
  "work-target-only-for-work-reference", "decision-time-is-real-canonical-utc-milliseconds",
];
assert(JSON.stringify(schema["x-research-observatory-semanticRules"]) === JSON.stringify(semanticRules), "semantic rules");
const supportedKeywords = new Set([
  "$schema", "$id", "title", "description", "x-research-observatory-semanticRules",
  "x-research-observatory-membershipLifecycle", "$defs", "$ref", "type", "pattern", "anyOf", "oneOf",
  "enum", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "items",
  "required", "properties", "additionalProperties", "const",
]);
function supportedNode(node) {
  assert(node !== null && typeof node === "object" && !Array.isArray(node), "schema object");
  for (const key of Object.keys(node)) assert(supportedKeywords.has(key), `unsupported schema keyword ${key}`);
  for (const key of ["anyOf", "oneOf"]) if (Array.isArray(node[key])) node[key].forEach(supportedNode);
  if (node.items) supportedNode(node.items);
  for (const key of ["$defs", "properties"]) if (node[key]) Object.values(node[key]).forEach(supportedNode);
}
supportedNode(schema);
const lifecycleBinding = schema["x-research-observatory-membershipLifecycle"];
const lifecyclePath = "packages/contracts/domain/domain-lifecycle.v1.json";
const lifecycleBytes = readFileSync(resolve(repo, lifecyclePath));
const lifecycle = JSON.parse(lifecycleBytes.toString("utf8"));
const corpusLifecycle = lifecycle.subjects?.find((subject) => subject.subjectKind === "corpus-item");
assert(lifecycleBinding?.sourcePath === lifecyclePath
  && lifecycleBinding.sourceSha256 === createHash("sha256").update(lifecycleBytes).digest("hex")
  && lifecycleBinding.profileVersion === lifecycle.profileVersion
  && lifecycleBinding.subjectKind === "corpus-item"
  && lifecycleBinding.initialState === corpusLifecycle?.initialState, "frozen corpus lifecycle binding");
assert(JSON.stringify(lifecycleBinding.terminalStates) === JSON.stringify(corpusLifecycle.states
  .filter((state) => state.terminal).map((state) => state.id)), "terminal lifecycle states");
assert(JSON.stringify(schema.$defs.Membership.enum) === JSON.stringify(corpusLifecycle.states.map((state) => state.id)),
  "corpus membership enum matches frozen lifecycle");
assert(JSON.stringify(lifecycleBinding.transitions) === JSON.stringify(corpusLifecycle.transitions.map((transition) => ({
  command: transition.command, from: transition.from, to: transition.to,
}))), "corpus transitions match frozen lifecycle");
for (const [name, documentType] of Object.entries(documents)) {
  const node = schema.$defs?.[name];
  assert(node?.type === "object" && node.additionalProperties === false, `${name} strict object`);
  assert(node.properties?.schemaVersion?.const === "1.0"
    && node.properties?.contractVersion?.const === "1.0.0"
    && node.properties?.documentType?.const === documentType, `${name} versioned envelope`);
  assert(JSON.stringify(node.required) === JSON.stringify(Object.keys(node.properties)), `${name} exact required fields`);
}

function tsType(node) {
  if (node.$ref) return node.$ref.slice("#/$defs/".length);
  if (Object.hasOwn(node, "const")) return JSON.stringify(node.const);
  if (Array.isArray(node.enum)) return node.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (Array.isArray(node.anyOf)) return node.anyOf.map(tsType).join(" | ");
  if (node.type === "array") return `ReadonlyArray<${tsType(node.items)}>`;
  if (node.type === "integer") return "number";
  if (node.type === "null") return "null";
  return "string";
}

const types = Object.entries(schema.$defs).map(([name, node]) => {
  if (node.type !== "object") return `export type ${name} = ${tsType(node)};`;
  return `export interface ${name} {\n${Object.entries(node.properties).map(([field, fieldSchema]) =>
    `  readonly ${field}: ${tsType(fieldSchema)};`).join("\n")}\n}`;
}).join("\n\n");
const templatePaths = {
  typescript: resolve(root, "corpus.template.ts.txt"),
  python: resolve(root, "corpus.template.py.txt"),
};
const outputs = {
  typescript: resolve(root, "generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/corpus_contracts.py"),
};
const replacements = {
  "@@SCHEMA_SHA256@@": sha256,
  "@@SCHEMA_JSON@@": JSON.stringify(schema, null, 2),
  "@@SCHEMA_JSON_STRING@@": JSON.stringify(JSON.stringify(schema)),
  "@@TYPES@@": types,
};
const render = (templatePath) => {
  let rendered = readFileSync(templatePath, "utf8").replace(/\r\n?/g, "\n");
  for (const [token, replacement] of Object.entries(replacements)) rendered = rendered.replaceAll(token, replacement);
  assert(!rendered.includes("@@"), `unresolved token in ${templatePath}`);
  return rendered;
};
const check = process.argv.includes("--check");
let changed = false;
for (const [language, outputPath] of Object.entries(outputs)) {
  const expected = render(templatePaths[language]);
  let current = null;
  try { current = readFileSync(outputPath, "utf8").replace(/\r\n?/g, "\n"); }
  catch (error) { if (error?.code !== "ENOENT") throw error; }
  if (current === expected) continue;
  if (check) throw new Error(`${outputPath.slice(repo.length + 1)} is stale; run node packages/contracts/corpus/generate.mjs`);
  writeFileSync(outputPath, expected, "utf8");
  changed = true;
}
console.log(changed ? "Corpus contracts: UPDATED" : "Corpus contracts: PASS");
