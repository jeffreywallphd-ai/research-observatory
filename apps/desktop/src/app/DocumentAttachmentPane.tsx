import { useEffect, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, type VersionContext } from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import {
  attachmentBeginRequest, attachmentCancelRequest, attachmentCommitRequest, attachmentProblemMessage,
  attachmentSelection, attachmentStatusMessage, attachmentStatusRequest, canStartAttachmentReview, canReviewAvailableCopies,
  isInterruptedPriorSessionStatus, newAttachmentId, sameAttachmentSelection,
  type AttachmentCandidate, type AttachmentCommitRequest, type AttachmentEvent, type AttachmentOutcome,
  type AttachmentProblemCode, type AttachmentSelection, type AttachmentMode, type AttachmentStatus,
} from "./documentAttachment";
import { nativeDocumentAttachmentPort, type DocumentAttachmentPort } from "./documentAttachmentNative";
import { AvailableCopiesPane } from "./AvailableCopiesPane";
import type { AttachmentBeginOutcome } from "./documentAttachment";

type Client = ReturnType<typeof createCoreApiClient>;
export interface AttachmentHandoff {
  readonly selection: AttachmentSelection;
  readonly operationId: string | null;
  readonly commitRequest: AttachmentCommitRequest | null;
  readonly attachmentId: string | null;
  readonly documentRevisionId: string | null;
  readonly copyId?: string | null;
}
interface PendingOperation {
  readonly operationId: string;
  readonly selection: AttachmentSelection;
  sessionId: string | null;
  candidateId: string | null;
  phase: "stage" | "commit";
  remote?: boolean;
}

const kindLabel = (kind: string): string => kind.replaceAll("-", " ");
const sourceTitle = (context: VersionContext, id: string): string =>
  context.sources.find((source) => source.assertionRevisionId === id)?.assertion.fields.find((field) => field.name === "title")?.observed
  ?? "Title not reported";
const sameSavedDecision = (left: AttachmentCommitRequest, right: AttachmentCommitRequest): boolean =>
  left.schemaVersion === right.schemaVersion && left.operationId === right.operationId
  && left.sessionId === right.sessionId && left.candidateId === right.candidateId
  && left.confirmationSha256 === right.confirmationSha256 && left.commandId === right.commandId
  && sameAttachmentSelection(left.selection, right.selection)
  && left.matchConfirmed === right.matchConfirmed && left.permittedUse === right.permittedUse;

