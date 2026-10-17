import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeSearchPage, decodeSearchExplanation } from "./generated";

const id = (ordinal: number) => `01900000-0000-7000-8000-${ordinal.toString().padStart(12, "0")}`;
const hash = "a".repeat(64);
const root = "C:/Research/synthetic";
const execution = () => ({ projectId: id(1), searchRunId: id(2), revisionId: id(3), jobId: id(4),
  generationId: id(5), sourceWatermark: 12, inputSha256: hash, resultSha256: hash, resultCount: 1,
  validatedAt: "2026-10-17T00:00:00.000Z", expiresAt: null,
  originalQuery: "café", normalizedQuery: '"café"', filters: { yearFrom: null, yearTo: null },
  rankingVersion: "ro-lexical-best-row-per-leaf-bm25-1", fieldWeights: [8, 4, 1, 2, 2, 10, 1, 1],
  scoreMeaning: "weighted-bm25-relevance", semanticState: "unqualified", rerankState: "not-run" });
const hit = () => ({ itemId: id(6), workId: id(7), workRevisionId: id(8), position: 1, score: 0.125,
  title: "Synthetic café", titleTruncated: false, year: 2020,
  snippet: { field: "title", start: 0, end: 6, text: "😀 café", highlights: [{ start: 2, end: 6 }], truncated: false },
  source: null });
const page = () => ({ execution: execution(), afterCursor: null, startPosition: 0, hits: [hit()], nextCursor: null });
const response = (value: unknown) => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32),
  etag: null, body: JSON.stringify(value) });

describe("bounded generated lexical search client", () => {
  it("preserves actual finite scores and codepoint highlights, rejects fabricated method and ranges", () => {
    expect(decodeSearchPage(page())).toEqual(page());
    expect(Object.isFrozen(decodeSearchPage(page())?.hits)).toBe(true);
    for (const score of [NaN, Infinity, -1]) expect(decodeSearchPage({ ...page(), hits: [{ ...hit(), score }] })).toBeNull();
    expect(decodeSearchPage({ ...page(), execution: { ...execution(), fieldWeights: [1, 1, 1, 1, 1, 1, 1, 1] } })).toBeNull();
    expect(decodeSearchPage({ ...page(), execution: { ...execution(), semanticState: "qualified" } })).toBeNull();
    expect(decodeSearchPage({ ...page(), hits: [{ ...hit(), snippet: { ...hit().snippet, highlights: [{ start: 2, end: 7 }] } }] })).toBeNull();
    expect(decodeSearchPage({ ...page(), hits: [hit(), hit()] })).toBeNull();
    expect(decodeSearchPage({ ...page(), probability: 0.9 })).toBeNull();
    expect(decodeSearchPage({ ...page(), execution: { ...execution(), resultCount: 2 } })).toBeNull();
    expect(decodeSearchPage({ ...page(), hits: [] })).toBeNull();
  });

  it("binds page and explanation replies to exact project, run and requested item", async () => {
    let reply: unknown = page();
    const requests: string[] = [];
    const client = createCoreApiClient(async (request) => { requests.push(request.path); return response(reply); });
    const command = { root, projectId: id(1), jobId: id(4), after: null, limit: 50 };
    await expect(client.pageLexicalSearch(command)).resolves.toEqual(page());
    reply = { ...page(), execution: { ...execution(), jobId: id(9) } };
    await expect(client.pageLexicalSearch(command)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    const explanation = { execution: execution(), itemId: id(6), score: 0.125,
      components: [{ leafSha256: hash, entryId: hash, field: null, matchKind: "literal", score: 0.125 }],
      filterEffect: "membership-only; statistical universe unchanged" };
    expect(decodeSearchExplanation(explanation)).toEqual(explanation);
    expect(decodeSearchExplanation({ ...explanation, score: 0.5 })).toBeNull();
    reply = explanation;
    await expect(client.explainLexicalSearch({ root, projectId: id(1), jobId: id(4), itemId: id(6) })).resolves.toEqual(explanation);
    await expect(client.explainLexicalSearch({ root, projectId: id(1), jobId: id(4), itemId: id(9) })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    expect(requests[0]).toBe("/projects/search/page");
    reply = page();
    const cursor = btoa(JSON.stringify({ nextPosition: 1, revisionId: id(3) })).replace(/=+$/, "");
    await expect(client.pageLexicalSearch({ ...command, after: cursor })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("binds the queued run acknowledgement to the originating command", async () => {
    let job = { projectId: id(1), commandId: id(10), jobId: id(4), workflowRunId: id(11), state: "runnable",
      attemptCount: 0, cancellationRequested: false, diagnosticCode: null };
    const client = createCoreApiClient(async () => response(job));
    const command = { root, projectId: id(1), commandId: id(10), query: "synthetic", filters: { yearFrom: null, yearTo: null } };
    await expect(client.executeLexicalSearch(command)).resolves.toEqual(job);
    job = { ...job, commandId: id(12) };
    await expect(client.executeLexicalSearch(command)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("rejects claimed actors, sessions and accessors before any transport", async () => {
    let calls = 0;
    const client = createCoreApiClient(async () => { calls += 1; return response(page()); });
    const command = { root, projectId: id(1), commandId: id(10), query: "synthetic", filters: { yearFrom: null, yearTo: null } };
    await expect(client.executeLexicalSearch({ ...command, actorId: id(11) } as any)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.executeLexicalSearch({ ...command, sessionId: "a".repeat(32) } as any)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.executeLexicalSearch({ ...command, get query(): string { throw new Error("must not execute accessor"); } })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(calls).toBe(0);
  });
});
