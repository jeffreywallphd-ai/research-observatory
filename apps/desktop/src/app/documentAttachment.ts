import type { VersionContext } from "@research-observatory/contracts/core-api";

export const DOCUMENT_ATTACHMENT_COMMANDS = {
  capabilities: "document_attachment_capabilities",
  begin: "document_attachment_begin",
  cancel: "document_attachment_cancel",
  commit: "document_attachment_commit",
  status: "document_attachment_status",
} as const;
export const DOCUMENT_ATTACHMENT_EVENT = "document_attachment_result";

export interface AttachmentSelection {
  readonly projectId: string;
  readonly workId: string;
  readonly workRevisionId: string;
  readonly versionId: string;
  readonly versionRevisionId: string;
  readonly sourceAssertionRevisionId: string;
}

export type AttachmentMode = "choose" | "drop";
export type AttachmentProblemCode = "unsupported-format" | "password-protected" | "oversize" | "unsafe-content"
  | "malformed-content" | "format-mismatch" | "rights-denied" | "interrupted" | "association-stale"
  | "authority-changed" | "worker-unavailable" | "storage-pressure" | "candidate-unavailable" | "unavailable";

export interface AttachmentCandidate {
  readonly candidateId: string;
  readonly sourceName: string;
  readonly byteLength: number;
  readonly format: "pdf" | "jats" | "tei" | "xml" | "html" | "docx" | "txt";
  readonly confirmationSha256: string;
  readonly confirmationRequired: true;
}

export interface AttachmentBeginRequest {
  readonly schemaVersion: "1.0";
  readonly mode: AttachmentMode;
  readonly operationId: string;
  readonly selection: AttachmentSelection;
}
export interface AttachmentCommitRequest {
  readonly schemaVersion: "1.0";
  readonly operationId: string;
  readonly sessionId: string;
  readonly candidateId: string;
  readonly confirmationSha256: string;
  readonly commandId: string;
  readonly selection: AttachmentSelection;
  readonly matchConfirmed: true;
  readonly permittedUse: "project-only";
}
export interface AttachmentCancelRequest {
  readonly schemaVersion: "1.0";
  readonly operationId: string;
  readonly sessionId: string | null;
  readonly candidateId: string | null;
}
export interface AttachmentStatusRequest {
  readonly schemaVersion: "1.0";
  readonly selection: AttachmentSelection;
  readonly operationId: string | null;
  readonly commandId: string | null;
}
export interface AttachmentStatus {
  readonly schemaVersion: "1.0";
  readonly status: "metadata-only" | "candidate" | "validating" | "processing" | "available" | "unavailable" | "denied" | "failed" | "cancelled" | "unconfirmed";
  readonly selection: AttachmentSelection;
  readonly operationId: string | null;
  readonly commandId: string | null;
  readonly attachmentId: string | null;
  readonly documentRevisionId: string | null;
  readonly code: AttachmentProblemCode | null;
  readonly retryRequest: AttachmentCommitRequest | null;
}
export type AttachmentEvent =
  | { readonly schemaVersion: "1.0"; readonly status: "candidate"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection; readonly candidate: AttachmentCandidate }
  | { readonly schemaVersion: "1.0"; readonly status: "rejected"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection; readonly code: AttachmentProblemCode }
  | { readonly schemaVersion: "1.0"; readonly status: "cancelled"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection };
export type AttachmentOutcome =
  | { readonly schemaVersion: "1.0"; readonly status: "attached"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection; readonly candidateId: string; readonly attachmentId: string; readonly documentRevisionId: string }
  | { readonly schemaVersion: "1.0"; readonly status: "rejected"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection; readonly code: AttachmentProblemCode }
  | { readonly schemaVersion: "1.0"; readonly status: "cancelled"; readonly operationId: string; readonly sessionId: string;
      readonly selection: AttachmentSelection };
