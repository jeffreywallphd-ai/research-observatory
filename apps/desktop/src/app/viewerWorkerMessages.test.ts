import { describe, expect, it } from "vitest";
import { viewerMessageFootprint } from "./viewerWorkerMessages";

describe("decoded PDF message admission", () => {
  it("counts shared backing stores once and retains every child object identity", () => {
    const buffer = new ArrayBuffer(128), child = { image: new Uint8Array(buffer) };
    const data = { first: child, repeated: child, alias: new Uint8Array(buffer) };
    const footprint = viewerMessageFootprint(data);
    expect(footprint.buffers).toEqual([buffer]);
    expect(footprint.objects).toContain(child); expect(footprint.objects).toContain(buffer);
    expect(footprint.objects.filter((item) => item === child)).toHaveLength(1);
    expect(footprint.bytes).toBe(128 + 4 * 48);
  });
  it("denies oversized decoded buffers, excessive text and accessors before cloning", () => {
    expect(() => viewerMessageFootprint({ image: new ArrayBuffer(16 * 1024 * 1024 + 1) })).toThrow("viewer-resource-limit");
    expect(() => viewerMessageFootprint({ text: "x".repeat(8 * 1024 * 1024 + 1) })).toThrow("viewer-resource-limit");
    let invoked = false;
    const data = Object.defineProperty({}, "image", { get: () => { invoked = true; return new ArrayBuffer(16); } });
    expect(() => viewerMessageFootprint(data)).toThrow("viewer-resource-limit"); expect(invoked).toBe(false);
  });
  it("includes Map and Set members and denies other hidden native storage", () => {
    const buffer = new ArrayBuffer(128), map = new Map([["image", buffer]]), set = new Set([map, buffer]);
    const result = viewerMessageFootprint(set);
    expect(result.buffers).toEqual([buffer]);
    expect(result.objects).toEqual(expect.arrayContaining([map, set, buffer]));
    expect(result.bytes).toBeGreaterThanOrEqual(128 + 10);
    expect(() => viewerMessageFootprint(new Map([["image", new ArrayBuffer(16 * 1024 * 1024 + 1)]]))).toThrow("viewer-resource-limit");
    expect(() => viewerMessageFootprint(new Blob([new Uint8Array(32)]))).toThrow("viewer-resource-limit");
    expect(() => viewerMessageFootprint(new Array(100001))).toThrow("viewer-resource-limit");
    class SdkRecord { readonly value = buffer; }
    expect(viewerMessageFootprint(new SdkRecord()).buffers).toEqual([buffer]);
  });
});
