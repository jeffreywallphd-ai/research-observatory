import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  CORPUS_REPORT_SCHEMA_SHA256,
  corpusReportContractErrors,
  decodeCorpusReportDocument,
} from "./generated";

function fixture(name: string): Record<string, any> {
  return JSON.parse(readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8"));
}

describe("portable corpus report contract", () => {
  it("pins the schema and round-trips immutable snapshot, member and drill values", () => {
    const schema = readFileSync(fileURLToPath(new URL("./corpus-report.schema.json", import.meta.url)));
    expect(createHash("sha256").update(schema).digest("hex")).toBe(CORPUS_REPORT_SCHEMA_SHA256);
    for (const name of ["valid-snapshot.v1.json", "valid-member.v1.json", "valid-drill-page.v1.json",
      "valid-overlap-snapshot.v1.json", "valid-overlap-member.v1.json"]) {
      const source = fixture(name);
      expect(corpusReportContractErrors(source)).toEqual([]);
      const decoded = decodeCorpusReportDocument(source);
      expect(decoded).toEqual(source);
      expect(decoded).not.toBe(source);
      expect(Object.isFrozen(decoded)).toBe(true);
    }
  });

  it("rejects denominator mismatch, missing known witness and imputed OA/full text", () => {
    const snapshot = fixture("valid-snapshot.v1.json");
    const member = fixture("valid-member.v1.json");
    expect(corpusReportContractErrors(fixture("invalid-denominator.v1.json")))
      .toEqual(["corpus-report-member-count-invalid"]);
    expect(corpusReportContractErrors(fixture("invalid-known-without-witness.v1.json")))
      .toEqual(["corpus-report-known-witness-required"]);
    expect(corpusReportContractErrors({ ...snapshot, coverage: snapshot.coverage.slice(1) }))
      .toEqual(["corpus-report-schema-invalid"]);
    const unsupported = structuredClone(member);
    unsupported.fields[5] = { ...unsupported.fields[5], state: "known", value: "yes", witnessRevisionId: null };
    expect(corpusReportContractErrors(unsupported)).toEqual(["corpus-report-known-witness-required"]);
    const falseSourceRoot = structuredClone(member);
    falseSourceRoot.paths[0] = { ...falseSourceRoot.paths[0], sourceKey: "connector:openalex", route: "import-member" };
    expect(corpusReportContractErrors(falseSourceRoot)).toEqual(["corpus-report-source-root-invalid"]);
    const falseRights = structuredClone(member);
    falseRights.paths[0] = { ...falseRights.paths[0], rightsPolicyRevisionId: null };
    expect(corpusReportContractErrors(falseRights)).toEqual(["corpus-report-path-rights-invalid"]);
    expect(corpusReportContractErrors({ ...member, rightsGrant: true })).toEqual(["corpus-report-schema-invalid"]);
  });

  it("keeps path counts and cross-source path pairs distinct from canonical item counts", () => {
    const snapshot = fixture("valid-overlap-snapshot.v1.json");
    expect(snapshot.memberCount).toBe(1);
    expect(snapshot.discoveryPathCount).toBe(3);
    expect(snapshot.sourceOverlaps[0].itemCount).toBe(1);
    expect(snapshot.sourceOverlaps[0].discoveryPathPairCount).toBe(2);
    expect(snapshot.routeOverlaps[0].discoveryPathPairCount).toBe(2);
    const wrong = structuredClone(snapshot);
    wrong.sourceContributions[1].discoveryPathCount = 1;
    expect(corpusReportContractErrors(wrong)).toEqual(["corpus-report-discovery-path-count-invalid"]);
  });

  it("binds drill scope, item order and one exact filter", () => {
    const page = fixture("valid-drill-page.v1.json");
    expect(corpusReportContractErrors({ ...page, projectId: page.snapshotId }))
      .toEqual(["corpus-report-page-scope-invalid"]);
    const wrongFilter = { ...page.filter, kind: "all", sourceKey: "connector:openalex" };
    expect(corpusReportContractErrors({ ...page, filter: wrongFilter })).toEqual(["corpus-report-page-invalid"]);
    const membership = { ...page.filter, kind: "membership", membership: "included" };
    expect(corpusReportContractErrors({ ...page, filter: membership })).toEqual(["corpus-report-page-filter-invalid"]);
    expect(corpusReportContractErrors({ ...page, filter: { ...page.filter, kind: "unattributed" } }))
      .toEqual(["corpus-report-page-filter-invalid"]);
    expect(corpusReportContractErrors({ ...page, nextCursor: "opaque", members: [] }))
      .toEqual(["corpus-report-page-cursor-invalid"]);
    expect(corpusReportContractErrors({ ...page, members: [page.members[0], page.members[0]] }))
      .toEqual(["corpus-report-page-order-invalid"]);
  });
});
