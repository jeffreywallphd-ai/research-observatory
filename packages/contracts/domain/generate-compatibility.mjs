#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const repo = resolve(fileURLToPath(new URL("../../..", import.meta.url)));
const domain = resolve(repo, "packages/contracts/domain");
const sources = {
  schema: resolve(domain, "domain-compatibility.schema.json"),
  policy: resolve(domain, "domain-compatibility.v1.json"),
  prior: resolve(domain, "fixtures/domain-contract-release.prior.v0.1.json"),
  current: resolve(domain, "fixtures/domain-contract-release.current.v1.json"),
  authority: resolve(domain, "domain-compatibility-authorities.v1.json"),
  eventCatalog: resolve(domain, "domain-event-catalog.v1.json"),
  projectManifest: resolve(repo, "packages/contracts/project/project-manifest.schema.json"),
  domainCore: resolve(domain, "domain-core.schema.json"),
  domainLifecycle: resolve(domain, "domain-lifecycle.schema.json"),
};
const templates = {
  typescript: resolve(domain, "compatibility.template.ts.txt"),
  python: resolve(domain, "compatibility.template.py.txt"),
};
const outputs = {
  typescript: resolve(domain, "compatibility.generated.ts"),
  python: resolve(repo, "services/core-api/src/research_observatory_core/domain_compatibility.py"),
};

const bytes = Object.fromEntries(Object.entries(sources).map(([key, path]) => [key, readFileSync(path)]));
const documents = Object.fromEntries(Object.entries(bytes).map(([key, value]) => [key, JSON.parse(value.toString("utf8"))]));
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const canonicalTextSha256 = (value) => sha256(Buffer.from(value.toString("utf8").replace(/\r\n?/g, "\n"), "utf8"));
const semverPattern = /^(0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\.(0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\.(0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])$/;
const compareSemver = (left, right) => {
  const l = left.split(".").map(Number);
  const r = right.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    if (l[index] !== r[index]) return l[index] < r[index] ? -1 : 1;
  }
  return 0;
};
const assert = (condition, message) => {
  if (!condition) throw new Error(`domain compatibility source invalid: ${message}`);
};
assert(canonicalTextSha256(Buffer.from("one\ntwo\n")) === canonicalTextSha256(Buffer.from("one\r\ntwo\r\n")), "canonical text newline parity");

const { schema, policy, prior, current } = documents;
const { authority, eventCatalog } = documents;
assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", "schema draft");
assert(schema.$ref === "#/$defs/CompatibilityPolicy" && typeof schema.$defs === "object", "schema root");
assert(Array.isArray(schema["x-research-observatory-semanticRules"]), "semantic rules");
assert(policy.documentType === "research-observatory-domain-compatibility-policy", "policy type");
assert(policy.policyVersion === "1.0.0", "policy version");
assert(semverPattern.test(policy.priorContractVersion) && semverPattern.test(policy.currentContractVersion), "contract versions");
assert(compareSemver(policy.priorContractVersion, policy.currentContractVersion) < 0, "ordered contract versions");

