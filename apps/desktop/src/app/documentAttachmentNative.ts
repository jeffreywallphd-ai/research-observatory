import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  DOCUMENT_ATTACHMENT_COMMANDS, DOCUMENT_ATTACHMENT_EVENT, attachmentProblemMessage,
  decodeAttachmentBeginOutcome, decodeAttachmentCapability, decodeAttachmentEvent, decodeAttachmentOutcome,
  decodeAttachmentStatus,
  type AttachmentBeginOutcome, type AttachmentBeginRequest, type AttachmentCancelRequest,
  type AttachmentCommitRequest, type AttachmentEvent, type AttachmentOutcome, type AttachmentStatus, type AttachmentStatusRequest,
} from "./documentAttachment";

export interface DocumentAttachmentPort {
  readonly available: (projectId: string) => Promise<boolean>;
  readonly subscribe: (handler: (event: AttachmentEvent) => void) => Promise<() => void>;
  readonly begin: (request: AttachmentBeginRequest) => Promise<AttachmentBeginOutcome>;
  readonly cancel: (request: AttachmentCancelRequest) => Promise<void>;
  readonly commit: (request: AttachmentCommitRequest) => Promise<AttachmentOutcome | null>;
  readonly status: (request: AttachmentStatusRequest) => Promise<AttachmentStatus | null>;
}

function nativeRuntime(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

// The native side resolves the project and owns the picker, OS drop, held file,
// stream, Core session and rights decision. This adapter carries only exact IDs.
export const nativeDocumentAttachmentPort: DocumentAttachmentPort = {
  async available(projectId) {
    if (!nativeRuntime()) return false;
    try {
      return decodeAttachmentCapability(await invoke<unknown>(DOCUMENT_ATTACHMENT_COMMANDS.capabilities, { projectId }), projectId);
    } catch { return false; }
  },
  async subscribe(handler) {
    if (!nativeRuntime()) throw new Error(attachmentProblemMessage("unavailable"));
    return listen<unknown>(DOCUMENT_ATTACHMENT_EVENT, ({ payload }) => {
      const event = decodeAttachmentEvent(payload);
      if (event) handler(event);
    });
  },
  async begin(request) {
    if (!nativeRuntime()) return { schemaVersion: "1.0", status: "unavailable", operationId: request.operationId };
    try {
      return decodeAttachmentBeginOutcome(await invoke<unknown>(DOCUMENT_ATTACHMENT_COMMANDS.begin, { request }))
        ?? { schemaVersion: "1.0", status: "unavailable", operationId: request.operationId };
    } catch { return { schemaVersion: "1.0", status: "unavailable", operationId: request.operationId }; }
  },
  async cancel(request) {
    if (!nativeRuntime()) return;
    try { await invoke<unknown>(DOCUMENT_ATTACHMENT_COMMANDS.cancel, { request }); }
    catch { /* Local state is cleared; native must discard on session/operation invalidation. */ }
  },
  async commit(request) {
    if (!nativeRuntime()) return null;
    try { return decodeAttachmentOutcome(await invoke<unknown>(DOCUMENT_ATTACHMENT_COMMANDS.commit, { request })); }
    catch { return null; }
  },
  async status(request) {
    if (!nativeRuntime()) return null;
    try { return decodeAttachmentStatus(await invoke<unknown>(DOCUMENT_ATTACHMENT_COMMANDS.status, { request })); }
    catch { return null; }
  },
};
