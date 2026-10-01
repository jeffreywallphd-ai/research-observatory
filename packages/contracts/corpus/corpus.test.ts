import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { CORPUS_MEMBERSHIP_SCHEMA_SHA256, corpusContractErrors, decodeCorpusDocument } from "./generated";

function fixture(name: string): Record<string, any> {
  return JSON.parse(readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8")) as Record<string, any>;
}

describe("portable corpus membership contract", () => {
  it("pins the exact schema bytes and accepts the three strict versioned documents", () => {
    const schema = readFileSync(fileURLToPath(new URL("./corpus-membership.schema.json", import.meta.url)));
    expect(createHash("sha256").update(schema).digest("hex")).toBe(CORPUS_MEMBERSHIP_SCHEMA_SHA256);
    for (const name of ["valid-corpus-item-revision.v1.json", "valid-discovery-path.v1.json", "valid-corpus-decision.v1.json"]) {
      const source = fixture(name);
      expect(corpusContractErrors(source)).toEqual([]);
      const read = decodeCorpusDocument(source);
      expect(read).toEqual(source);
      expect(read).not.toBe(source);
      expect(Object.isFrozen(read)).toBe(true);
    }
  });

  it("rejects unsupported envelopes, extra fields, identity swaps, and invalid initial state", () => {
    const item = fixture("valid-corpus-item-revision.v1.json");
    expect(corpusContractErrors({ ...item, contractVersion: "2.0.0" })).toEqual(["corpus-contract-schema-invalid"]);
    expect(corpusContractErrors({ ...item, privatePath: "C:/secret" })).toEqual(["corpus-contract-schema-invalid"]);
    expect(corpusContractErrors({ ...item, itemId: item.revisionId })).toEqual(["corpus-item-identity-invalid"]);
    expect(corpusContractErrors({ ...item, membership: "included" })).toEqual(["corpus-initial-state-invalid"]);
    expect(corpusContractErrors(fixture("invalid-corpus-item-unreasoned-availability.v1.json")))
      .toEqual(["corpus-initial-state-invalid"]);
    expect(corpusContractErrors({ ...item, review: "none" })).toEqual(["corpus-initial-state-invalid"]);
    expect(corpusContractErrors({ ...item, duplicateOfItemId: item.workId })).toEqual(["corpus-initial-state-invalid"]);
    expect(corpusContractErrors({ ...item, discoveryPathIds: [item.discoveryPathIds[0], item.discoveryPathIds[0]] }))
      .toEqual(["corpus-discovery-paths-invalid"]);
    expect(decodeCorpusDocument({ ...item, documentType: "research-observatory-corpus-decision" })).toBeNull();
  });

  it("keeps source-route and decision-authority fields typed and noninterchangeable", () => {
    const path = fixture("valid-discovery-path.v1.json");
    const decision = fixture("valid-corpus-decision.v1.json");
    expect(corpusContractErrors(fixture("invalid-discovery-path-mixed-source.v1.json")))
      .toEqual(["corpus-import-path-invalid"]);
    expect(corpusContractErrors({ ...path, direction: "corpus-item-to-source" }))
      .toEqual(["corpus-contract-schema-invalid"]);
    expect(corpusContractErrors({ ...path, occurredAt: "2026-02-30T20:00:00.000Z" }))
      .toEqual(["corpus-discovery-time-invalid"]);
    expect(corpusContractErrors({ ...path, predecessorItemRevisionId: path.itemId }))
      .toEqual(["corpus-discovery-identity-invalid"]);
    expect(corpusContractErrors({ ...path, predecessorItemRevisionId: decision.previousRevisionId }))
      .toEqual([]);
    expect(corpusContractErrors(fixture("invalid-corpus-decision-time.v1.json")))
      .toEqual(["corpus-decision-time-invalid"]);
    expect(corpusContractErrors({ ...path, kind: "connector-record", ordinal: 0,
      recordKeySha256: null, queryRevisionId: decision.actorId })).toEqual([]);
    expect(corpusContractErrors({ ...path, kind: "citation", ordinal: null,
      recordKeySha256: null, citingWorkRevisionId: decision.actorId })).toEqual([]);
    expect(corpusContractErrors({ ...path, recordKeySha256: null })).toEqual(["corpus-import-path-invalid"]);
    expect(corpusContractErrors({ ...path, queryRevisionId: decision.actorId })).toEqual(["corpus-import-path-invalid"]);
    expect(corpusContractErrors({ ...decision, reasonCode: "" })).toEqual(["corpus-contract-schema-invalid"]);
    expect(corpusContractErrors({ ...decision, occurredAt: "2026-99-99T99:99:99.999Z" })).toEqual(["corpus-decision-time-invalid"]);
    expect(corpusContractErrors({ ...decision, occurredAt: "0000-01-01T00:00:00.000Z" })).toEqual(["corpus-decision-time-invalid"]);
    expect(corpusContractErrors({ ...decision, evidenceRevisionIds: [path.sourceRevisionId, path.sourceRevisionId] }))
      .toEqual(["corpus-decision-evidence-invalid"]);
  });
});
