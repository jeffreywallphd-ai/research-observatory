import { invoke } from "@tauri-apps/api/core";
import { newAttachmentId } from "./documentAttachment";
import { decodeSourceIdentity, type SourceIdentity } from "./sourceAnchors";

export const VIEWER_SOURCE_LIMIT = 128 * 1024 * 1024;
export const VIEWER_RANGE_LIMIT = 1024 * 1024;
export const VIEWER_BUFFER_LIMIT = 256 * 1024 * 1024;
export interface ViewerSelector {
  readonly attachmentId: string;
  readonly documentRevisionId: string;
  readonly normalizedRevisionId: string | null;
}
export interface ViewerMetadata {
  readonly source: SourceIdentity;
  readonly normalizedRevisionId: string | null;
}
export interface DocumentViewerPort {
  readonly source: (projectId: string, selector: ViewerSelector) => Promise<ViewerMetadata | null>;
  // Resolution (including null) proves the owned participation is terminal or
  // never issued. Rejection means termination is unknown; callers must deny
  // replacement and retain admission accounting until closure is established.
  readonly range: (projectId: string, selector: ViewerSelector, requestId: string, start: number,
    end: number, signal: AbortSignal) => Promise<ArrayBuffer | null>;
}

export interface ViewerTextChunk {
  readonly metadata: ViewerMetadata; readonly nodeId: string; readonly nodeKind: string;
  readonly pageNumber: number | null; readonly offset: number; readonly text: string; readonly nextOffset: number | null;
}
export interface DocumentViewerTextPort {
  readonly text: (projectId: string, selector: ViewerSelector, nodeId: string, offset: number) => Promise<ViewerTextChunk | null>;
}

export function viewerSourcesMatch(left: SourceIdentity, right: SourceIdentity): boolean {
  return Object.entries(left).every(([key, value]) => key === "provenance"
    ? Object.entries(left.provenance).length === Object.entries(right.provenance).length
      && Object.entries(left.provenance).every(([field, expected]) => Object.entries(right.provenance).some(([other, actual]) => field === other && expected === actual))
    : Object.entries(right).some(([other, actual]) => other === key && value === actual));
}

export function decodeViewerText(value: unknown, projectId: string, selector: ViewerSelector, nodeId: string, offset: number): ViewerTextChunk | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const fields = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== 7 || ["metadata", "nodeId", "nodeKind", "pageNumber", "offset", "text", "nextOffset"].some((key) => !fields[key] || !("value" in fields[key]!))) return null;
  const text = fields["text"]!.value as unknown, next = fields["nextOffset"]!.value as unknown, page = fields["pageNumber"]!.value as unknown;
  const metadata = decodeViewerMetadata(fields["metadata"]!.value, projectId, selector);
  if (!metadata || !selector.normalizedRevisionId || fields["nodeId"]!.value !== nodeId || fields["offset"]!.value !== offset
    || typeof text !== "string" || Array.from(text).length > 4096
    || next !== null && next !== offset + Array.from(text).length
    || page !== null && (typeof page !== "number" || !Number.isInteger(page) || page < 1 || page > 500)
    || !["region", "title", "abstract", "section", "paragraph", "sentence", "list", "list-item", "footnote", "reference", "citation-marker", "table", "table-cell", "figure", "caption", "equation", "unknown"].includes(String(fields["nodeKind"]!.value))) return null;
  return { metadata, nodeId, nodeKind: fields["nodeKind"]!.value as string, pageNumber: page as number | null, offset, text, nextOffset: next as number | null };
}

export const nativeDocumentViewerTextPort: DocumentViewerTextPort = {
  async text(projectId, selector, nodeId, offset) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return null;
    try { return decodeViewerText(await invoke<unknown>("document_viewer_text", { request: { schemaVersion: "1.0", projectId, selector, nodeId, offset } }), projectId, selector, nodeId, offset); }
    catch { return null; }
  },
};

export function decodeViewerMetadata(value: unknown, projectId: string, selector: ViewerSelector): ViewerMetadata | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== 2 || !descriptors["source"] || !descriptors["normalizedRevisionId"]
    || Object.values(descriptors).some((field) => !("value" in field))) return null;
  const source = decodeSourceIdentity(descriptors["source"].value, projectId);
  const normalized = descriptors["normalizedRevisionId"].value as unknown;
  if (!source || source.byteLength <= 0 || source.attachmentId !== selector.attachmentId
    || source.documentRevisionId !== selector.documentRevisionId || normalized !== selector.normalizedRevisionId
    || normalized !== null && (typeof normalized !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(normalized)
      || normalized === source.documentRevisionId)) return null;
  return { source, normalizedRevisionId: normalized };
}

export class ViewerBufferBudget {
  private allocations = new Map<symbol, number>();
  private size = 0;
  get used(): number { return this.size; }
  reserve(bytes: number): () => void {
    if (!Number.isSafeInteger(bytes) || bytes < 0 || this.size + bytes > VIEWER_BUFFER_LIMIT) {
      throw new Error("viewer-resource-limit");
    }
    const key = Symbol();
    this.allocations.set(key, bytes); this.size += bytes;
    return () => {
      const held = this.allocations.get(key);
      if (held !== undefined) { this.size -= held; this.allocations.delete(key); }
    };
  }
}