export type AttachmentBeginOutcome =
  | { readonly schemaVersion: "1.0"; readonly status: "armed"; readonly operationId: string; readonly sessionId: string }
  | { readonly schemaVersion: "1.0"; readonly status: "unavailable" | "cancelled"; readonly operationId: string };

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;
const hex32 = /^[0-9a-f]{32}$/u;
const hex64 = /^[0-9a-f]{64}$/u;
const formats: readonly AttachmentCandidate["format"][] = ["pdf", "jats", "tei", "xml", "html", "docx", "txt"];
const problemCodes: readonly AttachmentProblemCode[] = ["unsupported-format", "password-protected", "oversize", "unsafe-content",
  "malformed-content", "format-mismatch", "rights-denied", "interrupted", "association-stale", "authority-changed",
  "worker-unavailable", "storage-pressure", "candidate-unavailable", "unavailable"];

function object(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !("value" in descriptors[key]!))) return null;
  const item = Object.fromEntries(Object.entries(descriptors).map(([key, descriptor]) => [key, descriptor.value]));
  return Object.keys(item).length === keys.length && keys.every((key) => Object.hasOwn(item, key)) ? item : null;
}
function id(value: unknown): value is string { return typeof value === "string" && uuid.test(value); }
function session(value: unknown): value is string { return typeof value === "string" && hex32.test(value); }
function operation(value: unknown): value is string { return id(value); }
function selection(value: unknown): AttachmentSelection | null {
  const item = object(value, ["projectId", "workId", "workRevisionId", "versionId", "versionRevisionId", "sourceAssertionRevisionId"]);
  if (!item || !Object.values(item).every(id)) return null;
  return item as unknown as AttachmentSelection;
}
function candidate(value: unknown): AttachmentCandidate | null {
  const item = object(value, ["candidateId", "sourceName", "byteLength", "format", "confirmationSha256", "confirmationRequired"]);
  if (!item || !id(item.candidateId) || typeof item.sourceName !== "string" || !item.sourceName.length || item.sourceName.length > 255
    || /[\\/\u0000-\u001f\u007f]/u.test(item.sourceName) || item.sourceName === "." || item.sourceName === ".."
    || typeof item.byteLength !== "number" || !Number.isSafeInteger(item.byteLength) || item.byteLength < 1 || item.byteLength > 128 * 1024 * 1024
    || !formats.includes(item.format as AttachmentCandidate["format"])
    || typeof item.confirmationSha256 !== "string" || !hex64.test(item.confirmationSha256) || item.confirmationRequired !== true) return null;
  return item as unknown as AttachmentCandidate;
}
function common(value: unknown, keys: readonly string[]): { item: Record<string, unknown>; selected: AttachmentSelection } | null {
  const item = object(value, keys), selected = selection(item?.selection);
  if (!item || !selected || item.schemaVersion !== "1.0" || !operation(item.operationId) || !session(item.sessionId)) return null;
  return { item, selected };
}

