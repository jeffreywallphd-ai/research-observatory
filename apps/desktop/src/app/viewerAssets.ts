// One allowance covers every concurrent bundled font/CMap read, its input
// chunks and destination copy. Completed assets remain charged until close;
// PDF.js decides how long to retain them, so early promise completion is not
// authority to reuse that memory.
export class ViewerAssetPool {
  private held = 0;
  private live = true;
  private readers = new Set<ReadableStreamDefaultReader<Uint8Array<ArrayBuffer>>>();
  constructor(private readonly limit = 8 * 1024 * 1024) {}
  get used(): number { return this.held; }
  private admit(bytes: number): () => void {
    if (!this.live) throw new Error("viewer-source-unavailable");
    if (!Number.isSafeInteger(bytes) || bytes < 0 || bytes > this.limit - this.held) throw new Error("viewer-resource-limit");
    this.held += bytes;
    let released = false;
    return () => { if (!released) { released = true; if (this.live) this.held -= bytes; } };
  }
  async read(stream: ReadableStream<Uint8Array<ArrayBuffer>>): Promise<Uint8Array<ArrayBuffer>> {
    if (!this.live) throw new Error("viewer-source-unavailable");
    const reader = stream.getReader(); this.readers.add(reader);
    const chunks: Uint8Array<ArrayBuffer>[] = [], releases: (() => void)[] = [];
    let size = 0, outputRelease: (() => void) | null = null;
    try {
      for (;;) {
        const result = await reader.read();
        if (!this.live) throw new Error("viewer-source-unavailable");
        if (result.done) break;
        // Count the actual backing store, not merely a subarray's view length.
        releases.push(this.admit(result.value.buffer.byteLength));
        chunks.push(result.value); size += result.value.byteLength;
      }
      outputRelease = this.admit(size);
      const buffer = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
      outputRelease = null; return buffer;
    } finally {
      chunks.length = 0;
      for (const release of releases) release(); outputRelease?.();
      this.readers.delete(reader); await reader.cancel().catch(() => undefined); reader.releaseLock();
    }
  }
  close(): void {
    if (!this.live) return;
    this.live = false;
    for (const reader of this.readers) void reader.cancel().catch(() => undefined);
    this.readers.clear(); this.held = 0;
  }
}
