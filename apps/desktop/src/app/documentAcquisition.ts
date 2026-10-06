import { invoke } from "@tauri-apps/api/core";
import { sameAttachmentSelection, type AttachmentBeginOutcome, type AttachmentSelection, decodeAttachmentBeginOutcome } from "./documentAttachment";

export interface AvailableCopy {
  readonly copyId: string;
  readonly copySha256: string;
  readonly provider: string;
  readonly host: string;
  readonly license: string | null;
  readonly version: string | null;
}
export interface CopyReview {
  readonly reviewId: string;
  readonly copy: AvailableCopy;
  readonly redirectHosts: readonly string[];
}
export interface RetainedCandidate {
  readonly candidateId: string;
  readonly sourceName: string;
  readonly originalOperationId: string;
}
export interface CopyInventory {
  readonly copies: readonly AvailableCopy[];
  readonly retained: readonly RetainedCandidate[];
}
export type AccessNeedKind = "unknown" | "unavailable" | "rights-denied" | "entitlement-required";
export type AccessNeedChannel = "manual" | "institutional";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const projectUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const digest = /^[0-9a-f]{64}$/u;
const host = /^[a-z0-9.-]{1,253}$/u;
function record(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Object.keys(descriptors).length !== keys.length || !keys.every((key) => descriptors[key] && "value" in descriptors[key]!)) return null;
  return Object.fromEntries(keys.map((key) => [key, descriptors[key]!.value]));
}
function text(value: unknown, maximum: number): value is string {
  return typeof value === "string" && value.length <= maximum && !/[\u0000-\u001f\u007f]/u.test(value);
}
export function decodeCopy(value: unknown): AvailableCopy | null {
  const copy = record(value, ["copyId", "copySha256", "provider", "host", "license", "version"]);
  if (!copy || typeof copy.copyId !== "string" || !uuid.test(copy.copyId)
    || typeof copy.copySha256 !== "string" || !digest.test(copy.copySha256) || !text(copy.provider, 64)
    || typeof copy.host !== "string" || !host.test(copy.host)
    || copy.license !== null && !text(copy.license, 4096) || copy.version !== null && !text(copy.version, 256)) return null;
  return copy as unknown as AvailableCopy;
}
function exactSelection(value: unknown, selected: AttachmentSelection): boolean {
  const item = record(value, ["projectId", "workId", "workRevisionId", "versionId", "versionRevisionId", "sourceAssertionRevisionId"]);
  return Boolean(item && typeof item.projectId === "string" && projectUuid.test(item.projectId)
    && Object.entries(item).filter(([key]) => key !== "projectId").every(([, id]) => typeof id === "string" && uuid.test(id))
    && sameAttachmentSelection(item as unknown as AttachmentSelection, selected));
}
export function decodeCopies(value: unknown, selected: AttachmentSelection): CopyInventory | null {
  const response = record(value, ["schemaVersion", "selection", "copies", "retained"]);
  if (!response || response.schemaVersion !== "1.0" || !exactSelection(response.selection, selected)
    || !Array.isArray(response.copies) || response.copies.length > 100) return null;
  const copies = response.copies.map(decodeCopy);
  if (copies.some((copy) => copy === null) || new Set(copies.map((copy) => copy!.copyId)).size !== copies.length) return null;
  if (!Array.isArray(response.retained) || response.retained.length > 50) return null;
  const retained = response.retained.map((value) => {
    const item = record(value, ["candidateId", "sourceName", "originalOperationId"]);
    return item && typeof item.candidateId === "string" && uuid.test(item.candidateId)
      && typeof item.originalOperationId === "string" && uuid.test(item.originalOperationId)
      && text(item.sourceName, 255) && item.sourceName.length > 0 && !/[\\/]/u.test(item.sourceName)
      ? item as unknown as RetainedCandidate : null;
  });
  if (retained.some((item) => item === null) || new Set(retained.map((item) => item!.candidateId)).size !== retained.length) return null;
  return { copies: copies as AvailableCopy[], retained: retained as RetainedCandidate[] };
}
export function decodeCopyReview(value: unknown, selected: AttachmentSelection, copy: AvailableCopy): CopyReview | null {
  const response = record(value, ["schemaVersion", "selection", "reviewId", "copy", "redirectHosts", "storeInspect", "egress"]);
  const returned = decodeCopy(response?.copy);
  if (!response || response.schemaVersion !== "1.0" || !exactSelection(response.selection, selected)
    || typeof response.reviewId !== "string" || !uuid.test(response.reviewId) || !returned
    || Object.keys(copy).some((key) => copy[key as keyof AvailableCopy] !== returned[key as keyof AvailableCopy])
    || !Array.isArray(response.redirectHosts) || response.redirectHosts.length !== 0
    || response.storeInspect !== "allowed" || response.egress !== "confirmed-preview-required") return null;
  return { reviewId: response.reviewId, copy: returned, redirectHosts: [] };
}
export interface DocumentAcquisitionPort {
  copies(selection: AttachmentSelection): Promise<CopyInventory | null>;
  review(selection: AttachmentSelection, copy: AvailableCopy): Promise<CopyReview | null>;
  clearReview(): Promise<void>;
  download(selection: AttachmentSelection, review: CopyReview, operationId: string): Promise<AttachmentBeginOutcome>;
  recover(selection: AttachmentSelection, candidate: RetainedCandidate, operationId: string): Promise<AttachmentBeginOutcome>;
  annotate(selection: AttachmentSelection, copy: AvailableCopy | null, commandId: string, kind: AccessNeedKind, channel: AccessNeedChannel): Promise<boolean>;
}
const native = (): boolean => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
export const nativeDocumentAcquisitionPort: DocumentAcquisitionPort = {
  async copies(selection) {
    if (!native()) return null;
    try { return decodeCopies(await invoke<unknown>("document_acquisition_copies", { request: { schemaVersion: "1.0", selection } }), selection); }
    catch { return null; }
  },
  async review(selection, copy) {
    if (!native()) return null;
    try { return decodeCopyReview(await invoke<unknown>("document_acquisition_review", { request: {
      schemaVersion: "1.0", selection, copyId: copy.copyId, copySha256: copy.copySha256 } }), selection, copy); }
    catch { return null; }
  },
  async clearReview() {
    if (native()) { try { await invoke("document_acquisition_clear_review"); } catch { /* No consent is inferred. */ } }
  },
  async download(selection, review, operationId) {
    const unavailable = { schemaVersion: "1.0", status: "unavailable", operationId } as const;
    if (!native()) return unavailable;
    try { return decodeAttachmentBeginOutcome(await invoke<unknown>("document_acquisition_download", { request: {
      schemaVersion: "1.0", selection, reviewId: review.reviewId, operationId, matchConfirmed: true, permittedUse: "project-only" } })) ?? unavailable; }
    catch { return unavailable; }
  },
  async annotate(selection, copy, commandId, kind, channel) {
    if (!native()) return false;
    try {
      const result = record(await invoke<unknown>("document_acquisition_access_need", { request: {
        schemaVersion: "1.0", selection, copyId: copy?.copyId ?? null, copySha256: copy?.copySha256 ?? null,
        commandId, kind, channel } }), ["schemaVersion", "status", "commandId"]);
      return Boolean(result?.schemaVersion === "1.0" && result.status === "recorded" && result.commandId === commandId);
    } catch { return false; }
  },
  async recover(selection, candidate, operationId) {
    const unavailable = { schemaVersion: "1.0", status: "unavailable", operationId } as const;
    if (!native()) return unavailable;
    try { return decodeAttachmentBeginOutcome(await invoke<unknown>("document_acquisition_recover", { request: {
      schemaVersion: "1.0", selection, operationId, candidateId: candidate.candidateId,
      originalOperationId: candidate.originalOperationId } })) ?? unavailable; }
    catch { return unavailable; }
  },
};
