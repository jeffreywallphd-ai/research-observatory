import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type ProjectProjection,
  type ProvenanceLineageNode,
  type ProvenanceLineagePage,
  type ProvenanceLineageRequest,
} from "@research-observatory/contracts/core-api";
import { Button, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PAGE_SIZE = 50;
const MAX_DEPTH = 8;

type LineageDirection = ProvenanceLineageRequest["direction"];
type LineageNodeRole =
  | "Selected output"
  | "Prior same-entity revision"
  | "Upstream source or alternate"
  | "Later same-entity revision"
  | "Downstream output"
  | "Source use"
  | "Invalidation or stale fact";

export interface AuditLineageWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialRevisionId?: string;
  readonly initialTrace?: ProvenanceLineagePage | null;
}

export function lineageAvailability(project: ProjectProjection | null): {
  readonly available: boolean;
  readonly reason: string | null;
} {
  if (!project) return { available: false, reason: "Open a local project to trace lineage." };
  if (!project.open || project.accessMode === "closed") {
    return { available: false, reason: "Open this project before tracing lineage." };
  }
  return { available: true, reason: null };
}

export function provenanceLineageRequest(
  project: ProjectProjection,
  revisionId: string,
  direction: LineageDirection,
  cursor: number,
): ProvenanceLineageRequest {
  if (!lineageAvailability(project).available || !UUID_V7.test(revisionId)
    || (direction !== "ancestors" && direction !== "descendants")
    || !Number.isInteger(cursor) || cursor < 0 || cursor > 10_000) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return {
    root: project.root,
    revisionId,
    direction,
    cursor,
    pageSize: PAGE_SIZE,
    maxDepth: MAX_DEPTH,
  };
}

export function continuationLineageRequest(
  accepted: ProvenanceLineageRequest,
  cursor: number,
): ProvenanceLineageRequest {
  if (accepted.cursor !== 0 || !Number.isInteger(cursor) || cursor <= 0 || cursor > 10_000) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return { ...accepted, cursor };
}

export async function loadLineagePage(
  client: ReturnType<typeof createCoreApiClient>,
  project: ProjectProjection,
  revisionId: string,
  direction: LineageDirection,
  cursor: number,
  accepted: ProvenanceLineageRequest | null = null,
): Promise<{ readonly request: ProvenanceLineageRequest; readonly page: ProvenanceLineagePage }> {
  if ((accepted === null && cursor !== 0) || (accepted !== null && cursor === 0)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  const request = accepted === null
    ? provenanceLineageRequest(project, revisionId, direction, cursor)
    : continuationLineageRequest(accepted, cursor);
  return { request, page: await client.lineage(request) };
}

export function lineageNodeRole(
  node: ProvenanceLineageNode,
  selected: ProvenanceLineageNode | undefined,
  direction: LineageDirection,
): LineageNodeRole {
  if (node.relationType === "wasInvalidatedBy") return "Invalidation or stale fact";
  if (node.relationType === "used") return "Source use";
  if (node.depth === 0 && node.revisionId === selected?.revisionId) return "Selected output";
  if (direction === "ancestors") {
    return selected && node.entityId === selected.entityId
      ? "Prior same-entity revision"
      : "Upstream source or alternate";
  }
  return selected && node.entityId === selected.entityId
    ? "Later same-entity revision"
    : "Downstream output";
}

function lineageNodeState(node: ProvenanceLineageNode): string {
  if (node.relationType === "wasInvalidatedBy" || node.knowledgeStatus === "stale") return "Stale or invalidated";
  if (node.depth === 0) return "Current selection";
  return "Historical";
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) {
    return {
      title: `${error.problem.title} (${error.problem.code})`,
      message: `${error.problem.detail} ${error.problem.remediation}`,
    };
  }
  return {
    title: "RO-CORE-LINEAGE-TRACE-FAILED",
    message: "The exact lineage trace could not be verified. Check local Core status and the revision ID, then retry.",
  };
}

