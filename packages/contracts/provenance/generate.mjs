#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../../..");
const schemaPath = resolve(root, "provenance-event.schema.json");
const templates = {
  typescript: resolve(root, "provenance-event.template.ts.txt"),
  python: resolve(root, "provenance-event.template.py.txt"),
};
const outputs = {
  typescript: resolve(root, "generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/provenance_contracts.py"),
};
const canonicalText = (value) => value.toString("utf8").replace(/\r\n?/g, "\n");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const schemaText = canonicalText(readFileSync(schemaPath));
const schema = JSON.parse(schemaText);
const assert = (condition, message) => {
  if (!condition) throw new Error(`provenance contract source invalid: ${message}`);
};
const semanticRules = [
  "actor-and-agent-match", "event-project-and-subject-match", "subject-binds-exact-event-object",
  "activity-time-is-ordered", "event-time-matches-activity-end", "input-output-revisions-are-disjoint",
  "entity-references-are-unique", "identity-namespace-is-consistent", "entity-policy-does-not-weaken-event",
  "relations-close-over-event-objects", "relation-identities-and-facts-are-unique",
  "relation-roles-match-event-objects", "relation-outcome-matches-activity-status",
  "activity-agent-relation-is-complete", "input-use-relations-are-complete",
  "output-generation-relations-are-complete", "output-attribution-relations-are-complete",
  "known-event-type-matches-activity", "known-event-relations-match-operation",
  "known-event-shape-matches-operation", "causation-is-not-self",
];
const knownMap = {
  "org.research-observatory.source.acquired.v1": "source-acquisition",
  "org.research-observatory.document.parsed.v1": "parsing",
  "org.research-observatory.evidence.extracted.v1": "extraction",
  "org.research-observatory.evidence.verified.v1": "verification",
  "org.research-observatory.decision.recorded.v1": "decision",
  "org.research-observatory.synthesis.produced.v1": "synthesis",
  "org.research-observatory.export.created.v1": "export",
  "org.research-observatory.entity.invalidated.v1": "invalidation",
};
const relationPolicy = {
  roles: {
    used: "input",
    wasGeneratedBy: "output",
    wasAssociatedWith: "activity-agent",
    wasDerivedFrom: "output-to-input",
    wasInvalidatedBy: "input",
    wasAttributedTo: "output-agent",
  },
  knownNonSuccessful: {
    "source-acquisition": {
      failed: ["wasAssociatedWith"],
      cancelled: ["wasAssociatedWith"],
      denied: ["wasAssociatedWith"],
    },
    other: {
      failed: ["used", "wasAssociatedWith"],
      cancelled: ["used", "wasAssociatedWith"],
      denied: ["wasAssociatedWith"],
    },
  },
  knownSucceeded: {
    "source-acquisition": ["wasGeneratedBy", "wasAssociatedWith", "wasAttributedTo"],
    transformation: ["used", "wasGeneratedBy", "wasAssociatedWith", "wasDerivedFrom", "wasAttributedTo"],
    invalidation: ["wasAssociatedWith", "wasInvalidatedBy"],
  },
};
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(schema.$ref === "#/$defs/ProvenanceEvent", "event root");
assert(schema.$defs?.ProvenanceEvent?.properties?.specversion?.const === "1.0", "CloudEvents version");
assert(JSON.stringify(schema["x-research-observatory-semanticRules"]) === JSON.stringify(semanticRules), "semantic rules");
assert(JSON.stringify(schema["x-research-observatory-knownEventActivityMap"]) === JSON.stringify(knownMap), "known event map");
assert(JSON.stringify(schema["x-research-observatory-relationPolicy"]) === JSON.stringify(relationPolicy), "relation policy");

const replacements = {
  "@@SCHEMA_SHA256@@": sha256(Buffer.from(schemaText, "utf8")),
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
  if (check) throw new Error(`${outputs[language].slice(repo.length + 1)} is stale; run node packages/contracts/provenance/generate.mjs`);
  writeFileSync(outputs[language], expected, "utf8");
  changed = true;
}
console.log(changed ? "Provenance contracts: UPDATED" : "Provenance contracts: PASS");
