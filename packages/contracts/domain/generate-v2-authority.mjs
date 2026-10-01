#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const repo = resolve(fileURLToPath(new URL("../../..", import.meta.url)));
const sourcePaths = {
  v1Schema: "packages/contracts/domain/domain-core.schema.json",
  v2Schema: "packages/contracts/domain/domain-core.v2.schema.json",
  v1Fixture: "packages/contracts/domain/fixtures/valid-core-aggregate.v1.json",
  lifecycleSchema: "packages/contracts/domain/domain-lifecycle.schema.json",
  corpusSchema: "packages/contracts/corpus/corpus-membership.schema.json",
  v1Release: "packages/contracts/domain/fixtures/domain-contract-release.current.v1.json",
  bridgeTest: "packages/contracts/domain/domain-v2.test.ts",
  adr: "docs/adr/ADR-0034-introduce-a-versioned-corpus-item-core-aggregate.md",
};
const outputPaths = {
  catalog: "packages/contracts/domain/domain-compatibility-authorities.v2.json",
  typescript: "packages/contracts/domain/v2-authority.generated.ts",
};
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const raw = (relativePath) => readFileSync(resolve(repo, relativePath));
const text = (relativePath) => raw(relativePath).toString("utf8").replace(/\r\n?/g, "\n");
const normalizedSha256 = (relativePath) => sha256(Buffer.from(text(relativePath), "utf8"));
const assert = (condition, message) => {
  if (!condition) throw new Error(`domain v2 authority source invalid: ${message}`);
};

const v1SchemaSha256 = sha256(raw(sourcePaths.v1Schema));
const v2SchemaSha256 = sha256(raw(sourcePaths.v2Schema));
const lifecycleSchemaSha256 = sha256(raw(sourcePaths.lifecycleSchema));
const corpusSchemaSha256 = sha256(raw(sourcePaths.corpusSchema));
const v1FixtureSha256 = sha256(raw(sourcePaths.v1Fixture));
assert(v1SchemaSha256 === "43c4a40b07d96a7fd54a6b63c053d33c999763d0273f63b90a9aaea045524abd", "frozen v1 schema drift");
assert(v1FixtureSha256 === "c218321113abd9ea548028b32db6cd4c47545a776ca53adc9abba1b5cb817205", "frozen v1 fixture drift");
const schemaSetId = (corePath, coreSha256, corpus = false) => `sha256:${sha256(Buffer.from(JSON.stringify([
  { path: corePath, sha256: coreSha256 },
  { path: sourcePaths.lifecycleSchema, sha256: lifecycleSchemaSha256 },
  ...(corpus ? [{ path: sourcePaths.corpusSchema, sha256: corpusSchemaSha256 }] : []),
])))}`;
const v1SchemaSetId = schemaSetId(sourcePaths.v1Schema, v1SchemaSha256);
const v2SchemaSetId = schemaSetId(sourcePaths.v2Schema, v2SchemaSha256, true);
const currentV1Release = JSON.parse(text(sourcePaths.v1Release));
assert(currentV1Release.contractVersion === "1.0.0" && currentV1Release.schemaSetId === v1SchemaSetId, "frozen v1 release schema-set identity");

const v1 = JSON.parse(text(sourcePaths.v1Schema));
const v2 = JSON.parse(text(sourcePaths.v2Schema));
const normalizedV2 = structuredClone(v2);
normalizedV2.$id = v1.$id;
normalizedV2.title = v1.title;
normalizedV2.description = v1.description;
const kinds = normalizedV2.$defs?.AggregateKind?.enum;
assert(Array.isArray(kinds) && kinds.filter((kind) => kind === "corpus-item").length === 1, "v2 corpus-item kind");
normalizedV2.$defs.AggregateKind.enum = kinds.filter((kind) => kind !== "corpus-item");
assert(normalizedV2.$defs.CoreAggregate?.properties?.schemaVersion?.const === "2.0", "v2 schema version");
assert(normalizedV2.$defs.CoreAggregate?.properties?.contractVersion?.const === "2.0.0", "v2 contract version");
normalizedV2.$defs.CoreAggregate.properties.schemaVersion = v1.$defs.CoreAggregate.properties.schemaVersion;
normalizedV2.$defs.CoreAggregate.properties.contractVersion = v1.$defs.CoreAggregate.properties.contractVersion;
assert(JSON.stringify(normalizedV2) === JSON.stringify(v1), "v2 changes beyond envelope version and closed kind");

