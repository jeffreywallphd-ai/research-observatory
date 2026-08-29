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

type JsonRecord = Record<string, unknown>;
const fixturePath = fileURLToPath(new URL("./fixtures/valid-source-acquired-event.v1.json", import.meta.url));
const fixture = (): JsonRecord => JSON.parse(readFileSync(fixturePath, "utf8")) as JsonRecord;
const uuid = (suffix: string): string => `018f47a2-4d6b-7f78-9f2e-7fb76c86${suffix}`;
const dataOf = (event: JsonRecord): JsonRecord => event.data as JsonRecord;
const activityOf = (event: JsonRecord): JsonRecord => dataOf(event).activity as JsonRecord;
const relationsOf = (event: JsonRecord): JsonRecord[] => dataOf(event).relations as JsonRecord[];
const reference = (entity: JsonRecord): JsonRecord => ({
  entityId: entity.entityId,
  revisionId: entity.revisionId,
});
const entitySubject = (event: JsonRecord, entity: JsonRecord): string =>
  `project/${event.projectid as string}/entity/${entity.entityKind as string}/${entity.entityId as string}/revision/${entity.revisionId as string}`;

function relation(
  relationId: string,
  relationType: string,
  entity: JsonRecord | null,
  relatedEntity: JsonRecord | null,
  activityId: string | null,
  agentId: string | null,
  occurredAt = "2026-08-29T15:00:01.000Z",
): JsonRecord {
  return { relationId, relationType, entity, relatedEntity, activityId, agentId, occurredAt };
}

function transformEvent(status: "succeeded" | "failed" | "cancelled" | "denied" = "succeeded"): JsonRecord {
  const event = fixture();
  event.type = "org.research-observatory.document.parsed.v1";
  const data = dataOf(event);
  const activity = activityOf(event);
  activity.activityType = "parsing";
  activity.status = status;
  const source = structuredClone((data.outputs as JsonRecord[])[0]!);
  const document = structuredClone(source);
  document.revisionId = uuid("dab3");
  document.entityKind = "document";
  document.contentHash = `sha256:${"3".repeat(64)}`;
  data.inputs = [source];
  data.outputs = status === "succeeded" ? [document] : [];
  event.subject = entitySubject(event, status === "succeeded" ? document : source);
  const activityId = activity.activityId as string;
  const agentId = (data.agent as JsonRecord).agentId as string;
  const eventRelations = [
    relation(uuid("daf4"), "used", reference(source), null, activityId, null),
    relation(uuid("daf2"), "wasAssociatedWith", null, null, activityId, agentId),
  ];
  if (status === "denied") eventRelations.splice(0, 1);
  if (status === "succeeded") {
    eventRelations.push(
      relation(uuid("daf1"), "wasGeneratedBy", reference(document), null, activityId, null),
      relation(uuid("daf5"), "wasDerivedFrom", reference(document), reference(source), activityId, null),
      relation(uuid("daf3"), "wasAttributedTo", reference(document), null, null, agentId),
    );
  }
  data.relations = eventRelations;
  return event;
}

function invalidationEvent(status: "succeeded" | "failed" | "cancelled" | "denied"): JsonRecord {
  const event = transformEvent(status === "succeeded" ? "failed" : status);
  event.type = "org.research-observatory.entity.invalidated.v1";
  const data = dataOf(event);
  const activity = activityOf(event);
  activity.activityType = "invalidation";
  activity.status = status;
  const input = (data.inputs as JsonRecord[])[0]!;
  event.subject = entitySubject(event, input);
  if (status === "succeeded") {
    data.relations = [
      relation(uuid("daf6"), "wasInvalidatedBy", reference(input), null, activity.activityId as string, null),
      relation(
        uuid("daf2"),
        "wasAssociatedWith",
        null,
        null,
        activity.activityId as string,
        (data.agent as JsonRecord).agentId as string,
      ),
    ];
  }
  return event;
}

function setTimes(event: JsonRecord, startedAt: string, endedAt: string): void {
  event.time = endedAt;
  const activity = activityOf(event);
  activity.startedAt = startedAt;
  activity.endedAt = endedAt;
  for (const item of relationsOf(event)) item.occurredAt = endedAt;
}