const expectedRules = [
  ["add-optional-field", "additive", []],
  ["widen-reader-type", "additive", []],
  ["deprecate-field", "deprecation", ["deprecation-window"]],
  ["add-required-field", "breaking", ["adr", "migration"]],
  ["remove-field", "breaking", ["adr", "migration"]],
  ["rename-field", "breaking", ["adr", "migration"]],
  ["narrow-reader-type", "breaking", ["adr", "migration"]],
  ["add-closed-enum-member", "breaking", ["adr", "migration"]],
  ["add-event-type", "breaking", ["adr", "migration"]],
  ["change-event-payload", "breaking", ["adr", "migration"]],
  ["change-identity-format", "breaking", ["adr", "migration"]],
  ["repurpose-meaning", "breaking", ["adr", "migration"]],
];
assert(JSON.stringify(policy.changeRules) === JSON.stringify(expectedRules.map(([changeKind, classification, requirements]) => ({ changeKind, classification, requirements }))), "change-rule catalog");
assert(JSON.stringify(policy.eventPolicy) === JSON.stringify({ envelopeVersioned: true, unknownEvent: "deny-and-audit", payloadUnknownFields: "reject", supportedVersions: [policy.priorContractVersion, policy.currentContractVersion] }), "event policy");
assert(JSON.stringify(policy.negotiation) === JSON.stringify({ roles: ["desktop", "sidecar", "server"], selection: "highest-exact-common", schemaSet: "exact-match", noOverlap: "deny" }), "negotiation policy");
assert(Array.isArray(policy.bridges) && policy.bridges.length === 1, "one governed bridge");
const bridge = policy.bridges[0];
assert(bridge.id === "legacy-project-uuidv4-to-canonical-uuidv7", "bridge identity");
assert(bridge.fromVersion === policy.priorContractVersion && bridge.toVersion === policy.currentContractVersion, "bridge versions");
assert(bridge.adrId === "ADR-0013" && bridge.strategy === "reader-bridge" && bridge.sourceRetention === "preserved", "bridge authority");
assert(existsSync(resolve(repo, bridge.testFixture)), "bridge fixture");
const bridgeFixture = JSON.parse(readFileSync(resolve(repo, bridge.testFixture), "utf8"));
assert(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(bridgeFixture.projectId), "bridge fixture UUIDv4 identity");

for (const [release, version, identity, reader, writer] of [
  [prior, policy.priorContractVersion, "legacy-project-uuidv4-bridge", "bridge-required", "denied"],
  [current, policy.currentContractVersion, "canonical-uuidv7", "native", "native"],
]) {
  assert(release.documentType === "research-observatory-domain-contract-release", "release type");
  assert(release.contractFamily === policy.contractFamily && release.contractVersion === version, "release identity");
  assert(release.identityFormat === identity && release.readerMode === reader && release.writerMode === writer, "release modes");
  assert(/^sha256:[0-9a-f]{64}$/.test(release.schemaSetId), "release schema-set identity");
}
assert(prior.schemaSetId === `sha256:${sha256(bytes.projectManifest)}`, "prior schema-set identity");
const currentSchemaSet = [
  { path: "packages/contracts/domain/domain-core.schema.json", sha256: sha256(bytes.domainCore) },
  { path: "packages/contracts/domain/domain-lifecycle.schema.json", sha256: sha256(bytes.domainLifecycle) },
];
assert(current.schemaSetId === `sha256:${sha256(Buffer.from(JSON.stringify(currentSchemaSet)))}`, "current schema-set identity");

assert(authority.schemaVersion === "1.0" && authority.documentType === "research-observatory-domain-compatibility-authority-catalog" && authority.catalogVersion === "1.0.0", "authority catalog identity");
assert(Array.isArray(authority.authorities) && authority.authorities.length === 1, "one accepted breaking authority");
const acceptedAuthority = authority.authorities[0];
const expectedScope = "Portable aggregate and revision identity, UUID minting authority, common scholarly value objects, and deterministic Python/TypeScript generation from the core domain schema.";
assert(acceptedAuthority.id === "authority.uuidv4-project-to-uuidv7-domain" && acceptedAuthority.changeKind === "change-identity-format", "authority identity");
assert(acceptedAuthority.fromVersion === policy.priorContractVersion && acceptedAuthority.toVersion === policy.currentContractVersion, "authority endpoints");
assert(acceptedAuthority.applicableTask === "CAP-03.S01.T03", "authority task scope");
assert(acceptedAuthority.adr?.id === "ADR-0013" && acceptedAuthority.adr.status === "Accepted" && acceptedAuthority.adr.decisionScope === expectedScope, "accepted ADR authority");
const adrPath = resolve(repo, acceptedAuthority.adr.path);
const adrBytes = readFileSync(adrPath);
assert(acceptedAuthority.adr.sha256 === canonicalTextSha256(adrBytes), "ADR evidence digest");
const adrText = adrBytes.toString("utf8");
assert(/^status: Accepted$/m.test(adrText) && adrText.includes(`decision_scope: ${expectedScope}`) && adrText.includes("CAP-03.S01.T03"), "ADR status and scope");
const adrIndex = JSON.parse(readFileSync(resolve(repo, "docs/adr/index.json"), "utf8"));
const indexedAdr = adrIndex.records.find((item) => item.id === "ADR-0013");
assert(indexedAdr?.status === "Accepted" && indexedAdr.path === acceptedAuthority.adr.path && JSON.stringify(indexedAdr.linkedTasks) === JSON.stringify(["CAP-03.S01.T01", "CAP-03.S01.T03"]), "ADR index authority");
const authorityMigration = acceptedAuthority.migration;
assert(authorityMigration.id === bridge.id && authorityMigration.strategy === bridge.strategy && authorityMigration.sourceRetention === bridge.sourceRetention, "authority migration");
assert(authorityMigration.fixturePath === bridge.testFixture, "authority fixture path");
assert(authorityMigration.fixtureSha256 === sha256(readFileSync(resolve(repo, authorityMigration.fixturePath))), "authority fixture digest");
assert(authorityMigration.compatibilityTestPath === "packages/contracts/domain/compatibility.test.ts", "authority test path");
assert(authorityMigration.compatibilityTestSha256 === canonicalTextSha256(readFileSync(resolve(repo, authorityMigration.compatibilityTestPath))), "authority test digest");

