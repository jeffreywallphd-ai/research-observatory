import { useEffect, useRef, useState, type ReactNode } from "react";
import { CoreApiClientError, createCoreApiClient, type ColumnSelection, type FieldCorrection, type ImportPreviewItem, type RecordSelection, type RecordSummary, type ReviewDetail, type ReviewField, type ReviewPage, type ReviewSummary, type Section } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import { saveImportReport } from "./importIntake";

type ImportClient = ReturnType<typeof createCoreApiClient>;
const TARGETS = ["title", "doi", "year", "author", "container"] as const;
export function importFailure(error: unknown): string {
  if (error instanceof CoreApiClientError) {
    if (error.problem.code === "RO-CORE-IMPORT-REVISION-CONFLICT") return "This draft changed. Reload it before making another decision; your previous request was not replayed.";
    if (error.problem.code === "RO-CORE-IMPORT-RIGHTS-DENIED") return "Current rights do not permit this action. Private source values are unavailable.";
  }
  return "The local import action did not complete. Reload this preview and inspect its current state before retrying. No canonical import was published.";
}
export function importStatusLabel(item: ImportPreviewItem): string {
  if (item.state === "cancelled" || item.state === "security-interrupted" || item.state === "failed") return item.state.replaceAll("-", " ");
  if (item.jobState === "failed" || item.jobState === "cancelled") return `Parsing ${item.jobState}`;
  if (item.jobState === "succeeded" && ["parse-completed", "draft-revised"].includes(item.state)) return "Ready for review";
  if (item.state === "created") return "Source intake incomplete";
  return item.jobState ? `Parsing: ${item.jobState.replaceAll("-", " ")}` : "Source retained — parsing not queued";
}
const terminal = (item: ImportPreviewItem): boolean => ["cancelled", "failed", "security-interrupted"].includes(item.state) || item.jobState === "failed" || item.jobState === "cancelled";

