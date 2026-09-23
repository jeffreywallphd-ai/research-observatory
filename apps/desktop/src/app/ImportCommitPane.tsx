import { useEffect, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, type ImportCommitStatus, type ImportManifestPage, type ImportManifestView, type ImportPreviewPage, type SummaryCounts } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";

type ImportClient = ReturnType<typeof createCoreApiClient>;
type PendingOperation = "status" | "action" | null;
const active = (status: ImportCommitStatus | null): boolean => Boolean(status?.jobState && !["succeeded", "failed", "cancelled"].includes(status.jobState));

export function ImportCommitPane({ root, projectId, previewId, revision, counts, client, disabled, announce }: {
  readonly root: string; readonly projectId: string; readonly previewId: string; readonly revision: number;
  readonly counts: SummaryCounts | null; readonly client: ImportClient; readonly disabled: boolean;
  readonly announce: (message: string) => void;
}): ReactNode {
  const [status, setStatus] = useState<ImportCommitStatus | null>(null);
  const [pending, setPending] = useState<PendingOperation>("status"), [failure, setFailure] = useState<string | null>(null);
  const pendingOperation = useRef<PendingOperation>(null);
  const loading = pending !== null;
  const [confirming, setConfirming] = useState(false);
  const [previous, setPrevious] = useState<ImportManifestView | null>(null);
  const [batches, setBatches] = useState<ImportPreviewPage | null>(null);
  const [showManifest, setShowManifest] = useState(false);
  const live = useRef(true), generation = useRef(0), lastState = useRef<string | null>(null);
  const reviewButton = useRef<HTMLButtonElement>(null), confirmHeading = useRef<HTMLHeadingElement>(null);
  const address = { root, previewId };

  async function perform(action: () => Promise<void>, operation: Exclude<PendingOperation, null> = "action"): Promise<void> {
    const ticket = generation.current;
    pendingOperation.current = operation; setPending(operation); setFailure(null);
    try { await action(); }
    catch {
      if (live.current && ticket === generation.current) {
        setStatus(null); setConfirming(false); setShowManifest(false);
        setFailure("The import outcome could not be confirmed. Refresh commit status before retrying. Current rights and the saved draft will be checked again; a missing reply does not mean nothing was imported.");
      }
    } finally {
      if (live.current && ticket === generation.current) { pendingOperation.current = null; setPending(null); }
    }
  }
  function accept(next: ImportCommitStatus | null, ticket: number): boolean {
    if (!live.current || ticket !== generation.current) return false;
    if (next?.manifest && next.manifest.projectId !== projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
    setStatus(next);
    if (next?.jobState && next.jobState !== lastState.current) {
      lastState.current = next.jobState;
      announce(next.manifest ? "Import committed. Source records are retained and await work/version reconciliation. Open the import manifest to inspect the result." : `Import commit: ${next.jobState.replaceAll("-", " ")}.`);
    }
    return true;
  }
  async function refresh(): Promise<void> {
    const ticket = ++generation.current;
    await perform(async () => { accept(await client.latestImportCommit(address), ticket); }, "status");
  }
  useEffect(() => {
    live.current = true; void refresh();
    return () => { live.current = false; generation.current += 1; };
  }, [client, root, previewId, revision]);
  useEffect(() => {
    if (disabled || loading || failure || !active(status)) return;
    const timer = globalThis.setTimeout(() => void refresh(), 1500);
    return () => globalThis.clearTimeout(timer);
  }, [disabled, loading, failure, status]);
  useEffect(() => { if (confirming) confirmHeading.current?.focus(); }, [confirming]);

  function back(): void {
    setConfirming(false);
    globalThis.requestAnimationFrame(() => { if (live.current) reviewButton.current?.focus(); });
  }
  async function commit(): Promise<void> {
    const ticket = ++generation.current;
    await perform(async () => {
      const prepared = await client.prepareImportCommit({ ...address, revision, previousManifestRevisionId: previous?.revisionId ?? null });
      if (!accept(prepared, ticket)) return;
      const next = await client.startImportCommit({ ...address, revision, previousManifestRevisionId: previous?.revisionId ?? null, requestId: prepared.requestId });
      if (accept(next, ticket)) setConfirming(false);
    });
  }
  async function cancel(): Promise<void> {
    if (disabled || pendingOperation.current === "action" || !active(status) || !status?.jobId) return;
    const ticket = ++generation.current;
    await perform(async () => { accept(await client.cancelImportCommit({ ...address, requestId: status.requestId, jobId: status.jobId! }), ticket); });
  }
  async function list(after: string | null): Promise<void> {
    const ticket = ++generation.current;
    await perform(async () => {
      const page = await client.importPreviews({ root, after, limit: 25 });
      if (live.current && ticket === generation.current) setBatches(page);
    });
  }
  async function compare(id: string): Promise<void> {
    const ticket = ++generation.current;
    await perform(async () => {
      const manifest = await client.importManifest({ root, previewId: id, revisionId: null });
      if (!live.current || ticket !== generation.current) return;
      if (!manifest) { setFailure("This batch has no committed manifest. Choose another batch or continue without comparison."); return; }
      if (manifest.projectId !== projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
      setPrevious(manifest); setBatches(null);
    });
  }
  const unavailable = disabled || loading;
  return <Panel title="Commit reviewed import">
    <div className="ro-stack" aria-label="Import commit" aria-busy={loading} onKeyDown={(event) => {
      if (event.key === "Escape" && confirming && !loading) { event.preventDefault(); event.stopPropagation(); back(); }
    }}>
      <p>Commit creates immutable source records and an import manifest in this project. It does not merge works or verify scholarly claims. Corrections and original source values stay traceable.</p>
      {!counts ? <p>Calculate the preview summary above before committing this draft.</p> : <p>Draft {revision}: {counts.includedRecords.toLocaleString()} included records; {counts.excludedRecords.toLocaleString()} excluded records; {counts.contextRows.toLocaleString()} context rows; {counts.warningRows.toLocaleString()} rows with warnings. Re-imports reuse existing source records; exact additions are reported after commit.</p>}
      {failure ? <Notification tone="danger" title="Commit status needs attention">{failure}</Notification> : null}
      {loading ? <p role="status">Reading or saving durable import status…</p> : null}
      {status?.jobState ? <StatusBadge>{status.manifest ? "Committed — awaiting reconciliation" : `Commit ${status.jobState.replaceAll("-", " ")}`}</StatusBadge> : !failure && !loading ? <StatusBadge>No commit job reported</StatusBadge> : null}
      {status?.manifest ? <p>The saved result uses manifest draft {status.manifest.draftRevision}. Your current draft is {revision}; later edits do not change that result. An identical re-import may reuse an earlier batch’s manifest.</p> : null}
      {active(status) ? <p>Changing this draft while its commit runs can stop the commit. Cancellation does not remove already committed records.</p> : null}
      {status?.jobState === "failed" || status?.jobState === "cancelled" ? <p>The saved request remains available. Inspect or explicitly retry its job in Task Center; reopening this page does not retry it.</p> : null}
      {status?.diagnosticCode ? <p>Diagnostic: {status.diagnosticCode}</p> : null}
      <div className="ro-action-row">
        <Button disabled={unavailable} onClick={() => void refresh()}>Refresh commit status</Button>
        {active(status) ? <Button disabled={disabled || pending === "action"} onClick={() => void cancel()}>Cancel import commit</Button> : null}
        <Button ref={reviewButton} disabled={unavailable || !counts || active(status) || confirming} onClick={() => setConfirming(true)}>Review commit…</Button>
        {status?.manifest ? <Button disabled={unavailable} onClick={() => setShowManifest(!showManifest)}>{showManifest ? "Hide import manifest" : "Open import manifest"}</Button> : null}
      </div>
      {confirming && counts ? <section className="ro-stack" aria-label="Confirm import commit">
        <h3 ref={confirmHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Confirm draft {revision}</h3>
        <p>{counts.includedRecords.toLocaleString()} records will be included. Existing source identities are reused. Excluded rows, warnings and decisions remain in the manifest. Unknown rights are not granted by committing.</p>
        <p>{previous ? `Compare against manifest ${previous.revisionId}, draft ${previous.draftRevision}. Matches are mechanical suggestions, not Work merges.` : "No earlier manifest selected. The result will not claim which records changed from an earlier file."}</p>
        <div className="ro-action-row"><Button disabled={unavailable} onClick={() => void list(null)}>Choose earlier import for comparison</Button>{previous ? <Button disabled={unavailable} onClick={() => setPrevious(null)}>Clear comparison</Button> : null}</div>
        {batches ? <div className="ro-stack"><ul className="ro-stack">{batches.items.map((item) => <li key={item.previewId}><Button disabled={unavailable} onClick={() => void compare(item.previewId)}>{item.sourceName}</Button></li>)}</ul><Button disabled={unavailable || batches.complete} onClick={() => void list(batches.nextAfter)}>More import batches</Button></div> : null}
        <div className="ro-action-row"><Button disabled={unavailable} onClick={back}>Back to draft</Button><Button tone="primary" disabled={unavailable} onClick={() => void commit()}>Commit this draft</Button></div>
      </section> : null}
      {showManifest && status?.manifest ? <ImportManifestPane key={status.manifest.revisionId} root={root} manifest={status.manifest} client={client} /> : null}
    </div>
  </Panel>;
}

function ImportManifestPane({ root, manifest, client }: { readonly root: string; readonly manifest: ImportManifestView; readonly client: ImportClient }): ReactNode {
  const [page, setPage] = useState<ImportManifestPage | null>(null), [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState(false), [cursors, setCursors] = useState<readonly number[]>([0]);
  const live = useRef(true), generation = useRef(0);
  async function load(nextCursors: readonly number[]): Promise<void> {
    const ticket = ++generation.current; setLoading(true); setFailure(false); setPage(null);
    try {
      const next = await client.importManifestMembers({ root, previewId: manifest.previewId, revisionId: manifest.revisionId, after: nextCursors.at(-1) ?? 0, limit: 25 });
      if (live.current && ticket === generation.current) { setPage(next); setCursors(nextCursors); }
    } catch { if (live.current && ticket === generation.current) setFailure(true); }
    finally { if (live.current && ticket === generation.current) setLoading(false); }
  }
  useEffect(() => { live.current = true; void load([0]); return () => { live.current = false; generation.current += 1; }; }, [client, root, manifest.revisionId]);
  return <section className="ro-stack" aria-label="Import manifest" aria-busy={loading}>
    <h3 className="ro-typography ro-typography--card-title">Immutable import manifest</h3>
    {!failure ? <><p>{manifest.createdCount.toLocaleString()} new source records; {manifest.reusedCount.toLocaleString()} reused source records. {manifest.selectedCount.toLocaleString()} selected of {manifest.recordCount.toLocaleString()} source rows. Work/version reconciliation is separate.</p>
    <dl className="import-rights">{Object.entries({ Manifest: manifest.revisionId, Source: manifest.sourceSha256, Parser: manifest.parserVersion, "Mapping revision": manifest.mappingRevision, "Draft revision": manifest.draftRevision, "Membership digest": manifest.membersSha256 }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="ro-wrap-anywhere">{value}</dd></div>)}</dl></> : null}
    {loading ? <p role="status">Reading manifest page…</p> : null}
    {failure ? <Notification tone="danger" title="Manifest unavailable">Current access could not be confirmed. Close the manifest and refresh commit status; retained records have not been removed.</Notification> : null}
    {page ? <DataTable caption="Immutable import decisions — current page" columns={[{ id: "row", label: "Source row" }, { id: "decision", label: "Decision" }, { id: "record", label: "Canonical source revision" }, { id: "comparison", label: "Compared with earlier import" }, { id: "warnings", label: "Warnings" }]} rows={page.records.map((item) => ({ row: item.ordinal, decision: item.included ? "Included" : "Excluded", record: <span className="ro-wrap-anywhere">{item.sourceRecordRevisionId ?? "None"}</span>, comparison: item.comparison.replaceAll("-", " "), warnings: item.warnings.join(", ") || "None reported" }))} rowKey={(row) => String(row.row)} /> : null}
    <nav className="ro-action-row" aria-label="Import manifest pages"><Button disabled={loading || cursors.length < 2} onClick={() => void load(cursors.slice(0, -1))}>Previous manifest records</Button><Button disabled={loading || !page || page.complete} onClick={() => page && void load([...cursors, page.nextAfter])}>Next manifest records</Button></nav>
  </section>;
}