assert(eventCatalog.schemaVersion === "1.0" && eventCatalog.documentType === "research-observatory-domain-event-catalog" && eventCatalog.catalogVersion === "1.0.0", "event catalog identity");
assert(eventCatalog.payloadSchemaId === `sha256:${sha256(bytes.domainLifecycle)}`, "event payload schema binding");
const transition = documents.domainLifecycle.$defs.LifecycleTransition;
const expectedEventVersions = [policy.priorContractVersion, policy.currentContractVersion];
assert(Array.isArray(eventCatalog.events) && eventCatalog.events.length === expectedEventVersions.length, "event catalog entries");
for (const [index, event] of eventCatalog.events.entries()) {
  assert(event.eventType === "domain.lifecycle-transition" && event.eventVersion === expectedEventVersions[index], "event identity and version");
  assert(event.payloadDocumentType === transition.properties.documentType.const, "event payload document type");
  assert(JSON.stringify(event.payloadRequiredFields) === JSON.stringify(transition.required), "event required fields");
  assert(JSON.stringify(event.payloadAllowedFields) === JSON.stringify(Object.keys(transition.properties)), "event allowed fields");
}
assert(JSON.stringify([...new Set(eventCatalog.events.map((event) => event.eventVersion))]) === JSON.stringify(policy.eventPolicy.supportedVersions), "event policy/catalog versions");

const replacements = {
  "@@SCHEMA_SHA256@@": sha256(bytes.schema),
  "@@POLICY_SHA256@@": sha256(bytes.policy),
  "@@PRIOR_SHA256@@": sha256(bytes.prior),
  "@@CURRENT_SHA256@@": sha256(bytes.current),
  "@@AUTHORITY_SHA256@@": sha256(bytes.authority),
  "@@EVENT_CATALOG_SHA256@@": sha256(bytes.eventCatalog),
  "@@POLICY_JSON@@": JSON.stringify(policy),
  "@@PRIOR_JSON@@": JSON.stringify(prior),
  "@@CURRENT_JSON@@": JSON.stringify(current),
  "@@AUTHORITY_JSON@@": JSON.stringify(authority),
  "@@EVENT_CATALOG_JSON@@": JSON.stringify(eventCatalog),
};
const render = (path) => {
  let rendered = readFileSync(path, "utf8").replace(/\r\n?/g, "\n");
  for (const [token, value] of Object.entries(replacements)) rendered = rendered.replaceAll(token, value);
  assert(!rendered.includes("@@"), `unresolved template token in ${path}`);
  return rendered;
};
const check = process.argv.includes("--check");
let changed = false;
for (const kind of ["typescript", "python"]) {
  const expected = render(templates[kind]);
  let actual = null;
  try { actual = readFileSync(outputs[kind], "utf8"); } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (actual === expected) continue;
  if (check) throw new Error(`${outputs[kind].slice(repo.length + 1)} is stale; run node packages/contracts/domain/generate-compatibility.mjs`);
  writeFileSync(outputs[kind], expected, "utf8");
  changed = true;
}
console.log(changed ? "Domain compatibility contract: UPDATED" : "Domain compatibility contract: PASS");
