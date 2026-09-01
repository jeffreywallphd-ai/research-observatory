import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type ProjectProjection,
  type WorkflowTaskCenterRun,
} from "@research-observatory/contracts/core-api";
import { Button, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

export interface TaskCenterWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialRuns?: readonly WorkflowTaskCenterRun[];
}

type Confirmation =
  | { readonly kind: "cancel" | "retry"; readonly workflow: WorkflowTaskCenterRun; readonly jobId: string }
  | null;

function commandId(): string {
  if (!globalThis.crypto) throw new Error("A system cryptographic random source is required for workflow commands.");
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function safeFailure(error: unknown): string {
  if (error instanceof CoreApiClientError) {
    return `${error.problem.title} (${error.problem.code}). ${error.problem.detail} ${error.problem.remediation}`;
  }
  return "Task Center could not reach the local workflow service. Existing workflow authority was not changed.";
}

function statusTone(state: WorkflowTaskCenterRun["state"]): "neutral" | "info" | "success" | "warning" | "danger" {
  if (state === "succeeded") return "success";
  if (state === "failed" || state === "cancelled") return "danger";
  if (state === "waiting-human" || state === "paused" || state === "cancelling") return "warning";
  return state === "running" ? "info" : "neutral";
}

function progressText(run: WorkflowTaskCenterRun): string {
  const progress = run.progress;
  if (progress.kind !== "quantified" || progress.completedUnits === null || progress.totalUnits === null) {
    return `Progress ${progress.kind.replace("-", " ")} · ${progress.unit}`;
  }
  return `${progress.completedUnits} of ${progress.totalUnits} ${progress.unit}`;
}

export function TaskCenterWorkspace({
  project,
  announce,
  transport = packagedProjectTransport,
  initialRuns,
}: TaskCenterWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const [runs, setRuns] = useState<readonly WorkflowTaskCenterRun[]>(initialRuns ?? []);
  const [selectedId, setSelectedId] = useState<string | null>(initialRuns?.[0]?.workflowRunId ?? null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(initialRuns === undefined);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLButtonElement>(null);
  const selectedWorkflowRef = useRef<HTMLButtonElement>(null);
  const requestGenerationRef = useRef(0);
  const writable = project?.accessMode === "read-write" && project.compatibilityState === "compatible";
  const available = !!project?.open && project.accessMode !== "closed";
  const projectKey = project ? `${project.projectId}\u0000${project.root}` : "";
  const activeProjectKeyRef = useRef(projectKey);
  activeProjectKeyRef.current = projectKey;

  const load = useCallback(async (announceChange = false): Promise<void> => {
    if (!project || !available) return;
    const generation = ++requestGenerationRef.current;
    const requestedProjectKey = projectKey;
    try {
      const page = await client.taskCenter(project.root, 50);
      if (generation !== requestGenerationRef.current || requestedProjectKey !== activeProjectKeyRef.current) return;
      setRuns(page.items);
      setSelectedId((current) => page.items.some((item) => item.workflowRunId === current)
        ? current
        : page.items[0]?.workflowRunId ?? null);
      setFailure(null);
      if (announceChange) announce(`Task Center refreshed. ${page.items.length} workflows available.`);
    } catch (error) {
      if (generation !== requestGenerationRef.current || requestedProjectKey !== activeProjectKeyRef.current) return;
      setFailure(safeFailure(error));
    } finally {
      if (generation === requestGenerationRef.current && requestedProjectKey === activeProjectKeyRef.current) {
        setLoading(false);
      }
    }
  }, [announce, available, client, project, projectKey]);

  useEffect(() => {
    requestGenerationRef.current += 1;
    setRuns(initialRuns ?? []);
    setSelectedId(initialRuns?.[0]?.workflowRunId ?? null);
    setFilter("");
    setFailure(null);
    setConfirmation(null);
    setBusy(false);
    restoreFocusRef.current = null;
    selectedWorkflowRef.current = null;
    if (initialRuns !== undefined || !available) {
      setLoading(false);
      return;
    }
    setLoading(true);
    let disposed = false;
    void load();
    const timer = globalThis.setInterval(() => { if (!disposed) void load(); }, 2_500);
    return () => {
      disposed = true;
      requestGenerationRef.current += 1;
      globalThis.clearInterval(timer);
    };
  }, [available, initialRuns, load, projectKey]);

  useEffect(() => { if (confirmation) cancelRef.current?.focus(); }, [confirmation]);

  if (!project) return <Notification tone="info" title="No project open">Open a local project to inspect durable work.</Notification>;
  if (!available) return <Notification tone="warning" title="Project is offline">Open this project before loading its Task Center.</Notification>;

  const normalized = filter.trim().toLowerCase();
  const visible = runs.filter((run) => !normalized
    || `${run.workflowKey} ${run.state} ${run.jobs.map((job) => job.activityType).join(" ")}`.toLowerCase().includes(normalized));
  const selected = runs.find((run) => run.workflowRunId === selectedId) ?? visible[0] ?? null;

  const replaceRun = (next: WorkflowTaskCenterRun): void => {
    setRuns((current) => {
      const without = current.filter((item) => item.workflowRunId !== next.workflowRunId);
      return [next, ...without];
    });
    setSelectedId(next.workflowRunId);
  };

  const closeConfirmation = (): void => {
    setConfirmation(null);
    globalThis.requestAnimationFrame(() => {
      const trigger = restoreFocusRef.current;
      if (trigger?.isConnected && !trigger.disabled) trigger.focus();
      else selectedWorkflowRef.current?.focus();
    });
  };

  const containConfirmationFocus = (event: KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Escape" && !busy) {
      event.preventDefault();
      closeConfirmation();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const confirmCommand = async (): Promise<void> => {
    const pending = confirmation;
    if (!pending || !project) return;
    const commandProjectKey = projectKey;
    setBusy(true);
    setFailure(null);
    try {
      const next = pending.kind === "cancel"
        ? await client.cancelWorkflowJob(project.root, pending.jobId, pending.workflow)
        : await client.retryWorkflowJob(project.root, pending.jobId, pending.workflow, commandId());
      if (commandProjectKey !== activeProjectKeyRef.current) return;
      replaceRun(next);
      announce(pending.kind === "cancel"
        ? "Cancellation requested. Active work will stop at its next safe point."
        : "Retry created a new continuation bound to the same workflow definition.");
      await load();
      closeConfirmation();
    } catch (error) {
      if (commandProjectKey !== activeProjectKeyRef.current) return;
      const message = safeFailure(error);
      setFailure(message);
      announce(`Task Center command failed. ${message}`);
    } finally {
      if (commandProjectKey === activeProjectKeyRef.current) setBusy(false);
    }
  };

  const decide = async (humanTaskId: string, disposition: "approved" | "rejected" | "deferred" | "not-applicable"): Promise<void> => {
    if (!selected || !project) return;
    const commandProjectKey = projectKey;
    setBusy(true);
    setFailure(null);
    try {
      const next = await client.decideWorkflowHumanTask(project.root, humanTaskId, selected, disposition, commandId());
      if (commandProjectKey !== activeProjectKeyRef.current) return;
      replaceRun(next);
      announce(`Decision ${disposition} recorded against workflow definition ${next.definitionVersion}.`);
    } catch (error) {
      if (commandProjectKey !== activeProjectKeyRef.current) return;
      const message = safeFailure(error);
      setFailure(message);
      announce(`Task Center command failed. ${message}`);
    } finally {
      if (commandProjectKey === activeProjectKeyRef.current) setBusy(false);
    }
  };

  return <div className="task-center-workspace" data-task-center-workspace>
    <div className="page-header">
      <div>
        <Typography as="h1" variant="page-title">Task Center</Typography>
        <Typography className="page-subtitle">Durable local workflows, human decisions, resource pools, recovery and retained outputs.</Typography>
      </div>
      <Button disabled={busy} onClick={() => void load(true)}>Refresh</Button>
    </div>
    {!writable ? <Notification tone="warning" title="Read-only workflow view">You can inspect durable work, but commands are disabled until the project is opened read-write.</Notification> : null}
    {failure ? <Notification tone="danger" title="Task Center unavailable">{failure}</Notification> : null}
    {loading ? <p role="status">Loading durable workflows…</p> : null}
    {!loading && runs.length === 0 ? <Panel title="No durable work"><p>Queued, running, waiting and failed workflows will appear here.</p></Panel> : null}
    {runs.length > 0 ? <div className="task-center-layout">
      <section aria-labelledby="workflow-list-title">
        <Typography id="workflow-list-title" as="h2" variant="section-title">Workflows</Typography>
        <Field id="task-center-filter" label="Filter workflows" input={{ type: "search", value: filter, onChange: (event) => setFilter(event.currentTarget.value) }} />
        <ul className="task-center-list" aria-label="Durable workflows">
          {visible.map((run) => <li key={run.workflowRunId}><button
            ref={run.workflowRunId === selected?.workflowRunId ? selectedWorkflowRef : undefined}
            type="button"
            aria-pressed={selected?.workflowRunId === run.workflowRunId}
            onClick={() => setSelectedId(run.workflowRunId)}
          >
            <strong>{run.workflowKey}</strong>
            <StatusBadge tone={statusTone(run.state)}>{run.state.replace("-", " ")}</StatusBadge>
            <span>{run.activeCompute ? "Compute active" : run.state === "waiting-human" ? "Waiting for review" : "No active compute"}</span>
            <span>{progressText(run)}</span>
          </button></li>)}
        </ul>
        {visible.length === 0 ? <p role="status">No workflows match this filter.</p> : null}
      </section>
      {selected ? <section aria-labelledby="workflow-detail-title" className="task-center-detail">
        <Typography id="workflow-detail-title" as="h2" variant="section-title">{selected.workflowKey}</Typography>
        <p>Definition {selected.definitionVersion} · snapshot {selected.snapshotRevision} · history {selected.revision}</p>
        {selected.continuationFromWorkflowRunId && selected.continuationFromJobId ? <p data-workflow-continuation>
          Continuation of run {selected.continuationFromWorkflowRunId} from job {selected.continuationFromJobId}.
        </p> : null}
        <p><strong>Execution:</strong> {selected.activeCompute ? "Compute is active." : selected.state === "waiting-human" ? "Compute is stopped while a human decision is required." : "No compute is active."}</p>
        {selected.steps.map((step) => <Panel key={step.stepRunId} title={step.stepKey} tone={step.state === "failed" ? "danger" : "neutral"}>
          <p>{step.kind} · {step.state.replace("-", " ")}</p>
          <p>Depends on: {step.dependsOn.length ? step.dependsOn.join(", ") : "workflow start"}.</p>
        </Panel>)}
        {selected.jobs.map((job) => <Panel key={job.jobId} title={job.activityType} tone={job.state === "failed" ? "danger" : "neutral"}>
          <p><strong>Status:</strong> {job.state.replace("-", " ")} · attempt {job.attemptCount} of {job.maxAttempts}</p>
          <p><strong>Resource pool:</strong> {job.resourcePool} · measured use not reported</p>
          <p><strong>Progress:</strong> {job.progress.kind === "quantified" ? `${job.progress.completedUnits} of ${job.progress.totalUnits} ${job.progress.unit}` : `${job.progress.kind} ${job.progress.unit}`}</p>
          {job.latestCheckpointId ? <p>Safe checkpoint recorded at {job.latestCheckpointAt ?? "an unknown time"}.</p> : <p>No checkpoint reported.</p>}
          {job.diagnosticCode ? <p role="status">Diagnostic: {job.diagnosticCode}</p> : null}
          <div className="task-center-actions">
            <Button disabled={!writable || busy || !["claimed", "running", "runnable", "retry-scheduled"].includes(job.state)} onClick={(event) => { restoreFocusRef.current = event.currentTarget; setConfirmation({ kind: "cancel", workflow: selected, jobId: job.jobId }); }}>Cancel safely</Button>
            <Button disabled={!writable || busy || !["failed", "cancelled"].includes(job.state)} onClick={(event) => { restoreFocusRef.current = event.currentTarget; setConfirmation({ kind: "retry", workflow: selected, jobId: job.jobId }); }}>Retry as continuation</Button>
          </div>
        </Panel>)}
        {selected.humanTasks.filter((task) => task.state === "requested" || task.state === "claimed").map((task) => <Panel key={task.humanTaskId} title="Decision required" tone="warning">
          <p>This exact workflow is waiting for a {task.requiredRole} decision. Compute is not active.</p>
          <p>Review {task.evidenceArtifactIds.length} bound evidence artifact(s). The definition—not this screen—controls each consequence.</p>
          <div className="task-center-actions">
            {task.allowedDispositions.map((disposition) => <Button key={disposition} disabled={!writable || busy} tone={disposition === "approved" ? "primary" : "secondary"} onClick={() => void decide(task.humanTaskId, disposition)}>{disposition.replace("-", " ")} — {task.consequencesByDisposition[disposition]?.replaceAll("-", " ")}</Button>)}
          </div>
        </Panel>)}
        <Panel title="Retained outputs and logs">
          <p>{selected.retainedArtifacts.length ? `Partial artifacts: ${selected.retainedArtifacts.join(", ")}.` : "No retained incomplete or quarantined artifacts."}</p>
          <ol className="task-center-events">
            {selected.events.map((event) => <li key={`${event.sequence}-${event.entityId}`}><strong>{event.sequence}</strong> {event.entityType} → {event.toState} · {event.reasonCode}</li>)}
          </ol>
        </Panel>
      </section> : null}
    </div> : null}
    {confirmation ? <div className="dialog-backdrop" role="presentation">
      <section className="task-center-confirmation" role="alertdialog" aria-modal="true" aria-labelledby="task-center-confirmation-title" onKeyDown={containConfirmationFocus}>
        <Typography id="task-center-confirmation-title" as="h2" variant="section-title">{confirmation.kind === "cancel" ? "Request safe cancellation?" : "Create a retry continuation?"}</Typography>
        <p>{confirmation.kind === "cancel"
          ? "Active work will stop at its next cooperative safe point. Any partial artifacts retain their recorded disposition."
          : "The failed or cancelled run remains immutable. Retry creates a new run bound to the exact same workflow definition."}</p>
        <div className="dialog-actions">
          <Button ref={cancelRef} disabled={busy} onClick={closeConfirmation}>Keep current state</Button>
          <Button tone={confirmation.kind === "cancel" ? "danger" : "primary"} disabled={busy} onClick={() => void confirmCommand()}>{busy ? "Working…" : "Confirm"}</Button>
        </div>
      </section>
    </div> : null}
  </div>;
}
