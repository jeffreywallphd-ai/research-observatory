import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import type { AttachmentHandoff } from "./DocumentAttachmentPane";
import { decodeViewerMetadata, decodeViewerText, viewerSourcesMatch, nativeDocumentViewerPort, nativeDocumentViewerTextPort, ViewerBufferBudget, ViewerByteSession,
  type DocumentViewerPort, type DocumentViewerTextPort, type ViewerMetadata, type ViewerSelector, type ViewerTextChunk } from "./documentViewer";
import { PdfDocumentViewer } from "./pdfDocumentViewer";
import { nativeSourceAnchorPort, type SourceAnchorPort } from "./sourceAnchorsNative";
import { decodeReaderOutline, decodeReaderRevisions, type ReaderOutlineNode } from "./sourceAnchors";

export interface PdfViewer {
  open(): Promise<number>; render(canvas: HTMLCanvasElement, page: number, scale: number): Promise<void>;
  thumbnail(canvas: HTMLCanvasElement, page: number): Promise<void>; releaseCanvas(canvas: HTMLCanvasElement): void;
  find(query: string, afterPage: number): Promise<number | null>; cancelSearch(): void; cancelRender(): void; close(): void;
}
interface Props {
  readonly project: ProjectProjection | null; readonly handoff: AttachmentHandoff | null; readonly active: boolean;
  readonly announce: (message: string) => void; readonly onReturn: () => void;
  readonly port?: DocumentViewerPort; readonly anchors?: SourceAnchorPort; readonly textPort?: DocumentViewerTextPort;
  readonly pdfFactory?: (bytes: ViewerByteSession, budget: ViewerBufferBudget, failure: (code: string) => void) => PdfViewer;
}
const pdfFactory = (bytes: ViewerByteSession, budget: ViewerBufferBudget, failure: (code: string) => void): PdfViewer => new PdfDocumentViewer(bytes, budget, failure);

export function DocumentViewerWorkspace(props: Props): ReactNode {
  const { project, handoff } = props;
  if (!props.active || !project?.open) return <Notification tone="info" title="No open source">Open the project and select a permitted copy from its Work/version.</Notification>;
  if (!handoff?.attachmentId || !handoff.documentRevisionId || handoff.selection.projectId !== project.projectId) {
    return <Panel title="Document Reader"><p>No exact source selected. Open a permitted copy from the selected Work/version.</p><Button onClick={props.onReturn}>Return to selected Work/version</Button></Panel>;
  }
  return <ViewerSession key={`${project.projectId}:${handoff.attachmentId}:${handoff.documentRevisionId}`} {...props}
    project={project} handoff={handoff as AttachmentHandoff & { attachmentId: string; documentRevisionId: string }} />;
}

