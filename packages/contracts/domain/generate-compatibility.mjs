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

const { schema, policy, prior, current } = documents;
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

const replacements = {
  "@@SCHEMA_SHA256@@": sha256(bytes.schema),
  "@@POLICY_SHA256@@": sha256(bytes.policy),
  "@@PRIOR_SHA256@@": sha256(bytes.prior),
  "@@CURRENT_SHA256@@": sha256(bytes.current),
  "@@POLICY_JSON@@": JSON.stringify(policy),
  "@@PRIOR_JSON@@": JSON.stringify(prior),
  "@@CURRENT_JSON@@": JSON.stringify(current),
};
const render = (path) => {
  let rendered = readFileSync(path, "utf8");
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