export const nativeDocumentViewerPort: DocumentViewerPort = {
  async source(projectId, selector) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return null;
    try {
      return decodeViewerMetadata(await invoke<unknown>("document_viewer_source", {
        request: { schemaVersion: "1.0", projectId, selector },
      }), projectId, selector);
    } catch { return null; }
  },
  async range(projectId, selector, requestId, start, end, signal) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window) || signal.aborted) return null;
    const cancel = () => {
      // This is only a stop signal. The range result below supplies the exact
      // physical-terminal acknowledgement; cancel IPC settlement proves none.
      void invoke("document_viewer_cancel", { request: { schemaVersion: "1.0", projectId, requestId } }).catch(() => undefined);
    };
    signal.addEventListener("abort", cancel, { once: true });
    try {
      const response = await invoke<unknown>("document_viewer_range", {
        request: { schemaVersion: "1.0", projectId, selector, requestId, start, end },
      });
      if (!(response instanceof ArrayBuffer) || response.byteLength !== end - start) throw new Error("viewer-owned-read-drain-pending");
      return !signal.aborted ? response : null;
    } catch (failure) {
      const fields: Record<string, PropertyDescriptor> = failure && typeof failure === "object" && !Array.isArray(failure)
        ? Object.getOwnPropertyDescriptors(failure) : {};
      if (Reflect.ownKeys(fields).length !== 4
        || ["schemaVersion", "projectId", "requestId", "drained"].some((key) => !fields[key] || !("value" in fields[key]!))
        || fields["schemaVersion"]!.value !== "1.0" || fields["projectId"]!.value !== projectId
        || fields["requestId"]!.value !== requestId || fields["drained"]!.value !== true) {
        throw new Error("viewer-owned-read-drain-pending");
      }
      return null;
    }
    finally { signal.removeEventListener("abort", cancel); }
  },
};

export class ViewerByteSession {
  private live = true;
  private drainFailed = false;
  private pending = new Map<string, { controller: AbortController; promise: Promise<Uint8Array<ArrayBuffer>> }>();
  constructor(readonly projectId: string, readonly selector: ViewerSelector, readonly metadata: ViewerMetadata,
    private readonly port: DocumentViewerPort, readonly budget: ViewerBufferBudget) {
    if (!decodeViewerMetadata(metadata, projectId, selector)) throw new Error("viewer-source-unavailable");
  }
  async read(start: number, end: number): Promise<Uint8Array<ArrayBuffer>> {
    if (this.drainFailed) throw new Error("viewer-owned-read-drain-pending");
    if (!this.live || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)
      || start < 0 || start >= end || end > this.metadata.source.byteLength || end - start > VIEWER_RANGE_LIMIT) {
      throw new Error("viewer-source-unavailable");
    }
    const key = `${start}:${end}`;
    const prior = this.pending.get(key);
    if (prior) return prior.promise;
    if (this.pending.size >= 8) throw new Error("viewer-queue-full");
    // Reserve bounded Core/native base64, decode, IPC and transfer copies.
    // The render owner separately reserves the worker and page surfaces.
    const release = this.budget.reserve((end - start) * 6 + 8192);
    const controller = new AbortController();
    let confirmedClosed = false;
    const promise = this.port.range(this.projectId, this.selector, newAttachmentId(), start, end, controller.signal)
      .catch(() => { this.drainFailed = true; throw new Error("viewer-owned-read-drain-pending"); })
      .then((buffer) => {
        // Port resolution denotes real termination (or a never-issued read),
        // including null for an explicitly acknowledged cancellation/denial.
        confirmedClosed = true;
        if (!this.live || controller.signal.aborted || !(buffer instanceof ArrayBuffer) || buffer.byteLength !== end - start) {
          throw new Error("viewer-source-unavailable");
        }
        return new Uint8Array(buffer);
      }).finally(() => { this.pending.delete(key); if (confirmedClosed) release(); });
    this.pending.set(key, { controller, promise });
    return promise;
  }
  cancelPending(): void {
    for (const pending of this.pending.values()) pending.controller.abort();
  }
  fresh(): ViewerByteSession {
    if (this.drainFailed || this.pending.size) throw new Error("viewer-owned-read-drain-pending");
    return new ViewerByteSession(this.projectId, this.selector, this.metadata, this.port, this.budget);
  }
  async drain(): Promise<void> {
    if (this.drainFailed) throw new Error("viewer-owned-read-drain-pending");
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        Promise.allSettled([...this.pending.values()].map((request) => request.promise)),
        new Promise<never>((_resolve, reject) => { timeout = setTimeout(() => reject(new Error("viewer-owned-read-drain-pending")), 1000); }),
      ]);
      if (this.drainFailed) throw new Error("viewer-owned-read-drain-pending");
    } catch {
      this.drainFailed = true;
      throw new Error("viewer-owned-read-drain-pending");
    } finally { if (timeout !== undefined) clearTimeout(timeout); }
  }
  close(): void { this.live = false; this.cancelPending(); }
}
