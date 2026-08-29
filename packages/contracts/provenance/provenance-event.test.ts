import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  PROVENANCE_SCHEMA_SHA256,
  canonicalProvenanceJson,
  decodeProvenanceEvent,
  isKnownProvenanceEvent,
  provenanceEventErrors,
} from "./generated";

const fixturePath = fileURLToPath(new URL("./fixtures/valid-source-acquired-event.v1.json", import.meta.url));
const fixture = (): Record<string, unknown> => JSON.parse(readFileSync(fixturePath, "utf8")) as Record<string, unknown>;

describe("portable provenance event contract", () => {
  it("decodes an immutable, content-minimized CloudEvent with PROV relations", () => {
    const input = fixture();
    expect(provenanceEventErrors(input)).toEqual([]);
    const decoded = decodeProvenanceEvent(input);
    expect(decoded).not.toBeNull();
    expect(isKnownProvenanceEvent(decoded!)).toBe(true);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.data.activity)).toBe(true);
    expect(Object.isFrozen(decoded?.data.outputs)).toBe(true);
    const before = canonicalProvenanceJson(decoded!);
    ((input.data as Record<string, unknown>).agent as Record<string, unknown>).role = "mutated";
    expect(canonicalProvenanceJson(decoded!)).toBe(before);
    expect(before).not.toContain("@example");
    expect(before).not.toContain("C:\\");
  });

  it("rejects raw content, personal fields, hostile keys, and malformed trace context", () => {
    const content = fixture();
    (content.data as Record<string, unknown>).rawPrompt = "unpublished text";
    expect(decodeProvenanceEvent(content)).toBeNull();
    const identity = fixture();
    ((identity.data as Record<string, unknown>).agent as Record<string, unknown>).email = "person@example.test";
    expect(decodeProvenanceEvent(identity)).toBeNull();
    const trace = fixture();
    trace.traceparent = "00-00000000000000000000000000000000-0000000000000000-01";
    expect(decodeProvenanceEvent(trace)).toBeNull();
    const hostile = JSON.parse(JSON.stringify(fixture()).replace("{", '{"__proto__":{"secret":"x"},')) as unknown;
    expect(decodeProvenanceEvent(hostile)).toBeNull();
    const subject = fixture();
    subject.subject = "project/550e8400-e29b-41d4-a716-446655440000/source-observation/------------------------------------";
    expect(decodeProvenanceEvent(subject)).toBeNull();
  });

  it("requires actor, time, project, inputs, outputs, configuration, and PROV relations to agree", () => {
    const actor = fixture();
    actor.actorid = "018f47a2-4d6b-7f78-9f2e-7fb76c86dbb1";
    expect(provenanceEventErrors(actor)).toContain("actor-and-agent-match");
    const time = fixture();
    ((time.data as Record<string, unknown>).activity as Record<string, unknown>).startedAt = "2026-08-29T15:00:02.000Z";
    ((time.data as Record<string, unknown>).activity as Record<string, unknown>).endedAt = "2026-08-29T15:00:01.500Z";
    expect(provenanceEventErrors(time)).toEqual(expect.arrayContaining(["activity-time-is-ordered", "event-time-matches-activity-end"]));
    const relation = fixture();
    ((relation.data as Record<string, unknown>).relations as unknown[]).splice(0, 1);
    expect(provenanceEventErrors(relation)).toContain("output-generation-relations-are-complete");
    const overlap = fixture();
    const data = overlap.data as Record<string, unknown>;
    data.inputs = structuredClone(data.outputs);
    expect(provenanceEventErrors(overlap)).toContain("input-output-sets-are-disjoint");
  });

  it("stores structurally valid future event types without interpreting them", () => {
    const unknown = fixture();
    unknown.type = "org.research-observatory.future.observed.v2";
    ((unknown.data as Record<string, unknown>).activity as Record<string, unknown>).activityType = "future-observation";
    const decoded = decodeProvenanceEvent(unknown);
    expect(decoded).not.toBeNull();
    expect(isKnownProvenanceEvent(decoded!)).toBe(false);
  });

  it("records a failed source acquisition without inventing an output entity", () => {
    const failed = fixture();
    const data = failed.data as Record<string, unknown>;
    (data.activity as Record<string, unknown>).status = "failed";
    data.outputs = [];
    data.relations = (data.relations as Array<Record<string, unknown>>).filter(
      (relation) => relation.relationType === "wasAssociatedWith",
    );
    expect(provenanceEventErrors(failed)).toEqual([]);
    expect(decodeProvenanceEvent(failed)).not.toBeNull();
  });

  it("binds both runtimes to exact schema bytes and canonical ordering", () => {
    const canonicalSchema = readFileSync(fileURLToPath(new URL("./provenance-event.schema.json", import.meta.url)), "utf8").replace(/\r\n?/g, "\n");
    expect(createHash("sha256").update(Buffer.from(canonicalSchema, "utf8")).digest("hex")).toBe(PROVENANCE_SCHEMA_SHA256);
    const first = canonicalProvenanceJson(fixture());
    const reordered = JSON.parse(first) as Record<string, unknown>;
    expect(canonicalProvenanceJson(reordered)).toBe(first);
  });
});
