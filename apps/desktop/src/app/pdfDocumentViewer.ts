import { AnnotationMode, PDFDataRangeTransport, PDFWorker, getDocument, type PDFDocumentLoadingTask,
  type PDFDocumentProxy, type PDFPageProxy, type RenderTask } from "pdfjs-dist";
import { VIEWER_RANGE_LIMIT, ViewerByteSession, type ViewerBufferBudget } from "./documentViewer";
import { retainViewerMessage } from "./viewerWorkerMessages";
import { ViewerAssetPool } from "./viewerAssets";
import type { TextContent } from "pdfjs-dist/types/src/display/api";

interface Surface { canvas: HTMLCanvasElement | null; context: CanvasRenderingContext2D | null }
const SURFACE_LIMIT = 32 * 1024 * 1024;
const assets = import.meta.glob<string>([
  "/node_modules/pdfjs-dist/cmaps/*.bcmap", "/node_modules/pdfjs-dist/standard_fonts/*.pfb", "/node_modules/pdfjs-dist/standard_fonts/*.ttf",
], { query: "?url", import: "default", eager: true });

// PDF.js shares missing-chunk demands across page/text operations. Cancelling
// an SDK task alone cannot cancel their deferred range turns. Retire that
// document/byte generation before admitting replacement work.
export class PdfDocumentViewer {
  private live = true;
  private generation = 0;
  private readonly operations = new Set<symbol>();
  private readonly searches = new Set<symbol>();
  private record: { decoder: PdfDecoderSession; bytes: ViewerByteSession; ready: Promise<number> } | null = null;
  private drained: Promise<void> = Promise.resolve();
  private initial = true;
  private retired = Promise.withResolvers<void>();
  constructor(private readonly source: ViewerByteSession, private readonly budget: ViewerBufferBudget,
    private readonly onFailure: (code: string) => void) {}

  private stop(): void {
    const retired = this.retired; this.retired = Promise.withResolvers<void>();
    this.generation += 1;
    const record = this.record; this.record = null;
    this.operations.clear(); this.searches.clear();
    if (!record) { retired.resolve(); return; }
    record.decoder.close();
    // No new decoder or range enters while the previous native/Core owner is
    // draining. A late/failed drain denies the replacement instead of overlap.
    this.drained = Promise.all([this.drained, record.bytes.drain()]).then(() => undefined);
    void this.drained.catch(() => undefined);
    // The decoder has actually terminated and its native byte owner has been
    // cancelled above. Settle caller operations whose SDK callbacks no longer
    // have a live worker; replacement admission still waits for the real drain.
    retired.resolve();
  }
  private async ensure(ticket: number): Promise<PdfDecoderSession | null> {
    const retired = this.retired.promise;
    await Promise.race([this.drained, retired]);
    if (!this.live || ticket !== this.generation) return null;
    if (!this.record) {
      const bytes = this.initial ? this.source : this.source.fresh(); this.initial = false;
      const decoder = new PdfDecoderSession(bytes, this.budget,
        (code) => { if (this.live && ticket === this.generation) this.onFailure(code); });
      this.record = { decoder, bytes, ready: decoder.open() };
    }
    const record = this.record;
    await Promise.race([record.ready, retired]);
    return this.live && ticket === this.generation && this.record === record ? record.decoder : null;
  }
  async open(): Promise<number> {
    const decoder = await this.ensure(this.generation);
    if (!decoder || !this.record) throw new Error("viewer-source-unavailable");
    return this.record.ready;
  }
  async render(canvas: HTMLCanvasElement, number: number, scale: number): Promise<void> {
    if (this.operations.size) this.stop();
    const ticket = this.generation, operation = Symbol(); this.operations.add(operation);
    const retired = this.retired.promise;
    try {
      const decoder = await this.ensure(ticket);
      if (decoder) await Promise.race([decoder.render(canvas, number, scale), retired]);
    } catch (error) { if (this.live && ticket === this.generation) throw error; }
    finally { this.operations.delete(operation); }
  }
  async thumbnail(canvas: HTMLCanvasElement, number: number): Promise<void> {
    const ticket = this.generation, operation = Symbol(); this.operations.add(operation);
    const retired = this.retired.promise;
    try {
      const decoder = await this.ensure(ticket);
      if (decoder) await Promise.race([decoder.thumbnail(canvas, number), retired]);
    } catch (error) { if (this.live && ticket === this.generation) throw error; }
    finally { this.operations.delete(operation); }
  }
  async find(query: string, afterPage: number): Promise<number | null> {
    const ticket = this.generation, operation = Symbol();
    const retired = this.retired.promise;
    this.operations.add(operation); this.searches.add(operation);
    try {
      const decoder = await this.ensure(ticket);
      const found = decoder ? await Promise.race([decoder.find(query, afterPage), retired.then(() => null)]) : null;
      return this.live && ticket === this.generation ? found : null;
    } catch (error) { if (this.live && ticket === this.generation) throw error; return null; }
    finally { this.operations.delete(operation); this.searches.delete(operation); }
  }
  cancelRender(): void { if (this.operations.size) this.stop(); }
  cancelSearch(): void { if (this.searches.size) this.stop(); }
  releaseCanvas(canvas: HTMLCanvasElement): void { this.record?.decoder.releaseCanvas(canvas); }
  close(): void { if (this.live) { this.live = false; this.stop(); this.source.close(); } }
}

