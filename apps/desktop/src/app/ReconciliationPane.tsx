import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { createCoreApiClient, type CandidateExplanation, type CandidatePage, type ReconciliationBatchStatus,
  type ReconciliationInspection, type ReviewContext } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import { ReconciliationReviewPane } from "./ReconciliationReviewPane";

type Client = ReturnType<typeof createCoreApiClient>;
const active = (status: ReconciliationBatchStatus | null): boolean => Boolean(status && !["succeeded", "failed", "cancelled"].includes(status.state));

export function ReconciliationPane({ root, projectId, client, announce, headingRef }: {
  readonly root: string; readonly projectId: string; readonly client: Client; readonly announce: (message: string) => void;
  readonly headingRef: RefObject<HTMLHeadingElement | null>;
}): ReactNode {
  const [requestId, setRequestId] = useState<string | null>(null), [status, setStatus] = useState<ReconciliationBatchStatus | null>(null);
  const [page, setPage] = useState<CandidatePage | null>(null), [cursors, setCursors] = useState<readonly number[]>([0]);
  const [pending, setPending] = useState<"status" | "action" | null>(null), [failure, setFailure] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ candidate: CandidateExplanation; inspections: readonly ReconciliationInspection[]; context: ReviewContext } | null>(null);
  const live = useRef(true), generation = useRef(0), pendingRef = useRef<"status" | "action" | null>(null), lastState = useRef<string | null>(null);
  const compareButton = useRef<HTMLButtonElement | null>(null);
  const lastCandidate = useRef<string | null>(null), restoreFocus = useRef(false);
  const current = (ticket: number): boolean => live.current && generation.current === ticket;
  const address = useMemo(() => ({ root }), [root]);
  useEffect(() => { live.current = true; return () => { live.current = false; generation.current += 1; }; }, []);

  async function perform(kind: "status" | "action", action: (ticket: number) => Promise<void>): Promise<void> {
    if (pendingRef.current === "action" || kind === "status" && pendingRef.current !== null) return;
    const ticket = ++generation.current;
    pendingRef.current = kind; setPending(kind); setFailure(null);
    try { await action(ticket); }
    catch {
      if (current(ticket)) {
        setPage(null); setSelected(null);
        setFailure("Current reconciliation evidence could not be read. Check accepted Intent and source rights, then refresh status or resume the same saved request. A missing reply does not mean publication failed.");
        announce("Reconciliation needs attention. The last reply was not confirmed.");
      }
    } finally { if (current(ticket)) { pendingRef.current = null; setPending(null); } }
  }
  function accept(next: ReconciliationBatchStatus, ticket: number): boolean {
    if (!current(ticket)) return false;
    setStatus(next);
    if (lastState.current !== next.state) { lastState.current = next.state; announce(next.state === "succeeded" ? "Candidate generation completed. Review suggestions before making an identity decision." : `Reconciliation ${next.state.replaceAll("-", " ")}.`); }
    return true;
  }
  async function candidatePage(next: ReconciliationBatchStatus, nextCursors: readonly number[], ticket: number): Promise<void> {
    if (!next.setRevisionId) return;
    const result = await client.inspectScholarlyDuplicateCandidates({ root, setRevisionId: next.setRevisionId, after: nextCursors.at(-1) ?? 0, limit: 25 });
    if (result.projectId !== projectId || result.requestId !== next.requestId) throw new Error("RO-CORE-RESPONSE-INVALID");
    if (current(ticket)) { setPage(result); setCursors(nextCursors); }
  }
  async function schedule(saved: string | null): Promise<void> {
    await perform("action", async (ticket) => {
      let request = saved;
      if (!request) {
        const prepared = await client.prepareScholarlyReconciliationBatch(address);
        if (!current(ticket)) return;
        request = prepared.requestId; setRequestId(request); setStatus(null); setPage(null); setSelected(null);
      }
      const next = await client.scheduleScholarlyReconciliationBatch({ root, requestId: request });
      if (accept(next, ticket)) await candidatePage(next, [0], ticket);
    });
  }
  async function refresh(nextCursors = cursors): Promise<void> {
    if (!status) return;
    await perform("status", async (ticket) => {
      const next = await client.inspectScholarlyReconciliationBatch({ root, requestId: status.requestId, jobId: status.jobId });
      if (accept(next, ticket)) await candidatePage(next, nextCursors, ticket);
    });
  }
  async function cancel(): Promise<void> {
    if (!status || !active(status)) return;
    await perform("action", async (ticket) => {
      const next = await client.cancelScholarlyReconciliationBatch({ root, requestId: status.requestId, jobId: status.jobId });
      if (accept(next, ticket)) await candidatePage(next, [0], ticket);
    });
  }
  useEffect(() => {
    if (pending || failure || !active(status)) return;
    const timer = globalThis.setTimeout(() => void refresh(), 1500);
    return () => globalThis.clearTimeout(timer);
  }, [status, pending, failure]);

  async function compare(candidate: CandidateExplanation): Promise<void> {
    await perform("action", async (ticket) => {
      const inspections = await Promise.all([candidate.left, candidate.right].map((assertionRevisionId) => client.inspectScholarlyReconciliation({ root, assertionRevisionId })));
      if (inspections.some((inspection) => inspection.assertion.projectId !== projectId)) throw new Error("RO-CORE-RESPONSE-INVALID");
      const workIds = [...new Set(inspections.flatMap((inspection) => inspection.canonicalWork ? [inspection.canonicalWork.workId] : []))].sort();
      const unassignedAssertionRevisionIds = inspections.filter((inspection) => !inspection.canonicalWork).map((inspection) => inspection.result.assertionRevisionId).sort();
      const context = await client.inspectScholarlyReviewContext({ root, workIds, unassignedAssertionRevisionIds });
      if (context.sources.some((source) => source.assertion.projectId !== projectId)) throw new Error("RO-CORE-RESPONSE-INVALID");
      if (current(ticket)) setSelected({ candidate, inspections, context });
    });
  }
  function closeComparison(): void {
    restoreFocus.current = true;
    setSelected(null);
  }
  useEffect(() => {
    if (selected || pending !== null || !restoreFocus.current) return;
    restoreFocus.current = false;
    globalThis.requestAnimationFrame(() => { if (live.current) (compareButton.current?.isConnected ? compareButton.current : headingRef.current)?.focus(); });
  }, [selected, pending, page, headingRef]);
  return <section className="ro-stack" aria-label="Duplicate and canonical-work review">
    <Panel title="Duplicate and canonical-work review"><div className="ro-stack" aria-busy={pending !== null}>
      <h2 ref={headingRef} tabIndex={-1} className="ro-typography ro-typography--section-title">Review accepted source records</h2>
      <p>Generate a local candidate set from accepted imports and retained scholarly-source pages. Exact compatible identifiers may link a Work; ambiguous similarity always requires a researcher decision. No external lookup is performed.</p>
      {failure ? <Notification tone="danger" title="Reconciliation unavailable">{failure}</Notification> : null}
      {pending ? <p role="status">{pending === "status" ? "Reading saved reconciliation status…" : "Checking current source authority…"}</p> : null}
      {status ? <StatusBadge>{status.state === "succeeded" ? "Candidate set published" : status.state.replaceAll("-", " ")}</StatusBadge> : <p>No candidate set opened in this view. Generating one preserves earlier source records, candidate sets and human decisions.</p>}
      {status?.diagnosticCode ? <p>Diagnostic: {status.diagnosticCode}</p> : null}
      {status?.state === "failed" || status?.state === "cancelled" ? <p>This job has stopped. Its history remains in Task Center. A new generation captures current accepted sources and current authority.</p> : null}
      <div className="ro-action-row">
        <Button tone="primary" disabled={pending !== null || active(status) || selected !== null} onClick={() => void schedule(null)}>Generate duplicate candidates</Button>
        {requestId && !status ? <Button disabled={pending !== null} onClick={() => void schedule(requestId)}>Resume saved generation request</Button> : null}
        {status ? <Button disabled={pending !== null || selected !== null} onClick={() => void refresh()}>Refresh reconciliation status</Button> : null}
        {active(status) ? <Button disabled={pending === "action"} onClick={() => void cancel()}>Cancel candidate generation</Button> : null}
      </div>
      {page ? <>
        <p>{page.recordCount} source assertion(s) in this snapshot; {page.candidateCount} candidate pair(s) from {page.comparedPairs} compared pair(s). Missing fields stay missing, and scores are not acceptance probabilities.</p>
        {page.inventoryState === "changed" ? <Notification tone="warning" title="Accepted source inventory changed">This historical candidate set excludes changes after its frozen inventory boundary. Generate a new set to review current inventory; existing scores remain unchanged.</Notification> : null}
        {page.membershipState === "changed" ? <Notification tone="warning" title="Work membership changed">These scores describe the original source comparison. Opening a comparison checks current Work membership and decision evidence again.</Notification> : null}
        {page.dependencyState === "requires-review" ? <Notification tone="warning" title="Dependent evidence requires review">A material dependency changed or its impact check is pending. Inspect current evidence and Audit &amp; Lineage before relying on downstream results.</Notification> : null}
        <details><summary>Candidate set and inventory provenance</summary><dl className="import-rights">{Object.entries({ "Candidate revision": page.setRevisionId, "Frozen inventory": page.inventorySha256, "Current inventory": page.currentInventorySha256 }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="ro-wrap-anywhere">{value}</dd></div>)}</dl></details>
        {page.candidateCount === 0 ? <p>No candidate pair met the configured ranking threshold in this bounded snapshot. This does not establish that the corpus has no duplicates.</p> : <DataTable caption="Duplicate candidates — historical comparison, current page" columns={[{ id: "pair", label: "Candidate" }, { id: "score", label: "Score / 10,000" }, { id: "signals", label: "Signals and conflicts" }, { id: "review", label: "Researcher review" }]}
          rows={page.items.map((candidate, index) => ({ pair: page.after + index + 1, score: candidate.score, signals: candidate.flags.join(", ") || "No conflict flag reported",
            review: <Button ref={(button) => { if (lastCandidate.current === `${candidate.left}/${candidate.right}`) compareButton.current = button; }} disabled={pending !== null || selected !== null} onClick={(event) => { lastCandidate.current = `${candidate.left}/${candidate.right}`; compareButton.current = event.currentTarget; void compare(candidate); }}>Compare candidate {page.after + index + 1}</Button> }))} rowKey={(row) => String(row.pair)} />}
        <nav className="ro-action-row" aria-label="Duplicate candidate pages"><Button disabled={pending !== null || selected !== null || cursors.length < 2} onClick={() => void refresh(cursors.slice(0, -1))}>Previous candidates</Button><Button disabled={pending !== null || selected !== null || page.nextAfter === null} onClick={() => page.nextAfter !== null && void refresh([...cursors, page.nextAfter])}>Next candidates</Button></nav>
      </> : null}
    </div></Panel>
    {selected ? <ReconciliationReviewPane key={`${selected.candidate.left}/${selected.candidate.right}`} root={root} projectId={projectId} client={client} initial={selected.context} inspections={selected.inspections} candidate={selected.candidate} announce={announce} onClose={closeComparison} onCommitted={() => { void refresh(); }}
      onDenied={() => { setPage(null); setSelected(null); setFailure("Current source or project access was denied. Check Intent and source rights before reopening reconciliation evidence."); restoreFocus.current = true; }} /> : null}
  </section>;
}
