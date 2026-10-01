import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  contractReleases,
  DomainCompatibilityProblem,
  domainCompatibilityNegotiationErrors,
  negotiateDomainCompatibility,
  type ComponentAdvertisement,
} from "./compatibility.generated";
import { CORE_DOMAIN_SCHEMA_SHA256, decodeCoreAggregate } from "./generated";
import {
  CORE_DOMAIN_SCHEMA_SHA256 as CORE_DOMAIN_V2_SCHEMA_SHA256,
  decodeCoreAggregate as decodeCoreAggregateV2,
} from "./generated-v2";
import { candidateCoreV2BridgeWitness, readCoreAggregateV2Candidate } from "./v2-bridge";
import { DOMAIN_V2_AUTHORITY_CATALOG, DOMAIN_V2_AUTHORITY_CATALOG_SHA256 } from "./v2-authority.generated";

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8")) as unknown;
}

const sha256 = (bytes: Uint8Array | string): string => createHash("sha256").update(bytes).digest("hex");

describe("portable core aggregate v2 candidate", () => {
  it("accepts corpus-item only under the exact v2 schema", () => {
    const v2 = fixture("valid-core-aggregate.corpus-item.v2.json");
    const v1 = fixture("valid-core-aggregate.v1.json");
    expect(decodeCoreAggregate(v2)).toBeNull();
    expect(decodeCoreAggregateV2(v2)?.aggregateKind).toBe("corpus-item");
    expect(decodeCoreAggregateV2(v1)).toBeNull();
    expect(decodeCoreAggregate(v1)).not.toBeNull();
  });

  it("binds both generated readers to their exact schema bytes", () => {
    const v1 = readFileSync(fileURLToPath(new URL("./domain-core.schema.json", import.meta.url)));
    const v2 = readFileSync(fileURLToPath(new URL("./domain-core.v2.schema.json", import.meta.url)));
    expect(sha256(v1)).toBe(CORE_DOMAIN_SCHEMA_SHA256);
    expect(sha256(v2)).toBe(CORE_DOMAIN_V2_SCHEMA_SHA256);
    const catalog = readFileSync(fileURLToPath(new URL("./domain-compatibility-authorities.v2.json", import.meta.url)));
    expect(sha256(catalog)).toBe(DOMAIN_V2_AUTHORITY_CATALOG_SHA256);
    expect(DOMAIN_V2_AUTHORITY_CATALOG.authorities[0]?.adr.status).toBe("Accepted");
    const corpus = readFileSync(fileURLToPath(new URL("../corpus/corpus-membership.schema.json", import.meta.url)));
    expect(sha256(corpus)).toBe(DOMAIN_V2_AUTHORITY_CATALOG.authorities[0]?.migration.corpusSchemaSha256);
  });

  it("retains exact v1 fields and identity through an explicit tagged reader bridge", () => {
    const v1 = fixture("valid-core-aggregate.v1.json");
    const read = readCoreAggregateV2Candidate(v1, candidateCoreV2BridgeWitness());
    expect(read?.sourceVersion).toBe("1.0.0");
    expect(read?.aggregate).toEqual(v1);
    expect(read?.aggregate.aggregateKind).toBe("evidence");
    expect(Object.isFrozen(read?.aggregate)).toBe(true);
    expect(readCoreAggregateV2Candidate(fixture("valid-core-aggregate.corpus-item.v2.json"), candidateCoreV2BridgeWitness())?.sourceVersion)
      .toBe("2.0.0");
  });

  it("denies altered bridge schema identities, version, status, and unknown source versions", () => {
    const v1 = fixture("valid-core-aggregate.v1.json");
    const witness = candidateCoreV2BridgeWitness();
    expect(readCoreAggregateV2Candidate(v1, { ...witness, v1SchemaSha256: "0".repeat(64) })).toBeNull();
    expect(readCoreAggregateV2Candidate(v1, { ...witness, v2SchemaSha256: "0".repeat(64) })).toBeNull();
    expect(readCoreAggregateV2Candidate(v1, { ...witness, sourceVersion: "0.1.0" })).toBeNull();
    const alteredStatus = "Proposed";
    expect(readCoreAggregateV2Candidate(v1, { ...witness, status: alteredStatus })).toBeNull();
    const wrongCatalog = structuredClone(DOMAIN_V2_AUTHORITY_CATALOG) as Record<string, any>;
    wrongCatalog.authorities[0].adr.status = alteredStatus;
    expect(readCoreAggregateV2Candidate(v1, witness, wrongCatalog)).toBeNull();
    const wrongSchemaCatalog = structuredClone(DOMAIN_V2_AUTHORITY_CATALOG) as Record<string, any>;
    wrongSchemaCatalog.authorities[0].migration.fromSchemaSha256 = "0".repeat(64);
    expect(readCoreAggregateV2Candidate(v1, witness, wrongSchemaCatalog)).toBeNull();
    const wrongCorpusCatalog = structuredClone(DOMAIN_V2_AUTHORITY_CATALOG) as Record<string, any>;
    wrongCorpusCatalog.authorities[0].migration.corpusSchemaSha256 = "0".repeat(64);
    expect(readCoreAggregateV2Candidate(v1, witness, wrongCorpusCatalog)).toBeNull();
    const circularCatalog: Record<string, unknown> = {};
    circularCatalog.self = circularCatalog;
    expect(readCoreAggregateV2Candidate(v1, witness, circularCatalog)).toBeNull();
    const unknown = { ...(v1 as Record<string, unknown>), contractVersion: "1.1.0" };
    expect(readCoreAggregateV2Candidate(unknown, witness)).toBeNull();
  });

  it("denies mixed v1/v2 process advertisements by exact generated schema-set and version overlap", () => {
    const currentV1 = contractReleases().find((release) => release.contractVersion === "1.0.0");
    const v2 = DOMAIN_V2_AUTHORITY_CATALOG.authorities[0];
    expect(currentV1).toBeDefined();
    expect(v2).toBeDefined();
    const lifecyclePath = v2.migration.sharedLifecycleSchemaPath;
    const lifecycleBytes = readFileSync(fileURLToPath(new URL("./domain-lifecycle.schema.json", import.meta.url)));
    expect(sha256(lifecycleBytes)).toBe(v2.migration.sharedLifecycleSchemaSha256);
    const schemaSetId = (corePath: string, coreSha256: string, includeCorpus = false): string => `sha256:${sha256(JSON.stringify([
      { path: corePath, sha256: coreSha256 },
      { path: lifecyclePath, sha256: v2.migration.sharedLifecycleSchemaSha256 },
      ...(includeCorpus ? [{ path: v2.migration.corpusSchemaPath, sha256: v2.migration.corpusSchemaSha256 }] : []),
    ]))}`;
    expect(v2.migration.fromSchemaSetId).toBe(currentV1!.schemaSetId);
    expect(v2.migration.fromSchemaSetId).toBe(schemaSetId(v2.migration.fromSchemaPath, CORE_DOMAIN_SCHEMA_SHA256));
    expect(v2.migration.toSchemaSetId).toBe(schemaSetId(v2.migration.toSchemaPath, CORE_DOMAIN_V2_SCHEMA_SHA256, true));
    expect(v2.migration.toSchemaSetId).not.toBe(currentV1!.schemaSetId);

    const desktopV1: ComponentAdvertisement = {
      schemaVersion: "1.0",
      documentType: "research-observatory-domain-compatibility-advertisement",
      role: "desktop",
      componentVersion: currentV1!.contractVersion,
      contractFamily: currentV1!.contractFamily,
      supportedContractVersions: [currentV1!.contractVersion],
      supportedEventVersions: ["1.0.0"],
      schemaSetId: currentV1!.schemaSetId,
    };
    const sidecarV2: ComponentAdvertisement = {
      ...desktopV1,
      role: "sidecar",
      componentVersion: v2.toVersion,
      supportedContractVersions: [v2.toVersion],
      schemaSetId: v2.migration.toSchemaSetId,
    };
    expect(domainCompatibilityNegotiationErrors([desktopV1, sidecarV2])).toEqual(["compatibility-schema-set-mismatch"]);
    expect(() => negotiateDomainCompatibility([desktopV1, sidecarV2])).toThrowError(DomainCompatibilityProblem);

    // Even an erroneous peer that copies the v1 schema-set identifier cannot share a contract version.
    const forgedSidecar = { ...sidecarV2, schemaSetId: desktopV1.schemaSetId };
    expect(domainCompatibilityNegotiationErrors([desktopV1, forgedSidecar])).toEqual(["compatibility-contract-version-no-overlap"]);
    expect(() => negotiateDomainCompatibility([desktopV1, forgedSidecar])).toThrowError(DomainCompatibilityProblem);
  });
});