export function mergeLineagePage(
  current: ProvenanceLineagePage,
  next: ProvenanceLineagePage,
  requestedCursor: number,
): ProvenanceLineagePage {
  if (current.revisionId !== next.revisionId || current.direction !== next.direction
    || current.nextCursor !== requestedCursor
    || (next.nextCursor !== null && (
      next.items.length === 0
      || next.nextCursor <= requestedCursor
      || next.nextCursor !== requestedCursor + next.items.length
    ))
    || current.exportAllowed !== (current.exportDenialReason === null)
    || next.exportAllowed !== (next.exportDenialReason === null)) {
    throw new Error("RO-CORE-RESPONSE-INVALID");
  }
  const identities = new Set(current.items.map((item) => item.factId));
  const lastDepth = current.items.at(-1)?.depth ?? 0;
  if (next.items.some((item) => identities.has(item.factId))
    || (next.items[0]?.depth ?? lastDepth) < lastDepth) throw new Error("RO-CORE-RESPONSE-INVALID");
  const items = [...current.items, ...next.items];
  const missingRevisionIds = [...new Set([...current.missingRevisionIds, ...next.missingRevisionIds])];
  const legacyEventCount = Math.max(current.legacyEventCount, next.legacyEventCount);
  const integrityReview = current.integrityState === "integrity-review"
    || next.integrityState === "integrity-review"
    || current.exportDenialReason === "integrity-review"
    || next.exportDenialReason === "integrity-review"
    || missingRevisionIds.length > 0
    || legacyEventCount > 0;
  const rightsRestricted = current.exportDenialReason === "rights-restricted"
    || next.exportDenialReason === "rights-restricted"
    || items.some((item) => item.rightsStatus === "denied" || item.rightsStatus === "unknown");
  const exportDenialReason = integrityReview
    ? "integrity-review"
    : rightsRestricted
      ? "rights-restricted"
      : null;
  return {
    ...next,
    items,
    missingRevisionIds,
    integrityState: integrityReview ? "integrity-review" : "verified",
    legacyEventCount,
    exportAllowed: exportDenialReason === null,
    exportDenialReason,
  };
}

export function lineageManifestReady(
  trace: ProvenanceLineagePage,
  acceptedQuery: ProvenanceLineageRequest | null,
): boolean {
  return acceptedQuery !== null
    && acceptedQuery.cursor === 0
    && acceptedQuery.revisionId === trace.revisionId
    && acceptedQuery.direction === trace.direction
    && trace.nextCursor === null
    && trace.integrityState === "verified"
    && trace.missingRevisionIds.length === 0
    && trace.legacyEventCount === 0
    && trace.exportAllowed
    && trace.exportDenialReason === null
    && !trace.items.some((item) => item.rightsStatus === "denied" || item.rightsStatus === "unknown");
}

export function exportLineageManifest(
  trace: ProvenanceLineagePage,
  acceptedQuery: ProvenanceLineageRequest | null,
): string {
  if (acceptedQuery === null || !lineageManifestReady(trace, acceptedQuery)) {
    throw new Error("RO-CORE-EXPORT-DENIED");
  }
  return JSON.stringify({
    schemaVersion: "1.0",
    manifestType: "content-minimized-lineage",
    completeness: "complete",
    revisionId: trace.revisionId,
    direction: trace.direction,
    acceptedBounds: {
      maxDepth: acceptedQuery.maxDepth,
      pageSize: acceptedQuery.pageSize,
      startCursor: 0,
      terminalCursor: trace.items.length,
    },
    integrityState: trace.integrityState,
    redaction: "research-content-and-raw-prompts-omitted",
    egressDecision: "local-file-only",
    items: trace.items,
  }, null, 2);
}

