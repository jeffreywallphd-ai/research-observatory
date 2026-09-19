import { useEffect, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, type ImportDuplicateGroups, type ImportDuplicateMembers, type ImportSummaryStatus, type RecordSummary } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";

type Reason = "raw" | "doi";
type ImportClient = ReturnType<typeof createCoreApiClient>;
const active = (status: ImportSummaryStatus | null): boolean => Boolean(status?.jobState && !["succeeded", "failed", "cancelled"].includes(status.jobState));
const statusLabel = (status: ImportSummaryStatus): string => status.counts ? "Complete for this draft" : status.jobState ? `Calculation ${status.jobState.replaceAll("-", " ")}` : "Not calculated";

export function ImportSummaryPane({ root, previewId, revision, client, disabled, announce, inspect, select, failureText }: {
  readonly root: string; readonly previewId: string; readonly revision: number; readonly client: ImportClient;
  readonly disabled: boolean; readonly announce: (message: string) => void;
  readonly inspect: (record: RecordSummary) => void; readonly select: (records: readonly RecordSummary[]) => void;
  readonly failureText: (error: unknown) => string;
}): ReactNode {
  const [status, setStatus] = useState<ImportSummaryStatus | null>(null);
  const [groups, setGroups] = useState<ImportDuplicateGroups | null>(null);
  const [members, setMembers] = useState<ImportDuplicateMembers | null>(null);
  const [reason, setReason] = useState<Reason>("doi");
  const [groupCursors, setGroupCursors] = useState<readonly (string | null)[]>([null]);
  const [memberCursors, setMemberCursors] = useState<readonly number[]>([0]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const live = useRef(true), generation = useRef(0);
  const lastStatusLabel = useRef<string | null>(null);
  const address = { root, previewId, revision };

  async function perform(ticket: number, action: () => Promise<void>): Promise<void> {
    setLoading(true); setFailure(null);
    try { await action(); }
    catch (error) {
      if (live.current && ticket === generation.current) { setStatus(null); setGroups(null); setMembers(null); setFailure(failureText(error)); }
    } finally { if (live.current && ticket === generation.current) setLoading(false); }
  }
  async function refresh(operation: "read" | "start" | "cancel" = "read"): Promise<void> {
    const ticket = ++generation.current;
    await perform(ticket, async () => {
      const next = operation === "start" ? await client.startImportSummary(address)
        : operation === "cancel" && status?.jobId ? await client.cancelImportSummary({ ...address, jobId: status.jobId })
        : await client.importSummary(address);
      if (!live.current || ticket !== generation.current) return;
      setStatus(next);
      if (next.counts) {
        const page = await client.importDuplicateGroups({ ...address, reason, after: null, limit: 25 });
        if (!live.current || ticket !== generation.current) return;
        setGroups(page); setGroupCursors([null]); setMembers(null);
      }
      const label = statusLabel(next);
      const changed = label !== lastStatusLabel.current;
      lastStatusLabel.current = label;
      if (changed && (next.counts || next.jobState === "failed" || next.jobState === "cancelled")) announce(`Preview summary: ${label}.`);
      else if (operation === "start") announce("Preview summary calculation requested. No canonical records will be changed.");
      else if (operation === "cancel") announce("Summary cancellation requested. The editable preview is retained.");
    });
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

  async function readGroups(nextReason: Reason, cursors: readonly (string | null)[]): Promise<void> {
    const ticket = ++generation.current;
    await perform(ticket, async () => {
      const page = await client.importDuplicateGroups({ ...address, reason: nextReason, after: cursors.at(-1) ?? null, limit: 25 });
      if (!live.current || ticket !== generation.current) return;
      setReason(nextReason); setGroups(page); setGroupCursors(cursors); setMembers(null);
    });
  }
  async function readMembers(groupKey: string, cursors: readonly number[]): Promise<void> {
    const ticket = ++generation.current;
    await perform(ticket, async () => {
      const page = await client.importDuplicateMembers({ ...address, reason, groupKey, after: cursors.at(-1) ?? 0, limit: 25 });
      if (!live.current || ticket !== generation.current) return;
      setMembers(page); setMemberCursors(cursors);
    });
  }
  const unavailable = disabled || loading;
  const counts = status?.counts;
  return <Panel title="Preview summary">
    <div className="ro-stack" aria-label="Import summary and duplicate candidates" aria-busy={loading}>
      <p>Revision {revision}. This is a summary of this import only, not a corpus merge.</p>
      {failure ? <Notification tone="danger" title="Summary unavailable">{failure}</Notification> : null}
      {loading ? <p role="status">Reading summary status…</p> : null}
      {status ? <StatusBadge>{statusLabel(status)}</StatusBadge> : null}
      {!counts ? <p>Counts and duplicate candidates are unavailable until calculation completes. Missing results are not zero.</p> : null}
      {status?.diagnosticCode ? <p>Diagnostic: {status.diagnosticCode}. Review the job in Task Center before retrying. Retry does not change the saved draft or permissions.</p> : null}
      {status?.jobState === "cancelled" ? <p>The summary was cancelled; your preview is intact. To calculate the same draft again, retry its job in Task Center.</p> : null}
      <div className="ro-action-row">
        <Button disabled={unavailable || Boolean(status?.jobId)} onClick={() => void refresh("start")}>Calculate preview summary</Button>
        <Button disabled={unavailable} onClick={() => void refresh()}>Refresh summary status</Button>
        {active(status) ? <Button disabled={unavailable} onClick={() => void refresh("cancel")}>Cancel summary calculation</Button> : null}
      </div>
      {counts ? <>
        <dl className="import-rights">
          <div><dt>Included records</dt><dd>{counts.includedRecords.toLocaleString()}</dd></div>
          <div><dt>Excluded records</dt><dd>{counts.excludedRecords.toLocaleString()}</dd></div>
          <div><dt>Context rows</dt><dd>{counts.contextRows.toLocaleString()} headers/directives</dd></div>
          <div><dt>Malformed rows</dt><dd>{counts.malformedRows.toLocaleString()}</dd></div>
          <div><dt>Rows with warnings</dt><dd>{counts.warningRows.toLocaleString()} ({counts.warningCount.toLocaleString()} warnings)</dd></div>
          <div><dt>Missing DOI</dt><dd>{(counts.includedRecords - counts.coverage.doi).toLocaleString()} included records</dd></div>
        </dl>
        <DataTable caption="Field coverage among included parsed records" columns={[{ id: "field", label: "Field" }, { id: "coverage", label: "Records with a usable value" }]} rows={Object.entries(counts.coverage).map(([field, value]) => ({ field, coverage: `${value.toLocaleString()} of ${counts.includedRecords.toLocaleString()}` }))} rowKey={(row) => String(row.field)} />
        <p>{counts.includedRecords.toLocaleString()} included records are ready for commit review. Canonical additions and re-import effects are determined at commit; work/version reconciliation follows separately.</p>
        <p>{counts.candidateRecords.toLocaleString()} included records have possible duplicates. Candidates share identical original record bytes or a unique normalized DOI. Overlapping reasons count each record once. No works have been merged.</p>
        <div className="ro-action-row" aria-label="Duplicate candidate reason">
          <Button disabled={unavailable} aria-pressed={reason === "doi"} onClick={() => void readGroups("doi", [null])}>Same DOI ({counts.doiDuplicateGroups})</Button>
          <Button disabled={unavailable} aria-pressed={reason === "raw"} onClick={() => void readGroups("raw", [null])}>Identical source bytes ({counts.rawDuplicateGroups})</Button>
        </div>
        {groups?.groups.length === 0 ? <p>No candidate groups for this reason in this draft.</p> : null}
        {groups?.groups.length ? <DataTable caption="Possible duplicate groups — current page" columns={[{ id: "group", label: "Group" }, { id: "count", label: "Included records" }, { id: "review", label: "Review" }]} rows={groups.groups.map((group) => ({ key: group.groupKey, group: `Starts at row ${group.firstOrdinal}`, count: group.memberCount, review: <Button disabled={unavailable} onClick={() => void readMembers(group.groupKey, [0])}>Review group at row {group.firstOrdinal}</Button> }))} rowKey={(row) => String(row.key)} /> : null}
        <nav className="ro-action-row" aria-label="Duplicate group pages"><Button disabled={unavailable || groupCursors.length < 2} onClick={() => void readGroups(reason, groupCursors.slice(0, -1))}>Previous groups</Button><Button disabled={unavailable || !groups || groups.complete} onClick={() => groups && void readGroups(reason, [...groupCursors, groups.nextAfter])}>Next groups</Button></nav>
        {members ? <>
          <DataTable caption="Candidate records — current group page" columns={[{ id: "record", label: "Record" }, { id: "doi", label: "DOI" }]} rows={members.records.map((record) => ({ key: record.recordKey, record: <Button disabled={unavailable} onClick={() => inspect(record)}>Compare candidate row {record.ordinal}: {record.title?.text ?? "Untitled"}{record.title?.truncated ? "…" : ""}</Button>, doi: record.doi?.text ?? "Not reported" }))} rowKey={(row) => String(row.key)} />
          <div className="ro-action-row"><Button disabled={unavailable || !members.records.length} onClick={() => select(members.records)}>Select this candidate page for editing</Button><span className="field-note">Uses the existing record selection below; up to 100 selected across pages.</span></div>
          <nav className="ro-action-row" aria-label="Candidate record pages"><Button disabled={unavailable || memberCursors.length < 2} onClick={() => void readMembers(members.groupKey, memberCursors.slice(0, -1))}>Previous candidates</Button><Button disabled={unavailable || members.complete} onClick={() => void readMembers(members.groupKey, [...memberCursors, members.nextAfter])}>Next candidates</Button></nav>
        </> : null}
      </> : null}
    </div>
  </Panel>;
}
