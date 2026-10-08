import { describe, expect, it, vi } from "vitest";
import { decodeViewerMetadata, decodeViewerText, viewerSourcesMatch, ViewerBufferBudget, ViewerByteSession } from "./documentViewer";
import { sourceAnchorFixture } from "../../../../tests/desktop/fixtures/anchor-contract";
import { decodeSourceAnchor } from "./sourceAnchors";

const fixture = sourceAnchorFixture();
const source = decodeSourceAnchor(fixture, "00000000-0000-7000-8000-000000000001", "00000000-0000-7000-8000-000000000003")!.target.source;
const selector = { attachmentId: source.attachmentId, documentRevisionId: source.documentRevisionId, normalizedRevisionId: null };
describe("controlled viewer source bytes", () => {
  it("binds metadata to the exact original and rejects injected paths and revisions", () => {
    const value = { source, normalizedRevisionId: null };
    expect(decodeViewerMetadata(value, source.projectId, selector)?.source).toEqual(source);
    expect(decodeViewerMetadata({ ...value, path: "untrusted" }, source.projectId, selector)).toBeNull();
    expect(decodeViewerMetadata({ ...value, source: { ...source, documentRevisionId: source.attachmentId } }, source.projectId, selector)).toBeNull();
  });
  it("reserves before an oversized canvas or source can enter the aggregate budget", () => {
    const budget = new ViewerBufferBudget();
    const releaseWorker = budget.reserve(144 * 1024 * 1024);
    const releaseRanges = budget.reserve(54 * 1024 * 1024);
    expect(() => budget.reserve(64 * 1024 * 1024)).toThrow("viewer-resource-limit");
    expect(budget.used).toBe(198 * 1024 * 1024);
    releaseRanges(); releaseRanges(); releaseWorker();
    expect(budget.used).toBe(0);
    for (const size of [NaN, Infinity, -1, 1.5]) expect(() => budget.reserve(size)).toThrow();
  });
  it("coalesces an exact request, cancels on close and denies late bytes", async () => {
    let resolve: (bytes: ArrayBuffer | null) => void = () => undefined;
    let calls = 0, cancellations = 0;
    const session = new ViewerByteSession(source.projectId, selector, { source, normalizedRevisionId: null }, {
      source: async () => null,
      range: async (_project, _selector, _request, _start, _end, signal) => {
        calls += 1;
        signal.addEventListener("abort", () => { cancellations += 1; }, { once: true });
        return new Promise<ArrayBuffer | null>((complete) => { resolve = complete; });
      },
    }, new ViewerBufferBudget());
    const first = session.read(0, 4);
    const duplicate = session.read(0, 4);
    expect(calls).toBe(1);
    session.close();
    resolve(new ArrayBuffer(4));
    await expect(first).rejects.toThrow("viewer-source-unavailable");
    await expect(duplicate).rejects.toThrow("viewer-source-unavailable");
    expect(cancellations).toBe(1);
    expect(session.budget.used).toBe(0);
    await expect(session.read(0, 4)).rejects.toThrow();
  });
  it("denies malformed ranges and byte-length mismatch without an original-sized copy", async () => {
    let calls = 0;
    const session = new ViewerByteSession(source.projectId, selector, { source, normalizedRevisionId: null }, {
      source: async () => null,
      range: async () => { calls += 1; return new ArrayBuffer(3); },
    }, new ViewerBufferBudget());
    for (const [start, end] of [[-1, 4], [0, 0], [0, 1048577], [0, Infinity], [0.5, 4]]) {
      await expect(session.read(start!, end!)).rejects.toThrow();
    }
    expect(calls).toBe(0);
    await expect(session.read(0, 4)).rejects.toThrow("viewer-source-unavailable");
    expect(session.budget.used).toBe(0);
    session.close();
  });
  it("binds bounded Unicode text to its accepted revision, element and offset", () => {
    const selected = { ...selector, normalizedRevisionId: "00000000-0000-7000-8000-000000000011" };
    const nodeId = "00000000-0000-7000-8000-000000000012";
    const value = { metadata: { source, normalizedRevisionId: selected.normalizedRevisionId }, nodeId,
      nodeKind: "paragraph", pageNumber: 1, offset: 0, text: "A😀e", nextOffset: 3 };
    expect(decodeViewerText(value, source.projectId, selected, nodeId, 0)?.text).toBe("A😀e");
    for (const changed of [{ ...value, offset: 1 }, { ...value, nextOffset: 4 }, { ...value, nodeId: source.attachmentId },
      { ...value, text: "x".repeat(4097) }, { ...value, path: "untrusted" }, { ...value, pageNumber: 501 }]) {
      expect(decodeViewerText(changed, source.projectId, selected, nodeId, 0)).toBeNull();
    }
    expect(viewerSourcesMatch(source, { ...source, workRevisionId: nodeId })).toBe(false);
    expect(viewerSourcesMatch(source, { ...source })).toBe(true);
  });
  it("retains unknown physical-drain failure after transport settlement and denies replacement", async () => {
    let fail: (error: Error) => void = () => undefined;
    const budget = new ViewerBufferBudget();
    const session = new ViewerByteSession(source.projectId, selector, { source, normalizedRevisionId: null }, {
      source: async () => null,
      range: async () => new Promise<ArrayBuffer | null>((_resolve, reject) => { fail = reject; }),
    }, budget);
    const read = session.read(0, 4);
    session.close();
    fail(new Error("viewer-owned-read-drain-pending"));
    await expect(read).rejects.toThrow("viewer-owned-read-drain-pending");
    await expect(session.drain()).rejects.toThrow("viewer-owned-read-drain-pending");
    expect(() => session.fresh()).toThrow("viewer-owned-read-drain-pending");
    expect(budget.used).toBe(4 * 6 + 8192);
  });
  it("latches a drain deadline even when the actual owner acknowledges closure later", async () => {
    vi.useFakeTimers();
    try {
      let closeOwner: () => void = () => undefined;
      const session = new ViewerByteSession(source.projectId, selector, { source, normalizedRevisionId: null }, {
        source: async () => null,
        range: async () => new Promise<null>((resolve) => { closeOwner = () => resolve(null); }),
      }, new ViewerBufferBudget());
      const read = session.read(0, 4);
      const stopped = expect(read).rejects.toThrow("viewer-source-unavailable");
      session.close();
      const drain = expect(session.drain()).rejects.toThrow("viewer-owned-read-drain-pending");
      await vi.advanceTimersByTimeAsync(1000);
      await drain;
      expect(() => session.fresh()).toThrow("viewer-owned-read-drain-pending");
      expect(session.budget.used).toBe(4 * 6 + 8192);
      closeOwner(); await stopped;
      expect(session.budget.used).toBe(0);
      await expect(session.drain()).rejects.toThrow("viewer-owned-read-drain-pending");
    } finally { vi.useRealTimers(); }
  });
});