export function AuditLineageWorkspace({
  project,
  announce,
  transport = packagedProjectTransport,
  initialRevisionId = "",
  initialTrace = null,
}: AuditLineageWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const availability = lineageAvailability(project);
  const [revisionId, setRevisionId] = useState(initialRevisionId);
  const [direction, setDirection] = useState<LineageDirection>(initialTrace?.direction ?? "ancestors");
  const [trace, setTrace] = useState<ProvenanceLineagePage | null>(initialTrace);
  const [traceQuery, setTraceQuery] = useState<ProvenanceLineageRequest | null>(
    initialTrace && project ? provenanceLineageRequest(project, initialTrace.revisionId, initialTrace.direction, 0) : null,
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  useEffect(() => {
    setRevisionId("");
    setTrace(null);
    setTraceQuery(null);
    setFailure(null);
  }, [project?.projectId]);

  const runTrace = async (cursor: number, append: boolean): Promise<void> => {
    if (!project) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = await loadLineagePage(
        client,
        project,
        revisionId,
        direction,
        cursor,
        append ? traceQuery : null,
      );
      const request = result.request;
      const next = result.page;
      setTrace((current) => append && current ? mergeLineagePage(current, next, cursor) : next);
      if (!append) setTraceQuery({ ...request, cursor: 0 });
      announce(append ? "More lineage records loaded." : "Exact output lineage traced.");
    } catch (error) {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Lineage trace did not complete. ${safe.title}`);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void runTrace(0, false);
  };
  const selected = trace?.items.find((item) => item.depth === 0);
  const validRevision = UUID_V7.test(revisionId);
  const humanDecisions = trace?.items.filter(
    (item) => item.entityKind === "decision" && item.agentType === "human",
  ) ?? [];
  const manifestReady = trace ? lineageManifestReady(trace, traceQuery) : false;
  const downloadManifest = (): void => {
    if (!trace) return;
    try {
      const payload = exportLineageManifest(trace, traceQuery);
      const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `lineage-${trace.revisionId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      announce("Content-minimized lineage manifest exported locally.");
    } catch {
      announce("Lineage export remains denied by integrity or rights policy.");
    }
  };

  return (
    <section className="audit-lineage-workspace" aria-labelledby="audit-lineage-title" data-audit-lineage-workspace>
      <div className="page-header">
        <Typography id="audit-lineage-title" as="h1" variant="page-title">Audit &amp; lineage</Typography>
        <Typography className="page-subtitle">
          Trace an exact output revision through content-free source, transformation, configuration, actor, and audit identities.
        </Typography>
      </div>

      {!availability.available ? (
        <Panel title="Lineage unavailable">
          <p role="status">{availability.reason}</p>
          <p>No project content or identifiers are requested while this boundary is unavailable.</p>
        </Panel>
      ) : (
        <form className="lineage-trace-form" onSubmit={submit}>
          <label htmlFor="lineage-revision-id">Exact output revision ID</label>
          <input
            id="lineage-revision-id"
            value={revisionId}
            onChange={(event) => setRevisionId(event.currentTarget.value.trim().toLowerCase())}
            pattern="[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
            maxLength={36}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="lineage-revision-help"
            required
          />
          <span id="lineage-revision-help" className="field-note">
            Use the immutable UUIDv7 attached to the synthesis sentence, evidence field, claim, or other output.
          </span>
          <label htmlFor="lineage-direction">Trace direction</label>
          <select
            id="lineage-direction"
            value={direction}
            onChange={(event) => setDirection(event.currentTarget.value as LineageDirection)}
          >
            <option value="ancestors">Sources and prior transformations</option>
            <option value="descendants">Downstream outputs and decisions</option>
          </select>
          <Button type="submit" tone="primary" disabled={busy || !validRevision} data-trace-lineage>
            {busy ? "Tracing…" : "Trace lineage"}
          </Button>
        </form>
      )}

      {failure ? (
        <div className="lineage-notice lineage-notice--danger" role="alert">
          <strong>{failure.title}</strong>
          <span>{failure.message}</span>
        </div>
      ) : null}

      {trace ? (
        <>
          <div className="lineage-summary-grid">
            <Panel title="Output identity">
              <dl className="lineage-identity">
                <div><dt>Revision</dt><dd><code>{trace.revisionId}</code></dd></div>
                <div><dt>Direction</dt><dd>{trace.direction}</dd></div>
                <div><dt>Records shown</dt><dd>{trace.items.length}</dd></div>
              </dl>
            </Panel>
            <Panel title="Provenance completeness">
              <StatusBadge tone={trace.integrityState === "verified" ? "success" : "warning"}>
                {trace.integrityState === "verified" ? "Verified" : "Integrity review required"}
              </StatusBadge>
              <p>{trace.legacyEventCount} legacy {trace.legacyEventCount === 1 ? "event" : "events"} remain visibly identified.</p>
            </Panel>
          </div>

          {trace.integrityState === "integrity-review" ? (
            <div className="lineage-notice" role="alert">
              <strong>Integrity review required</strong>
              <span>Keep this trace available for inspection, but do not rely on it for export or claim use until repaired.</span>
            </div>
          ) : null}

          {trace.missingRevisionIds.length ? (
            <div className="lineage-notice" role="alert">
              <strong>Referenced revisions are missing</strong>
              <ul>{trace.missingRevisionIds.map((item) => <li key={item}><code>{item}</code></li>)}</ul>
            </div>
          ) : null}

          <section className="lineage-results" aria-labelledby="lineage-results-title">
            <div className="lineage-results-heading">
              <Typography id="lineage-results-title" as="h2" variant="section-title">Lineage trace</Typography>
              <span>{trace.items.length === 0 ? "No canonical lineage record found." : "All returned branches remain visible."}</span>
            </div>
            {trace.items.length ? (
              <div className="lineage-table-scroll">
                <table>
                  <caption>Exact, content-free provenance facts discovered by the wasDerivedFrom {trace.direction} traversal for the selected output revision</caption>
                  <thead><tr><th scope="col">Relation and state</th><th scope="col">Entity revision</th><th scope="col">Transformation and configuration</th><th scope="col">Responsible actor</th><th scope="col">Audit event</th></tr></thead>
                  <tbody>
                    {trace.items.map((node) => (
                      <tr key={node.factId}>
                        <td><strong>{lineageNodeRole(node, selected, trace.direction)}</strong><span>{lineageNodeState(node)} · depth {node.depth}</span></td>
                        <td><span>{node.entityKind} · {node.entityDirection}</span><code>{node.entityId}</code><code>{node.revisionId}</code>{node.relatedRevisionId ? <code>{node.relatedRevisionId}</code> : null}</td>
                        <td><span>{node.activityType} · {node.activityStatus}</span><code>{node.activityId}</code><span>{node.configurationId} · {node.configurationVersion}</span><code>{node.configurationHash}</code></td>
                        <td><span>{node.agentType} · {node.agentRole}</span><code>{node.agentId}</code></td>
                        <td><span>{node.relationType} · {node.eventType}</span><code>{node.eventId}</code><time dateTime={node.occurredAt}>{node.occurredAt}</time></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {trace.nextCursor !== null ? (
              <Button disabled={busy} onClick={() => { void runTrace(trace.nextCursor ?? 0, true); }}>
                {busy ? "Loading…" : "Load more lineage"}
              </Button>
            ) : null}
          </section>

          <section className="lineage-governed-region" aria-labelledby="lineage-audit-events-title" data-audit-events>
            <Typography id="lineage-audit-events-title" as="h2" variant="section-title">Audit events</Typography>
            <p>Content-minimized security, model, scholarly, rights, and invalidation facts returned by Core.</p>
            <ol>{trace.items.map((node) => <li key={`audit:${node.factId}`}><code>{node.eventId}</code> {node.eventType} · {node.activityStatus} · <time dateTime={node.occurredAt}>{node.occurredAt}</time></li>)}</ol>
          </section>

          <section className="lineage-governed-region" aria-labelledby="lineage-rights-title" data-rights-egress>
            <Typography id="lineage-rights-title" as="h2" variant="section-title">Rights &amp; egress decisions</Typography>
            <ul>{trace.items.map((node) => <li key={`rights:${node.factId}`}><code>{node.revisionId}</code> · rights {node.rightsStatus}</li>)}</ul>
            <p>Local manifest export: {manifestReady ? "allowed" : trace.exportAllowed && trace.nextCursor !== null ? "pending (load every lineage page)" : `denied (${trace.exportDenialReason})`}. This trace does not authorize remote egress.</p>
          </section>

          <section className="lineage-governed-region" aria-labelledby="lineage-decisions-title" data-human-decisions>
            <Typography id="lineage-decisions-title" as="h2" variant="section-title">Human decisions</Typography>
            {humanDecisions.length ? <ul>{humanDecisions.map((node) => <li key={`decision:${node.factId}`}>{node.agentRole} · <code>{node.agentId}</code> · {node.eventType}</li>)}</ul> : <p>No human decision is recorded in this trace.</p>}
          </section>

          <section className="lineage-governed-region" aria-labelledby="lineage-export-title" data-export-manifest>
            <Typography id="lineage-export-title" as="h2" variant="section-title">Exportable manifest</Typography>
            <p>Local JSON omits research content, raw prompts, secrets, and hidden rationale. Exact identities and policy states remain.</p>
            <Button onClick={downloadManifest} disabled={!manifestReady}>Export content-minimized manifest</Button>
            {trace.exportAllowed && trace.nextCursor !== null
              ? <p role="status">Load every lineage page before exporting the complete manifest.</p>
              : !manifestReady
                ? <p role="alert">Export denied: {trace.exportDenialReason === "integrity-review" ? "integrity review is required" : "one or more lineage targets are rights-restricted"}.</p>
                : null}
          </section>

          <div className="lineage-transparency-note">
            <strong>Useful transparency</strong>
            <p>
              This view exposes exact sources, transformations, configuration or prompt-version identities, model or human roles,
              alternatives, decisions, and stale state—not hidden model rationale or chain-of-thought. Raw prompts and research text
              remain behind their governed content and rights boundaries.
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}