const predecessor = JSON.parse(text(sourcePaths.v1Fixture));
assert(predecessor.schemaVersion === "1.0" && predecessor.contractVersion === "1.0.0", "exact predecessor fixture version");
const adrText = text(sourcePaths.adr);
const status = /^status: (Accepted)$/m.exec(adrText)?.[1];
const scope = /^decision_scope: (.+)$/m.exec(adrText)?.[1];
assert(/^id: ADR-0034$/m.test(adrText) && status === "Accepted" && scope !== undefined, "accepted ADR identity/status/scope");
assert(adrText.includes("  - CAP-04.S04.T01"), "ADR task link");
const index = JSON.parse(text("docs/adr/index.json"));
const indexed = index.records?.find((item) => item.id === "ADR-0034");
assert(indexed?.path === sourcePaths.adr && indexed.status === status && indexed.linkedTasks?.includes("CAP-04.S04.T01"), "indexed ADR status/scope");

const catalog = {
  schemaVersion: "1.0",
  documentType: "research-observatory-domain-compatibility-authority-catalog",
  catalogVersion: "2.0.0",
  authorities: [{
    id: "authority.domain-core-v1-to-v2-corpus-item",
    changeKind: "add-closed-enum-member",
    fromVersion: "1.0.0",
    toVersion: "2.0.0",
    applicableTask: "CAP-04.S04.T01",
    adr: {
      id: "ADR-0034",
      status,
      decisionScope: scope,
      path: sourcePaths.adr,
      sha256: normalizedSha256(sourcePaths.adr),
    },
    migration: {
      id: "domain-core-v1-preserved-read-in-v2",
      strategy: "reader-bridge",
      sourceRetention: "preserved",
      fromSchemaPath: sourcePaths.v1Schema,
      fromSchemaSha256: v1SchemaSha256,
      fromSchemaSetId: v1SchemaSetId,
      toSchemaPath: sourcePaths.v2Schema,
      toSchemaSha256: v2SchemaSha256,
      toSchemaSetId: v2SchemaSetId,
      sharedLifecycleSchemaPath: sourcePaths.lifecycleSchema,
      sharedLifecycleSchemaSha256: lifecycleSchemaSha256,
      corpusSchemaPath: sourcePaths.corpusSchema,
      corpusSchemaSha256,
      fixturePath: sourcePaths.v1Fixture,
      fixtureSha256: v1FixtureSha256,
      compatibilityTestPath: sourcePaths.bridgeTest,
      compatibilityTestSha256: normalizedSha256(sourcePaths.bridgeTest),
    },
  }],
};
const catalogText = `${JSON.stringify(catalog, null, 2)}\n`;
const generated = `// Generated by packages/contracts/domain/generate-v2-authority.mjs. Do not edit by hand.\n`
  + `// Local v2 bridge metadata is not process-negotiation authority.\n\n`
  + `export const DOMAIN_V2_AUTHORITY_CATALOG_SHA256 = "${sha256(Buffer.from(catalogText, "utf8"))}";\n`
  + `export const DOMAIN_V2_AUTHORITY_CATALOG = ${JSON.stringify(catalog, null, 2)} as const;\n`;
const expected = { catalog: catalogText, typescript: generated };
const check = process.argv.includes("--check");
let changed = false;
for (const [kind, relativePath] of Object.entries(outputPaths)) {
  let current = null;
  try { current = text(relativePath); } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (current === expected[kind]) continue;
  if (check) throw new Error(`${relativePath} is stale; run node packages/contracts/domain/generate-v2-authority.mjs`);
  writeFileSync(resolve(repo, relativePath), expected[kind], "utf8");
  changed = true;
}
console.log(changed ? "Domain v2 local authority: UPDATED" : "Domain v2 local authority: PASS");
