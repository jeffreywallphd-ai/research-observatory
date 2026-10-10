import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Notification } from "@research-observatory/ui-components";
import { newAttachmentId } from "./documentAttachment";
import { type ViewerMetadata, type ViewerMainAdmission } from "./documentViewer";
import { decodeReaderAction, nativeReaderActionPort, readerActions,
  type ReaderAction, type ReaderActionPort, type ReaderActionRequest, type ReaderPolicy } from "./viewerActions";

const labels: Record<ReaderAction, string> = {
  "copy-quotation": "Copy selected quotation with source identifiers",
  "print-quotation": "Print selected quotation with source identifiers",
  "export-quotation": "Save selected quotation with source identifiers",
  "export-annotation": "Save anchor annotation without quoted text",
  "open-external-original": "Open retained original with a local application",
};
interface Props {
  readonly metadata: ViewerMetadata; readonly anchorId: string | null;
  readonly main: ViewerMainAdmission; readonly reserveCore: () => () => void;
  readonly announce: (message: string) => void; readonly onReturn: () => void;
  readonly port?: ReaderActionPort;
}
interface Owned { readonly request: ReaderActionRequest; readonly release: () => void }

export function ViewerActionsPane({ metadata, anchorId, main, reserveCore, announce, onReturn, port = nativeReaderActionPort }: Props): ReactNode {
  const [action, setAction] = useState<ReaderAction>("copy-quotation"), [decision, setDecision] = useState<ReaderPolicy | null>(null);
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [unknown, setUnknown] = useState(false);
  const [allocationReady, setAllocationReady] = useState(false);
  const [status, setStatus] = useState("Choose an action, then check its current permissions.");
  const live = useRef(false), generation = useRef(0), owned = useRef<Owned | null>(null), reviewId = useRef<string | null>(null);
  const focus = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let release = (): void => undefined;
    try { release = main.context(); setAllocationReady(true); } catch { setAllocationReady(false); notify("The Reader context allocation is busy. Wait for current contexts to close."); }
    return () => { release(); };
  }, [main]);
  function notify(message: string): void { setStatus(message); announce(message); }
  function closeOwned(operation: Owned): void { if (owned.current === operation) owned.current = null; operation.release(); }
  useEffect(() => {
    live.current = true; setDecision(null); setConfirmed(false); reviewId.current = null; generation.current += 1;
    return () => {
      live.current = false; generation.current += 1;
      const pending = owned.current;
      if (pending) void port.cancel(pending.request.projectId, pending.request.operationId).then(drained => { if (drained) closeOwned(pending); });
    };
  }, [metadata.source.projectId, metadata.source.attachmentId, metadata.source.documentRevisionId, metadata.normalizedRevisionId, anchorId, port]);

  async function run(stage: ReaderActionRequest["stage"]): Promise<void> {
    if (owned.current || unknown || !allocationReady) return;
    const ticket = generation.current, priorFocus = document.activeElement;
    const request: ReaderActionRequest = { schemaVersion: "1.0", projectId: metadata.source.projectId,
      selector: { attachmentId: metadata.source.attachmentId, documentRevisionId: metadata.source.documentRevisionId, normalizedRevisionId: metadata.normalizedRevisionId },
      operationId: newAttachmentId(), stage, action, anchorId: stage === "rights-review" || action === "open-external-original" ? null : anchorId,
      expectedPolicyRevisionId: decision?.policyRevisionId ?? null,
      commandId: stage === "rights-review" ? reviewId.current ??= newAttachmentId() : null,
      confirmed: stage === "execute" || stage === "rights-review" && confirmed };
    let releaseCore = (): void => undefined, releaseMain = (): void => undefined;
    try { releaseMain = main.context(); releaseCore = reserveCore(); }
    catch { releaseMain(); notify("The local Reader allocation is busy. Wait for current work to finish, then retry."); return; }
    let released = false;
    const operation: Owned = { request, release: () => { if (!released) { released = true; releaseMain(); releaseCore(); } } };
    owned.current = operation; setBusy(true); setUnknown(false);
    notify(stage === "rights-review" ? "Recording only this source's permitted use. No output is sent." : stage === "execute" ? "Checking current rights and the Native destination…" : "Checking current permissions…");
    let reply;
    try { reply = decodeReaderAction(await port.request(request), request, metadata); }
    catch { reply = null; }
    const drained = reply?.drained === true || await port.cancel(request.projectId, request.operationId);
    if (drained) closeOwned(operation);
    if (!live.current) return;
    if (generation.current !== ticket) {
      setBusy(!drained); setUnknown(!drained); setDecision(null);
      notify(drained ? "The previous source action closed. Check permissions for the current selection."
        : "The previous source action is still draining; check completion before issuing another action.");
      return;
    }
    setBusy(!drained); setUnknown(!drained);
    if (!drained) { notify("The issued action has not confirmed physical closure. Check completion or restart the application before issuing another action."); return; }
    if (!reply) { setDecision(null); notify("The action could not be confirmed. Review current permissions before retrying; an ambiguous rights review reuses its command identifier."); }
    else if (reply.status === "policy" && reply.decision) {
      setDecision(reply.decision); setConfirmed(false);
      notify(reply.decision.state === "ready" ? "Source permission is current. The action still requires explicit Native destination confirmation."
        : reply.decision.canReview ? "Permission is missing or unknown. Record a permitted use only when you have authority for this exact copy and action."
        : `This action is unavailable: ${reply.decision.reasonCode.replaceAll("-", " ")}. Return to source review if needed.`);
    } else if (reply.status === "recorded") {
      setDecision(null); setConfirmed(false); reviewId.current = null;
      notify("Permitted use recorded. No action was performed. Check current permissions, then choose the action separately.");
    } else if (reply.status === "completed") {
      setDecision(null); notify("The explicit action completed. Delivered plaintext is outside the project's protection; extraction remains unverified.");
    } else if (reply.status === "partial") {
      setDecision(null); notify("The action was only partly confirmed. Output may already have reached the local destination. Check it before retrying; delivered plaintext remains outside project protection.");
    } else { setDecision(null); notify(reply.status === "cancelled" ? "Action cancelled. Check current permissions before retrying." : "The action or destination is unavailable. Review the source and permissions, then retry."); }
    requestAnimationFrame(() => { if (live.current && generation.current === ticket && document.activeElement === document.body) {
      if (priorFocus instanceof HTMLElement && priorFocus.isConnected && !priorFocus.matches(":disabled")) priorFocus.focus(); else focus.current?.focus();
    } });
  }
  async function cancel(): Promise<void> {
    const pending = owned.current; if (!pending) return;
    const drained = await port.cancel(pending.request.projectId, pending.request.operationId);
    if (drained) closeOwned(pending);
    if (!live.current) return;
    if (drained) { setBusy(false); setUnknown(false); setDecision(null); notify("Physical closure confirmed. Review current permissions before retrying."); }
    else { setUnknown(true); notify("Cancellation requested. The action still owns its resources until physical closure is confirmed."); }
  }
  const selectionRequired = action !== "open-external-original" && (!anchorId || !metadata.normalizedRevisionId);
  return <section className="ro-stack ro-wrap-anywhere" aria-label="Rights-aware Reader actions" aria-busy={busy}>
    <h2 ref={focus} tabIndex={-1}>Permitted source actions</h2>
    <label>Action <select aria-label="Reader source action" value={action} disabled={busy} onChange={event => {
      setAction(event.currentTarget.value as ReaderAction); setDecision(null); setConfirmed(false); reviewId.current = null; generation.current += 1;
    }}>{readerActions.map(value => <option key={value} value={value}>{labels[value]}</option>)}</select></label>
    <p>{action === "export-annotation" ? "The annotation includes selected anchor identifiers, position and uncertainty; it excludes quotation and surrounding text."
      : action === "open-external-original" ? "Choose a local destination and application. The retained original is delivered as plaintext outside this application's privacy controls."
      : "Only the exact saved quotation is delivered, with source, revision, anchor and permission identifiers. Surrounding text is excluded."}</p>
    {action === "print-quotation" ? <p>Local printing currently supports Microsoft Print to PDF. Choose that printer and a local folder; other printers are unavailable. The PDF uses the application's quotation layout.</p> : null}
    {selectionRequired ? <p>Select a saved anchor's quotation action control in Anchor inspection first.</p> : null}
    <p role="status" aria-live="polite">{status}</p>
    <Button disabled={busy || !allocationReady} onClick={() => void run("policy")}>Check current permissions</Button>
    {decision?.canReview ? <Notification tone="warning" title="Confirm this source's permitted use">
      <p>This records only the selected action's missing permissions for this exact retained copy. Existing denial, expiry, disputes and other restrictions cannot be overridden here. A license or access observation alone is not permission.</p>
      <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.currentTarget.checked)} /> I have authority to permit this exact source copy and selected use.</label>
      <Button disabled={busy || !allocationReady || !confirmed} onClick={() => void run("rights-review")}>Record permitted use only</Button>
    </Notification> : null}
    <Button disabled={busy || !allocationReady || selectionRequired || decision?.state !== "ready"} onClick={() => void run("execute")}>{labels[action]}</Button>
    {busy ? <Button onClick={() => void cancel()}>{unknown ? "Check completion / request cancellation" : "Cancel source action"}</Button> : null}
    <Button onClick={onReturn}>Review selected source permissions</Button>
    <p>The 2048-codepoint selection cap is a technical limit, not a license allowance. Inspection, parsing and permissions do not verify a scholarly claim.</p>
  </section>;
}