describe("portable provenance event contract", () => {
  it("decodes an immutable, content-minimized CloudEvent with exact PROV revision relations", () => {
    const input = fixture();
    expect(provenanceEventErrors(input)).toEqual([]);
    const decoded = decodeProvenanceEvent(input);
    expect(decoded).not.toBeNull();
    expect(isKnownProvenanceEvent(decoded!)).toBe(true);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.data.activity)).toBe(true);
    expect(Object.isFrozen(decoded?.data.outputs)).toBe(true);
    const before = canonicalProvenanceJson(decoded!);
    ((input.data as JsonRecord).agent as JsonRecord).role = "mutated";
    expect(canonicalProvenanceJson(decoded!)).toBe(before);
    expect(before).not.toContain("@example");
    expect(before).not.toContain("C:\\");
  });

  it("rejects sensitive fields, hostile keys, malformed identities, and unbound subjects", () => {
    const content = fixture();
    dataOf(content).rawPrompt = "unpublished text";
    expect(decodeProvenanceEvent(content)).toBeNull();
    const identity = fixture();
    (dataOf(identity).agent as JsonRecord).email = "person@example.test";
    expect(decodeProvenanceEvent(identity)).toBeNull();
    const trace = fixture();
    trace.traceparent = "00-00000000000000000000000000000000-0000000000000000-01";
    expect(decodeProvenanceEvent(trace)).toBeNull();
    const hostile = JSON.parse(JSON.stringify(fixture()).replace("{", '{"__proto__":{"secret":"x"},')) as unknown;
    expect(decodeProvenanceEvent(hostile)).toBeNull();
    const unbound = fixture();
    unbound.subject = (unbound.subject as string).replace(uuid("dab2"), uuid("da99"));
    expect(provenanceEventErrors(unbound)).toContain("subject-binds-exact-event-object");
    const wrongKind = fixture();
    wrongKind.subject = (wrongKind.subject as string).replace("entity/source-observation/", "entity/document/");
    expect(provenanceEventErrors(wrongKind)).toContain("subject-binds-exact-event-object");
  });

  it.each(["succeeded", "failed", "cancelled", "denied"] as const)(
    "accepts an exact revision-to-revision transform with %s outcome",
    (status) => {
      const event = transformEvent(status);
      expect(provenanceEventErrors(event)).toEqual([]);
      expect(decodeProvenanceEvent(event)).not.toBeNull();
    },
  );

  it.each(["succeeded", "failed", "cancelled", "denied"] as const)(
    "accepts a non-contradictory %s invalidation event",
    (status) => {
      expect(provenanceEventErrors(invalidationEvent(status))).toEqual([]);
    },
  );

  it("records a failed source acquisition against its exact activity without inventing an entity", () => {
    const failed = fixture();
    const data = dataOf(failed);
    const activity = activityOf(failed);
    activity.status = "failed";
    data.outputs = [];
    data.relations = relationsOf(failed).filter((item) => item.relationType === "wasAssociatedWith");
    failed.subject = `project/${failed.projectid as string}/activity/${activity.activityType as string}/${activity.activityId as string}`;
    expect(provenanceEventErrors(failed)).toEqual([]);
  });

  it("rejects contradictory outcome relations and every wrong entity role", () => {
    const deniedInvalidation = invalidationEvent("denied");
    const input = (dataOf(deniedInvalidation).inputs as JsonRecord[])[0]!;
    relationsOf(deniedInvalidation).push(
      relation(uuid("daf7"), "wasInvalidatedBy", reference(input), null, activityOf(deniedInvalidation).activityId as string, null),
    );
    expect(provenanceEventErrors(deniedInvalidation)).toEqual(expect.arrayContaining([
      "relation-outcome-matches-activity-status",
      "known-event-relations-match-operation",
    ]));

    const wrongCases: Array<(event: JsonRecord) => void> = [
      (event) => { relationsOf(event).find((item) => item.relationType === "used")!.entity = reference((dataOf(event).outputs as JsonRecord[])[0]!); },
      (event) => { relationsOf(event).find((item) => item.relationType === "wasGeneratedBy")!.entity = reference((dataOf(event).inputs as JsonRecord[])[0]!); },
      (event) => { relationsOf(event).find((item) => item.relationType === "wasAttributedTo")!.entity = reference((dataOf(event).inputs as JsonRecord[])[0]!); },
      (event) => {
        const derived = relationsOf(event).find((item) => item.relationType === "wasDerivedFrom")!;
        derived.entity = reference((dataOf(event).inputs as JsonRecord[])[0]!);
        derived.relatedEntity = reference((dataOf(event).outputs as JsonRecord[])[0]!);
      },
    ];
    for (const mutate of wrongCases) {
      const event = transformEvent();
      mutate(event);
      expect(provenanceEventErrors(event)).toContain("relation-roles-match-event-objects");
    }

    const acquiredAndInvalidated = fixture();
    const acquired = (dataOf(acquiredAndInvalidated).outputs as JsonRecord[])[0]!;
    relationsOf(acquiredAndInvalidated).push(
      relation(uuid("daf7"), "wasInvalidatedBy", reference(acquired), null, activityOf(acquiredAndInvalidated).activityId as string, null),
    );
    expect(provenanceEventErrors(acquiredAndInvalidated)).toEqual(expect.arrayContaining([
      "relation-roles-match-event-objects",
      "known-event-relations-match-operation",
    ]));
  });

  it("requires unique relation identities, facts, and exact revision endpoints", () => {
    const duplicate = transformEvent();
    relationsOf(duplicate).push(structuredClone(relationsOf(duplicate)[0]!));
    expect(provenanceEventErrors(duplicate)).toContain("relation-identities-and-facts-are-unique");

    const reusedId = transformEvent();
    const distinct = structuredClone(relationsOf(reusedId)[0]!);
    distinct.occurredAt = "2026-08-29T15:00:00.500Z";
    relationsOf(reusedId).push(distinct);
    expect(provenanceEventErrors(reusedId)).toContain("relation-identities-and-facts-are-unique");

    const wrongRevision = transformEvent();
    (relationsOf(wrongRevision).find((item) => item.relationType === "used")!.entity as JsonRecord).revisionId = uuid("da99");
    expect(provenanceEventErrors(wrongRevision)).toContain("relations-close-over-event-objects");
  });

  it("stores a structurally valid future event type without interpreting its catalog meaning", () => {
    const unknown = fixture();
    unknown.type = "org.research-observatory.future.observed.v2";
    activityOf(unknown).activityType = "future-observation";
    const decoded = decodeProvenanceEvent(unknown);
    expect(decoded).not.toBeNull();
    expect(isKnownProvenanceEvent(decoded!)).toBe(false);
  });

  it("uses the same schema-compatible UTC range and canonical ordering", () => {
    const yearZero = fixture();
    setTimes(yearZero, "0000-01-01T00:00:00.000Z", "0000-01-01T00:00:01.000Z");
    expect(decodeProvenanceEvent(yearZero)).toBeNull();
    expect(() => canonicalProvenanceJson(yearZero)).toThrow("invalid provenance event");
    const minimum = fixture();
    setTimes(minimum, "0001-01-01T00:00:00.000Z", "0001-01-01T00:00:01.000Z");
    expect(decodeProvenanceEvent(minimum)).not.toBeNull();
    expect(canonicalProvenanceJson(JSON.parse(canonicalProvenanceJson(minimum)) as JsonRecord)).toBe(
      canonicalProvenanceJson(minimum),
    );
    const maximum = fixture();
    setTimes(maximum, "9999-12-31T23:59:58.999Z", "9999-12-31T23:59:59.999Z");
    expect(decodeProvenanceEvent(maximum)).not.toBeNull();
    expect(canonicalProvenanceJson(JSON.parse(canonicalProvenanceJson(maximum)) as JsonRecord)).toBe(
      canonicalProvenanceJson(maximum),
    );

    const canonicalSchema = readFileSync(fileURLToPath(new URL("./provenance-event.schema.json", import.meta.url)), "utf8").replace(/\r\n?/g, "\n");
    expect(createHash("sha256").update(Buffer.from(canonicalSchema, "utf8")).digest("hex")).toBe(PROVENANCE_SCHEMA_SHA256);
    const first = canonicalProvenanceJson(fixture());
    expect(canonicalProvenanceJson(JSON.parse(first) as JsonRecord)).toBe(first);
  });
});
