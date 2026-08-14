import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  CORE_DOMAIN_SCHEMA_SHA256,
  decodeCoreAggregate,
  domainContractErrors,
  isUuidV7,
} from "./generated";

function fixture(name: string): unknown {
  const path = fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

describe("portable core domain contract", () => {
  it("decodes current expected and disputed aggregates without replacing observed wording", () => {
    const expected = decodeCoreAggregate(fixture("valid-core-aggregate.v1.json"));
    const disputed = decodeCoreAggregate(fixture("disputed-core-aggregate.v1.json"));

    expect(expected?.displayLabel.observed).toBe("The intervention was associated with lower attrition.");
    expect(disputed?.displayLabel.observed).toBe("may contribute to");
    expect(disputed?.displayLabel.alternatives.map((item) => [item.value, item.disposition])).toEqual([
      ["is associated with", "disputed"],
      ["causes", "rejected"],
    ]);
  });

  it("fails closed on non-v7 identity, path-bearing anchors, missing disputes, and unknown fields", () => {
    for (const name of [
      "invalid-uuidv4-aggregate.json",
      "invalid-path-bearing-source-reference.json",
      "invalid-disputed-without-alternative.json",
    ]) {
      expect(decodeCoreAggregate(fixture(name)), name).toBeNull();
      expect(domainContractErrors(fixture(name)), name).not.toEqual([]);
    }
    const value = structuredClone(fixture("valid-core-aggregate.v1.json")) as Record<string, unknown>;
    value.absolutePath = "C:\\private\\study";
    expect(decodeCoreAggregate(value)).toBeNull();

    const semantic = structuredClone(fixture("valid-core-aggregate.v1.json")) as {
      aggregateId: string;
      revisionId: string;
      createdAt: string;
      modifiedAt: string;
      rights: { allowedUses: string[]; deniedUses: string[] };
    };
    semantic.revisionId = semantic.aggregateId;
    expect(domainContractErrors(semantic)).toContain("revision-identity-distinct");
    semantic.revisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2";
    semantic.modifiedAt = "2026-08-14T11:59:59Z";
    expect(domainContractErrors(semantic)).toContain("modified-at-not-before-created-at");
    semantic.modifiedAt = semantic.createdAt;
    semantic.rights.deniedUses.push("view");
    expect(domainContractErrors(semantic)).toContain("rights-allowed-and-denied-disjoint");
  });

  it("binds the generated decoder to the exact language-neutral schema bytes", () => {
    const path = fileURLToPath(new URL("./domain-core.schema.json", import.meta.url));
    expect(createHash("sha256").update(readFileSync(path)).digest("hex")).toBe(CORE_DOMAIN_SCHEMA_SHA256);
  });

  it("recognizes only canonical lower-case RFC 9562 UUIDv7 values", () => {
    expect(isUuidV7("017f22e2-79b0-7cc3-98c4-dc0c0c07398f")).toBe(true);
    expect(isUuidV7("018f47a2-4d6b-4f78-9f2e-7fb76c86d9a1")).toBe(false);
    expect(isUuidV7("017F22E2-79B0-7CC3-98C4-DC0C0C07398F")).toBe(false);
    expect(isUuidV7("00000000-0000-7000-0000-000000000000")).toBe(false);
    expect(isUuidV7("017f22e2-79b0-7cc3-98c4-dc0c0c07398f\n")).toBe(false);
  });

  it("rejects local paths and trailing controls without rejecting portable identifiers", () => {
    const base = fixture("valid-core-aggregate.v1.json") as {
      displayLabel: { observed: string };
      confidence: Record<string, unknown>;
      externalIdentifiers: Array<{ scheme: string; observedValue: string; normalizedValue: string | null }>;
    };
    for (const local of ["C:\\private\\paper.pdf", "C:private\\paper.pdf", "\\\\server\\paper.pdf", "/home/private/paper.pdf", "~/private/paper.pdf", "../private/paper.pdf", "file:///private/paper.pdf"]) {
      for (const field of ["observedValue", "normalizedValue"] as const) {
        const value = structuredClone(base);
        value.externalIdentifiers[0]![field] = local;
        expect(decodeCoreAggregate(value), `${field}: ${local}`).toBeNull();
      }
    }
    for (const text of ["word\n", "word\r"]) {
      const observed = structuredClone(base);
      observed.displayLabel.observed = text;
      expect(decodeCoreAggregate(observed)).toBeNull();
      const confidence = structuredClone(base);
      confidence.confidence = { kind: "quantified", value: 0.5, basis: text };
      expect(decodeCoreAggregate(confidence)).toBeNull();
    }
    const web = structuredClone(base);
    web.externalIdentifiers[0] = {
      ...web.externalIdentifiers[0]!,
      scheme: "url",
      observedValue: "HTTPS://example.org/article/7",
      normalizedValue: "https://example.org/article/7",
    };
    expect(decodeCoreAggregate(web)).not.toBeNull();
  });

  it("returns an owned deeply frozen revision snapshot", () => {
    const input = fixture("valid-core-aggregate.v1.json") as {
      displayLabel: { observed: string };
      sourceReferences: Array<{ sourceLabel: string }>;
    };
    const decoded = decodeCoreAggregate(input);
    expect(decoded).not.toBeNull();
    const before = JSON.stringify(decoded);
    input.displayLabel.observed = "mutated after validation";
    input.sourceReferences[0]!.sourceLabel = "mutated source";
    expect(JSON.stringify(decoded)).toBe(before);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.displayLabel)).toBe(true);
    expect(Object.isFrozen(decoded?.sourceReferences)).toBe(true);
  });

  it("accepts serialized Draft integer-valued numbers", () => {
    const decoded = decodeCoreAggregate(fixture("valid-integral-float-core-aggregate.v1.json"));
    expect(decoded?.revision).toBe(1);
    expect(decoded?.sourceReferences[0]?.sourceRevision).toBe(1);
  });
});
