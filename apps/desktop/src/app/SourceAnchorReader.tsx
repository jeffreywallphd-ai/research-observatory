import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import { newAttachmentId as newCommandId } from "./documentAttachment";
import { codepointRangeToUtf16, decodeReaderOutline, decodeSourceAnchor, type AnchorSelection, type ReaderOutlineNode, type SourceAnchor, type SourceIdentity } from "./sourceAnchors";
import { nativeSourceAnchorPort, type SourceAnchorPort } from "./sourceAnchorsNative";

function sameSource(a: SourceIdentity, b: SourceIdentity): boolean {
  return (["projectId", "attachmentId", "documentId", "documentRevisionId", "candidateId", "sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId", "objectSha256", "byteLength", "format"] as const)
    .every((key) => a[key] === b[key]) && a.provenance.kind === b.provenance.kind
    && (a.provenance.kind === "local-import" || b.provenance.kind === "remote-acquisition"
      && a.provenance.locationId === b.provenance.locationId && a.provenance.receiptSha256 === b.provenance.receiptSha256);
}

export function AnchorPassage({ anchor, scale }: { readonly anchor: SourceAnchor; readonly scale: number }): ReactNode {
  const value = decodeSourceAnchor(anchor, anchor.target.projectId, anchor.target.revisionId);
  if (!value || ![100, 125, 150, 200].includes(scale)) return <Notification tone="warning" title="Passage unavailable">The stored selectors do not agree. Return to source review.</Notification>;
  const target = value.target;
  const context = target.context;
  const range = context ? codepointRangeToUtf16(context.text, context.highlight) : null;
  return <section className="ro-stack ro-wrap-anywhere" aria-label="Exact source passage">
    <h3>Accepted structured text</h3>
    <p>{target.pageRegion ? `Page ${target.pageRegion.pageNumber} · block region available; this view shows structured text.`
      : `Structural/text fallback · coordinates ${target.coordinatesState.replaceAll("-", " ")}.`}</p>
    {context && range ? <p className="anchor-passage-text" style={{ fontSize: `${scale}%` }}>{context.text.slice(0, range.start)}<mark aria-label="Selected source passage">{context.text.slice(range.start, range.end)}</mark>{context.text.slice(range.end)}</p>
      : <Notification tone="info" title="Structural anchor">This element has no text span. Its exact structural identity is retained; inspect its source when page viewing is available.</Notification>}
    <p>Revision {target.revisionId} · element {target.nodeId}</p>
    <StatusBadge tone="info">Unverified extraction</StatusBadge>
    <p>{target.confidence.state === "reported" ? `Parser confidence ${target.confidence.value}` : `Confidence ${target.confidence.state.replaceAll("-", " ")}`}. Parser confidence does not verify a scholarly claim.</p>
  </section>;
}

interface Props {
  readonly source: SourceIdentity;
  readonly revisionId: string;
  readonly active: boolean;
  readonly announce: (message: string) => void;
  readonly onReturn: () => void;
  readonly port?: SourceAnchorPort;
}

// CAP-05.S04 owns activation of the protected reader route and source-byte viewer.
// Unmounting this bounded inspection component releases all retained research text.
export function SourceAnchorReader(props: Props): ReactNode {
  if (!props.active) return <Notification tone="info" title="Project locked">Unlock the project to inspect its source passages.</Notification>;
  const source = props.source;
  const key = [source.projectId, source.attachmentId, source.documentRevisionId, source.sourceAssertionRevisionId,
    source.documentId, source.candidateId, source.workId, source.workRevisionId, source.versionId,
    source.versionRevisionId, source.objectSha256, props.revisionId].join(":");
  return <ReaderSession key={key} {...props} />;
}

