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
  | "Downstream output";

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

export function lineageNodeRole(
  node: ProvenanceLineageNode,
  selected: ProvenanceLineageNode | undefined,
  direction: LineageDirection,
): LineageNodeRole {
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
  if (node.eventType.includes(".invalidated.")) return "Stale or invalidated";
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

function appendPage(current: ProvenanceLineagePage, next: ProvenanceLineagePage): ProvenanceLineagePage {
  if (current.revisionId !== next.revisionId || current.direction !== next.direction) return next;
  return {
    ...next,
    items: [...current.items, ...next.items],
    missingRevisionIds: [...new Set([...current.missingRevisionIds, ...next.missingRevisionIds])],
    integrityState: current.integrityState === "integrity-review" ? "integrity-review" : next.integrityState,
    legacyEventCount: Math.max(current.legacyEventCount, next.legacyEventCount),
  };
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
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  useEffect(() => {
    setRevisionId("");
    setTrace(null);
    setFailure(null);
  }, [project?.projectId]);

  const runTrace = async (cursor: number, append: boolean): Promise<void> => {
    if (!project) return;
    setBusy(true);
    setFailure(null);
    try {
      const next = await client.lineage(provenanceLineageRequest(project, revisionId, direction, cursor));
      setTrace((current) => append && current ? appendPage(current, next) : next);
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
                  <caption>Exact, content-free wasDerivedFrom {trace.direction} traversal for the selected output revision</caption>
                  <thead><tr><th scope="col">Relation and state</th><th scope="col">Entity revision</th><th scope="col">Transformation and configuration</th><th scope="col">Responsible actor</th><th scope="col">Audit event</th></tr></thead>
                  <tbody>
                    {trace.items.map((node) => (
                      <tr key={`${node.eventId}:${node.revisionId}`}>
                        <td><strong>{lineageNodeRole(node, selected, trace.direction)}</strong><span>{lineageNodeState(node)} · depth {node.depth}</span></td>
                        <td><span>{node.entityKind}</span><code>{node.entityId}</code><code>{node.revisionId}</code></td>
                        <td><span>{node.activityType} · {node.activityStatus}</span><code>{node.activityId}</code><span>{node.configurationId} · {node.configurationVersion}</span><code>{node.configurationHash}</code></td>
                        <td><span>{node.agentType} · {node.agentRole}</span><code>{node.agentId}</code></td>
                        <td><span>{node.eventType}</span><code>{node.eventId}</code><time dateTime={node.occurredAt}>{node.occurredAt}</time></td>
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
