// Installed before PDF.js executes in its dedicated worker. Conservatively
// retain allocation charges until collection or worker termination. Imported
// PDF data cannot supply executable callbacks, URLs or allocation authority.
export function installViewerWorkerQuota(scope: Record<string, unknown>, limit: number): { readonly used: () => number; readonly accept: (buffer: ArrayBuffer) => void } {
  let used = 0;
  const held = new WeakSet<object>();
  const originalBuffer = scope["ArrayBuffer"] as typeof ArrayBuffer;
  const collected = new FinalizationRegistry<number>((bytes) => { used -= bytes; });
  function admit(bytes: number): void {
    if (!Number.isSafeInteger(bytes) || bytes < 0 || bytes > limit - used) throw new Error("viewer-resource-limit");
  }
  function account(buffer: ArrayBuffer): void {
    if (held.has(buffer)) return;
    const bytes = buffer.byteLength;
    admit(bytes); used += bytes; held.add(buffer); collected.register(buffer, bytes);
  }
  const names = ["ArrayBuffer", "Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array", "Uint16Array", "Int32Array", "Uint32Array", "Float32Array", "Float64Array", "BigInt64Array", "BigUint64Array"];
  for (const name of names) {
    const original = scope[name] as { new (...args: unknown[]): ArrayBuffer | ArrayBufferView; readonly BYTES_PER_ELEMENT?: number; readonly prototype: object };
    const bytesPerElement = name === "ArrayBuffer" ? 1 : original.BYTES_PER_ELEMENT!;
    const guarded = new Proxy(original, {
      construct(target, args, newTarget) {
        const value: unknown = args[0];
        const view = name !== "ArrayBuffer" && value instanceof originalBuffer;
        if (!view) {
          let count: unknown = value ?? 0;
          if (name !== "ArrayBuffer" && typeof value === "object" && value !== null) {
            if (ArrayBuffer.isView(value)) count = "length" in value ? value.length : undefined;
            else if (Array.isArray(value)) count = value.length;
            else throw new Error("viewer-resource-limit");
          }
          if (typeof count !== "number") throw new Error("viewer-resource-limit");
          admit(count * bytesPerElement);
        }
        // Resizable backing stores can grow outside constructor admission.
        if (name === "ArrayBuffer" && args[1] !== undefined) throw new Error("viewer-resource-limit");
        const result = Reflect.construct(target, args, newTarget) as ArrayBuffer | ArrayBufferView;
        if (!view) account(result instanceof originalBuffer ? result : result.buffer as ArrayBuffer);
        return result;
      },
    });
    scope[name] = guarded;
    Object.defineProperty(original.prototype, "constructor", { value: guarded, configurable: false, writable: false });
  }
  const slice = originalBuffer.prototype.slice;
  Object.defineProperty(originalBuffer.prototype, "slice", {
    value(this: ArrayBuffer, start = 0, end = this.byteLength): ArrayBuffer {
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end)) throw new Error("viewer-resource-limit");
      const begin = start < 0 ? Math.max(this.byteLength + start, 0) : Math.min(start, this.byteLength);
      const finish = end < 0 ? Math.max(this.byteLength + end, 0) : Math.min(end, this.byteLength);
      admit(Math.max(0, finish - begin));
      const result = slice.call(this, start, end); account(result); return result;
    }, configurable: false, writable: false,
  });
  for (const method of ["resize", "transfer", "transferToFixedLength"]) {
    Object.defineProperty(originalBuffer.prototype, method, { value: () => { throw new Error("viewer-resource-limit"); }, configurable: false, writable: false });
  }
  const Encoder = scope["TextEncoder"] as typeof TextEncoder | undefined;
  if (Encoder) {
    const encode = Encoder.prototype.encode, encodeInto = Encoder.prototype.encodeInto;
    function encodedLength(input: string): number {
      let size = 0;
      for (let index = 0; index < input.length; index += 1) {
        const code = input.charCodeAt(index);
        if (code < 0x80) size += 1;
        else if (code < 0x800) size += 2;
        else if (code >= 0xd800 && code <= 0xdbff && index + 1 < input.length
          && input.charCodeAt(index + 1) >= 0xdc00 && input.charCodeAt(index + 1) <= 0xdfff) { size += 4; index += 1; }
        else size += 3;
        admit(size);
      }
      return size;
    }
    Object.defineProperty(Encoder.prototype, "encode", { value(this: TextEncoder, input = ""): Uint8Array<ArrayBuffer> {
      if (typeof input !== "string") throw new Error("viewer-resource-limit");
      admit(encodedLength(input));
      const result = encode.call(this, input); account(result.buffer); return result;
    }, configurable: false, writable: false });
    if (encodeInto) Object.defineProperty(Encoder.prototype, "encodeInto", { value(this: TextEncoder, input: string, output: Uint8Array<ArrayBuffer>): TextEncoderEncodeIntoResult {
      if (typeof input !== "string" || !ArrayBuffer.isView(output)) throw new Error("viewer-resource-limit");
      account(output.buffer); return encodeInto.call(this, input, output);
    }, configurable: false, writable: false });
  }
  scope["SharedArrayBuffer"] = undefined;
  // This viewer deliberately uses PDF.js's JavaScript decoders. Other worker
  // native allocations/egress APIs are unavailable to this integration.
  scope["WebAssembly"] = undefined;
  scope["OffscreenCanvas"] = undefined;
  scope["ImageDecoder"] = undefined;
  scope["createImageBitmap"] = undefined;
  scope["Blob"] = undefined;
  scope["Response"] = undefined;
  scope["CompressionStream"] = undefined;
  scope["DecompressionStream"] = undefined;
  scope["structuredClone"] = undefined;
  scope["fetch"] = () => Promise.reject(new Error("viewer-remote-resource-denied"));
  scope["XMLHttpRequest"] = undefined;
  scope["WebSocket"] = undefined;
  scope["importScripts"] = () => { throw new Error("viewer-remote-resource-denied"); };
  return { used: () => used, accept: account };
}