export function attachmentSelection(context: VersionContext, versionId: string, sourceAssertionRevisionId: string): AttachmentSelection | null {
  const versions = context.versions.filter((item) => item.versionId === versionId);
  const placements = context.placements.filter((item) => item.versionId === versionId);
  const version = versions[0], placement = placements[0];
  if (versions.length !== 1 || placements.length !== 1 || !version || !placement || placement.state !== "assigned" || placement.workIds.length !== 1
    || !sourceAssertionRevisionId || !version.definition.assertionRevisionIds.includes(sourceAssertionRevisionId)) return null;
  const works = context.works.filter((item) => item.workId === placement.workIds[0]);
  const work = works[0];
  if (works.length !== 1 || !work || work.disposition !== "active" || work.aliasTarget !== null || !version.definition.assertionRevisionIds.length
    || version.definition.assertionRevisionIds.some((assertion) => !work.assertionRevisionIds.includes(assertion)
      || !context.sources.some((source) => source.assertionRevisionId === assertion && source.assertion.projectId === context.projectId))) return null;
  return { projectId: context.projectId, workId: work.workId, workRevisionId: work.revisionId,
    versionId: version.versionId, versionRevisionId: version.revisionId, sourceAssertionRevisionId };
}
export function sameAttachmentSelection(first: AttachmentSelection | null, second: AttachmentSelection | null): boolean {
  return Boolean(first && second && first.projectId === second.projectId && first.workId === second.workId
    && first.workRevisionId === second.workRevisionId && first.versionId === second.versionId
    && first.versionRevisionId === second.versionRevisionId && first.sourceAssertionRevisionId === second.sourceAssertionRevisionId);
}
export function attachmentBeginRequest(mode: AttachmentMode, operationId: string, selected: AttachmentSelection): AttachmentBeginRequest {
  return { schemaVersion: "1.0", mode, operationId, selection: selected };
}
export function attachmentCommitRequest(operationId: string, sessionId: string, candidateId: string, confirmationSha256: string,
  commandId: string, selected: AttachmentSelection): AttachmentCommitRequest {
  return { schemaVersion: "1.0", operationId, sessionId, candidateId, confirmationSha256, commandId,
    selection: selected, matchConfirmed: true, permittedUse: "project-only" };
}
export function attachmentCancelRequest(operationId: string, sessionId: string | null, candidateId: string | null): AttachmentCancelRequest {
  return { schemaVersion: "1.0", operationId, sessionId, candidateId };
}
export function attachmentStatusRequest(selected: AttachmentSelection, operationId: string | null = null,
  commandId: string | null = null): AttachmentStatusRequest {
  return { schemaVersion: "1.0", selection: selected, operationId, commandId };
}
export function decodeAttachmentCommitRequest(value: unknown): AttachmentCommitRequest | null {
  const item = object(value, ["schemaVersion", "operationId", "sessionId", "candidateId", "confirmationSha256",
    "commandId", "selection", "matchConfirmed", "permittedUse"]);
  const selected = selection(item?.selection);
  if (!item || !selected || item.schemaVersion !== "1.0" || !operation(item.operationId) || !session(item.sessionId)
    || !id(item.candidateId) || typeof item.confirmationSha256 !== "string" || !hex64.test(item.confirmationSha256)
    || !operation(item.commandId) || item.matchConfirmed !== true || item.permittedUse !== "project-only") return null;
  return { schemaVersion: "1.0", operationId: item.operationId, sessionId: item.sessionId, candidateId: item.candidateId,
    confirmationSha256: item.confirmationSha256, commandId: item.commandId, selection: selected,
    matchConfirmed: true, permittedUse: "project-only" };
}
export function decodeAttachmentStatus(value: unknown): AttachmentStatus | null {
  const item = object(value, ["schemaVersion", "status", "selection", "operationId", "commandId", "attachmentId", "documentRevisionId", "code", "retryRequest"]);
  const selected = selection(item?.selection);
  const retryRequest = item?.retryRequest === null ? null : decodeAttachmentCommitRequest(item?.retryRequest);
  if (!item || !selected || item.schemaVersion !== "1.0"
    || !["metadata-only", "candidate", "validating", "processing", "available", "unavailable", "denied", "failed", "cancelled", "unconfirmed"].includes(item.status as string)
    || item.operationId !== null && !operation(item.operationId) || item.commandId !== null && !operation(item.commandId)
    || item.attachmentId !== null && !id(item.attachmentId) || item.documentRevisionId !== null && !id(item.documentRevisionId)
    || item.code !== null && !problemCodes.includes(item.code as AttachmentProblemCode)
    || item.retryRequest !== null && !retryRequest
    || (item.attachmentId === null) !== (item.documentRevisionId === null)
    || (["candidate", "validating", "processing", "available", "cancelled", "unconfirmed"].includes(item.status as string) && item.operationId === null)
    || (["processing", "available", "unconfirmed"].includes(item.status as string) && item.commandId === null)
    || (["processing", "available"].includes(item.status as string) && (item.attachmentId === null || item.code !== null))
    || (["candidate", "validating", "unconfirmed", "cancelled"].includes(item.status as string) && item.attachmentId !== null)
    || (["candidate", "validating", "processing", "available", "metadata-only", "unconfirmed"].includes(item.status as string) && item.code !== null)
    || (["denied", "failed", "unavailable"].includes(item.status as string) && item.code === null)
    || (item.status === "unconfirmed") !== (retryRequest !== null)
    || retryRequest && (retryRequest.operationId !== item.operationId || retryRequest.commandId !== item.commandId
      || !sameAttachmentSelection(retryRequest.selection, selected))
    || item.status === "metadata-only" && item.attachmentId !== null) return null;
  return { schemaVersion: "1.0", status: item.status as AttachmentStatus["status"], selection: selected,
    operationId: item.operationId as string | null, commandId: item.commandId as string | null,
    attachmentId: item.attachmentId as string | null, documentRevisionId: item.documentRevisionId as string | null,
    code: item.code as AttachmentProblemCode | null, retryRequest };
}
export function attachmentStatusMessage(result: AttachmentStatus | null): string {
  if (!result) return "Attachment status unavailable. Whether this version already has a local copy has not been checked.";
  const states: Record<AttachmentStatus["status"], string> = {
    "metadata-only": "Authoritative status: metadata only; no local copy attached to this exact version revision.",
    candidate: "Authoritative status: candidate awaiting researcher review; no attachment recorded.",
    validating: "Authoritative status: native validation in progress; no attachment result confirmed.",
    processing: "Authoritative status: attachment recorded; local processing is pending.",
    available: "Authoritative status: attachment available for permitted local inspection.",
    unavailable: "Authoritative status: attachment unavailable; inspect the reason before retrying.",
    denied: "Authoritative status: attachment denied; keep metadata only and review permission.",
    failed: "Authoritative status: attachment failed; inspect the reason before retrying.",
    cancelled: "Authoritative status: attachment cancelled; no result from this operation is trusted.",
    unconfirmed: "Authoritative status: the saved attachment decision has no confirmed result. Retry the same command after reviewing current authority.",
  };
  return states[result.status] + (result.code ? ` ${attachmentProblemMessage(result.code)}` : "");
}
export function canStartAttachmentReview(result: AttachmentStatus | null): boolean {
  if (!result) return false;
  if (result.code === "rights-denied" || result.code === "association-stale" || result.code === "authority-changed") return false;
  if (result.status === "metadata-only" || result.status === "cancelled") return true;
  if (result.status === "failed") return true;
  return result.status === "unavailable" && ["interrupted", "worker-unavailable", "storage-pressure",
    "candidate-unavailable", "unavailable"].includes(result.code ?? "");
}
export function decodeAttachmentEvent(value: unknown): AttachmentEvent | null {
  const probe = object(value, ["schemaVersion", "status", "operationId", "sessionId", "selection", "candidate"])
    ?? object(value, ["schemaVersion", "status", "operationId", "sessionId", "selection", "code"])
    ?? object(value, ["schemaVersion", "status", "operationId", "sessionId", "selection"]);
  if (!probe) return null;
  if (probe.status === "candidate") {
    const found = common(value, ["schemaVersion", "status", "operationId", "sessionId", "selection", "candidate"]);
    const detail = candidate(probe.candidate);
    return found && detail ? { schemaVersion: "1.0", status: "candidate", operationId: found.item.operationId as string,
      sessionId: found.item.sessionId as string, selection: found.selected, candidate: detail } : null;
  }
  if (probe.status === "rejected") {
    const found = common(value, ["schemaVersion", "status", "operationId", "sessionId", "selection", "code"]);
    return found && problemCodes.includes(probe.code as AttachmentProblemCode)
      ? { schemaVersion: "1.0", status: "rejected", operationId: found.item.operationId as string,
        sessionId: found.item.sessionId as string, selection: found.selected, code: probe.code as AttachmentProblemCode } : null;
  }
  const found = common(value, ["schemaVersion", "status", "operationId", "sessionId", "selection"]);
  return probe.status === "cancelled" && found ? { schemaVersion: "1.0", status: "cancelled", operationId: found.item.operationId as string,
    sessionId: found.item.sessionId as string, selection: found.selected } : null;
}
export function decodeAttachmentOutcome(value: unknown): AttachmentOutcome | null {
  const attached = common(value, ["schemaVersion", "status", "operationId", "sessionId", "selection", "candidateId", "attachmentId", "documentRevisionId"]);
  if (attached?.item.status === "attached" && id(attached.item.candidateId) && id(attached.item.attachmentId) && id(attached.item.documentRevisionId)) {
    return { schemaVersion: "1.0", status: "attached", operationId: attached.item.operationId as string,
      sessionId: attached.item.sessionId as string, selection: attached.selected, candidateId: attached.item.candidateId,
      attachmentId: attached.item.attachmentId, documentRevisionId: attached.item.documentRevisionId };
  }
  const stopped = decodeAttachmentEvent(value);
  return stopped?.status === "rejected" || stopped?.status === "cancelled" ? stopped : null;
}
export function decodeAttachmentBeginOutcome(value: unknown): AttachmentBeginOutcome | null {
  const armed = object(value, ["schemaVersion", "status", "operationId", "sessionId"]);
  if (armed?.schemaVersion === "1.0" && armed.status === "armed" && operation(armed.operationId) && session(armed.sessionId))
    return armed as unknown as AttachmentBeginOutcome;
  const stopped = object(value, ["schemaVersion", "status", "operationId"]);
  return stopped?.schemaVersion === "1.0" && (stopped.status === "unavailable" || stopped.status === "cancelled") && operation(stopped.operationId)
    ? stopped as unknown as AttachmentBeginOutcome : null;
}
export function decodeAttachmentCapability(value: unknown, projectId: string): boolean {
  const item = object(value, ["schemaVersion", "status", "projectId"]);
  return Boolean(item?.schemaVersion === "1.0" && item.status === "ready" && item.projectId === projectId);
}
export function attachmentProblemMessage(code: AttachmentProblemCode): string {
  const messages: Record<AttachmentProblemCode, string> = {
    "unsupported-format": "Unsupported document format. Choose a PDF, JATS, TEI, XML, HTML, DOCX or text copy.",
    "password-protected": "This copy is password protected. Choose an unlocked, lawfully usable copy.",
    oversize: "This copy exceeds the 128 MiB limit. Choose a smaller supported copy; no file was truncated.",
    "unsafe-content": "This copy failed safety inspection. Do not preview or bypass it; choose a safe alternative.",
    "malformed-content": "This copy is malformed. Choose another supported copy.",
    "format-mismatch": "The file type does not match its content. Choose a correctly labeled copy.",
    "rights-denied": "Rights deny local attachment. Keep metadata only and review source permission.",
    interrupted: "Copy or inspection was interrupted. Retry with a fresh check of this Work and version.",
    "association-stale": "The Work, version or source changed. Refresh current evidence before retrying.",
    "authority-changed": "Project or source authority changed. Reopen the project and review permission.",
    "worker-unavailable": "Local document inspection is unavailable. Retry when the worker is ready.",
    "storage-pressure": "Local storage cannot admit this copy. Free space or choose a smaller file.",
    "candidate-unavailable": "The pending candidate is unavailable. Choose the file again.",
    unavailable: "The native attachment bridge is unavailable. No file was selected or attached.",
  };
  return messages[code];
}

export function newAttachmentId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  const time = BigInt(Date.now());
  for (let index = 0; index < 6; index += 1) bytes[5 - index] = Number((time >> BigInt(index * 8)) & 255n);
  bytes[6] = (bytes[6]! & 15) | 0x70;
  bytes[8] = (bytes[8]! & 63) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
