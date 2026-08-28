import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  CURRENT_DOMAIN_RELEASE_SHA256,
  DOMAIN_COMPATIBILITY_POLICY_SHA256,
  DOMAIN_COMPATIBILITY_SCHEMA_SHA256,
  DomainCompatibilityProblem,
  PRIOR_DOMAIN_RELEASE_SHA256,
  assessDomainChange,
  contractReleases,
  domainCompatibilityNegotiationErrors,
  domainCompatibilityPolicy,
  negotiateDomainCompatibility,
  readCompatibility,
  type ComponentAdvertisement,
} from "./compatibility.generated";

const root = new URL("./", import.meta.url);

function advertisement(role: "desktop" | "sidecar" | "server", versions = ["0.1.0", "1.0.0"]): ComponentAdvertisement {
  return {
    schemaVersion: "1.0",
    documentType: "research-observatory-domain-compatibility-advertisement",
    role,
    componentVersion: "1.0.0",
    contractFamily: "research-observatory-domain",
    supportedContractVersions: versions,
    supportedEventVersions: versions,
    schemaSetId: contractReleases()[1]!.schemaSetId,
  };
}

function proposal(kind: string, fromVersion = "1.0.0", toVersion = "1.1.0"): Record<string, unknown> {
  return {
    schemaVersion: "1.0",
    documentType: "research-observatory-domain-change-proposal",
    fromVersion,
    toVersion,
    changeKind: kind,
    artifactId: "domain.aggregate",
    adrId: null,
    migration: null,
    deprecation: null,
  };
}

describe("portable domain compatibility policy", () => {
  it("binds the schema, policy, and current/prior release bytes", () => {
    const paths = [
      ["domain-compatibility.schema.json", DOMAIN_COMPATIBILITY_SCHEMA_SHA256],
      ["domain-compatibility.v1.json", DOMAIN_COMPATIBILITY_POLICY_SHA256],
      ["fixtures/domain-contract-release.prior.v0.1.json", PRIOR_DOMAIN_RELEASE_SHA256],
      ["fixtures/domain-contract-release.current.v1.json", CURRENT_DOMAIN_RELEASE_SHA256],
    ] as const;
    for (const [path, expected] of paths) {
      expect(createHash("sha256").update(readFileSync(fileURLToPath(new URL(path, root)))).digest("hex")).toBe(expected);
    }
    expect(domainCompatibilityPolicy().eventPolicy).toEqual({
      envelopeVersioned: true,
      unknownEvent: "deny-and-audit",
      payloadUnknownFields: "reject",
      supportedVersions: ["0.1.0", "1.0.0"],
    });
    expect(contractReleases().map((item) => item.contractVersion)).toEqual(["0.1.0", "1.0.0"]);
  });

  it("recognizes current native reads and only the governed prior bridge", () => {
    expect(readCompatibility("1.0.0")).toMatchObject({ mode: "native", bridgeId: null });
    expect(readCompatibility("0.1.0")).toMatchObject({
      mode: "bridge-required",
      bridgeId: "legacy-project-uuidv4-to-canonical-uuidv7",
    });
    expect(readCompatibility("0.0.9")).toEqual({
      mode: "unsupported",
      contractVersion: null,
      bridgeId: null,
      diagnosticCode: "compatibility-read-unsupported",
    });
  });

  it("allows additive/deprecation evolution and gates every breaking change", () => {
    expect(assessDomainChange(proposal("add-optional-field"))).toMatchObject({ classification: "additive", allowed: true });
    const deprecated = proposal("deprecate-field");
    deprecated.deprecation = { since: "1.1.0", removalNotBefore: "1.2.0", replacement: "domain.new-field" };
    expect(assessDomainChange(deprecated)).toMatchObject({ classification: "deprecation", allowed: true });

    const breaking = proposal("change-identity-format", "1.0.0", "2.0.0");
    expect(assessDomainChange(breaking).errors).toEqual([
      "compatibility-breaking-adr-required",
      "compatibility-breaking-migration-required",
    ]);
    breaking.adrId = "ADR-0013";
    breaking.migration = {
      id: "legacy-project-uuidv4-to-canonical-uuidv7",
      fromVersion: "1.0.0",
      toVersion: "2.0.0",
      strategy: "reader-bridge",
      sourceRetention: "preserved",
      testFixture: "packages/contracts/project/fixtures/valid-project-manifest.v1.json",
    };
    expect(assessDomainChange(breaking)).toMatchObject({ classification: "breaking", allowed: true, errors: [] });
    expect(assessDomainChange(proposal("remove-field")).errors).toContain("compatibility-breaking-major-required");
  });

  it("selects the highest exact common contract and event versions independent of role order", () => {
    const forward = negotiateDomainCompatibility([advertisement("desktop"), advertisement("sidecar")]);
    const reversed = negotiateDomainCompatibility([advertisement("sidecar"), advertisement("desktop")]);
    expect(forward).toEqual(reversed);
    expect(forward).toMatchObject({ contractVersion: "1.0.0", eventVersion: "1.0.0", roles: ["desktop", "sidecar"] });

    const priorSet = contractReleases()[0]!.schemaSetId;
    const items = [advertisement("server", ["0.1.0"]), advertisement("desktop", ["0.1.0"]), advertisement("sidecar", ["0.1.0"])];
    for (const item of items) (item as { schemaSetId: string }).schemaSetId = priorSet;
    expect(negotiateDomainCompatibility(items)).toMatchObject({ contractVersion: "0.1.0", eventVersion: "0.1.0", roles: ["desktop", "sidecar", "server"] });
  });

  it("fails closed on hostile advertisements with stable content-free codes", () => {
    expect(domainCompatibilityNegotiationErrors([advertisement("desktop"), advertisement("desktop")])).toEqual(["compatibility-role-duplicate"]);
    expect(domainCompatibilityNegotiationErrors([advertisement("desktop"), advertisement("server")])).toEqual(["compatibility-required-role-missing"]);
    const drifted = { ...advertisement("sidecar"), schemaSetId: contractReleases()[0]!.schemaSetId };
    expect(domainCompatibilityNegotiationErrors([advertisement("desktop"), drifted])).toEqual(["compatibility-schema-set-mismatch"]);
    const hostile = { ...advertisement("sidecar"), researchText: "private manuscript" };
    expect(domainCompatibilityNegotiationErrors([advertisement("desktop"), hostile])).toEqual(["compatibility-advertisement-invalid"]);
    expect(() => negotiateDomainCompatibility([advertisement("desktop", ["1.0.0"]), advertisement("sidecar", ["0.1.0"])]))
      .toThrowError(DomainCompatibilityProblem);
  });

  it("returns immutable policy, release, assessment, and negotiated snapshots", () => {
    const policy = domainCompatibilityPolicy();
    const assessment = assessDomainChange(proposal("add-optional-field"));
    const negotiated = negotiateDomainCompatibility([advertisement("desktop"), advertisement("sidecar")]);
    expect(Object.isFrozen(policy)).toBe(true);
    expect(Object.isFrozen(policy.changeRules)).toBe(true);
    expect(Object.isFrozen(contractReleases()[0])).toBe(true);
    expect(Object.isFrozen(assessment.errors)).toBe(true);
    expect(Object.isFrozen(negotiated.roles)).toBe(true);
  });
});
