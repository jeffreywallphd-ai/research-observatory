import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";
import { installViewerWorkerQuota } from "./viewerWorkerQuota";

describe("dedicated viewer worker backing stores", () => {
  it("configures the authenticated source allowance once and rejects excess before construction", () => {
    const result = runInNewContext(`
      const mib = 1024 * 1024;
      const quota = (${installViewerWorkerQuota.toString()})(globalThis, 16 * mib);
      new Uint8Array(1);
      let invalid = false, repeated = false, denied = false;
      try { quota.configure(145 * mib); } catch { invalid = true; }
      quota.configure(26 * mib);
      const source = new Uint8Array(10 * mib);
      try { quota.configure(144 * mib); } catch { repeated = true; }
      try { new Uint8Array(16 * mib); } catch { denied = true; }
      ({ invalid, repeated, denied, used: quota.used(), sourceLength: source.length });
    `) as unknown;
    expect(result).toEqual({ invalid: true, repeated: true, denied: true, used: 10 * 1024 * 1024 + 1, sourceLength: 10 * 1024 * 1024 });
  });
  it("admits allocations before construction and counts copies but not aliases", () => {
    const result = runInNewContext(`
      const quota = (${installViewerWorkerQuota.toString()})(globalThis, 256);
      const original = new Uint8Array(128);
      const alias = new Uint8Array(original.buffer, 0, 64);
      const copy = original.slice(0, 64);
      const slicedBuffer = original.buffer.slice(0, 32);
      let denied = false;
      try { new Float64Array(8); } catch { denied = true; }
      ({ used: quota.used(), denied, sourceLength: original.length, aliasLength: alias.length,
        copyLength: copy.length, slicedLength: slicedBuffer.byteLength });
    `) as unknown;
    expect(result).toEqual({ used: 224, denied: true, sourceLength: 128, aliasLength: 64, copyLength: 64, slicedLength: 32 });
  });
  it("closes growable, native allocation and network escape paths", async () => {
    const result = await runInNewContext(`
      (${installViewerWorkerQuota.toString()})(globalThis, 256);
      let resizable = false, resize = false, transfer = false;
      try { new ArrayBuffer(32, { maxByteLength: 512 }); } catch { resizable = true; }
      const buffer = new ArrayBuffer(32);
      try { buffer.resize(512); } catch { resize = true; }
      try { buffer.transfer(512); } catch { transfer = true; }
      fetch(['https:', '', 'untrusted.invalid'].join('/')).then(() => null, () => ({ resizable, resize, transfer,
        shared: typeof SharedArrayBuffer, wasm: typeof WebAssembly, canvas: typeof OffscreenCanvas }));
    `) as unknown;
    expect(result).toEqual({ resizable: true, resize: true, transfer: true, shared: "undefined", wasm: "undefined", canvas: "undefined" });
  });
  it("admits the font encoder's native result before encoding and denies native clone paths", () => {
    const result = runInNewContext(`
      const nativeBytes = Uint8Array;
      let calls = 0;
      class TextEncoder { encode(input) { calls++; return new nativeBytes(input.length); } }
      globalThis.TextEncoder = TextEncoder;
      globalThis.structuredClone = value => value;
      const quota = (${installViewerWorkerQuota.toString()})(globalThis, 8);
      const encoded = new TextEncoder().encode('font');
      let denied = false;
      try { new TextEncoder().encode('123456789'); } catch { denied = true; }
      ({ used: quota.used(), calls, denied, length: encoded.length, clone: typeof structuredClone });
    `) as unknown;
    expect(result).toEqual({ used: 4, calls: 1, denied: true, length: 4, clone: "undefined" });
  });
});