class PdfDecoderSession {
  private readonly worker: Worker;
  private readonly pdfWorker: PDFWorker;
  private loading: PDFDocumentLoadingTask | null = null;
  private document: PDFDocumentProxy | null = null;
  private renderTask: RenderTask | null = null;
  private renderChain: Promise<void> = Promise.resolve();
  private thumbnailTasks = new Set<RenderTask>();
  private textReaders = new Set<ReadableStreamDefaultReader<TextContent>>();
  private page: PDFPageProxy | null = null;
  private live = true;
  private generation = 0;
  private searchGeneration = 0;
  private surfaceBytes = 0;
  private surfaces = new Map<HTMLCanvasElement, number>();
  private releases: (() => void)[] = [];
  private readonly assets = new ViewerAssetPool();
  private readonly assetStop = new AbortController();
  private readonly assetRequests = new Map<string, Promise<Uint8Array<ArrayBuffer>>>();
  private failure: Error | null = null;
  private readonly bytes: ViewerByteSession;
  constructor(bytes: ViewerByteSession, budget: ViewerBufferBudget, private readonly onFailure: (code: string) => void) {
    this.bytes = bytes;
    let worker: Worker | null = null;
    try {
      // Includes worker source/decoder backing stores, main decoded clones and
      // all page/intermediate surfaces, and local built-in font/CMap resources.
      this.releases.push(budget.reserve(144 * 1024 * 1024));
      this.releases.push(budget.reserve(64 * 1024 * 1024));
      this.releases.push(budget.reserve(8 * 1024 * 1024));
      this.worker = worker = new Worker(new URL("./documentViewer.worker.ts", import.meta.url), { type: "module", name: "protected-document-viewer" });
      const messages = { held: 0 };
      this.worker.addEventListener("message", (event: MessageEvent<unknown>) => {
        try {
          if (event.data && typeof event.data === "object" && "viewerFailure" in event.data) throw new Error("viewer-resource-limit");
          retainViewerMessage(event, this.worker, messages);
        } catch { event.stopImmediatePropagation(); this.fail("viewer-resource-limit"); }
      });
      this.worker.addEventListener("error", (event) => { event.preventDefault(); this.fail("viewer-source-unavailable"); });
      this.pdfWorker = PDFWorker.create({ port: this.worker });
    } catch (error) { worker?.terminate(); for (const release of this.releases) release(); throw error; }
  }
  private fail(code: string): void {
    if (!this.live) return;
    this.failure = new Error(code); this.onFailure(code); this.close();
  }
  private createSurface(width: number, height: number): Surface {
    const canvas = document.createElement("canvas"); this.sizeSurface(canvas, width, height);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) { this.dropSurface(canvas); throw new Error("viewer-source-unavailable"); }
    return { canvas, context };
  }
  private sizeSurface(canvas: HTMLCanvasElement, width: number, height: number): void {
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0 || width > 8192 || height > 8192) throw new Error("viewer-resource-limit");
    const count = Math.ceil(width) * Math.ceil(height) * 4;
    const prior = this.surfaces.get(canvas) ?? 0;
    if (this.surfaceBytes - prior + count > SURFACE_LIMIT) throw new Error("viewer-resource-limit");
    // Release the previous native canvas before admitting its replacement.
    canvas.width = canvas.height = 0;
    this.surfaceBytes = this.surfaceBytes - prior + count; this.surfaces.set(canvas, count);
    canvas.width = Math.ceil(width); canvas.height = Math.ceil(height);
  }
  private dropSurface(canvas: HTMLCanvasElement): void {
    this.surfaceBytes -= this.surfaces.get(canvas) ?? 0; this.surfaces.delete(canvas);
    canvas.width = canvas.height = 0;
  }
  async open(): Promise<number> {
    if (!this.live) throw this.failure ?? new Error("viewer-source-unavailable");
    const owner = this;
    class SourceRanges extends PDFDataRangeTransport {
      constructor() { super(owner.bytes.metadata.source.byteLength, null, true); }
      override requestDataRange(begin: number, end: number): void {
        void owner.bytes.read(begin, end).then((chunk) => {
          if (owner.live) this.onDataRange(begin, chunk);
        }).catch(() => owner.fail("viewer-source-unavailable"));
      }
      override abort(): void { owner.bytes.close(); }
    }
    class CanvasFactory {
      create(width: number, height: number): Surface { return owner.createSurface(width, height); }
      reset(surface: Surface, width: number, height: number): void {
        if (!surface.canvas) throw new Error("viewer-source-unavailable"); owner.sizeSurface(surface.canvas, width, height);
      }
      destroy(surface: Surface): void {
        if (surface.canvas) owner.dropSurface(surface.canvas); surface.canvas = surface.context = null;
      }
    }
    class BinaryDataFactory {
      async fetch({ kind, filename }: { kind: string; filename: string }): Promise<Uint8Array<ArrayBuffer>> {
        if (!owner.live || !/^[A-Za-z0-9_-]+\.(?:bcmap|pfb|ttf)$/u.test(filename)) throw new Error("viewer-remote-resource-denied");
        const folder = kind === "cMapUrl" ? "cmaps" : kind === "standardFontDataUrl" ? "standard_fonts" : null;
        const url = folder ? assets[`/node_modules/pdfjs-dist/${folder}/${filename}`] : undefined;
        if (!url) throw new Error("viewer-remote-resource-denied");
        const target = new URL(url, window.location.href);
        if (target.origin !== window.location.origin || !["http:", "https:", "tauri:"].includes(target.protocol)) throw new Error("viewer-remote-resource-denied");
        // These immutable bundled resources are public application assets.
        // Sharing their bounded promise does not cache any original source.
        const prior = owner.assetRequests.get(target.href);
        if (prior) return prior;
        const request = (async () => {
          const response = await fetch(target, { credentials: "omit", redirect: "error", signal: owner.assetStop.signal });
          if (!response.ok || !owner.live || !response.body) throw new Error("viewer-source-unavailable");
          return owner.assets.read(response.body);
        })();
        owner.assetRequests.set(target.href, request);
        try { return await request; }
        catch (error) { owner.assetRequests.delete(target.href); throw error; }
      }
    }
    // Each range repeats complete source authentication. Use the already
    // approved 1MiB range bound to avoid many small authenticated round trips;
    // automatic prefetch/streaming stays disabled and SDK reads remain serial.
    this.loading = getDocument({ range: new SourceRanges(), worker: this.pdfWorker, rangeChunkSize: VIEWER_RANGE_LIMIT,
      disableRange: false, disableStream: true, disableAutoFetch: true, enableXfa: false,
      useWorkerFetch: false, useWasm: false, isOffscreenCanvasSupported: false, isImageDecoderSupported: false,
      maxImageSize: 4 * 1024 * 1024, canvasMaxAreaInBytes: 16 * 1024 * 1024,
      disableFontFace: true, useSystemFonts: false, fontExtraProperties: false, stopAtErrors: true,
      enableHWA: false, verbosity: 0, CanvasFactory, BinaryDataFactory });
    const document = await this.loading.promise;
    if (!this.live || document.numPages < 1 || document.numPages > 500) { this.close(); throw new Error("viewer-resource-limit"); }
    this.document = document; return document.numPages;
  }
  cancelRender(): void { this.generation += 1; this.renderTask?.cancel(); }
  async find(query: string, afterPage: number): Promise<number | null> {
    if (!this.live || !this.document || !query || Array.from(query).length > 200
      || !Number.isSafeInteger(afterPage) || afterPage < 0 || afterPage > this.document.numPages) return null;
    const ticket = ++this.searchGeneration, document = this.document;
    for (let index = 0; index < document.numPages; index += 1) {
      if (!this.live || ticket !== this.searchGeneration) return null;
      const number = (afterPage + index) % document.numPages + 1, page = await document.getPage(number);
      let size = 0;
      const parts: string[] = [];
      // Own the public SDK stream reader. Killing its worker alone does not
      // settle getTextContent's pending read; cancellation must close that
      // main-thread reader as well as the decoder/native byte generation.
      const reader = page.streamTextContent({ disableNormalization: true }).getReader() as ReadableStreamDefaultReader<TextContent>;
      this.textReaders.add(reader);
      try {
        while (this.live && ticket === this.searchGeneration) {
          const chunk = await reader.read();
          if (chunk.done) break;
          for (const item of chunk.value.items) {
            if (!("str" in item)) continue;
            size += item.str.length;
            if (size > 262144) throw new Error("viewer-resource-limit");
            parts.push(item.str);
          }
        }
      } finally {
        this.textReaders.delete(reader);
        void reader.cancel().catch(() => undefined);
        reader.releaseLock();
        if (page !== this.page) page.cleanup();
      }
      const matched = parts.join(" ").toLowerCase().includes(query.toLowerCase());
      if (!this.live || ticket !== this.searchGeneration) return null;
      if (matched) return number;
    }
    return null;
  }
  cancelSearch(): void { this.searchGeneration += 1; }
  async thumbnail(canvas: HTMLCanvasElement, number: number): Promise<void> {
    if (!this.live || !this.document || number < 1 || number > this.document.numPages) return;
    const ticket = this.generation, document = this.document;
    const current = (): boolean => this.live && ticket === this.generation;
    const page = await document.getPage(number);
    let task: RenderTask | null = null, complete = false;
    try {
      if (!current()) return;
      const first = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: Math.min(96 / first.width, 128 / first.height) });
      this.sizeSurface(canvas, viewport.width, viewport.height);
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("viewer-source-unavailable");
      task = page.render({ canvas, canvasContext: context, viewport, annotationMode: AnnotationMode.DISABLE });
      this.thumbnailTasks.add(task); await task.promise; complete = current();
    } catch (error) { if (current()) throw error; }
    finally {
      if (task) this.thumbnailTasks.delete(task);
      if (!complete) this.dropSurface(canvas);
      if (page !== this.page) page.cleanup();
    }
  }
  releaseCanvas(canvas: HTMLCanvasElement): void { this.dropSurface(canvas); }
  async render(canvas: HTMLCanvasElement, number: number, scale: number): Promise<void> {
    if (!this.live || !this.document || !Number.isSafeInteger(number) || number < 1 || number > this.document.numPages
      || ![0.75, 1, 1.25, 1.5, 2].includes(scale)) throw new Error("viewer-source-unavailable");
    this.renderTask?.cancel(); for (const task of this.thumbnailTasks) task.cancel();
    const ticket = ++this.generation, document = this.document;
    const current = (): boolean => this.live && ticket === this.generation;
    const render = async (): Promise<void> => {
      if (!current()) return;
      await Promise.allSettled([...this.thumbnailTasks].map((task) => task.promise));
      const prior = this.page; this.page = null; prior?.cleanup(); await document.cleanup();
      if (!current()) return;
      const page = await document.getPage(number);
      if (!current()) { page.cleanup(); return; }
      this.page = page; const viewport = page.getViewport({ scale }); this.sizeSurface(canvas, viewport.width, viewport.height);
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("viewer-source-unavailable");
      this.renderTask = page.render({ canvas, canvasContext: context, viewport, annotationMode: AnnotationMode.DISABLE });
      try { await this.renderTask.promise; } catch (error) { if (current()) throw error; }
      if (!current()) this.dropSurface(canvas);
    };
    const result = this.renderChain.then(render); this.renderChain = result.catch(() => undefined); return result;
  }
  close(): void {
    if (!this.live) return;
    this.live = false; this.generation += 1; this.searchGeneration += 1; this.bytes.close(); this.renderTask?.cancel();
    this.assetStop.abort(); this.assets.close();
    this.assetRequests.clear();
    for (const reader of this.textReaders) void reader.cancel().catch(() => undefined);
    this.textReaders.clear();
    for (const task of this.thumbnailTasks) task.cancel(); this.thumbnailTasks.clear();
    // Termination is immediate even when an untrusted decoder is still busy.
    this.worker.terminate(); this.pdfWorker.destroy();
    void this.loading?.destroy().catch(() => undefined);
    for (const canvas of this.surfaces.keys()) this.dropSurface(canvas);
    for (const release of this.releases) release(); this.releases = [];
    this.document = this.page = this.renderTask = this.loading = null;
  }
}
