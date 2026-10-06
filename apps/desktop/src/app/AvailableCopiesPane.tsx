import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Notification } from "@research-observatory/ui-components";
import { newAttachmentId, type AttachmentSelection, type AttachmentBeginOutcome } from "./documentAttachment";
import { nativeDocumentAcquisitionPort, type AccessNeedChannel, type AccessNeedKind, type AvailableCopy, type CopyReview, type DocumentAcquisitionPort, type RetainedCandidate } from "./documentAcquisition";

export function AvailableCopiesPane({ selection, disabled, downloadAllowed, announce, beginRemote, initialCopyId, onCopySelect, port = nativeDocumentAcquisitionPort }: {
  readonly selection: AttachmentSelection;
  readonly disabled: boolean;
  readonly downloadAllowed: boolean;
  readonly announce: (message: string) => void;
  readonly beginRemote: (operationId: string, action: () => Promise<AttachmentBeginOutcome>) => Promise<void>;
  readonly initialCopyId?: string | null | undefined;
  readonly onCopySelect: (copyId: string | null) => void;
  readonly port?: DocumentAcquisitionPort;
}): ReactNode {
  const [copies, setCopies] = useState<readonly AvailableCopy[] | null>(null);
  const [retained, setRetained] = useState<readonly RetainedCandidate[]>([]);
  const [inventoryBinding, setInventoryBinding] = useState("");
  const [review, setReview] = useState<CopyReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [use, setUse] = useState(false);
  const [message, setMessage] = useState("Checking retained copy metadata locally…");
  const [kind, setKind] = useState<AccessNeedKind>("unknown");
  const [channel, setChannel] = useState<AccessNeedChannel>("manual");
  const ticket = useRef(0), live = useRef(true), heading = useRef<HTMLHeadingElement>(null), trigger = useRef<HTMLButtonElement | null>(null);
  const binding = JSON.stringify(selection);
  useEffect(() => {
    live.current = true;
    const generation = ++ticket.current;
    setCopies(null); setRetained([]); setReview(null); setConfirmed(false); setUse(false); setBusy(false);
    setMessage("Checking retained copy metadata locally…");
    void port.copies(selection).then((result) => {
      if (!live.current || ticket.current !== generation) return;
      setCopies(result?.copies ?? null); setRetained(result?.retained ?? []);
      setInventoryBinding(binding);
      setMessage(result === null ? "Copy review is unavailable. Metadata remains available; choose a lawful local file or record a local access need."
        : result.copies.length ? "Copy observations are retained separately. Current policy must be reviewed before any download."
          : "No retained full-text location is known. The metadata record remains useful; availability is not verified.");
    });
    return () => { live.current = false; ticket.current += 1; void port.clearReview(); };
  }, [port, binding]);
  function closeReview(): void {
    ticket.current += 1; setReview(null); setConfirmed(false); setUse(false); setBusy(false);
    void port.clearReview(); trigger.current?.focus();
  }
  async function open(copy: AvailableCopy, button: HTMLButtonElement): Promise<void> {
    if (busy || disabled || !downloadAllowed) return;
    const generation = ++ticket.current;
    trigger.current = button; setReview(null); setConfirmed(false); setUse(false); setBusy(true);
    onCopySelect(copy.copyId);
    const result = await port.review(selection, copy);
    if (!live.current || ticket.current !== generation) return;
    setBusy(false); setReview(result);
    const message = result ? "Exact copy reviewed locally. Confirm association and permitted use before Download."
      : "This copy cannot currently be downloaded. Check current rights, Intent, privacy and native session; no content was fetched.";
    setMessage(message); announce(message);
    if (result) queueMicrotask(() => heading.current?.focus());
  }
  async function confirmedDownload(): Promise<void> {
    if (!review || !confirmed || !use || busy || disabled || !downloadAllowed) return;
    const selected = review, operation = newAttachmentId(), generation = ++ticket.current;
    setBusy(true); setReview(null); setConfirmed(false); setUse(false);
    setMessage("Downloading the confirmed copy into encrypted local staging. A candidate still requires explicit Attach.");
    await beginRemote(operation, () => port.download(selection, selected, operation));
    if (live.current && ticket.current === generation) setBusy(false);
  }
  async function annotate(): Promise<void> {
    if (busy || disabled) return;
    const generation = ++ticket.current;
    setBusy(true);
    const ok = await port.annotate(selection, review?.copy ?? null, newAttachmentId(), kind, channel);
    if (!live.current || ticket.current !== generation) return;
    setBusy(false);
    const message = ok ? "Local access need recorded. No message was sent, no content was fetched, and no availability or permission was granted."
      : "The local access need could not be recorded. Metadata remains available.";
    setMessage(message); announce(message);
  }
  async function recover(candidate: RetainedCandidate): Promise<void> {
    if (busy || disabled) return;
    const generation = ++ticket.current, operation = newAttachmentId();
    setReview(null); setConfirmed(false); setUse(false); setBusy(true);
    onCopySelect(candidate.copyId);
    void port.clearReview();
    setMessage("Reviewing current authority for the retained inspected candidate. No download is being repeated; explicit Attach remains required.");
    await beginRemote(operation, () => port.recover(selection, candidate, operation));
    if (live.current && ticket.current === generation) setBusy(false);
  }
  return <section className="ro-stack" aria-label="Available copies" aria-busy={busy}>
    <h4>Available copies</h4>
    <p>Source metadata and an open-access label do not grant permission. Each source, observed version and license stays distinct.</p>
    {initialCopyId ? <p className="ro-wrap-anywhere">Returned selected copy: {initialCopyId}. Its earlier confirmation has been cleared; review current authority again.</p> : null}
    {(inventoryBinding === binding ? copies : null)?.map((copy) => <section key={copy.copyId} className="ro-stack ro-wrap-anywhere" aria-label={`Retained copy from ${copy.host}`}>
      <dl className="import-rights"><div><dt>Provider and host</dt><dd>{copy.provider || "Unknown"} · {copy.host}</dd></div>
        <div><dt>Observed version</dt><dd>{copy.version ?? "Unknown"}</dd></div><div><dt>License</dt><dd>{copy.license ?? "Unknown"}</dd></div>
        <div><dt>Type, size and checksum</dt><dd>Unknown until inspection</dd></div><div><dt>Current access policy</dt><dd>Unknown until current review</dd></div></dl>
      <p>OA/access state: Unknown. This observation grants no permission.</p>
      <Button disabled={disabled || busy || !downloadAllowed} onClick={(event) => void open(copy, event.currentTarget)}>Review this copy · {copy.host}</Button>
    </section>)}
    {inventoryBinding === binding && retained.length ? <section className="ro-stack" aria-label="Retained inspected candidates"><h4>Retained inspected candidates</h4>
      <p>These pending copies are not canonical attachments or readable documents. Review current authority without downloading again, then explicitly confirm Attach.</p>
      {retained.map((item) => {
        const origin = copies?.find((copy) => copy.copyId === item.copyId);
        return <section key={item.candidateId} className="ro-stack ro-wrap-anywhere" aria-label={`Retained inspected candidate ${item.candidateId}`}>
          <p>{item.sourceName} · candidate {item.candidateId}</p>
          <dl className="import-rights"><div><dt>Origin copy</dt><dd>{item.copyId ?? "Local file"}</dd></div>
            <div><dt>Provider and host</dt><dd>{origin ? `${origin.provider || "Unknown"} · ${origin.host}` : "Unknown"}</dd></div>
            <div><dt>Observed version</dt><dd>{origin?.version ?? "Unknown"}</dd></div>
            <div><dt>License</dt><dd>{origin?.license ?? "Unknown"}</dd></div></dl>
          <Button disabled={disabled || busy} onClick={() => void recover(item)}>Review retained candidate · {item.sourceName} · {item.candidateId}</Button>
        </section>;
      })}
    </section> : null}
    {review ? <section className="ro-stack" aria-label="Review selected remote copy" onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeReview(); }
    }}><h4 ref={heading} tabIndex={-1}>Review this exact copy</h4>
      <p>{review.copy.provider || "Unknown provider"} · {review.copy.host} · version {review.copy.version ?? "Unknown"} · license {review.copy.license ?? "Unknown"}.</p>
      <p>Store and inspect: allowed by current policy. Initial host: {review.copy.host}. Allowed redirect hosts: none. Review has fetched no content.</p>
      <p>Download contacts this host and stores the inspected copy encrypted locally. It grants no export, redistribution or model use and makes no canonical attachment.</p>
      <label className="ro-cluster"><input type="checkbox" checked={confirmed} disabled={disabled || busy} onChange={(event) => setConfirmed(event.currentTarget.checked)} />I confirm this copy matches the selected Work and version.</label>
      <label className="ro-cluster"><input type="checkbox" checked={use} disabled={disabled || busy} onChange={(event) => setUse(event.currentTarget.checked)} />I may store and inspect this copy in this project.</label>
      <div className="ro-action-row"><Button tone="primary" disabled={disabled || busy || !downloadAllowed || !confirmed || !use} onClick={() => void confirmedDownload()}>Download this copy</Button>
        <Button disabled={busy} onClick={closeReview}>Cancel copy review</Button></div>
    </section> : null}
    <Notification tone="info" title="Local access need"><p>Unknown, unavailable, denied and entitlement-required are distinct local notes. A manual or institutional placeholder sends nothing and grants no permission. You may later supply a lawful local file.</p>
      <div className="ro-field"><label htmlFor="copy-access-kind">Access state</label><select id="copy-access-kind" value={kind} disabled={busy || disabled} onChange={(event) => setKind(event.currentTarget.value as AccessNeedKind)}>
        <option value="unknown">Unknown</option><option value="unavailable">Unavailable</option><option value="rights-denied">Rights denied</option><option value="entitlement-required">Entitlement required</option></select></div>
      <div className="ro-field"><label htmlFor="copy-access-channel">Local request placeholder</label><select id="copy-access-channel" value={channel} disabled={busy || disabled} onChange={(event) => setChannel(event.currentTarget.value as AccessNeedChannel)}>
        <option value="manual">Manual</option><option value="institutional">Institutional</option></select></div>
      <Button disabled={busy || disabled} onClick={() => void annotate()}>Record local access need</Button>
    </Notification>
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}