export function DocumentAttachmentPane({ root, context, versionId, client, announce, onClose, onTaskCenter, initialSourceId,
  onRecoveryContext: recoveryContext, initialHandoff, port = nativeDocumentAttachmentPort }: {
  readonly root: string;
  readonly context: VersionContext;
  readonly versionId: string;
  readonly client: Client;
  readonly announce: (message: string) => void;
  readonly onClose: () => void;
  readonly onTaskCenter?: ((handoff: AttachmentHandoff) => void) | undefined;
  readonly onRecoveryContext?: ((selection: AttachmentSelection, handoff: AttachmentHandoff | null) => void) | undefined;
  readonly initialSourceId?: string | undefined;
  readonly initialHandoff?: AttachmentHandoff | null | undefined;
  readonly port?: DocumentAttachmentPort;
}): ReactNode {
  const version = context.versions.find((item) => item.versionId === versionId);
  const sourceIds = version?.definition.assertionRevisionIds ?? [];
  const [sourceId, setSourceId] = useState(sourceIds.includes(initialSourceId ?? "") ? initialSourceId! : "");
  const [copyId, setCopyId] = useState<string | null>(initialHandoff?.copyId ?? null);
  const onRecoveryContext = (selection: AttachmentSelection, handoff: AttachmentHandoff | null): void =>
    recoveryContext?.(selection, handoff ? { ...handoff, copyId } : null);
  const [permittedUse, setPermittedUse] = useState<"" | "project-only" | "unknown" | "denied">("");
  const [matchConfirmed, setMatchConfirmed] = useState(false);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [candidate, setCandidate] = useState<AttachmentCandidate | null>(null);
  const [committed, setCommitted] = useState<AttachmentOutcome | null>(() => {
    const command = initialHandoff?.commitRequest;
    return command && initialHandoff?.attachmentId && initialHandoff.documentRevisionId
      ? { schemaVersion: "1.0", status: "attached", operationId: command.operationId, sessionId: command.sessionId,
        selection: command.selection, candidateId: command.candidateId, attachmentId: initialHandoff.attachmentId,
        documentRevisionId: initialHandoff.documentRevisionId } : null;
  });
  const [problem, setProblem] = useState<AttachmentProblemCode | null>(null);
  const [unconfirmed, setUnconfirmed] = useState<AttachmentCommitRequest | null>(initialHandoff?.attachmentId ? null : initialHandoff?.commitRequest ?? null);
  const [retryHeld, setRetryHeld] = useState(Boolean(initialHandoff?.commitRequest && !initialHandoff.attachmentId));
  const [attachmentStatus, setAttachmentStatus] = useState<AttachmentStatus | null>(null);
  const [statusNonce, setStatusNonce] = useState(0);
  const [status, setStatus] = useState("Attachment status has not been confirmed. Select the retained source assertion to check this exact version before choosing a copy.");
  const live = useRef(true), generation = useRef(0), pending = useRef<PendingOperation | null>(initialHandoff?.commitRequest && !initialHandoff.attachmentId
    ? { operationId: initialHandoff.commitRequest.operationId, selection: initialHandoff.commitRequest.selection,
      sessionId: initialHandoff.commitRequest.sessionId, candidateId: initialHandoff.commitRequest.candidateId, phase: "commit" } : null), committedRef = useRef(Boolean(initialHandoff?.attachmentId));
  const unconfirmedRef = useRef<AttachmentCommitRequest | null>(initialHandoff?.attachmentId ? null : initialHandoff?.commitRequest ?? null);
  const lastCommit = useRef<AttachmentCommitRequest | null>(initialHandoff?.commitRequest ?? null);
  const heading = useRef<HTMLHeadingElement>(null), candidateHeading = useRef<HTMLHeadingElement>(null);
  const statusHeading = useRef<HTMLParagraphElement>(null);
  const taskCenterHandoff = useRef(false);
  const selected = attachmentSelection(context, versionId, sourceId);
  const placement = context.placements.find((item) => item.versionId === versionId);
  const work = placement?.workIds.length === 1 ? context.works.find((item) => item.workId === placement.workIds[0]) : null;
  const validVersion = Boolean(version && placement?.state === "assigned" && work?.disposition === "active");
  const cleanupRequired = problem === "cleanup-required" || attachmentStatus?.code === "cleanup-required";
  const canBegin = available && !cleanupRequired && selected !== null && canStartAttachmentReview(attachmentStatus);
  const canReviewCopies = available && !cleanupRequired && selected !== null && canReviewAvailableCopies(attachmentStatus);
  const responseCommand = committed?.status === "attached" && lastCommit.current
    && sameAttachmentSelection(committed.selection, lastCommit.current.selection)
    && committed.operationId === lastCommit.current.operationId
    && committed.sessionId === lastCommit.current.sessionId
    && committed.candidateId === lastCommit.current.candidateId ? lastCommit.current : null;
  const historicalReply: AttachmentHandoff | null = committed?.status === "attached" && responseCommand
    ? { selection: responseCommand.selection, operationId: responseCommand.operationId, commitRequest: responseCommand,
      attachmentId: committed.attachmentId, documentRevisionId: committed.documentRevisionId } : null;
  const recoverableAfterReply = Boolean(committed?.status === "attached" && attachmentStatus && responseCommand
    && sameAttachmentSelection(committed.selection, attachmentStatus.selection)
    && attachmentStatus.operationId === committed.operationId
    && attachmentStatus.commandId === responseCommand.commandId
    && ["failed", "cancelled", "unavailable"].includes(attachmentStatus.status)
    && canStartAttachmentReview(attachmentStatus)
    && (attachmentStatus.attachmentId === null || attachmentStatus.attachmentId === committed.attachmentId)
    && (attachmentStatus.documentRevisionId === null || attachmentStatus.documentRevisionId === committed.documentRevisionId));
  const committedBlocksNew = Boolean(committed) && !recoverableAfterReply;

  useEffect(() => {
    let active = true;
    setAttachmentStatus(null);
    if (selected) {
      const savedCommand = lastCommit.current && sameAttachmentSelection(selected, lastCommit.current.selection)
        ? lastCommit.current : null;
      const handoff = initialHandoff && sameAttachmentSelection(selected, initialHandoff.selection) ? initialHandoff : null;
      const request = attachmentStatusRequest(selected, savedCommand?.operationId ?? handoff?.operationId ?? null,
        savedCommand?.commandId ?? handoff?.commitRequest?.commandId ?? null);
      void port.status(request).then((result) => {
        const interruptedPriorSession = result && isInterruptedPriorSessionStatus(savedCommand, request, result,
          committed !== null) && unconfirmedRef.current !== null && savedCommand !== null
          && sameSavedDecision(unconfirmedRef.current, savedCommand);
        if (active && live.current && result && sameAttachmentSelection(request.selection, result.selection)
          && (request.operationId === null || result.operationId === request.operationId)
          && (request.commandId === null || result.commandId === request.commandId || interruptedPriorSession)) {
          if (result.status === "unconfirmed" && (!result.retryRequest || lastCommit.current
            && !sameSavedDecision(lastCommit.current, result.retryRequest))) {
            setRetryHeld(true);
            const message = "The native status did not match the exact saved attachment decision. No retry was sent; check durable status in Task Center.";
            setStatus(message); announce(message);
            return;
          }
          setAttachmentStatus(result);
          const command = unconfirmedRef.current;
          if (interruptedPriorSession && command) {
            generation.current += 1;
            pending.current = null; unconfirmedRef.current = null; lastCommit.current = null;
            setUnconfirmed(null); setRetryHeld(false); setBusy(false); setCandidate(null);
            setMatchConfirmed(false); setPermittedUse(""); setProblem(null);
            const message = "The saved attachment decision belongs to an earlier session and cannot be retried. Choose the file again after reviewing the current Work/version and rights.";
            setStatus(message); announce(message);
            onRecoveryContext?.(command.selection, null);
            return;
          }
          if (!command && (result.status === "processing" || result.status === "available")
            && result.attachmentId && result.documentRevisionId) {
            onRecoveryContext?.(selected, historicalReply && result.operationId === historicalReply.operationId
              && result.commandId === historicalReply.commitRequest?.commandId ? historicalReply
              : { selection: selected, operationId: result.operationId,
                commitRequest: null, attachmentId: result.attachmentId, documentRevisionId: result.documentRevisionId });
          }
          if (result.status === "unconfirmed" && result.retryRequest) {
            const retry = result.retryRequest;
            setRetryHeld(false);
            pending.current = { operationId: retry.operationId, selection: retry.selection, sessionId: retry.sessionId,
              candidateId: retry.candidateId, phase: "commit" };
            unconfirmedRef.current = retry; lastCommit.current = retry; setUnconfirmed(retry);
            onRecoveryContext?.(retry.selection, historicalReply && retry.operationId === historicalReply.operationId
              && retry.commandId === historicalReply.commitRequest?.commandId
              && retry.sessionId === historicalReply.commitRequest?.sessionId
              && retry.candidateId === historicalReply.commitRequest?.candidateId ? historicalReply
              : { selection: retry.selection, operationId: retry.operationId,
                commitRequest: retry, attachmentId: null, documentRevisionId: null });
          }
          if (command && result.commandId === command.commandId && result.operationId === command.operationId) {
            if ((result.status === "processing" || result.status === "available") && result.attachmentId && result.documentRevisionId) {
              committedRef.current = true; pending.current = null; unconfirmedRef.current = null; setUnconfirmed(null);
              setCandidate(null); setMatchConfirmed(false); setPermittedUse("");
              setCommitted({ schemaVersion: "1.0", status: "attached", operationId: command.operationId,
                sessionId: command.sessionId, selection: command.selection, candidateId: command.candidateId,
                attachmentId: result.attachmentId, documentRevisionId: result.documentRevisionId });
              onRecoveryContext?.(command.selection, { selection: command.selection, operationId: command.operationId,
                commitRequest: command, attachmentId: result.attachmentId, documentRevisionId: result.documentRevisionId });
            } else if (["denied", "failed", "cancelled", "unavailable"].includes(result.status)) {
              pending.current = null; unconfirmedRef.current = null; setUnconfirmed(null); setRetryHeld(false);
              const retained = historicalReply && historicalReply.commitRequest?.commandId === command.commandId
                ? historicalReply : null;
              if (!retained) lastCommit.current = null;
              onRecoveryContext?.(command.selection, retained);
            }
          }
        }
      }).catch(() => { /* Unknown is safer than an invented absence. */ });
    }
    return () => { active = false; };
  }, [port, context, versionId, sourceId, statusNonce]);

  function clearPending(message: string): void {
    generation.current += 1;
    const operation = pending.current;
    pending.current = null;
    if (operation) void port.cancel(attachmentCancelRequest(operation.operationId, operation.sessionId, operation.candidateId));
    committedRef.current = false;
    setCandidate(null); setCommitted(null); setUnconfirmed(null); setRetryHeld(false);
    unconfirmedRef.current = null; lastCommit.current = null;
    setMatchConfirmed(false); setPermittedUse("");
    setBusy(false); setProblem(null); setStatus(message);
    announce(message);
  }
  function cancelAndReturn(): void {
    if (unconfirmedRef.current) return;
    clearPending("Attachment cancelled. Selected Work/version and metadata remain unchanged.");
    onClose();
  }

  useEffect(() => {
    live.current = true;
    heading.current?.focus();
    let unsubscribe: (() => void) | null = null;
    const listener = async (): Promise<void> => {
      try {
        unsubscribe = await port.subscribe(handleEvent);
        if (!live.current) { unsubscribe(); return; }
        const ready = await port.available(context.projectId);
        if (live.current) {
          setAvailable(ready);
          if (!ready) setStatus("Native attachment is unavailable until the trusted bridge is installed. Metadata and selected version remain available.");
        }
      } catch {
        if (live.current) { setAvailable(false); setStatus("Native attachment is unavailable until the trusted bridge is installed."); }
      }
    };
    void listener();
    return () => {
      live.current = false; generation.current += 1;
      const operation = pending.current;
      pending.current = null;
      if (operation && !taskCenterHandoff.current && !committedRef.current && !unconfirmedRef.current)
        void port.cancel(attachmentCancelRequest(operation.operationId, operation.sessionId, operation.candidateId));
      if (unsubscribe) unsubscribe();
    };
  }, [port, context.projectId, versionId]);
  useEffect(() => { if (candidate) candidateHeading.current?.focus(); }, [candidate]);

  useEffect(() => {
    if (!busy) return;
    let disposed = false, checking = false;
    const ticket = generation.current;
    const timer = globalThis.setInterval(() => {
      const operation = pending.current;
      if (disposed || checking || !operation?.remote || operation.phase !== "stage" || !operation.sessionId) return;
      checking = true;
      void port.status(attachmentStatusRequest(operation.selection, operation.operationId)).then((result) => {
        if (disposed || !live.current || generation.current !== ticket || pending.current !== operation
          || !result || result.operationId !== operation.operationId
          || !sameAttachmentSelection(result.selection, operation.selection)) return;
        if (result.status === "downloading" || result.status === "validating") {
          setAttachmentStatus(result);
          setStatus(result.status === "validating"
            ? "Validating the encrypted copy at the native boundary. Explicit Attach remains required."
            : "Downloading confirmed copy into encrypted local staging. Explicit Attach remains required.");
        }
      }).catch(() => { /* An unreadable status does not invent a terminal result. */ })
        .finally(() => { checking = false; });
    }, 1_000);
    return () => { disposed = true; globalThis.clearInterval(timer); };
  }, [busy, port]);

  function handleEvent(event: AttachmentEvent): void {
    const operation = pending.current;
    if (!live.current || !operation || event.operationId !== operation.operationId
      || !sameAttachmentSelection(operation.selection, event.selection)
      || operation.sessionId !== null && operation.sessionId !== event.sessionId) return;
    operation.sessionId = event.sessionId;
    if (operation.phase === "commit") return;
    if (event.status === "candidate") {
      operation.candidateId = event.candidate.candidateId;
      setCandidate(event.candidate); setProblem(null); setBusy(false); setMatchConfirmed(false); setPermittedUse("");
      setStatus("Candidate inspected by the native boundary. Confirm the exact Work/version and permitted local use before attachment.");
      announce("Document candidate ready for researcher confirmation.");
    } else if (event.status === "rejected") {
      pending.current = null; lastCommit.current = null;
      setCandidate(null); setProblem(event.code); setBusy(false);
      setStatus(attachmentProblemMessage(event.code));
      announce("Document attachment needs attention.");
    } else {
      pending.current = null; lastCommit.current = null;
      setCandidate(null); setBusy(false);
      setStatus("Attachment cancelled. Selected Work/version and metadata remain unchanged.");
      announce("Attachment cancelled.");
      onClose();
    }
  }

  async function exactCurrent(binding: AttachmentSelection, ticket: number): Promise<boolean> {
    try {
      const fresh = await client.inspectScholarlyVersionContext({ root, workIds: [binding.workId] });
      if (!live.current || generation.current !== ticket) return false;
      if (fresh.projectId === context.projectId && sameAttachmentSelection(binding,
        attachmentSelection(fresh, binding.versionId, binding.sourceAssertionRevisionId))) return true;
    } catch { /* Deny on unreadable or changed authority. */ }
    if (live.current && generation.current === ticket) {
      if (unconfirmedRef.current || lastCommit.current) {
        const message = "Current Work/version or source authority changed. An earlier attachment decision may have succeeded; no new command was sent. Check exact native status in Task Center and review current authority.";
        setBusy(false); setStatus(message); setProblem(null); announce(message);
        return false;
      }
      clearPending("Work, version, source or rights evidence changed. Refresh current version evidence before retrying; no attachment was made.");
      setProblem("association-stale");
    }
    return false;
  }

  async function begin(mode: AttachmentMode): Promise<void> {
    if (!canBegin || busy || !selected || unconfirmed || committedBlocksNew) return;
    const ticket = ++generation.current;
    setBusy(true); setProblem(null); setCandidate(null);
    setMatchConfirmed(false); setPermittedUse("");
    setStatus("Checking current Work/version and source authority…");
    if (!await exactCurrent(selected, ticket)) return;
    lastCommit.current = null;
    committedRef.current = false; setCommitted(null);
    const previous = pending.current;
    pending.current = null;
    if (previous) void port.cancel(attachmentCancelRequest(previous.operationId, previous.sessionId, previous.candidateId));
    const operationId = newAttachmentId();
    pending.current = { operationId, selection: selected, sessionId: null, candidateId: null, phase: "stage" };
    setStatus(mode === "choose" ? "Waiting for the native document picker…" : "Native file drop armed for this selected version…");
    const result = await port.begin(attachmentBeginRequest(mode, operationId, selected));
    const operation = pending.current;
    if (!live.current || generation.current !== ticket || operation?.operationId !== operationId) {
      void port.cancel(attachmentCancelRequest(operationId, result.status === "armed" ? result.sessionId : null, null));
      return;
    }
    if (result.status === "armed") {
      if (operation.sessionId && operation.sessionId !== result.sessionId) {
        clearPending("The native reply did not match this attachment operation. Choose the file again.");
        setProblem("interrupted"); return;
      }
      operation.sessionId = result.sessionId;
      if (!operation.candidateId) setBusy(false);
    } else {
      clearPending(result.status === "cancelled" ? "File selection cancelled. Selected Work/version and metadata remain unchanged."
        : attachmentProblemMessage("unavailable"));
      if (result.status === "unavailable") setProblem("unavailable");
      if (result.status === "cancelled") onClose();
    }
  }

  async function commit(): Promise<void> {
    const operation = pending.current;
    if (!operation || !selected || !sameAttachmentSelection(operation.selection, selected)
      || !operation.sessionId || busy || unconfirmed && retryHeld || committed && !unconfirmed
      || !unconfirmed && (!candidate || !matchConfirmed || permittedUse !== "project-only")) return;
    const ticket = ++generation.current;
    setBusy(true); setProblem(null); setStatus("Rechecking exact Work/version and rights before attachment…");
    if (!await exactCurrent(selected, ticket)) return;
    const command = unconfirmed ?? attachmentCommitRequest(operation.operationId, operation.sessionId!, candidate!.candidateId,
      candidate!.confirmationSha256, newAttachmentId(), selected);
    operation.phase = "commit";
    setUnconfirmed(command); setRetryHeld(false); unconfirmedRef.current = command; lastCommit.current = command;
    onRecoveryContext?.(selected, { selection: selected, operationId: command.operationId,
      commitRequest: command, attachmentId: null, documentRevisionId: null });
    const result = await port.commit(command);
    if (!live.current || generation.current !== ticket || pending.current?.operationId !== operation.operationId) return;
    setBusy(false);
    if (!result) {
      setStatus("The attachment reply was not confirmed. Retry the same saved decision; do not choose another file until its outcome is known.");
      announce("Attachment reply unconfirmed. Retry the same decision.");
      setStatusNonce((value) => value + 1);
      return;
    }
    if (result.operationId !== operation.operationId || result.sessionId !== operation.sessionId
      || !sameAttachmentSelection(result.selection, selected)
      || result.status === "attached" && result.candidateId !== command.candidateId) {
      setStatus("The native result did not match the selected version. No result is trusted; retry the same saved decision.");
      announce("Attachment result could not be matched."); return;
    }
    setUnconfirmed(null); unconfirmedRef.current = null;
    operation.phase = "stage";
    if (result.status === "attached") {
      committedRef.current = true; pending.current = null;
      setCandidate(null); setMatchConfirmed(false); setPermittedUse("");
      setCommitted(result); setStatus("Native attachment response reported a recorded copy for this exact Work/version revision. Check durable processing status in Task Center; the protected reader is pending.");
      announce("Document attachment recorded for the selected version.");
      onRecoveryContext?.(selected, { selection: selected, operationId: command.operationId,
        commitRequest: command, attachmentId: result.attachmentId, documentRevisionId: result.documentRevisionId });
    } else if (result.status === "rejected") {
      pending.current = null; if (!historicalReply) lastCommit.current = null;
      setProblem(result.code); setCandidate(null); setStatus(attachmentProblemMessage(result.code));
      announce("Document attachment needs attention.");
      onRecoveryContext?.(selected, historicalReply);
    } else {
      pending.current = null; if (!historicalReply) lastCommit.current = null;
      setCandidate(null); setStatus("Attachment cancelled. Selected Work/version and metadata remain unchanged.");
      announce("Attachment cancelled.");
      onRecoveryContext?.(selected, historicalReply);
    }
    setStatusNonce((value) => value + 1);
  }

  async function beginRemote(operationId: string, action: () => Promise<AttachmentBeginOutcome>): Promise<void> {
    if (!selected || busy || unconfirmed || committedBlocksNew || candidate) return;
    const ticket = ++generation.current;
    setBusy(true); setProblem(null); setMatchConfirmed(false); setPermittedUse("");
    if (!await exactCurrent(selected, ticket)) return;
    pending.current = { operationId, selection: selected, sessionId: null, candidateId: null, phase: "stage", remote: true };
    setStatus("Downloading confirmed copy into encrypted local staging. Explicit Attach remains required.");
    const result = await action();
    const operation = pending.current;
    if (!live.current || generation.current !== ticket || operation?.operationId !== operationId) {
      void port.cancel(attachmentCancelRequest(operationId, result.status === "armed" ? result.sessionId : null, null));
      return;
    }
    if (result.status === "armed" && (!operation.sessionId || operation.sessionId === result.sessionId)) {
      operation.sessionId = result.sessionId;
    } else {
      clearPending("Download requires fresh current-copy review. Metadata remains available; no attachment is confirmed.");
      setProblem("unavailable");
    }
  }

  const currentStatus = problem ? attachmentProblemMessage(problem) : status;
  return <Panel title="Attach full text to selected version"><section className="ro-stack ro-form" aria-label="Selected-version attachment"
    aria-busy={busy} onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation();
        if (unconfirmed) { setStatus("The attachment decision is unresolved. Use Task Center to check exact status or retry the same saved decision."); statusHeading.current?.focus(); }
        else if (committedBlocksNew) onClose();
        else cancelAndReturn();
      }
    }}>
    <h4 ref={heading} tabIndex={-1}>Selected Work and version</h4>
    <p>Local full-text attachment follows the current Work/version selection. Filename and title similarity cannot establish an association.</p>
    {validVersion ? <dl className="import-rights ro-wrap-anywhere">
      <div><dt>Work</dt><dd>{work!.workId} · revision {work!.revisionId}</dd></div>
      <div><dt>Version</dt><dd>{kindLabel(version!.definition.kind)} · {versionId} · revision {version!.revisionId}</dd></div>
      <div><dt>Full text</dt><dd><span role="status" aria-live="polite" aria-atomic="true">{attachmentStatusMessage(attachmentStatus)}</span>
        {attachmentStatus?.attachmentId && attachmentStatus.documentRevisionId
          ? ` Attachment ${attachmentStatus.attachmentId} · document revision ${attachmentStatus.documentRevisionId}.` : null}</dd></div>
    </dl> : <Notification tone="warning" title="Select an unambiguous current version">This version must belong to exactly one active Work. Refresh version evidence before attachment.</Notification>}
    {committed?.status === "attached" ? <p className="ro-wrap-anywhere">Earlier native response reported attachment {committed.attachmentId} and document revision {committed.documentRevisionId}; current authoritative status is shown above.</p> : null}
    <div className="ro-field"><label htmlFor="attachment-source">Source assertion for this version</label>
      <select id="attachment-source" value={sourceId} disabled={busy || Boolean(unconfirmed) || committedBlocksNew} onChange={(event) => {
        clearPending("Source selection changed. The pending candidate was discarded."); setCopyId(null); setSourceId(event.currentTarget.value);
      }}><option value="">Select the retained source assertion</option>{sourceIds.map((id) => <option key={id} value={id}>{sourceTitle(context, id).slice(0, 120)} · {id}</option>)}</select>
    </div>
    <p>Source rights and acquisition status remain separate. Choose a lawful local copy; this selection does not grant export, redistribution or model use.</p>
    {selected ? <AvailableCopiesPane selection={selected} downloadAllowed={canReviewCopies}
      disabled={!canReviewCopies && attachmentStatus?.status !== "candidate" || busy || Boolean(unconfirmed) || committedBlocksNew || Boolean(candidate)}
      announce={announce} beginRemote={beginRemote} initialCopyId={initialHandoff?.copyId === copyId ? copyId : null} onCopySelect={setCopyId} /> : null}
    <div className="ro-action-row"><Button disabled={!canBegin || busy || Boolean(unconfirmed) || committedBlocksNew} onClick={() => void begin("choose")}>Choose local full-text file…</Button></div>
    <section className="ro-stack" aria-label="Native document drop target" data-document-native-drop-target="true">
      <p>Native document drop target for this selected version. File paths and bytes stay outside the renderer. Arm this target before dropping a lawful local copy.</p>
      <Button disabled={!canBegin || busy || Boolean(unconfirmed) || committedBlocksNew} onClick={() => void begin("drop")}>Arm native file drop</Button>
    </section>
    {!available ? <Notification tone="info" title="Native attachment unavailable">Production choose, drop and attach remain unavailable until the trusted native/Core bridge is installed. No renderer file chooser or drop-path event is used.</Notification> : null}
    {candidate ? <section className="ro-stack" aria-label="Pending document candidate"><h4 ref={candidateHeading} tabIndex={-1}>Pending document candidate</h4>
      <p className="ro-wrap-anywhere">{candidate.sourceName} · {candidate.format.toUpperCase()} · {candidate.byteLength.toLocaleString()} bytes. Native inspection produced this candidate; no canonical attachment has been recorded yet.</p>
      <label className="ro-cluster"><input type="checkbox" checked={matchConfirmed} disabled={busy || Boolean(unconfirmed)} onChange={(event) => setMatchConfirmed(event.currentTarget.checked)} />I confirm this file belongs to the selected Work and version shown above.</label>
      <div className="ro-field"><label htmlFor="attachment-rights">Permitted use</label><select id="attachment-rights" value={permittedUse} disabled={busy || Boolean(unconfirmed)} onChange={(event) => setPermittedUse(event.currentTarget.value as typeof permittedUse)}>
        <option value="">Select rights status</option><option value="project-only">I may store and inspect this copy in this project</option>
        <option value="unknown">Unknown — keep metadata only</option><option value="denied">Denied — keep metadata only</option></select></div>
      {permittedUse === "unknown" ? <p>Rights unknown. Keep metadata only until permitted use is established.</p> : null}
      {permittedUse === "denied" ? <p>Rights denied. Keep metadata only and review source permission.</p> : null}
      <Button tone="primary" disabled={busy || !matchConfirmed || permittedUse !== "project-only" || Boolean(unconfirmed)} onClick={() => void commit()}>Attach to selected version</Button>
    </section> : null}
    <p ref={statusHeading} tabIndex={-1} role="status" aria-live="polite">{currentStatus}</p>
    <div className="ro-action-row"><Button disabled={Boolean(unconfirmed) || committedBlocksNew} onClick={cancelAndReturn}>Cancel attachment</Button>
      {unconfirmed ? <Button disabled={busy || !available || retryHeld} onClick={() => void commit()}>Retry same attachment decision</Button>
        : <Button disabled={!canBegin || busy || committedBlocksNew} onClick={() => void begin("choose")}>Choose another file…</Button>}
      <Button disabled={!selected || busy && !pending.current?.remote || !onTaskCenter} onClick={() => { if (!selected) return; taskCenterHandoff.current = true; onTaskCenter?.({ selection: selected,
        copyId,
        operationId: pending.current?.operationId ?? attachmentStatus?.operationId ?? committed?.operationId ?? null,
        commitRequest: lastCommit.current && (unconfirmed || committed) && lastCommit.current.operationId === (pending.current?.operationId ?? committed?.operationId)
          ? lastCommit.current : null,
        attachmentId: committed?.status === "attached" ? committed.attachmentId : attachmentStatus?.attachmentId ?? null,
        documentRevisionId: committed?.status === "attached" ? committed.documentRevisionId : attachmentStatus?.documentRevisionId ?? null }); }}>View Task Center</Button>
      <Button disabled={busy || Boolean(unconfirmed)} onClick={onClose}>Return to Work versions</Button></div>
    <Button disabled>Open in Document Reader · pending viewer</Button>
    <p>The reader stays unavailable until CAP-05.S04 provides protected source viewing and an exact-revision return route.</p>
  </section></Panel>;
}
