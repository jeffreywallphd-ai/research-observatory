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
  });
});
