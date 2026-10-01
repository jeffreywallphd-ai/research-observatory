import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeCorpusItemRevision } from "./generated";

const root = "C:/Research/synthetic";
const id = (ordinal: number) => `01900000-0000-7000-8000-${ordinal.toString().padStart(12, "0")}`;
const source = () => ({ kind: "import-member" as const, contextId: id(1), revisionId: id(2),
  ordinal: 1, recordKey: "a".repeat(64) });
const item = () => ({ schemaVersion: "1.0" as const, projectId: id(3), itemId: id(4), revisionId: id(5),
  previousRevisionId: null, workId: id(6), workRevisionId: id(7), membership: "candidate" as const,
  review: "pending" as const, duplicateOfItemId: null, availability: "unknown" as const,
  discoveryPathIds: [id(8)], decisionRevisionId: null });
const response = (value: unknown) => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32),
  etag: null, body: JSON.stringify(value) });

describe("bounded corpus Core client", () => {
  it("validates the initial candidate projection and rejects fabricated authority", () => {
    expect(decodeCorpusItemRevision(item())).toEqual(item());
    expect(decodeCorpusItemRevision({ ...item(), membership: "included" })).toBeNull();
    expect(decodeCorpusItemRevision({ ...item(), actorId: id(9) })).toBeNull();
    expect(decodeCorpusItemRevision({ ...item(), discoveryPathIds: [id(8), id(8)] })).toBeNull();
    expect(decodeCorpusItemRevision({ ...item(), previousRevisionId: id(9) })).toBeNull();
    const included = { ...item(), revisionId: id(9), previousRevisionId: id(5),
      decisionRevisionId: id(10), membership: "included" as const };
    expect(decodeCorpusItemRevision(included)).toEqual(included);
    expect(decodeCorpusItemRevision({ ...included, decisionRevisionId: null })).toBeNull();
  });

  it("binds create and inspect replies to requested Work and item identities", async () => {
    let reply: unknown = item();
    const paths: string[] = [];
    const client = createCoreApiClient(async (request) => { paths.push(request.path); return response(reply); });
    const create = { root, commandId: id(10), workId: id(6), workRevisionId: id(7), source: source() };
    await expect(client.createCorpusItem(create)).resolves.toEqual(item());
    reply = { ...item(), workRevisionId: id(11) };
    await expect(client.createCorpusItem(create)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    reply = item();
    await expect(client.inspectCorpusItem({ root, itemId: id(4) })).resolves.toEqual(item());
    await expect(client.inspectCorpusItem({ root, itemId: id(11) })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    expect(paths).toEqual(["/projects/corpus/create", "/projects/corpus/create",
      "/projects/corpus/inspect", "/projects/corpus/inspect"]);
  });

  it("denies untrusted source, actor, and accessor commands before transport", async () => {
    let calls = 0;
    const client = createCoreApiClient(async () => { calls += 1; return response(item()); });
    const command = { root, commandId: id(10), workId: id(6), workRevisionId: id(7), source: source() };
    await expect(client.createCorpusItem({ ...command, source: { ...source(), recordKey: null } })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.createCorpusItem({ ...command, actorId: id(9) } as any)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.createCorpusItem({ ...command, get source() { return source(); } })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(calls).toBe(0);
  });
});