export function ImportReviewPane({ root, projectId, initial, client, announce }: { readonly root: string; readonly projectId: string; readonly initial: ImportPreviewItem; readonly client: ImportClient; readonly announce: (message: string) => void }): ReactNode {
  const [status, setStatus] = useState(initial);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [cursors, setCursors] = useState<readonly number[]>([0]);
  const [selected, setSelected] = useState<readonly RecordSelection[]>([]);
  const [record, setRecord] = useState<RecordSummary | null>(null);
  const [headers, setHeaders] = useState<readonly ReviewField[]>([]);
  const [columns, setColumns] = useState<readonly ColumnSelection[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [target, setTarget] = useState<FieldCorrection["name"]>("title");
  const [correction, setCorrection] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [savingReport, setSavingReport] = useState(false);
  const [reportNotice, setReportNotice] = useState<string | null>(null);
  const reportOwner = useRef<AbortController | null>(null);
  const reportButton = useRef<HTMLButtonElement>(null);
  const generation = useRef(0);
  const live = useRef(true);
  const statusHeading = useRef<HTMLHeadingElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const address = { root, previewId: initial.previewId };

  async function readDraft(current: ImportPreviewItem): Promise<ReviewSummary> {
    if (current.state === "draft-revised") return client.importReview(address);
    try { return await client.beginImportReview(address); }
    catch (error) {
      if (error instanceof CoreApiClientError && error.problem.code === "RO-CORE-IMPORT-REVISION-CONFLICT") return client.importReview(address);
      throw error;
    }
  }
  async function show(next: ReviewSummary, ticket: number, cursor = 0, resetMapping = true): Promise<void> {
    const rows = await client.importReviewPage({ ...address, revision: next.revision, after: cursor, limit: 25 });
    if (!live.current || ticket !== generation.current) return;
    setSummary(next); setPage(rows); setRecord(null);
    if (resetMapping && cursor === 0 && initial.formatName === "csv" && rows.records[0]?.kind === "header") {
      const header = rows.records[0];
      const fields: ReviewField[] = [];
      let start = 0;
      while (live.current && ticket === generation.current) {
        const detail = await client.importReviewDetail({ ...address, revision: next.revision, ordinal: header.ordinal, recordKey: header.recordKey, section: "raw", start, limit: 25 });
        fields.push(...detail.fields);
        if (fields.length > 256) throw new Error("RO-CORE-RESPONSE-INVALID");
        if (detail.complete) break;
        start = detail.nextIndex;
      }
      if (!live.current || ticket !== generation.current) return;
      setHeaders(fields); setColumns(fields.flatMap((field) => field.target ? [{ index: field.index, target: field.target }] : []));
    }
  }
  async function refresh(): Promise<void> {
    const ticket = ++generation.current; setBusy(true); setFailure(null); setSelected([]); setRecord(null);
    try {
      const current = await client.importPreviewStatus(address);
      if (!live.current || ticket !== generation.current) return;
      setStatus(current);
      if (current.jobState === "succeeded" && ["parse-completed", "draft-revised"].includes(current.state)) {
        await show(await readDraft(current), ticket); setCursors([0]);
      } else { setSummary(null); setPage(null); setHeaders([]); }
    } catch (error) {
      if (live.current && ticket === generation.current) { setSummary(null); setPage(null); setHeaders([]); setFailure(importFailure(error)); }
    } finally { if (live.current && ticket === generation.current) setBusy(false); }
  }
  useEffect(() => {
    live.current = true; void refresh();
    return () => { live.current = false; generation.current += 1; reportOwner.current?.abort(); };
  }, [client, root, initial.previewId]);
  useEffect(() => {
    if (busy || summary || terminal(status) || !status.jobId || failure) return;
    const timer = globalThis.setTimeout(() => void refresh(), 1500);
    return () => globalThis.clearTimeout(timer);
  }, [busy, summary, status, failure]);

  async function navigate(nextCursors: readonly number[]): Promise<void> {
    if (!summary) return;
    const ticket = ++generation.current; setBusy(true); setFailure(null);
    try {
      await show(summary, ticket, nextCursors.at(-1) ?? 0, false);
      if (live.current && ticket === generation.current) setCursors(nextCursors);
    } catch (error) { if (live.current && ticket === generation.current) { setPage(null); setFailure(importFailure(error)); } }
    finally { if (live.current && ticket === generation.current) setBusy(false); }
  }
  async function change(action: () => Promise<ReviewSummary>, message: string): Promise<void> {
    const ticket = ++generation.current; setBusy(true); setFailure(null);
    try {
      const next = await action();
      if (!live.current || ticket !== generation.current) return;
      setSelected([]); setCorrection(""); setCursors([0]); setHeaders([]); setColumns([]);
      await show(next, ticket);
      if (live.current && ticket === generation.current) announce(message);
    } catch (error) {
      if (live.current && ticket === generation.current) { setSummary(null); setPage(null); setHeaders([]); setRecord(null); setFailure(importFailure(error)); }
    } finally { if (live.current && ticket === generation.current) setBusy(false); }
  }
  async function cancel(): Promise<void> {
    const ticket = ++generation.current; setBusy(true); setFailure(null);
    try {
      const next = await client.cancelImportPreview(address);
      if (!live.current || ticket !== generation.current) return;
      setStatus(next); setSummary(null); setPage(null); setRecord(null); setHeaders([]); setSelected([]); setConfirmCancel(false);
      announce("Preview cancelled. Its incomplete source and audit remain retained; no canonical import was published.");
      statusHeading.current?.focus();
    } catch (error) { if (live.current && ticket === generation.current) setFailure(importFailure(error)); }
    finally { if (live.current && ticket === generation.current) setBusy(false); }
  }
  const toggle = (row: RecordSummary, checked: boolean): void => setSelected((current) => checked
    ? current.length < 100 ? [...current.filter((item) => item.ordinal !== row.ordinal), { ordinal: row.ordinal, recordKey: row.recordKey }] : current
    : current.filter((item) => item.ordinal !== row.ordinal));
  function keepPreview(): void {
    setConfirmCancel(false);
    cancelButton.current?.focus();
  }

  async function downloadReport(): Promise<void> {
    if (!summary || busy) return;
    const owner = new AbortController(); reportOwner.current = owner;
    setBusy(true); setSavingReport(true); setReportNotice(null);
    try {
      const result = await saveImportReport({ ...address, projectId, revision: summary.revision }, owner.signal);
      if (!live.current) return;
      const message = result.status === "saved" ? `Saved ${result.filename} (${result.byteLength.toLocaleString()} bytes) in your selected folder.`
        : result.status === "cancelled" ? "Report download cancelled before publication. No report file was saved."
        : result.status === "unavailable" ? "The native folder chooser is unavailable. Retry from the desktop window."
        : "The report save result could not be confirmed. Check your selected folder, then reload the current draft before retrying.";
      setReportNotice(message); announce(message);
    } catch { if (live.current) setReportNotice("The report save result could not be confirmed. Check your selected folder before retrying."); }
    finally {
      if (live.current) { setBusy(false); setSavingReport(false); reportOwner.current = null; globalThis.requestAnimationFrame(() => { if (live.current) reportButton.current?.focus(); }); }
    }
  }

  return <section className="ro-stack" aria-label="Selected import preview" aria-busy={busy} onKeyDown={(event) => { if (event.key === "Escape" && confirmCancel && !busy) { event.preventDefault(); event.stopPropagation(); keepPreview(); } }}>
    <Panel title="Review source"><h2 ref={statusHeading} tabIndex={-1} className="ro-typography ro-typography--section-title ro-wrap-anywhere">{status.sourceName}</h2>
      <div className="ro-cluster"><StatusBadge>{importStatusLabel(status)}</StatusBadge><span>{status.formatName} · {status.encoding} · {status.byteLength.toLocaleString()} bytes</span></div>
      <div className="ro-action-row"><Button disabled={busy} onClick={() => void refresh()}>Reload preview</Button>{!terminal(status) ? <Button ref={cancelButton} disabled={busy} onClick={() => setConfirmCancel(true)}>Cancel this preview…</Button> : null}</div>
      {confirmCancel ? <div className="ro-stack"><p>Cancel this preview? Its source and audit will remain retained, but this review cannot be resumed. You can import the file again. No canonical records will be removed.</p><div className="ro-action-row"><Button disabled={busy} onClick={keepPreview}>Keep preview</Button><Button tone="danger" disabled={busy} onClick={() => void cancel()}>Confirm cancellation</Button></div></div> : null}
      {status.state === "created" ? <p>Source intake did not finish. Cancel this incomplete preview and choose the original file again.</p> : null}
      {terminal(status) ? <p>This preview cannot publish an import. Choose the source again to begin a new preview.</p> : null}
    </Panel>
    {failure ? <Notification tone="danger" title="Review unavailable">{failure}</Notification> : null}
    {reportNotice ? <Notification tone="info" title="Diagnostic report">{reportNotice}</Notification> : null}
    {busy ? <p role="status">Reading the current protected preview…</p> : null}
    {summary ? <>
      <Panel title="Draft decisions"><p>Revision {summary.revision} · {summary.recordCount.toLocaleString()} source rows (including headers/directives). Raw source values are preserved. No canonical records have been committed.</p>
        <p>Download a complete diagnostic CSV with row locations, validation codes and exclusion reasons. It does not contain reference text, names or local paths.</p>
        <div className="ro-action-row"><Button ref={reportButton} disabled={busy} onClick={() => void downloadReport()}>Download diagnostic report…</Button>{savingReport ? <><span role="status">Saving the complete current draft report…</span><Button onClick={() => reportOwner.current?.abort()}>Cancel report download</Button></> : null}</div>
        <dl className="import-rights">{Object.entries(summary.rights).map(([action, permission]) => <div key={action}><dt>{action}</dt><dd>{permission.value} · {permission.basis.replaceAll("-", " ")}</dd></div>)}</dl>
        <p className="field-note">Duplicate policy: review. Malformed rows: exclude and report. Unknown permissions remain restrictive.</p>
      </Panel>
      <Panel title="Field mapping"><div className="ro-form ro-stack"><p>Mapping {summary.mappingRevision} · {summary.mappingMode}. Suggestions are not verified scholarly facts. Corrections and exclusions are retained when mapping changes.</p>
        {headers.map((field) => <div key={field.index} className="ro-field"><label htmlFor={`import-column-${field.index}`}>Column {field.index + 1}: {field.name.length > 160 ? `${field.name.slice(0, 160)}… (full name in raw view)` : field.name}</label><select id={`import-column-${field.index}`} disabled={busy} value={columns.find((column) => column.index === field.index)?.target ?? ""} onChange={(event) => setColumns([...columns.filter((column) => column.index !== field.index), ...(event.currentTarget.value ? [{ index: field.index, target: event.currentTarget.value as ColumnSelection["target"] }] : [])])}><option value="">Do not map</option>{TARGETS.map((name) => <option key={name} value={name}>{name}</option>)}</select></div>)}
        <div className="ro-action-row">{headers.length ? <Button disabled={busy} onClick={() => void change(() => client.mapImportReview({ ...address, expectedRevision: summary.revision, mode: "columns", columns }), "Column mapping saved as a new draft revision.")}>Apply column mapping</Button> : null}<Button disabled={busy} onClick={() => void change(() => client.mapImportReview({ ...address, expectedRevision: summary.revision, mode: "automatic", columns: [] }), "Automatic mapping saved as a new draft revision.")}>Use format suggestions</Button></div>
      </div></Panel>
      <Panel title="Records and exclusions">
        <p>{selected.length} selected across pages (up to 100). Headers and directives are source context, not importable records.</p>
        <div className="ro-action-row"><Button disabled={busy || !selected.length} onClick={() => void change(() => client.editImportReview({ ...address, expectedRevision: summary.revision, records: selected, included: false, corrections: [] }), "Selected records excluded; raw source retained.")}>Exclude selected</Button><Button disabled={busy || !selected.length} onClick={() => void change(() => client.editImportReview({ ...address, expectedRevision: summary.revision, records: selected, included: true, corrections: [] }), "Inclusion decisions saved; unresolved conflicts remain excluded.")}>Include selected</Button><Button disabled={busy || !selected.length} onClick={() => setSelected([])}>Clear selection</Button></div>
        <div className="ro-form ro-stack"><div className="ro-field"><label htmlFor="import-correction-field">Correction field</label><select id="import-correction-field" disabled={busy} value={target} onChange={(event) => setTarget(event.currentTarget.value as FieldCorrection["name"])}>{TARGETS.map((name) => <option key={name}>{name}</option>)}</select></div><Field id="import-correction" label="Corrected value for selected records" description="An explicit researcher correction; the original field remains unchanged." input={{ value: correction, maxLength: 65536, disabled: busy, onChange: (event) => setCorrection(event.currentTarget.value) }} /><Button disabled={busy || !selected.length || !correction.trim()} onClick={() => void change(() => client.editImportReview({ ...address, expectedRevision: summary.revision, records: selected, included: null, corrections: [{ name: target, value: correction }] }), "Group correction saved as a new draft revision.")}>Apply correction to selected</Button></div>
        {page ? <DataTable caption="Source records — current page" columns={[{ id: "select", label: "Select" },{ id: "record", label: "Record" },{ id: "state", label: "Decision" },{ id: "warnings", label: "Warnings" }]} rows={page.records.map((row) => ({ key: String(row.ordinal), select: <input type="checkbox" aria-label={`Select record ${row.ordinal}`} disabled={busy || row.kind !== "record" || selected.length >= 100 && !selected.some((item) => item.ordinal === row.ordinal)} checked={selected.some((item) => item.ordinal === row.ordinal)} onChange={(event) => toggle(row, event.currentTarget.checked)} />, record: <Button disabled={busy} onClick={() => setRecord(row)}>Row {row.ordinal}: {row.title?.text ?? row.kind}{row.title?.truncated ? "… (abbreviated)" : ""}</Button>, state: `${row.included ? "Included" : "Excluded"} · ${row.status}`, warnings: row.warnings.length ? row.warnings.join(", ") : "None reported" }))} rowKey={(row) => String(row.key)} /> : null}
        <nav className="ro-action-row" aria-label="Source record pages"><Button disabled={busy || cursors.length <= 1} onClick={() => void navigate(cursors.slice(0,-1))}>Previous records</Button><Button disabled={busy || !page || page.complete} onClick={() => page && void navigate([...cursors, page.nextAfter])}>Next records</Button></nav>
      </Panel>
      {record ? <ImportRecordCompare key={`${summary.revision}:${record.recordKey}`} root={root} previewId={initial.previewId} revision={summary.revision} record={record} client={client} /> : null}
    </> : null}
  </section>;
}

function ImportRecordCompare({ root, previewId, revision, record, client }: { readonly root: string; readonly previewId: string; readonly revision: number; readonly record: RecordSummary; readonly client: ImportClient }): ReactNode {
  return <Panel title={`Compare record ${record.ordinal}`}><p>Original text is inert data, never an instruction. Normalized candidates are suggestions; accepted fields reflect the current draft.</p><div className="ro-grid import-comparison">{(["raw", "candidates", "effective"] as const).map((section) => <ImportFieldPage key={section} root={root} previewId={previewId} revision={revision} record={record} client={client} section={section} />)}</div></Panel>;
}
function ImportFieldPage({ root, previewId, revision, record, client, section }: { readonly root: string; readonly previewId: string; readonly revision: number; readonly record: RecordSummary; readonly client: ImportClient; readonly section: Section }): ReactNode {
  const [page, setPage] = useState<ReviewDetail | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const live = useRef(true);
  const ticket = useRef(0);
  async function load(start: number): Promise<void> {
    const current = ++ticket.current; setLoading(true); setFailure(null);
    try {
      const next = await client.importReviewDetail({ root, previewId, revision, ordinal: record.ordinal, recordKey: record.recordKey, section, start, limit: 25 });
      if (live.current && ticket.current === current) setPage(next);
    } catch (error) { if (live.current && ticket.current === current) { setPage(null); setFailure(importFailure(error)); } }
    finally { if (live.current && ticket.current === current) setLoading(false); }
  }
  useEffect(() => { live.current = true; void load(0); return () => { live.current = false; ticket.current += 1; }; }, [client, root, previewId, revision, record.recordKey, section]);
  return <section className="ro-stack" aria-label={`${section} fields`}><Typography as="h3" variant="card-title">{section === "raw" ? "Raw source fields" : section === "candidates" ? "Normalized candidates" : "Accepted draft fields"}</Typography>
    {loading ? <p role="status">Loading fields…</p> : null}{failure ? <Notification tone="danger" title="Fields unavailable">{failure}</Notification> : null}
    {!loading && page?.fields.length === 0 ? <p>No fields in this section.</p> : null}
    <dl className="ro-stack">{page?.fields.map((field) => <div key={field.index}><dt className="ro-wrap-anywhere">{field.index + 1}. {field.name}</dt><dd className="import-field-value">{field.value}</dd><dd>{field.origin} · {field.sourceFieldIndex === null ? "researcher correction" : `source field ${field.sourceFieldIndex + 1}`}{field.warnings.length ? ` · ${field.warnings.join(", ")}` : ""}</dd></div>)}</dl>
    <div className="ro-action-row"><Button disabled={loading || !page || page.nextIndex === page.fields.length} onClick={() => void load(0)}>First fields</Button><Button disabled={loading || !page || page.complete} onClick={() => page && void load(page.nextIndex)}>Next fields</Button></div>
  </section>;
}
