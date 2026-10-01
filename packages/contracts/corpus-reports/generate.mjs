#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const bytes = readFileSync(resolve(root, "corpus-report.schema.json"));
const schema = JSON.parse(bytes.toString("utf8"));
const hash = createHash("sha256").update(bytes).digest("hex");
const assert = (condition, reason) => {
  if (!condition) throw new Error(`corpus report schema invalid: ${reason}`);
};
const documentNames = ["CorpusReportSnapshot", "CorpusReportMember", "CorpusReportDrillPage"];
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "draft");
assert(JSON.stringify(schema.oneOf) === JSON.stringify(documentNames.map((name) => ({ $ref: `#/$defs/${name}` }))),
  "document union");
for (const name of documentNames) {
  const properties = schema.$defs[name]?.properties;
  assert(properties?.schemaVersion?.const === "1.0" && properties?.contractVersion?.const === "1.0.0",
    `${name} envelope`);
}
const allowed = new Set([
  "$schema", "$id", "title", "description", "x-research-observatory-semanticRules",
  "oneOf", "$defs", "$ref", "type", "pattern", "enum", "anyOf", "const", "required",
  "properties", "additionalProperties", "minimum", "maximum", "minLength", "maxLength",
  "minItems", "maxItems", "items",
]);
function supported(node) {
  assert(node !== null && typeof node === "object" && !Array.isArray(node), "schema node");
  for (const key of Object.keys(node)) assert(allowed.has(key), `unsupported keyword ${key}`);
  for (const key of ["anyOf", "oneOf"]) if (Array.isArray(node[key])) node[key].forEach(supported);
  if (node.items) supported(node.items);
  for (const key of ["$defs", "properties"]) if (node[key]) Object.values(node[key]).forEach(supported);
}
supported(schema);
function tsType(node) {
  if (node.$ref) return node.$ref.slice(8);
  if (Object.hasOwn(node, "const")) return JSON.stringify(node.const);
  if (Array.isArray(node.enum)) return node.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (Array.isArray(node.anyOf)) return node.anyOf.map(tsType).join(" | ");
  if (node.type === "array") return `ReadonlyArray<${tsType(node.items)}>`;
  if (node.type === "integer") return "number";
  if (node.type === "boolean") return "boolean";
  if (node.type === "null") return "null";
  return "string";
}
const types = Object.entries(schema.$defs).map(([name, node]) => {
  if (node.type !== "object") return `export type ${name} = ${tsType(node)};`;
  return `export interface ${name} {\n${Object.entries(node.properties).map(([field, shape]) =>
    `  readonly ${field}: ${tsType(shape)};`).join("\n")}\n}`;
}).join("\n\n");
const template = readFileSync(resolve(root, "corpus-report.template.ts.txt"), "utf8").replace(/\r\n?/g, "\n");
const expected = template.replaceAll("@@TYPES@@", types)
  .replaceAll("@@SCHEMA_SHA256@@", hash)
  .replaceAll("@@SCHEMA_JSON@@", JSON.stringify(schema, null, 2));
assert(!expected.includes("@@"), "unresolved template token");
const output = resolve(root, "generated.ts");
let current = null;
try { current = readFileSync(output, "utf8").replace(/\r\n?/g, "\n"); }
catch (error) { if (error?.code !== "ENOENT") throw error; }
if (current === expected) console.log("Corpus report contract: PASS");
else if (process.argv.includes("--check")) throw new Error("Corpus report generated.ts is stale");
else { writeFileSync(output, expected, "utf8"); console.log("Corpus report contract: UPDATED"); }
