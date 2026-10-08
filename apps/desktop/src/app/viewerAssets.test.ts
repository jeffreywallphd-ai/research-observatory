import { describe, expect, it } from "vitest";
import { ViewerAssetPool } from "./viewerAssets";

describe("shared bundled-font and CMap storage", () => {
  it("admits overlapping chunks and concatenation against one shared allowance", async () => {
    const pool = new ViewerAssetPool(8 * 1024 * 1024);
    let first: ReadableStreamDefaultController<Uint8Array<ArrayBuffer>> | null = null;
    let second: ReadableStreamDefaultController<Uint8Array<ArrayBuffer>> | null = null;
    const a = new ReadableStream<Uint8Array<ArrayBuffer>>({ start(value) { first = value; } });
    const b = new ReadableStream<Uint8Array<ArrayBuffer>>({ start(value) { second = value; } });
    const reads = [pool.read(a), pool.read(b)];
    first!.enqueue(new Uint8Array(3 * 1024 * 1024)); second!.enqueue(new Uint8Array(3 * 1024 * 1024));
    await Promise.resolve(); await Promise.resolve();
    expect(pool.used).toBe(6 * 1024 * 1024);
    first!.close(); second!.close();
    const results = await Promise.allSettled(reads);
    expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(1);
    expect(results.filter((result) => result.status === "rejected")).toHaveLength(1);
    expect(pool.used).toBe(3 * 1024 * 1024);
    pool.close(); expect(pool.used).toBe(0);
  });
  it("releases failed input chunks and denies streams after close", async () => {
    const pool = new ViewerAssetPool(64);
    const input = new ReadableStream<Uint8Array<ArrayBuffer>>({ start(value) { value.enqueue(new Uint8Array(40)); value.close(); } });
    await expect(pool.read(input)).rejects.toThrow("viewer-resource-limit"); expect(pool.used).toBe(0);
    pool.close();
    await expect(pool.read(new ReadableStream())).rejects.toThrow("viewer-source-unavailable");
  });
});
