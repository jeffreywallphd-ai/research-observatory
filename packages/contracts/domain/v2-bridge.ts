/** Local v1/v2 read bridge. This does not advertise process compatibility. */
import {
  CORE_DOMAIN_SCHEMA_SHA256 as V1_SCHEMA_SHA256,
  decodeCoreAggregate as decodeV1,
  type CoreAggregate as CoreAggregateV1,
} from "./generated";
import {
  CORE_DOMAIN_SCHEMA_SHA256 as V2_SCHEMA_SHA256,
  decodeCoreAggregate as decodeV2,
  type CoreAggregate as CoreAggregateV2,
} from "./generated-v2";
import { DOMAIN_V2_AUTHORITY_CATALOG, DOMAIN_V2_AUTHORITY_CATALOG_SHA256 } from "./v2-authority.generated";

export interface CoreV2BridgeWitness {
  readonly adrId: "ADR-0034";
  readonly status: "Accepted";
  readonly sourceVersion: "1.0.0";
  readonly targetVersion: "2.0.0";
  readonly catalogSha256: string;
  readonly adrSha256: string;
  readonly v1SchemaSha256: string;
  readonly v2SchemaSha256: string;
  readonly v1FixtureSha256: string;
  readonly compatibilityTestSha256: string;
}

const candidate = DOMAIN_V2_AUTHORITY_CATALOG.authorities[0];
const WITNESS: CoreV2BridgeWitness = Object.freeze({
  adrId: candidate.adr.id,
  status: candidate.adr.status,
  sourceVersion: candidate.fromVersion,
  targetVersion: candidate.toVersion,
  catalogSha256: DOMAIN_V2_AUTHORITY_CATALOG_SHA256,
  adrSha256: candidate.adr.sha256,
  v1SchemaSha256: candidate.migration.fromSchemaSha256,
  v2SchemaSha256: candidate.migration.toSchemaSha256,
  v1FixtureSha256: candidate.migration.fixtureSha256,
  compatibilityTestSha256: candidate.migration.compatibilityTestSha256,
});

export type CoreV2CandidateRead =
  | Readonly<{ sourceVersion: "1.0.0"; aggregate: CoreAggregateV1 }>
  | Readonly<{ sourceVersion: "2.0.0"; aggregate: CoreAggregateV2 }>;

export function candidateCoreV2BridgeWitness(): CoreV2BridgeWitness {
  return WITNESS;
}

function exactWitness(value: unknown): boolean {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const expected = WITNESS as unknown as Record<string, unknown>;
  const keys = Object.keys(expected);
  return Object.keys(candidate).length === keys.length
    && keys.every((key) => Object.hasOwn(candidate, key) && candidate[key] === expected[key]);
}

export function readCoreAggregateV2Candidate(value: unknown, witness: unknown, authorityCatalog: unknown = DOMAIN_V2_AUTHORITY_CATALOG): CoreV2CandidateRead | null {
  try {
    if (JSON.stringify(authorityCatalog) !== JSON.stringify(DOMAIN_V2_AUTHORITY_CATALOG)) return null;
    if (candidate.adr.status !== "Accepted"
      || candidate.changeKind !== "add-closed-enum-member"
      || candidate.migration.strategy !== "reader-bridge"
      || candidate.migration.sourceRetention !== "preserved"
      || candidate.migration.fromSchemaSha256 !== V1_SCHEMA_SHA256
      || candidate.migration.toSchemaSha256 !== V2_SCHEMA_SHA256
      || !exactWitness(witness)
      || value === null || typeof value !== "object" || Array.isArray(value)) return null;
    const record = value as Record<string, unknown>;
    if (record.schemaVersion === "1.0" && record.contractVersion === "1.0.0") {
      const aggregate = decodeV1(value);
      return aggregate === null ? null : Object.freeze({ sourceVersion: "1.0.0", aggregate });
    }
    if (record.schemaVersion === "2.0" && record.contractVersion === "2.0.0") {
      const aggregate = decodeV2(value);
      return aggregate === null ? null : Object.freeze({ sourceVersion: "2.0.0", aggregate });
    }
  } catch {
    // Malformed caller-owned data and hostile getters never escape the reader boundary.
  }
  return null;
}
