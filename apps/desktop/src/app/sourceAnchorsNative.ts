import { invoke } from "@tauri-apps/api/core";
import {
  decodeAnchorIds, decodeReaderOutline, decodeReaderRevisions, decodeSourceAnchor,
  type AnchorSelection, type ReaderOutline, type ReaderRevisions, type SourceAnchor,
} from "./sourceAnchors";

export interface SourceAnchorPort {
  readonly revisions: (projectId: string, attachmentId: string) => Promise<ReaderRevisions | null>;
  readonly outline: (projectId: string, revisionId: string, afterNodeId?: string | null) => Promise<ReaderOutline | null>;
  readonly list: (projectId: string, revisionId: string, afterId?: string | null) => Promise<readonly string[] | null>;
  readonly read: (projectId: string, revisionId: string, anchorId: string) => Promise<SourceAnchor | null>;
  readonly create: (projectId: string, commandId: string, selection: AnchorSelection) => Promise<SourceAnchor | null>;
}

async function request(command: string, fields: object): Promise<unknown> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return null;
  try { return await invoke<unknown>(command, { request: { schemaVersion: "1.0", ...fields } }); }
  catch { return null; }
}

// Root, session, human actor, rights and protected quote/context remain Core/native owned.
export const nativeSourceAnchorPort: SourceAnchorPort = {
  async revisions(projectId, attachmentId) {
    return decodeReaderRevisions(await request("document_reader_revisions", { projectId, attachmentId }), projectId, attachmentId);
  },
  async outline(projectId, revisionId, afterNodeId = null) {
    return decodeReaderOutline(await request("document_reader_outline", { projectId, revisionId, afterNodeId }), projectId, revisionId);
  },
  async list(projectId, revisionId, afterId = null) {
    return decodeAnchorIds(await request("document_reader_anchor_list", { projectId, revisionId, afterId }));
  },
  async read(projectId, revisionId, anchorId) {
    const receipt = decodeSourceAnchor(await request("document_reader_anchor_read", { projectId, anchorId, expectedRevisionId: revisionId }), projectId, revisionId);
    return receipt?.anchorId === anchorId ? receipt : null;
  },
  async create(projectId, commandId, selection) {
    const receipt = decodeSourceAnchor(await request("document_reader_anchor_create", { projectId, commandId, selection }), projectId, selection.revisionId);
    return receipt?.target.nodeId === selection.nodeId && (selection.normalizedRange === null
      || receipt.target.textPosition?.start === selection.normalizedRange.start && receipt.target.textPosition.end === selection.normalizedRange.end)
      ? receipt : null;
  },
};