function ReaderSession({ source, revisionId, announce, onReturn, port = nativeSourceAnchorPort }: Props): ReactNode {
  const [nodes, setNodes] = useState<readonly ReaderOutlineNode[]>([]);
  const [nextNode, setNextNode] = useState<string | null>(null);
  const [anchors, setAnchors] = useState<readonly string[]>([]);
  const [moreAnchors, setMoreAnchors] = useState(false);
  const [anchor, setAnchor] = useState<SourceAnchor | null>(null);
  const [selection, setSelection] = useState<AnchorSelection | null>(null);
  const [busy, setBusy] = useState(true);
  const [status, setStatus] = useState("Loading permitted source anchors…");
  const [scale, setScale] = useState(100);
  const [refresh, setRefresh] = useState(0);
  const live = useRef(true), generation = useRef(0);
  const passageHeading = useRef<HTMLHeadingElement>(null);
  const pending = useRef<{ commandId: string; selection: AnchorSelection } | null>(null);

  function notify(message: string): void { setStatus(message); announce(message); }
  function current(ticket: number): boolean { return live.current && generation.current === ticket; }
  function checked(value: SourceAnchor | null): SourceAnchor | null {
    const result = decodeSourceAnchor(value, source.projectId, revisionId);
    return result && sameSource(result.target.source, source) ? result : null;
  }

  useEffect(() => {
    live.current = true;
    const ticket = ++generation.current;
    setAnchor(null); setSelection(null); setNodes([]); setAnchors([]); setNextNode(null); setMoreAnchors(false); setBusy(true);
    void Promise.all([port.outline(source.projectId, revisionId), port.list(source.projectId, revisionId)]).then(([outline, ids]) => {
      if (!current(ticket)) return;
      const value = decodeReaderOutline(outline, source.projectId, revisionId);
      if (!value || !sameSource(value.source, source) || ids === null) {
        notify("Source access is unavailable or no longer permitted. Return to the selected version or retry current status.");
      } else {
        setNodes(value.nodes); setNextNode(value.nextNodeId); setAnchors(ids); setMoreAnchors(ids.length === 100);
        notify(ids.length ? "Select a saved anchor to inspect its exact passage." : "No saved anchors for this revision. Select a text element and save its exact passage anchor.");
      }
      setBusy(false);
    }).catch(() => { if (current(ticket)) { setBusy(false); notify("Source access could not be confirmed. Return to source review or retry current status."); } });
    return () => { live.current = false; generation.current += 1; };
  }, [port, source.projectId, revisionId, refresh]);

  useEffect(() => {
    if (anchor) passageHeading.current?.focus();
  }, [anchor]);

  async function open(id: string): Promise<void> {
    if (busy || pending.current) return;
    const ticket = ++generation.current;
    setAnchor(null); setSelection(null); setBusy(true);
    const value = checked(await port.read(source.projectId, revisionId, id).catch(() => null));
    if (!current(ticket)) return;
    setBusy(false);
    if (!value || value.anchorId !== id) { notify("This anchor is unavailable or no longer permitted. No different passage was substituted."); return; }
    setAnchor(value); notify("Exact accepted-revision passage selected.");
  }

  async function save(): Promise<void> {
    if (busy || !selection) return;
    pending.current ??= { commandId: newCommandId(), selection };
    const command = pending.current, ticket = ++generation.current;
    setAnchor(null); setBusy(true);
    const value = checked(await port.create(source.projectId, command.commandId, command.selection).catch(() => null));
    if (!current(ticket)) return;
    setBusy(false);
    if (!value) { notify("Anchor creation was not confirmed. Retry this same selection and command; return and reopen saved anchors to check durable status."); return; }
    pending.current = null; setSelection(null); setAnchor(value);
    setAnchors((old) => old.includes(value.anchorId) || old.length === 100 ? old : [...old, value.anchorId]);
    if (anchors.length === 100) setMoreAnchors(true);
    notify("Source anchor saved. Its exact revision and passage will remain available after restart while current rights permit access.");
  }

  async function more(kind: "nodes" | "anchors"): Promise<void> {
    if (busy || pending.current) return;
    const ticket = ++generation.current;
    setBusy(true);
    if (kind === "nodes") {
      const value = decodeReaderOutline(await port.outline(source.projectId, revisionId, nextNode).catch(() => null), source.projectId, revisionId);
      if (!current(ticket)) return;
      if (value && sameSource(value.source, source)) { setNodes(value.nodes); setNextNode(value.nextNodeId); }
      else { setAnchor(null); notify("More source elements could not be confirmed. Retry current source status."); }
    } else {
      const ids = await port.list(source.projectId, revisionId, anchors.at(-1) ?? null).catch(() => null);
      if (!current(ticket)) return;
      if (ids) { setAnchors(ids); setMoreAnchors(ids.length === 100); }
      else { setAnchor(null); notify("More saved anchors could not be confirmed. Retry current source status."); }
    }
    setBusy(false);
  }

  const blockedTransfer = (event: { preventDefault(): void }): void => {
    event.preventDefault(); notify("Copy, print and export are unavailable in this text inspection view.");
  };
  return <section className="ro-stack source-anchor-reader" aria-label="Document Reader" aria-busy={busy}
    onCopy={blockedTransfer} onCut={blockedTransfer} onContextMenu={blockedTransfer}
    onKeyDown={(event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") blockedTransfer(event);
      if (event.key === "Escape") { event.preventDefault(); onReturn(); }
    }}>
    <div className="ro-action-row" id="reader-source-context"><Button onClick={onReturn}>Return to selected Work/version</Button>
      <label>Text size <select value={scale} onChange={(event) => setScale(Number(event.currentTarget.value))}>{[100, 125, 150, 200].map((value) => <option key={value} value={value}>{value}%</option>)}</select></label>
      <Button disabled={busy || Boolean(pending.current)} onClick={() => setRefresh((value) => value + 1)}>Retry current source status</Button></div>
    <p role="status" aria-live="polite">{status}</p>
    <div className="source-anchor-layout">
      <aside className="document-outline"><Panel title="Document outline"><ul className="source-anchor-list">{nodes.map((node) => <li key={node.nodeId}>
        <Button disabled={busy || Boolean(pending.current) || !node.hasText} onClick={() => { setAnchor(null); setSelection(node.selection); notify("Text element selected. Save its exact passage anchor to inspect it."); }}>
          {node.nodeKind.replaceAll("-", " ")} · {node.preview || "No text span"}{node.pageNumber ? ` · page ${node.pageNumber}` : ""}</Button></li>)}</ul>
        {nextNode ? <Button disabled={busy || Boolean(pending.current)} onClick={() => void more("nodes")}>More source elements</Button> : null}
        <h3>Saved anchors</h3><ul className="source-anchor-list">{anchors.map((id, index) => <li key={id}><Button disabled={busy || Boolean(pending.current)} onClick={() => void open(id)}>Open saved anchor {index + 1}</Button></li>)}</ul>
        {moreAnchors ? <Button disabled={busy || Boolean(pending.current)} onClick={() => void more("anchors")}>More saved anchors</Button> : null}
      </Panel></aside>
      <article className="ro-card anchor-paper" aria-label="Accepted structured-text passage"><h2 ref={passageHeading} tabIndex={-1}>Source passage</h2>
        {anchor ? <AnchorPassage anchor={anchor} scale={scale} /> : <p>Select an exact saved anchor or a text element. No source passage is selected.</p>}
        {selection ? <Button tone="primary" disabled={busy} onClick={() => void save()}>{pending.current ? "Retry same anchor command" : "Save and inspect passage anchor"}</Button> : null}</article>
      <aside className="document-inspector"><Panel title="Selected passage"><p className="ro-wrap-anywhere">Revision {revisionId}</p>
        {anchor ? <dl className="ro-wrap-anywhere"><dt>Anchor</dt><dd>{anchor.anchorId}</dd><dt>Structural element</dt><dd>{anchor.target.nodeId}</dd>
          <dt>Source</dt><dd>{source.format.toUpperCase()} · exact permitted copy</dd></dl> : <p>No source passage selected.</p>}
        <p>Copy, print and export are unavailable in this text inspection view.</p><p>Saving an anchor does not verify or accept an evidence claim.</p>
      </Panel></aside>
    </div>
  </section>;
}
