import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";
import { boundPdfWorkerRanges } from "../../pdfjsWorkerBuild";

const upstream = readFileSync("node_modules/pdfjs-dist/build/pdf.worker.mjs", "utf8");

interface RangeManager {
  sendRequest(begin: number, end: number): Promise<void>;
  abort(reason: Error): void;
  requestAllChunks(noFetch: boolean): Promise<unknown>;
  onReceiveData(data: { begin: number; chunk: ArrayBuffer }): void;
}
function requestFixture() {
  const source = boundPdfWorkerRanges(upstream);
  const declaration = source.match(/class ChunkedStreamManager \{[\s\S]*?\n\}\n\n;\/\//u)?.[0].replace(/\n\n;\/\/$/u, "");
  expect(declaration).toBeTruthy();
  const started: number[] = [], received: number[] = [];
  const releases: (() => void)[] = [];
  let active = 0, maximum = 0;
  const stream = {
    getRangeReader(begin: number) {
      started.push(begin); active += 1; maximum = Math.max(maximum, active);
      let read = false;
      const ready = new Promise<void>((resolve) => releases.push(resolve));
      return { async read() {
        if (read) { active -= 1; return { done: true }; }
        read = true; await ready; return { value: new Uint8Array([begin]).buffer, done: false };
      } };
    },
    cancelAllRequests() { for (const release of releases) release(); },
  };
  type ReaderStream = typeof stream;
  const Manager = runInNewContext(`(${declaration})`, {
    ChunkedStream: class {},
    arrayBuffersToBytes: (buffers: ArrayBuffer[]) => new Uint8Array(buffers[0]!),
  }) as new (readerStream: ReaderStream, options: object) => RangeManager;
  const manager = new Manager(stream, { length: 128 * 1024 * 1024, rangeChunkSize: 65536, disableAutoFetch: true });
  manager.onReceiveData = ({ begin }) => { received.push(begin); };
  void manager.requestAllChunks(true).catch(() => undefined);
  return { manager, started, received, releases, maximum: () => maximum };
}

describe("pinned local PDF worker range admission", () => {
  it("schedules the actual SDK range readers before Core admission", async () => {
    const fixture = requestFixture();
    const pending = Array.from({ length: 14 }, (_, index) => fixture.manager.sendRequest(index, index + 1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fixture.started).toEqual([0]);
    for (let index = 0; index < pending.length; index += 1) {
      fixture.releases[index]!();
      await pending[index];
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    expect(fixture.maximum()).toBe(1);
    expect(fixture.received).toEqual(Array.from({ length: 14 }, (_, index) => index));
  });
  it("does not admit deferred SDK requests after document cancellation", async () => {
    const fixture = requestFixture();
    const pending = Array.from({ length: 14 }, (_, index) => fixture.manager.sendRequest(index, index + 1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.manager.abort(new Error("test-document-closed"));
    await Promise.all(pending);
    expect(fixture.started).toEqual([0]);
    expect(fixture.received).toEqual([]);
  });
  it("bounds the real worker's contiguous and sparse requests without omitting chunks", () => {
    const transformed = boundPdfWorkerRanges(upstream);
    const method = transformed.match(/  groupChunks\(chunks\) \{[\s\S]*?\n  \}\n  onReceiveData/u)?.[0].replace(/\n  onReceiveData$/u, "");
    expect(method).toBeTruthy();
    // Execute the pinned worker's actual method, not a duplicate implementation.
    const manager = runInNewContext(`({ chunkSize: 65536, ${method} })`) as {
      groupChunks(chunks: number[]): { beginChunk: number; endChunk: number }[];
    };
    for (const chunks of [[], Array.from({ length: 2048 }, (_, index) => index), [0, 1, 4, 5, 40, 41]]) {
      const groups = manager.groupChunks(chunks);
      expect(groups.every((group) => (group.endChunk - group.beginChunk) * 65536 <= 1048576)).toBe(true);
      expect(groups.flatMap((group) => Array.from({ length: group.endChunk - group.beginChunk }, (_, index) => index + group.beginChunk))).toEqual(chunks);
    }
  });
  it("fails closed on an unreviewed dependency or changed patch location", () => {
    expect(() => boundPdfWorkerRanges(upstream + "\n")).toThrow("pdf-worker-pin-mismatch");
    expect(() => boundPdfWorkerRanges(upstream.replace("prevChunk + 1 !== chunk", "false"))).toThrow("pdf-worker-pin-mismatch");
  });
});
