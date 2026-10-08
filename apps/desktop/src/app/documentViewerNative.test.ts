import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nativeDocumentViewerPort } from "./documentViewer";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
const projectId = "00000000-0000-7000-8000-000000000001";
const requestId = "00000000-0000-7000-8000-000000000002";
const selector = { attachmentId: "00000000-0000-7000-8000-000000000003",
  documentRevisionId: "00000000-0000-7000-8000-000000000004", normalizedRevisionId: null };

// Explicit IPC doubles: these test terminal-disposition consumption, not the
// physical Native/Core boundary, which has separate encrypted-reader proof.
describe("native range terminal acknowledgement", () => {
  beforeEach(() => { invoke.mockReset(); vi.stubGlobal("window", { __TAURI_INTERNALS__: {} }); });
  afterEach(() => vi.unstubAllGlobals());
  it("does not use settled cancel IPC as evidence that the original read closed", async () => {
    let finish: (failure: unknown) => void = () => undefined;
    invoke.mockImplementation((command: string) => command === "document_viewer_cancel" ? Promise.resolve()
      : new Promise((_resolve, reject) => { finish = reject; }));
    const stop = new AbortController();
    const read = nativeDocumentViewerPort.range(projectId, selector, requestId, 0, 4, stop.signal);
    let settled = false; void read.then(() => { settled = true; });
    stop.abort();
    await Promise.resolve();
    expect(invoke).toHaveBeenCalledWith("document_viewer_cancel", { request: { schemaVersion: "1.0", projectId, requestId } });
    expect(settled).toBe(false);
    finish({ schemaVersion: "1.0", projectId, requestId, drained: true });
    expect(await read).toBeNull();
  });
  it("denies unknown, failed, substituted and injected acknowledgements", async () => {
    const ack = { schemaVersion: "1.0", projectId, requestId, drained: true };
    for (const failure of [new Error("transport lost"), { ...ack, drained: false },
      { ...ack, requestId: selector.attachmentId }, { ...ack, projectId: requestId },
      { ...ack, root: "untrusted" }, { ...ack, drained: "true" }]) {
      invoke.mockRejectedValueOnce(failure);
      await expect(nativeDocumentViewerPort.range(projectId, selector, requestId, 0, 4, new AbortController().signal))
        .rejects.toThrow("viewer-owned-read-drain-pending");
    }
  });
  it("denies malformed raw responses and accepts only the exact bounded bytes", async () => {
    invoke.mockResolvedValueOnce(new ArrayBuffer(3));
    await expect(nativeDocumentViewerPort.range(projectId, selector, requestId, 0, 4, new AbortController().signal))
      .rejects.toThrow("viewer-owned-read-drain-pending");
    invoke.mockResolvedValueOnce(new ArrayBuffer(4));
    expect((await nativeDocumentViewerPort.range(projectId, selector, requestId, 0, 4, new AbortController().signal))?.byteLength).toBe(4);
  });
});
