import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Panel, StatusBadge } from "@research-observatory/ui-components";
import { decodeTableFigureNotice, decodeTableFigurePage, type DocumentTableFigurePort, type StructureJump, type TableFigurePage, type TableFigurePreview } from "./documentTableFigures";
import { newAttachmentId } from "./documentAttachment";
import { viewerSourcesMatch, type ViewerMainAdmission, type ViewerMetadata } from "./documentViewer";

interface Props { readonly metadata: ViewerMetadata; readonly revisionId: string; readonly port: DocumentTableFigurePort;
  readonly main: ViewerMainAdmission; readonly reserveCore: () => () => void; readonly onSource: (jump: StructureJump) => void;
  readonly onPreview: (entry: TableFigurePreview) => void; readonly onFailure: (code: string) => void }
export function ViewerTableFiguresPane(props: Props): ReactNode {
  const [page, setPage] = useState<TableFigurePage | null>(null), [busy, setBusy] = useState(false), [checked, setChecked] = useState(false);
  const [rationale, setRationale] = useState(""), [status, setStatus] = useState("Inspect tables and figures in this exact accepted revision.");
  const live = useRef(false), generation = useRef(0), pending = useRef(false), retained = useRef<(() => void) | null>(null);
  const knownHead = useRef<string | null>(null), command = useRef<{ id: string; key: string } | null>(null), heading = useRef<HTMLHeadingElement>(null);
  function clear(): void { retained.current?.(); retained.current = null; setPage(null); }
  useEffect(() => {
    live.current = true; generation.current += 1; clear(); setBusy(false); setChecked(false); setRationale(""); knownHead.current = null; command.current = null;
    setStatus("Inspect tables and figures in this exact accepted revision.");
    return () => { live.current = false; generation.current += 1; retained.current?.(); retained.current = null; };
  }, [props.revisionId, props.metadata, props.port, props.main]);

  async function load(mode: "read" | "enrich" | "exclude", afterOrder: number | null = null, afterCell: number | null = null, cellObjectId: string | null = null, restart = false): Promise<void> {
    if (pending.current) return;
    const selected = page?.entries[0], reason = rationale;
    if (mode === "exclude" && (!selected || selected.excluded || !knownHead.current || !reason.trim() || Array.from(reason).length > 256)) return;
    const expected = restart ? null : knownHead.current;
    if (mode === "exclude") afterOrder = selected!.order ? selected!.order - 1 : null;
    pending.current = true; const ticket = ++generation.current;
    clear(); setBusy(true); setStatus(mode === "exclude" ? "Recording this exclusion and retaining the original parse…"
      : mode === "enrich" ? "Extracting source-grounded tables and figures…" : "Checking tables, figures and current permission…");
    let releaseMain = (): void => undefined, releaseCore = (): void => undefined, terminal = true;
    const current = (): boolean => live.current && generation.current === ticket;
    try {
      releaseMain = props.main.context(); releaseCore = props.reserveCore();
      const project = props.metadata.source.projectId;
      let result: unknown;
      if (mode === "read") {
        terminal = false; result = await props.port.read(project, props.revisionId, expected, afterOrder, afterCell, cellObjectId);
      } else {
        const key = JSON.stringify([mode, expected, mode === "exclude" ? selected!.nodeId : null, mode === "exclude" ? reason : null]);
        if (!command.current || command.current.key !== key) command.current = { id: newAttachmentId(), key };
        terminal = false;
        result = mode === "exclude" ? await props.port.exclude(project, props.revisionId, command.current.id, expected!, selected!.nodeId, reason)
          : await props.port.enrich(project, props.revisionId, command.current.id, expected);
      }
      terminal = true;
      const value = decodeTableFigurePage(result, project, props.revisionId), notice = mode === "read" ? decodeTableFigureNotice(result, project, props.revisionId) : null;
      if (!current()) { releaseMain(); return; }
      setChecked(true);
      if (notice && viewerSourcesMatch(notice.source, props.metadata.source)) {
        knownHead.current = notice.collectionRevisionId; releaseMain();
        setStatus(notice.reasonCode === "viewer-resource-limit" ? "Tables and figures exceed the local Reader limit. The accepted document remains available."
          : "Saved tables and figures could not be confirmed. Review current source permission, then refresh the extraction."); return;
      }
      if (!value || !viewerSourcesMatch(value.source, props.metadata.source) || value.afterOrder !== afterOrder
        || mode === "read" && expected !== null && value.collectionRevisionId !== expected
        || (value.entries[0]?.afterCell ?? null) !== afterCell || afterCell !== null && value.entries[0]?.nodeId !== cellObjectId
        || mode === "exclude" && (value.entries[0]?.exclusion?.nodeId !== selected!.nodeId || value.entries[0]?.exclusion?.commandId !== command.current?.id || value.entries[0]?.exclusion?.rationale !== reason)) {
        releaseMain(); setStatus(result === null && mode === "read" && expected === null ? "No table or figure collection is recorded. Extract from this accepted revision."
          : "This exact extraction could not be confirmed. Check the current source and try again."); return;
      }
      if (mode !== "read") command.current = null;
      retained.current = releaseMain; knownHead.current = value.collectionRevisionId; setPage(value); setRationale("");
      setStatus(value.total ? `Object ${(value.entries[0]?.order ?? 0) + 1} of ${value.total}. Captions, cells and confidence remain unverified.`
        : "No recognized tables or figures were found. This does not establish their absence.");
      heading.current?.focus();
    } catch (error) {
      const code = error instanceof Error ? error.message : "viewer-owned-read-drain-pending";
      terminal = terminal || code === "viewer-resource-limit" || code === "viewer-source-unavailable";
      if (terminal) releaseMain();
      if (current()) {
        setStatus(code === "viewer-resource-limit" ? "This extraction exceeds the local Reader limit. The original and accepted document remain retained."
          : "Table or figure access could not be confirmed. Return to source review.");
        if (!terminal) props.onFailure("viewer-owned-read-drain-pending");
      }
    } finally {
      if (terminal) { releaseCore(); pending.current = false; }
      if (current()) setBusy(false);
    }
  }
  const entry = page?.entries[0];
  return <Panel title="Tables and figures"><section className="ro-stack ro-wrap-anywhere" aria-label="Table and figure inspection" aria-busy={busy}>
    <h2 ref={heading} tabIndex={-1}>Tables and figures</h2><p role="status">{status}</p>
    <div className="ro-action-row"><Button disabled={busy} onClick={() => void load("read", null, null, null, true)}>Inspect tables and figures</Button>
      {checked ? <Button disabled={busy} onClick={() => void load("enrich")}>{knownHead.current ? "Refresh tables and figures" : "Extract tables and figures"}</Button> : null}
      {page?.nextAfterOrder !== null && page?.nextAfterOrder !== undefined ? <Button disabled={busy} onClick={() => void load("read", page.nextAfterOrder)}>Next table or figure</Button> : null}</div>
    {entry ? <section aria-label={`${entry.kind} ${entry.order + 1}`} className="ro-stack">
      <h3>{entry.kind === "table" ? "Table" : "Figure"} {entry.order + 1}</h3><StatusBadge tone={entry.excluded ? "warning" : "info"}>{entry.excluded ? "Excluded by researcher" : "Unverified extraction"}</StatusBadge>
      {entry.labels.map(label => <p key={label.nodeId} className="anchor-passage-text">{label.textPreview}</p>)}
      {entry.labelCount > entry.labels.length ? <p>Showing {entry.labels.length} of {entry.labelCount} labels.</p> : null}
      <p>Caption association: {entry.captionState.replaceAll("-", " ")}. Parser confidence: {entry.confidence.value ?? entry.confidence.state.replaceAll("-", " ")}.</p>
      {entry.captions.map(caption => <div key={caption.nodeId}><p className="anchor-passage-text">{caption.textPreview || "Empty reported caption."}</p>
        {caption.truncated ? <p>Caption preview truncated; {caption.textLength.toLocaleString()} codepoints remain retained.</p> : null}
        <Button disabled={busy} onClick={() => props.onSource(caption.jump)}>Jump to caption source</Button></div>)}
      {entry.captionCount > entry.captions.length ? <p>Showing {entry.captions.length} of {entry.captionCount} candidate captions.</p> : null}
      {entry.jump.normalizedRange ? <Button disabled={busy} onClick={() => props.onSource(entry.jump)}>Jump to {entry.kind} source</Button> : null}
      {entry.preview.kind === "source-page-region" ? <><p>Original preview: exact source page {entry.preview.locator.pageIndex + 1}{entry.preview.basis === "cell" ? " · location reported by a cell; table bounds not reported" : ""}.</p>
        <Button disabled={busy} onClick={() => props.onPreview(entry)}>Show original {entry.kind} page</Button></> : <p>Original image preview unavailable: {entry.preview.reason.replaceAll("-", " ")}.</p>}
      {entry.retainedPreviewState === "unavailable" ? <p>A reported parser preview is retained but cannot be delivered as an authenticated image.</p> : null}
      {entry.kind === "table" ? <><p>Reported grid: {entry.rows?.toLocaleString()} rows × {entry.columns?.toLocaleString()} columns · {entry.gridState}. Inspect source for merged, split or uncertain cells.</p>
        <table className="ro-table"><caption>Extracted cell observations · unverified</caption><thead><tr><th scope="col">Location</th><th scope="col">Extracted text</th><th scope="col">Quality</th><th scope="col">Source</th></tr></thead>
          <tbody>{entry.cells.map(cell => <tr key={cell.nodeId}><td>Row {cell.row + 1}, column {cell.column + 1}<br />Span {cell.rowSpan} × {cell.columnSpan} · {cell.headerState.replaceAll("-", " ")}</td>
            <td className="anchor-passage-text">{cell.textPreview || "Empty cell."}{cell.truncated ? <p>Preview truncated; full text retained.</p> : null}</td>
            <td>{cell.triage.replaceAll("-", " ")} · {cell.confidence.value ?? cell.confidence.state.replaceAll("-", " ")} · unverified</td>
            <td><Button disabled={busy} onClick={() => props.onSource(cell.jump)}>Inspect cell source</Button></td></tr>)}</tbody></table>
        <p>Showing {entry.cells.length} of {entry.cellCount.toLocaleString()} retained cells. Low or reported confidence never verifies evidence.</p>
        {entry.nextAfterCell !== null ? <Button disabled={busy} onClick={() => void load("read", entry.order ? entry.order - 1 : null, entry.nextAfterCell, entry.nodeId)}>Next cells</Button> : null}</> : null}
      {entry.warnings.length ? <p>Reported warnings: {entry.warnings.join(", ")}.</p> : null}
      {entry.exclusion ? <><p>Exclusion rationale: {entry.exclusion.rationale}</p><p>Original parse and earlier observations remain retained.</p></>
        : <form className="ro-stack" onSubmit={event => { event.preventDefault(); void load("exclude"); }}>
          <label>Reason to exclude this unreliable extraction<input aria-label="Exclusion rationale" maxLength={512} value={rationale} disabled={busy} onChange={event => setRationale(event.currentTarget.value)} /></label>
          <p>Exclusion records your decision in a new revision. The original parse remains retained.</p>
          <Button type="submit" disabled={busy || !rationale.trim() || Array.from(rationale).length > 256}>Exclude this extraction</Button></form>}
    </section> : null}
  </section></Panel>;
}