function ViewerSession({ project, handoff, announce, onReturn, port = nativeDocumentViewerPort, anchors = nativeSourceAnchorPort,
  textPort = nativeDocumentViewerTextPort, pdfFactory: createPdf = pdfFactory }: Props & {
    project: ProjectProjection; handoff: AttachmentHandoff & { attachmentId: string; documentRevisionId: string };
  }): ReactNode {
  const [metadata, setMetadata] = useState<ViewerMetadata | null>(null), [pdf, setPdf] = useState<PdfViewer | null>(null);
  const [page, setPage] = useState(1), [pages, setPages] = useState(0), [scale, setScale] = useState(1);
  const [status, setStatus] = useState("Checking current copy and inspection permission…"), [busy, setBusy] = useState(true);
  const [failure, setFailure] = useState<string | null>(null), [retry, setRetry] = useState(0), [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false), [revisions, setRevisions] = useState<readonly string[]>([]);
  const [revision, setRevision] = useState(""), [nodes, setNodes] = useState<readonly ReaderOutlineNode[]>([]);
  const [nextNode, setNextNode] = useState<string | null>(null), [text, setText] = useState<ViewerTextChunk | null>(null);
  const [textBusy, setTextBusy] = useState(false), [textStatus, setTextStatus] = useState("Choose an accepted revision to inspect structured text.");
  const canvas = useRef<HTMLCanvasElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const thumbnails = useRef(new Map<number, HTMLCanvasElement>()), generation = useRef(0), textGeneration = useRef(0), searchGeneration = useRef(0), live = useRef(true);
  const ownedPdf = useRef<PdfViewer | null>(null);
  const selector: ViewerSelector = { attachmentId: handoff.attachmentId, documentRevisionId: handoff.documentRevisionId, normalizedRevisionId: null };
  function restoreFocus(target: Element | null, current: () => boolean): void {
    requestAnimationFrame(() => {
      if (!live.current || !current() || document.activeElement !== document.body) return;
      if (target instanceof HTMLElement && target.isConnected && !target.matches(":disabled")) target.focus();
      else heading.current?.focus();
    });
  }
  function notify(message: string): void { setStatus(message); announce(message); }
  function fail(code: string): void {
    if (!live.current) return;
    setFailure(code); setBusy(false); setText(null); setNodes([]); setQuery(""); ownedPdf.current?.close();
    notify(code === "viewer-resource-limit" ? "This source exceeds the local viewer limit. Its original and metadata remain retained; return to source review."
      : "Source access could not be confirmed. Return to the selected version, review its availability and permissions, then retry.");
  }
  useEffect(() => {
    live.current = true; const ticket = ++generation.current;
    const current = (): boolean => live.current && generation.current === ticket;
    let bytes: ViewerByteSession | null = null, viewer: PdfViewer | null = null;
    setMetadata(null); setPdf(null); setPages(0); setPage(1); setRevision(""); setRevisions([]); setText(null); setFailure(null); setBusy(true);
    setNodes([]); setNextNode(null); setQuery(""); setSearching(false); setTextBusy(false);
    setStatus("Checking current copy and inspection permission…"); setTextStatus("Choose an accepted revision to inspect structured text.");
    heading.current?.focus();
    void (async () => {
      const value = decodeViewerMetadata(await port.source(project.projectId, selector), project.projectId, selector);
      if (!current()) return;
      if (!value || Object.entries(handoff.selection).some(([key, expected]) => value.source[key as keyof typeof value.source] !== expected)) { fail("viewer-source-unavailable"); return; }
      setMetadata(value);
      // The original is readable without an accepted parse or derive permission.
      // Accepted revision lookup may deny separately and must not replace it.
      void anchors.revisions(project.projectId, handoff.attachmentId).then((result) => {
        const accepted = decodeReaderRevisions(result, project.projectId, handoff.attachmentId);
        if (current() && accepted && viewerSourcesMatch(accepted.source, value.source)) setRevisions(accepted.revisions.map((item) => item.revisionId));
      }).catch(() => undefined);
      if (value.source.format === "pdf") {
        const budget = new ViewerBufferBudget(); bytes = new ViewerByteSession(project.projectId, selector, value, port, budget);
        viewer = createPdf(bytes, budget, (code) => { if (current()) fail(code); }); ownedPdf.current = viewer;
        const count = await viewer.open();
        if (!current()) { viewer.close(); return; }
        setPages(count); setPdf(viewer); notify("Original loaded. Rendering the first permitted page…");
      } else { setBusy(false); notify("Select an accepted revision for inert structured text. Active HTML, attachments and external document actions are unavailable."); }
    })().catch(() => { if (current()) fail("viewer-source-unavailable"); });
    return () => { live.current = false; generation.current += 1; textGeneration.current += 1; searchGeneration.current += 1; bytes?.close(); viewer?.close(); ownedPdf.current = null; };
  }, [project.projectId, handoff.attachmentId, handoff.documentRevisionId, port, anchors, createPdf, retry]);

  useEffect(() => {
    if (!pdf || !canvas.current || failure) return;
    let active = true; const priorFocus = document.activeElement; setBusy(true); setSearching(false);
    const element = canvas.current;
    void pdf.render(element, page, scale).then(async () => {
      if (!active || !live.current) return;
      setBusy(false); notify(`Page ${page} of ${pages} displayed.`);
      restoreFocus(priorFocus, () => active);
      // Only the bounded previous/current/next thumbnail window is rendered.
      for (const [number, thumbnail] of thumbnails.current) {
        if (!active || !live.current) return;
        await pdf.thumbnail(thumbnail, number);
      }
    }).catch(() => { if (active && live.current) fail("viewer-source-unavailable"); });
    return () => { active = false; searchGeneration.current += 1; pdf.cancelSearch(); pdf.cancelRender(); };
  }, [pdf, page, scale, failure]);

  async function outline(selectedRevision: string, after: string | null = null): Promise<void> {
    const ticket = ++textGeneration.current, priorFocus = document.activeElement;
    setText(null); setTextBusy(true);
    const value = decodeReaderOutline(await anchors.outline(project.projectId, selectedRevision, after).catch(() => null), project.projectId, selectedRevision);
    if (!live.current || ticket !== textGeneration.current) return;
    setTextBusy(false);
    restoreFocus(priorFocus, () => ticket === textGeneration.current);
    if (!value || !metadata || !viewerSourcesMatch(value.source, metadata.source)) {
      setNodes([]); setNextNode(null); setTextStatus("Structured text is unavailable or no longer permitted. The original remains separately governed."); return;
    }
    setNodes(value.nodes); setNextNode(value.nextNodeId); setTextStatus("Select a structural element to inspect its bounded text and exact source revision.");
  }
  async function passage(node: ReaderOutlineNode, offset = 0): Promise<void> {
    const ticket = ++textGeneration.current, priorFocus = document.activeElement; setText(null); setTextBusy(true);
    const selection = { ...selector, normalizedRevisionId: revision };
    const value = decodeViewerText(await textPort.text(project.projectId, selection, node.nodeId, offset).catch(() => null), project.projectId, selection, node.nodeId, offset);
    if (!live.current || ticket !== textGeneration.current) return;
    setTextBusy(false);
    restoreFocus(priorFocus, () => ticket === textGeneration.current);
    if (!value || !metadata || !viewerSourcesMatch(value.metadata.source, metadata.source)) { setTextStatus("This exact text element could not be confirmed. No substitute passage was displayed."); return; }
    setText(value); setTextStatus("Accepted structured text displayed. Extraction remains unverified.");
    if (value.pageNumber && pages >= value.pageNumber) setPage(value.pageNumber);
  }
  async function search(): Promise<void> {
    if (!pdf || !query || searching) return;
    setSearching(true); const ticket = generation.current, searchTicket = ++searchGeneration.current;
    try {
      const found = await pdf.find(query, page);
      if (!live.current || ticket !== generation.current || searchTicket !== searchGeneration.current) return;
      if (found) { setPage(found); notify(`Search found matching text on page ${found}. Inspect the original page for context.`); }
      else notify("No matching text was found in this PDF's readable page text. Image-only text may be unavailable.");
    } catch { if (live.current && ticket === generation.current && searchTicket === searchGeneration.current) fail("viewer-resource-limit"); }
    finally { if (live.current && ticket === generation.current && searchTicket === searchGeneration.current) setSearching(false); }
  }
  const visiblePages = [page - 1, page, page + 1].filter((number) => number >= 1 && number <= pages);
  function blocked(event: { preventDefault(): void }): void { event.preventDefault(); announce("Copy, print, external open and export are unavailable until their current rights are checked."); }
  return <section className="ro-page-region ro-stack protected-document-viewer" aria-label="Document Reader"
    onCopy={blocked} onCut={blocked} onContextMenu={blocked} onDragStart={blocked}
    onKeyDown={(event) => {
      if ((event.ctrlKey || event.metaKey) && ["p", "s"].includes(event.key.toLowerCase())) blocked(event);
      if (event.key === "Escape") { event.preventDefault(); pdf?.close(); onReturn(); }
    }}>
    <header className="page-header"><h1 className="ro-typography ro-typography--page-title" ref={heading} tabIndex={-1}>Document Reader</h1>
      <p className="page-subtitle">Inspect an exact permitted copy beside accepted structured text and its provenance.</p></header>
    <div className="ro-action-row" id="reader-source-context"><Button onClick={() => { pdf?.close(); onReturn(); }}>Return to selected Work/version</Button>
      <Button disabled={busy || searching || page <= 1 || Boolean(failure)} onClick={() => setPage((value) => value - 1)}>Previous page</Button>
      <Button disabled={busy || searching || page >= pages || Boolean(failure)} onClick={() => setPage((value) => value + 1)}>Next page</Button>
      <label>Page <select aria-label="Source page" disabled={busy || searching || !pages || Boolean(failure)} value={page} onChange={(event) => setPage(Number(event.currentTarget.value))}>
        {Array.from({ length: pages || 1 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}</select> of {pages || "not reported"}</label>
      <label>Zoom <select aria-label="Source zoom" disabled={busy || searching || !pdf || Boolean(failure)} value={scale} onChange={(event) => setScale(Number(event.currentTarget.value))}>
        {[0.75, 1, 1.25, 1.5, 2].map((value) => <option key={value} value={value}>{value * 100}%</option>)}</select></label>
      <Button disabled={busy} onClick={() => setRetry((value) => value + 1)}>Retry current source status</Button></div>
    <p role="status" aria-live="polite">{status}</p>
    {failure ? <Notification tone="warning" title="Source view unavailable">{status}</Notification> : null}
    <form className="ro-action-row" onSubmit={(event) => { event.preventDefault(); void search(); }}><label htmlFor="viewer-find">Find in PDF page text</label>
      <input id="viewer-find" maxLength={200} value={query} disabled={!pdf || Boolean(failure) || searching} onChange={(event) => setQuery(event.currentTarget.value)} />
      <Button type="submit" disabled={!query || !pdf || busy || searching || Boolean(failure)}>Find next</Button>
      {searching ? <Button onClick={() => {
        searchGeneration.current += 1; pdf?.cancelSearch(); setSearching(false); setBusy(true);
        notify("Search cancelled. Restoring the current permitted page…");
        const ticket = generation.current, searchTicket = searchGeneration.current;
        if (pdf && canvas.current) void pdf.render(canvas.current, page, scale).then(() => {
          if (live.current && ticket === generation.current && searchTicket === searchGeneration.current) {
            setBusy(false); notify("Search cancelled.");
          }
        }).catch(() => { if (live.current && ticket === generation.current) fail("viewer-source-unavailable"); });
      }}>Cancel search</Button> : null}</form>
    <div className="source-anchor-layout viewer-layout">
      <aside className="document-outline"><Panel title="Document outline"><div className="viewer-thumbnails">{visiblePages.map((number) => <Button key={number} aria-pressed={page === number}
        disabled={busy || searching || Boolean(failure)} onClick={() => setPage(number)}><canvas aria-hidden="true" ref={(element) => {
          const prior = thumbnails.current.get(number); if (prior && prior !== element) pdf?.releaseCanvas(prior);
          if (element) thumbnails.current.set(number, element); else thumbnails.current.delete(number);
        }} /><span>Page {number}</span></Button>)}</div>
        <label>Accepted structured revision <select value={revision} disabled={textBusy || Boolean(failure)} onChange={(event) => {
          const value = event.currentTarget.value; setRevision(value); setNodes([]); setText(null); setNextNode(null); if (value) void outline(value);
        }}><option value="">Choose accepted revision</option>{revisions.map((id, index) => <option key={id} value={id}>Accepted revision {index + 1} · {id}</option>)}</select></label>
        {revisions.length === 0 ? <p>No permitted accepted structured revision is available. Viewing the original does not require one.</p> : null}
        <ul className="source-anchor-list">{nodes.map((node) => <li key={node.nodeId}><Button disabled={textBusy || Boolean(failure)} onClick={() => void passage(node)}>{node.nodeKind.replaceAll("-", " ")} · {node.preview || "No readable text"}{node.pageNumber ? ` · page ${node.pageNumber}` : ""}</Button></li>)}</ul>
        {nextNode ? <Button disabled={textBusy} onClick={() => void outline(revision, nextNode)}>More source elements</Button> : null}
      </Panel></aside>
      <article className="ro-card viewer-paper" aria-label="Original source page" aria-busy={busy}><h2>Original source</h2>
        {pdf && !failure ? <canvas ref={canvas} role="img" aria-label={`Original PDF page ${page} of ${pages}. Use structured text for readable extraction.`} /> : <p>{busy ? "Opening protected source…" : "An original page rendering is unavailable for this format. Choose a permitted accepted revision for structured text."}</p>}
        <section aria-label="Accepted structured text" aria-busy={textBusy}><h2>Accepted structured text</h2><p role="status">{textStatus}</p>
          {text ? <><p className="anchor-passage-text">{text.text || "This structural element has no readable text."}</p><StatusBadge tone="info">Unverified extraction</StatusBadge>
            {text.nextOffset !== null ? <Button disabled={textBusy} onClick={() => { const node = nodes.find((item) => item.nodeId === text.nodeId); if (node) void passage(node, text.nextOffset!); }}>Next text chunk</Button> : null}</> : null}
        </section>
      </article>
      <aside className="document-inspector"><Panel title="Source provenance"><dl className="ro-wrap-anywhere"><dt>Work</dt><dd>{handoff.selection.workId}</dd><dt>Version revision</dt><dd>{handoff.selection.versionRevisionId}</dd>
        <dt>Original revision</dt><dd>{handoff.documentRevisionId}</dd><dt>Accepted structured revision</dt><dd>{revision || "Not selected"}</dd>
        <dt>Source</dt><dd>{metadata ? `${metadata.source.format.toUpperCase()} · ${metadata.source.byteLength.toLocaleString()} bytes · ${metadata.source.provenance.kind.replaceAll("-", " ")}` : "Current source not confirmed"}</dd>
        <dt>Source hash</dt><dd>{metadata?.source.objectSha256 || "Not confirmed"}</dd><dt>Selected text element</dt><dd>{text?.nodeId || "Not selected"}</dd></dl>
        <p>Inspection is checked for every source request. Structured text also requires current derivation permission. No scholarly claim is verified by viewing a page.</p>
        <p>PDF scripts, forms, attachments and external links are inactive. Copy, print, external open and export are currently unavailable.</p>
      </Panel></aside>
    </div>
  </section>;
}
