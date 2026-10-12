import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  decodeProblemDetail,
  type CoreApiRequest,
  type CoreApiResponse,
  type CoreApiTransport,
  type ProjectCreateRequest,
  type ProjectProjection,
  type ProjectRecoveryProjection,
  type WorkflowProfileCatalogProjection,
} from "@research-observatory/contracts/core-api";
import { invoke } from "@tauri-apps/api/core";
import { Button, DirectoryPickerField, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { LocalServiceBoundary, type RuntimeState } from "./LocalServiceBoundary";
import { chooseProjectDirectory, defaultProjectParent, projectDestination, projectDirectoryName, type DirectoryPurpose } from "./directoryPicker";

export interface ProjectsWorkspaceProps {
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly selectedProject?: ProjectProjection | null;
  readonly onProjectChange?: (project: ProjectProjection) => void;
  readonly initialCatalog?: WorkflowProfileCatalogProjection | null;
}

function hasTauriRuntime(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

export async function packagedProjectTransport(request: CoreApiRequest): Promise<CoreApiResponse> {
  if (!hasTauriRuntime()) throw new Error("RO-CORE-HOST-UNAVAILABLE");
  return await invoke<CoreApiResponse>("core_api_request", { request });
}

export function projectActionLabels(project: ProjectProjection | null): readonly string[] {
  if (!project) return [];
  if (project.open) return ["Close project"];
  const actions: string[] = [];
  if (project.lifecycleState === "active") {
    actions.push(project.compatibilityState === "compatible" ? "Open project" : "Open read-only");
  }
  if (project.lifecycleState === "active" && project.compatibilityState === "compatible") actions.push("Archive project");
  if (project.lifecycleState === "archived" && project.compatibilityState === "compatible") {
    actions.push("Restore project");
  }
  if (project.lifecycleState !== "trash" && project.compatibilityState === "compatible") {
    actions.push("Move to recoverable trash");
  }
  return actions;
}

export function projectCompatibilityGuidance(project: ProjectProjection): {
  readonly title: string;
  readonly message: string;
} | null {
  if (project.compatibilityState === "compatible") return null;
  if (project.compatibilityState === "migration-required") {
    return {
      title: "Migration required · read-only",
      message: "Keep the original unchanged. First create and verify a complete backup, then run the reviewed migration against a working copy.",
    };
  }
  return {
    title: "Newer project format · read-only",
    message: "Keep the original unchanged. First create and verify a complete backup, then use a compatible application version with the working copy.",
  };
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) {
    if (error.problem.code === "RO-CORE-PROJECT-ALREADY-EXISTS") {
      return {
        title: "The destination already exists",
        message: "Change the project name or choose a different parent folder. The existing folder will not be overwritten; your entries are kept.",
      };
    }
    return {
      title: `${error.problem.title} (${error.problem.code})`,
      message: `${error.problem.detail} ${error.problem.remediation}`,
    };
  }
  if (error instanceof Error && error.message === "RO-CORE-REQUEST-INVALID") {
    return {
      title: "Review project details",
      message: "Check the project name, location, research objective and selected use case. No project request was sent.",
    };
  }
  return {
    title: "RO-CORE-PROJECT-ACTION-FAILED",
    message: "The local project action did not complete. Review Core status and retry once.",
  };
}

const recoveryStates = ["unavailable-proof", "denied", "preview-ready", "cancelled", "copying", "verification-failed", "verified-copy-ready", "open-failed", "recovered"] as const;
type RecoveryState = ProjectRecoveryProjection["state"];
type RecoveryCommand = "preview" | "confirm" | "cancel" | "status";
type RecoveryFlow = { readonly sourceRoot: string; readonly destinationRoot: string; readonly projection: ProjectRecoveryProjection };

export function decodeProjectRecoveryProjection(value: unknown): ProjectRecoveryProjection | null {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const record = value as Record<string, unknown>;
    const keys = ["previewId", "state", "reasonCodes", "requiresConfirmation", "sourceDisplayLabel", "destinationDisplayLabel", "verifiedFactSummary"];
    if (Reflect.ownKeys(record).length !== keys.length || Reflect.ownKeys(record).some((key) => typeof key !== "string" || !keys.includes(key))) return null;
    const text = (item: unknown, maximum: number): item is string => typeof item === "string" && item.length > 0 && item.length <= maximum && item.isWellFormed() && !/[\x00-\x1f\x7f]/.test(item);
    if (typeof record.previewId !== "string" || !/^[0-9a-f]{32}$/.test(record.previewId)
      || !recoveryStates.includes(record.state as RecoveryState)
      || record.requiresConfirmation !== (record.state === "preview-ready")
      || !text(record.sourceDisplayLabel, 120) || !text(record.destinationDisplayLabel, 120)
      || !Array.isArray(record.reasonCodes) || record.reasonCodes.length > 8
      || record.reasonCodes.some((code) => typeof code !== "string" || !/^[a-z0-9-]{1,120}$/.test(code))
      || (record.verifiedFactSummary !== null && (!text(record.verifiedFactSummary, 240)
        || !["verified-copy-ready", "open-failed", "recovered"].includes(record.state as string)))) return null;
    return Object.freeze({ ...record, reasonCodes: Object.freeze([...record.reasonCodes]) }) as unknown as ProjectRecoveryProjection;
  } catch { return null; }
}

export function projectRecoveryActionLabels(state: RecoveryState): readonly string[] {
  if (state === "preview-ready") return ["Cancel", "Create verified recovery copy"];
  if (state === "copying") return ["Cancel before publication"];
  if (state === "verified-copy-ready" || state === "open-failed") return ["Open verified recovery copy"];
  if (state === "recovered") return [];
  return ["Review recovery explanation", "Choose another project"];
}

export function projectRecoveryCanAdvance(previous: RecoveryState, next: RecoveryState): boolean {
  if (previous === next) return true;
  if (previous === "preview-ready") return ["copying", "cancelled", "verification-failed", "verified-copy-ready"].includes(next);
  if (previous === "copying") return ["cancelled", "verification-failed", "verified-copy-ready"].includes(next);
  if (previous === "verified-copy-ready") return next === "open-failed" || next === "recovered";
  return previous === "open-failed" && next === "recovered";
}

export async function requestProjectRecovery(transport: CoreApiTransport, action: RecoveryCommand, value: Readonly<Record<string, string>>): Promise<ProjectRecoveryProjection> {
  const keys = action === "preview" ? ["root", "destinationRoot"] : action === "confirm" ? ["root", "previewId", "confirmation"] : ["root", "previewId"];
  const root = (item: unknown): item is string => typeof item === "string" && item.length <= 4096 && item.isWellFormed()
    && /^[a-z]:[\\/]/i.test(item) && !/[\x00-\x1f\x7f<>"|?*]/.test(item) && !item.slice(2).includes(":")
    && item.slice(3).replaceAll("\\", "/").split("/").every((part) => part !== "." && part !== "..");
  if (!["preview", "confirm", "cancel", "status"].includes(action)
    || Reflect.ownKeys(value).length !== keys.length || Reflect.ownKeys(value).some((key) => typeof key !== "string" || !keys.includes(key))
    || !root(value.root) || (action === "preview" ? !root(value.destinationRoot) : !/^[0-9a-f]{32}$/.test(value.previewId ?? ""))
    || (action === "confirm" && value.confirmation !== "recover-working-copy")) throw new Error("RO-CORE-REQUEST-INVALID");
  const body = JSON.stringify(Object.fromEntries(keys.map((key) => [key, value[key]])));
  const response = await transport({ method: "POST", path: `/projects/recovery/${action}`, body, ifMatch: null, idempotencyKey: null });
  if (!Number.isInteger(response.status) || typeof response.traceId !== "string" || !/^[0-9a-f]{32}$/.test(response.traceId)
    || typeof response.body !== "string" || new TextEncoder().encode(response.body).length > 1_048_576) throw new Error("RO-CORE-RESPONSE-INVALID");
  let decoded: unknown;
  try { decoded = JSON.parse(response.body); } catch { throw new Error("RO-CORE-RESPONSE-INVALID"); }
  if (response.status >= 400) {
    const problem = response.contentType === "application/problem+json" ? decodeProblemDetail(decoded) : null;
    if (!problem || problem.status !== response.status || problem.traceId !== response.traceId) throw new Error("RO-CORE-RESPONSE-INVALID");
    throw new CoreApiClientError(problem);
  }
  const projection = response.status === 200 && response.contentType === "application/json" ? decodeProjectRecoveryProjection(decoded) : null;
  if (!projection || (action !== "preview" && projection.previewId !== value.previewId)
    || (action === "preview" && !["preview-ready", "denied", "unavailable-proof"].includes(projection.state))
    || (action === "confirm" && !["copying", "verified-copy-ready", "verification-failed", "cancelled"].includes(projection.state))) throw new Error("RO-CORE-RESPONSE-INVALID");
  return projection;
}

const recoveryMessages: Readonly<Record<RecoveryState, { title: string; message: string }>> = {
  "unavailable-proof": { title: "Recovery proof is unavailable", message: "This session cannot be authenticated for recovery. Keep the original unchanged and choose another project or review your verified backup." },
  denied: { title: "Recovery is denied", message: "The ownership, source or destination checks did not permit a copy. Review the explanation below or choose another project." },
  "preview-ready": { title: "Review recovery copy", message: "Core verified eligibility for this exact source and destination. Confirm only if you want a new verified working copy." },
  cancelled: { title: "Recovery cancelled", message: "No verified copy was published. The original project remains unchanged." },
  copying: { title: "Creating and verifying the recovery copy…", message: "The original project remains unchanged. You can request cancellation before publication; opening remains unavailable until verification finishes." },
  "verification-failed": { title: "Recovery verification failed", message: "No usable recovery copy was published. Partial output is retained separately. The original project remains unchanged." },
  "verified-copy-ready": { title: "Verified recovery copy is ready", message: "Review the verified facts, then explicitly open the working copy. No project has been reopened or reparsed automatically." },
  "open-failed": { title: "The recovery copy could not be opened", message: "The verified copy is retained. Review Core status and explicitly retry opening; the original project remains unchanged." },
  recovered: { title: "Recovery copy opened", message: "The working copy is open through the normal project boundary. Accepted research facts are unchanged; no reparse or acceptance was triggered." },
};

function ProjectRecoveryRegion({ sourceRoot, transport, announce, disabled, onBusyChange, onRecovered }: {
  sourceRoot: string; transport: CoreApiTransport; announce: (message: string) => void; disabled: boolean;
  onBusyChange: (busy: boolean) => void; onRecovered: (project: ProjectProjection) => void;
}): ReactNode {
  const [parent, setParent] = useState("");
  const [flow, setFlow] = useState<RecoveryFlow | null>(null);
  const flowRef = useRef<RecoveryFlow | null>(null);
  const [commandBusy, setCommandBusy] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [statusUnavailable, setStatusUnavailable] = useState(false);
  const [cancellationRequested, setCancellationRequested] = useState(false);
  const [reviewDismissed, setReviewDismissed] = useState(false);
  const confirmationAttempted = useRef(false);
  const [projectDetailsConfirmed, setProjectDetailsConfirmed] = useState(false);
  const [copyClosed, setCopyClosed] = useState(false);
  const [failure, setFailure] = useState<{ title: string; message: string } | null>(null);
  const mounted = useRef(false);
  const pending = useRef(false);
  const generation = useRef(0);
  const pickerAbort = useRef<AbortController | null>(null);
  const pickerButton = useRef<HTMLButtonElement>(null);
  const reviewButton = useRef<HTMLButtonElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const openCopyButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const status = useRef<HTMLParagraphElement>(null);
  const previousState = useRef<RecoveryState | null>(null);
  const restoreActionFocus = useRef(false);
  const destinationRoot = projectDestination(parent, "recovered-working-copy");
  const state = flow?.projection.state ?? null;
  const active = state === "copying" || (state === "preview-ready" && (!reviewDismissed || confirmationAttempted.current));
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; generation.current++; pickerAbort.current?.abort();
      const retained = flowRef.current;
      if (retained && ["preview-ready", "copying"].includes(retained.projection.state)) {
        void requestProjectRecovery(transport, "cancel", { root: retained.sourceRoot, previewId: retained.projection.previewId }).catch(() => {});
      }
      onBusyChange(false);
    };
  }, [onBusyChange, transport]);
  useEffect(() => { onBusyChange(commandBusy || choosing || active); }, [active, choosing, commandBusy, onBusyChange]);
  useEffect(() => {
    if (state === "preview-ready" && !reviewDismissed) {
      if (dialog.current && !dialog.current.open) dialog.current.showModal();
      if (!commandBusy) cancelButton.current?.focus();
    } else if (!commandBusy && (previousState.current !== state || restoreActionFocus.current)) {
      if (state === "copying" || state === "verified-copy-ready" || state === "recovered") status.current?.focus();
      else if (state === "open-failed" && openCopyButton.current && !openCopyButton.current.disabled) openCopyButton.current.focus();
      else if (state && !reviewButton.current?.disabled) reviewButton.current?.focus();
      else if (state) status.current?.focus();
    }
    if (!commandBusy) { previousState.current = state; restoreActionFocus.current = false; }
    if (reviewDismissed && !commandBusy && state === "preview-ready") {
      if (!reviewButton.current?.disabled) reviewButton.current?.focus();
      else status.current?.focus();
    }
  }, [commandBusy, reviewDismissed, state]);
  const apply = useCallback((next: ProjectRecoveryProjection): void => {
    const current = flowRef.current;
    if (!current || next.previewId !== current.projection.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
    if (!projectRecoveryCanAdvance(current.projection.state, next.state)) return;
    const updated = { ...current, projection: next };
    flowRef.current = updated; setFlow(updated);
    if (next.state !== current.projection.state || next.reasonCodes.join("|") !== current.projection.reasonCodes.join("|")
      || next.verifiedFactSummary !== current.projection.verifiedFactSummary) {
      announce(`${recoveryMessages[next.state].title}. ${recoveryMessages[next.state].message}`);
    }
  }, [announce]);
  useEffect(() => {
    if (state !== "copying" || statusUnavailable || disabled) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async (): Promise<void> => {
      const current = flowRef.current;
      if (!stopped && mounted.current && current?.projection.state === "copying" && !pending.current) {
        try {
          const next = await requestProjectRecovery(transport, "status", { root: current.sourceRoot, previewId: current.projection.previewId });
          if (!stopped && mounted.current) apply(next);
        } catch {
          if (!stopped && mounted.current) { setStatusUnavailable(true); setFailure({ title: "Recovery status is unavailable", message: "No success or cancellation is assumed. Explicitly read the current status before another action." }); }
        }
      }
      if (!stopped) timer = setTimeout(() => void tick(), 250);
    };
    timer = setTimeout(() => void tick(), 250);
    return () => { stopped = true; clearTimeout(timer); };
  }, [apply, disabled, state, statusUnavailable, transport]);
  const chooseParent = async (): Promise<void> => {
    if (disabled || pending.current || active || !mounted.current) return;
    pending.current = true; onBusyChange(true); setChoosing(true); setFailure(null);
    const epoch = generation.current;
    const abort = new AbortController(); pickerAbort.current = abort;
    const result = await chooseProjectDirectory({ purpose: "create-parent", ...(parent ? { previousLocation: parent } : {}) }, abort.signal);
    pending.current = false;
    if (!mounted.current || abort.signal.aborted || generation.current !== epoch) return;
    if (result.status === "selected") {
      setParent(result.path); flowRef.current = null; setFlow(null); setStatusUnavailable(false); setCancellationRequested(false);
      setReviewDismissed(false); confirmationAttempted.current = false; setProjectDetailsConfirmed(false); setCopyClosed(false);
      announce("Recovery parent folder selected. No project action was performed.");
    } else {
      setFailure({ title: result.status === "cancelled" ? "Selection cancelled" : "Recovery folder chooser is unavailable", message: "Your previous selection and recovery state are unchanged. Retry from the folder button." });
      announce(result.status === "cancelled" ? "Selection cancelled. Your previous selection is unchanged." : "Folder selection did not complete. No project action was performed.");
    }
    setChoosing(false); onBusyChange(false);
    requestAnimationFrame(() => { if (mounted.current) pickerButton.current?.focus(); });
  };
  const command = async (action: RecoveryCommand | "open" | "close"): Promise<void> => {
    if (disabled || pending.current || !mounted.current) return;
    const current = flowRef.current;
    if (action === "preview" && (!sourceRoot || !destinationRoot || active)) return;
    if (action !== "preview" && !current) return;
    if (action === "cancel" || action === "confirm") setReviewDismissed(true);
    if (action === "confirm") confirmationAttempted.current = true;
    pending.current = true; onBusyChange(true); setCommandBusy(true); setFailure(null);
    const epoch = generation.current;
    const owns = (): boolean => mounted.current && generation.current === epoch;
    try {
      if (action === "preview") {
        const next = await requestProjectRecovery(transport, "preview", { root: sourceRoot, destinationRoot });
        if (!owns()) return;
        const reviewed = { sourceRoot, destinationRoot, projection: next };
        flowRef.current = reviewed; setFlow(reviewed); setStatusUnavailable(false); setCancellationRequested(false);
        setReviewDismissed(false); confirmationAttempted.current = false; setProjectDetailsConfirmed(false); setCopyClosed(false);
        announce(`${recoveryMessages[next.state].title}. ${recoveryMessages[next.state].message}`);
      } else if (action === "open" && current) {
        if (!["verified-copy-ready", "open-failed"].includes(current.projection.state)) return;
        const opened = await client.openProject({ root: current.destinationRoot });
        if (!owns()) return;
        if (!opened.open || opened.accessMode !== "read-write" || opened.root.replaceAll("\\", "/").toLowerCase() !== current.destinationRoot.replaceAll("\\", "/").toLowerCase()) throw new Error("RO-CORE-RESPONSE-INVALID");
        setProjectDetailsConfirmed(true); setCopyClosed(false); onRecovered(opened);
        const next = await requestProjectRecovery(transport, "status", { root: current.sourceRoot, previewId: current.projection.previewId });
        if (owns()) { apply(next); setStatusUnavailable(false); }
      } else if (action === "close" && current) {
        if (current.projection.state !== "recovered" || projectDetailsConfirmed) return;
        const closed = await client.closeProject({ root: current.destinationRoot });
        if (!owns()) return;
        if (closed.open || closed.accessMode !== "closed" || closed.root.replaceAll("\\", "/").toLowerCase() !== current.destinationRoot.replaceAll("\\", "/").toLowerCase()) throw new Error("RO-CORE-RESPONSE-INVALID");
        setProjectDetailsConfirmed(true); setCopyClosed(true); setStatusUnavailable(false); onRecovered(closed);
        announce("The recovery copy is closed. Its confirmed project details are available; opening again remains an explicit action.");
      } else if (current) {
        const next = await requestProjectRecovery(transport, action as RecoveryCommand, { root: current.sourceRoot, previewId: current.projection.previewId,
          ...(action === "confirm" ? { confirmation: "recover-working-copy" } : {}) });
        if (owns()) { apply(next); setStatusUnavailable(false); if (next.state === "preview-ready") confirmationAttempted.current = false; if (action === "cancel" && next.state === "copying") setCancellationRequested(true); }
      }
    } catch (error) {
      if (!owns()) return;
      setFailure(safeFailure(error));
      if (action !== "preview") setStatusUnavailable(true);
      announce("Recovery outcome could not be confirmed. Read the current status. The original project remains unchanged.");
    } finally {
      pending.current = false;
      if (owns()) { restoreActionFocus.current = true; setCommandBusy(false); onBusyChange(flowRef.current?.projection.state === "copying" || (flowRef.current?.projection.state === "preview-ready" && confirmationAttempted.current)); }
    }
  };
  const dismissReview = (): void => {
    setReviewDismissed(true);
    if (disabled || pending.current) {
      setStatusUnavailable(true);
      setFailure({ title: "Cancellation is not confirmed", message: "The review is dismissed locally. Wait for the pending response or start Core explicitly, then read recovery status before another action." });
      announce("Recovery review dismissed. Cancellation is not confirmed; read recovery status before another action.");
      return;
    }
    void command("cancel");
  };
  const message = state ? recoveryMessages[state] : null;
  return <section aria-label="Project recovery"><Panel title="Recover a project"><div className="ro-stack">
    <p>The original project remains unchanged. Review eligibility before confirming a verified local working copy; opening it is a separate action.</p>
    <p className="ro-wrap-anywhere">Recovery source: {flow?.sourceRoot || sourceRoot || "Choose a project folder in Open an existing project."}</p>
    {flow && flow.sourceRoot !== sourceRoot ? <p className="ro-wrap-anywhere">New selection for a later review: {sourceRoot}. The retained recovery actions below still belong to the displayed recovery source.</p> : null}
    <DirectoryPickerField id="project-recovery-parent" label="Recovery copy parent folder" value={parent} buttonRef={pickerButton}
      description="Choose an existing local parent. The new recovered-working-copy destination is shown below and will never overwrite an existing folder."
      disabled={disabled || commandBusy || choosing || active} pending={choosing} onChoose={() => void chooseParent()} />
    <output className="ro-directory-location" aria-label="Recovery copy destination">{destinationRoot || "Select a parent folder before reviewing recovery."}</output>
    <Button ref={reviewButton} disabled={commandBusy || choosing || ((!sourceRoot || !destinationRoot || disabled || active || ["verified-copy-ready", "open-failed"].includes(state ?? "")) && !statusUnavailable && !(state === "preview-ready" && reviewDismissed))}
      onClick={() => {
        if (disabled) { setFailure({ title: "The local service is not ready", message: "Use the explicit Core startup action, then read the recovery status. No recovery operation is replayed." }); return; }
        if (statusUnavailable) void command("status");
        else if (state === "preview-ready" && reviewDismissed) setReviewDismissed(false);
        else void command("preview");
      }}>{statusUnavailable ? (disabled ? "Review recovery explanation" : "Read recovery status") : "Review recovery"}</Button>
    {message ? <div className="ro-notice" data-recovery-state={state}>
      <Typography as="h3" variant="section-title">{statusUnavailable ? `Last confirmed state: ${message.title}` : copyClosed ? "Recovery copy closed" : state === "recovered" && !projectDetailsConfirmed ? "Core reports the copy opened; project details are not confirmed" : message.title}</Typography>
      <p ref={status} tabIndex={-1} role="status">{statusUnavailable ? "The current recovery outcome is not confirmed. Read recovery status before another action. The original project remains unchanged." : copyClosed ? "The working copy is closed through the normal project boundary. Opening it again remains an explicit action in Current project." : state === "recovered" && !projectDetailsConfirmed ? "The open response was not confirmed. You can explicitly close this exact copy to obtain confirmed project details. Opening is never replayed automatically." : message.message}</p>
      {flow ? <output className="ro-directory-location" aria-label="Retained recovery copy destination">{flow.destinationRoot}</output> : null}
      {flow?.projection.reasonCodes.length ? <p>Recovery explanation: {flow.projection.reasonCodes.join(" · ")}</p> : null}
      {flow?.projection.verifiedFactSummary ? <p>{flow.projection.verifiedFactSummary}</p> : null}
      {state === "copying" ? <Button disabled={disabled || commandBusy || cancellationRequested} onClick={() => void command("cancel")}>{cancellationRequested ? "Cancellation requested; awaiting status" : "Cancel before publication"}</Button> : null}
      {(state === "verified-copy-ready" || state === "open-failed") && !statusUnavailable ? <Button ref={openCopyButton} tone="primary" disabled={disabled || commandBusy} onClick={() => void command("open")}>Open verified recovery copy</Button> : null}
      {state === "recovered" && !projectDetailsConfirmed && !statusUnavailable ? <Button disabled={disabled || commandBusy} onClick={() => void command("close")}>Close project</Button> : null}
    </div> : null}
    {failure ? <Notification tone="warning" title={failure.title}>{failure.message}</Notification> : null}
    {state === "preview-ready" && !reviewDismissed ? <dialog ref={dialog} className="ro-dialog" aria-labelledby="project-recovery-review-title" aria-describedby="project-recovery-review-description"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
        const first = controls[0];
        const last = controls.at(-1);
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first.focus();
        }
      }}
      onCancel={(event) => { event.preventDefault(); dismissReview(); }}>
      <Typography id="project-recovery-review-title" as="h2" variant="section-title">Review recovery copy</Typography>
      <div className="ro-dialog__body ro-stack"><p id="project-recovery-review-description">Create a verified working copy of {flow?.projection.sourceDisplayLabel}. The original is preserved. This does not reopen, reparse or accept research results.</p>
        <output className="ro-directory-location" aria-label="Reviewed recovery destination">{flow?.destinationRoot}</output>
        {failure ? <Notification tone="warning" title={failure.title}>{failure.message}</Notification> : null}</div>
      <div className="ro-dialog__actions ro-action-row"><Button ref={cancelButton} disabled={commandBusy} onClick={dismissReview}>Cancel</Button>
        <Button tone="primary" disabled={disabled || commandBusy || statusUnavailable} onClick={() => void command("confirm")}>Create verified recovery copy</Button>
        {statusUnavailable ? <Button disabled={commandBusy} onClick={() => void command("status")}>Read recovery status</Button> : null}</div>
    </dialog> : null}
  </div></Panel></section>;
}

export function ProjectsWorkspace({
  announce,
  transport = packagedProjectTransport,
  selectedProject = null,
  onProjectChange,
  initialCatalog = null,
}: ProjectsWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const [project, setProject] = useState<ProjectProjection | null>(selectedProject);
  const [parentDirectory, setParentDirectory] = useState("");
  const [folderSuggestionId] = useState(() => globalThis.crypto.randomUUID().replaceAll("-", "").slice(0, 12));
  const [displayName, setDisplayName] = useState("");
  const [researchObjective, setResearchObjective] = useState("");
  const [primaryUseCase, setPrimaryUseCase] = useState<ProjectCreateRequest["primaryUseCase"] | "">(
    initialCatalog?.profiles[0]?.profileId ?? "",
  );
  const [catalog, setCatalog] = useState<WorkflowProfileCatalogProjection | null>(initialCatalog);
  const [openRoot, setOpenRoot] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);
  const [serviceState, setServiceState] = useState<RuntimeState>("starting");
  const [catalogState, setCatalogState] = useState<"waiting" | "loading" | "ready" | "failed">(initialCatalog ? "ready" : "waiting");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const mounted = useRef(false);
  const mutationPending = useRef(false);
  const recoveryPending = useRef(false);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const recoveryBusyChanged = useCallback((next: boolean): void => { recoveryPending.current = next; setRecoveryBusy(next); }, []);
  const mutationGeneration = useRef(0);
  const folderPending = useRef(false);
  const folderGeneration = useRef(0);
  const folderRequest = useRef<AbortController | null>(null);
  const parentChosenByUser = useRef(false);
  const parentSelectionPending = useRef(false);
  const parentButton = useRef<HTMLButtonElement>(null);
  const openButton = useRef<HTMLButtonElement>(null);
  const restoreFolderFocus = useRef<HTMLButtonElement | null>(null);
  const [folderBusy, setFolderBusy] = useState<DirectoryPurpose | null>(null);
  const [folderNotice, setFolderNotice] = useState<{ title: string; message: string; failed: boolean } | null>(null);
  const [defaultState, setDefaultState] = useState<"waiting" | "loading" | "available" | "unavailable">("waiting");
  const [defaultAttempt, setDefaultAttempt] = useState(0);
  const observesNativeService = transport === packagedProjectTransport && !initialCatalog;
  const serviceReady = !observesNativeService || serviceState === "ready";
  const actionsDisabled = busy !== null || folderBusy !== null || recoveryBusy || !serviceReady;
  const directoryName = projectDirectoryName(displayName, folderSuggestionId);
  const destination = projectDestination(parentDirectory, directoryName);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      mutationGeneration.current++;
      folderGeneration.current++;
      folderRequest.current?.abort();
      restoreFolderFocus.current = null;
    };
  }, []);

  useEffect(() => {
    if (!serviceReady || parentChosenByUser.current || parentDirectory) return;
    const controller = new AbortController();
    setDefaultState("loading");
    void defaultProjectParent(controller.signal).then((result) => {
      if (controller.signal.aborted || !mounted.current || parentChosenByUser.current || parentSelectionPending.current) return;
      if (result.status === "available") {
        setParentDirectory(result.path);
        setDefaultState("available");
      } else setDefaultState("unavailable");
    });
    return () => controller.abort();
  }, [defaultAttempt, parentDirectory, serviceReady]);

  useEffect(() => {
    if (folderBusy !== null) return;
    const trigger = restoreFolderFocus.current;
    restoreFolderFocus.current = null;
    if (mounted.current && trigger?.isConnected && !trigger.closest("[inert], [hidden]")) trigger.focus();
  }, [folderBusy]);

  const chooseFolder = async (purpose: DirectoryPurpose): Promise<void> => {
    if (!mounted.current || mutationPending.current || folderPending.current || recoveryPending.current) return;
    folderPending.current = true;
    const generation = ++folderGeneration.current;
    if (purpose === "create-parent") parentSelectionPending.current = true;
    const controller = new AbortController();
    folderRequest.current = controller;
    setFolderBusy(purpose);
    setFolderNotice(null);
    const previousLocation = purpose === "create-parent" ? parentDirectory : openRoot;
    const result = await chooseProjectDirectory({ purpose, ...(previousLocation ? { previousLocation } : {}) }, controller.signal);
    folderPending.current = false;
    if (purpose === "create-parent") parentSelectionPending.current = false;
    if (controller.signal.aborted || !mounted.current || generation !== folderGeneration.current) return;
    folderRequest.current = null;
    if (result.status === "selected") {
      if (purpose === "create-parent") {
        parentChosenByUser.current = true;
        setParentDirectory(result.path);
      }
      else setOpenRoot(result.path);
      announce("Folder selected. No project action was performed.");
    } else {
      // An attempted choice is not a selection. A default response discarded
      // during the dialog must be rediscovered after cancel/failure.
      if (purpose === "create-parent" && !parentDirectory) setDefaultAttempt((attempt) => attempt + 1);
      const notice = result.status === "cancelled" ? {
        title: "Selection cancelled", message: "Your previous folder and form entries are unchanged.", failed: false,
      } : result.status === "unavailable" ? {
        title: "The folder chooser is unavailable", message: "Retry from the folder button. No project action was performed.", failed: true,
      } : {
        title: "This folder cannot be used", message: "Choose an accessible local folder. Your form entries are unchanged. No project action was performed.", failed: true,
      };
      setFolderNotice(notice);
      announce(`${notice.title}. ${notice.message}`);
    }
    restoreFolderFocus.current = purpose === "create-parent" ? parentButton.current : openButton.current;
    setFolderBusy(null);
  };

  useEffect(() => setProject(selectedProject), [selectedProject]);

  useEffect(() => {
    if (initialCatalog) {
      setCatalog(initialCatalog);
      setCatalogState("ready");
      return;
    }
    if (!serviceReady) {
      setCatalog(null);
      setCatalogState("waiting");
      return;
    }
    let cancelled = false;
    setCatalogState("loading");
    void client.workflowProfileCatalog().then((next) => {
      if (!cancelled) { setCatalog(next); setCatalogState("ready"); }
    }).catch(() => {
      if (!cancelled) { setCatalog(null); setCatalogState("failed"); }
    });
    return () => { cancelled = true; };
  }, [catalogAttempt, client, initialCatalog, serviceReady]);

  const selectedProfile = catalog?.profiles.find((profile) => profile.profileId === primaryUseCase) ?? null;

  const run = async (label: string, action: () => Promise<ProjectProjection>): Promise<void> => {
    if (!serviceReady || mutationPending.current || folderPending.current || recoveryPending.current || !mounted.current) return;
    mutationPending.current = true;
    const generation = mutationGeneration.current;
    const ownsResult = (): boolean => mounted.current && mutationGeneration.current === generation;
    setBusy(label);
    setFailure(null);
    try {
      const next = await action();
      if (!ownsResult()) return;
      setProject(next);
      onProjectChange?.(next);
      setOpenRoot(next.root);
      setDeleteConfirmation("");
      announce(`${label} completed.`);
    } catch (error) {
      if (!ownsResult()) return;
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`${label} did not complete. ${safe.title}`);
    } finally {
      mutationPending.current = false;
      if (ownsResult()) setBusy(null);
    }
  };

  const createProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!serviceReady || !destination || catalogState !== "ready" || !selectedProfile || !primaryUseCase || !researchObjective.trim()) return;
    void run("Create project", () => client.createProject({
      parentDirectory,
      directoryName,
      displayName,
      primaryUseCase,
      researchObjective: researchObjective.trim(),
    }));
  };

  const openProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!openRoot) return;
    void run("Open project", () => client.openProject({ root: openRoot }));
  };

  return (
    <section className="projects-workspace ro-page-region" aria-labelledby="projects-title" data-projects-workspace>
      <div className="page-header">
        <Typography id="projects-title" as="h1" variant="page-title">Local projects</Typography>
        <Typography className="page-subtitle">
          Create or open a governed local project package. Project documents remain on this computer.
        </Typography>
      </div>

      {failure ? <Notification tone="danger" title={failure.title}>{failure.message}</Notification> : null}

      {observesNativeService ? <LocalServiceBoundary announce={announce} observeOnly onStateChange={setServiceState} /> : null}
      {folderBusy ? <Notification title="Choosing a folder…">
        Complete or cancel the native dialog. Other folder buttons and project submission remain unavailable while it is open.
      </Notification> : folderNotice ? <Notification tone={folderNotice.failed ? "warning" : "info"} title={folderNotice.title}>
        {folderNotice.message}
      </Notification> : null}

      <div className="project-workflow-grid ro-grid">
        <Panel title="Create a local project">
          <form className="project-form ro-form" onSubmit={createProject}>
            <Field
              id="project-display-name"
              label="Project name"
              description="Use a descriptive name. The application suggests the new folder name for you."
              input={{ value: displayName, onChange: (event) => setDisplayName(event.currentTarget.value), required: true, maxLength: 120, disabled: busy !== null }}
            />
            <DirectoryPickerField id="project-parent-directory" label="Parent folder" value={parentDirectory}
              description={parentDirectory ? "The new project will be created here. Change folder to choose another local location."
                : defaultState === "unavailable" ? "A default folder is not available. Choose an existing accessible local folder."
                  : "Finding your default project folder. You can also choose an existing local folder."}
              buttonRef={parentButton} disabled={busy !== null || folderBusy !== null || recoveryBusy} pending={folderBusy === "create-parent"}
              onChoose={() => void chooseFolder("create-parent")} />
            <div className="ro-field">
              <span className="ro-field__label" id="project-destination-label">New project destination</span>
              <output className="ro-directory-location" id="project-destination" aria-labelledby="project-destination-label">
                {destination || (parentDirectory && directoryName
                  ? "This destination cannot be used. Shorten the project name or choose another parent folder."
                  : "Enter a project name and select a parent folder to see the destination.")}
              </output>
              <span className="ro-field__description">Review the destination before Create. Existing folders are never overwritten or automatically numbered.</span>
            </div>
            <label htmlFor="project-research-objective">Research objective</label>
            <textarea
              id="project-research-objective"
              value={researchObjective}
              onChange={(event) => setResearchObjective(event.currentTarget.value)}
              rows={3}
              maxLength={4000}
              required
              disabled={busy !== null}
            />
            <label htmlFor="project-primary-use-case">Primary use case</label>
            {catalogState === "failed" ? (
              <Notification tone="danger" title="Could not load use cases">
                <p>Your entries are unchanged. Load the available research types before creating a project.</p>
                <p><code>RO-CORE-CATALOG-FAILED</code></p>
                <Button disabled={!serviceReady || busy !== null} onClick={() => setCatalogAttempt((attempt) => attempt + 1)}>
                  Retry loading use cases
                </Button>
              </Notification>
            ) : catalogState !== "ready" ? (
              <p role="status">{catalogState === "waiting" ? "Waiting for the local service. Your entries are kept here." : "Loading research use cases…"}</p>
            ) : null}
            <select
              id="project-primary-use-case"
              value={primaryUseCase}
              onChange={(event) => setPrimaryUseCase(event.currentTarget.value as ProjectCreateRequest["primaryUseCase"])}
              required
              disabled={busy !== null || !catalog || catalogState !== "ready"}
            >
              <option value="" disabled>{catalogState === "ready" ? "Select a governed use case" : catalogState === "failed" ? "Use cases unavailable" : catalogState === "waiting" ? "Waiting for local service…" : "Loading governed use cases…"}</option>
              {catalog?.profiles.map((profile) => (
                <option key={profile.profileId} value={profile.profileId}>{profile.title}</option>
              ))}
            </select>
            {selectedProfile ? (
              <div className="workflow-profile-preview ro-notice" aria-live="polite">
                <Typography as="h3" variant="section-title">{selectedProfile.title}</Typography>
                <p>{selectedProfile.purpose}</p>
                <p><strong>Expected output:</strong> {selectedProfile.expectedOutputs.join(", ")}</p>
                <p><strong>Process form:</strong> {selectedProfile.processForm === "revisitable" ? "Revisitable process" : "Linear process"}</p>
                <ol>{selectedProfile.stages.map((stage) => <li key={stage.stageKey}>{stage.label}{stage.optional ? " (optional)" : ""}</li>)}</ol>
                <p className="field-note">All tools remain available. The selected workflow does not weaken evidence or provenance requirements.</p>
              </div>
            ) : null}
            <Button tone="primary" type="submit" disabled={actionsDisabled || !destination || catalogState !== "ready" || !selectedProfile || !researchObjective.trim()}>Create project</Button>
          </form>
        </Panel>

        <Panel title="Open an existing project">
          <form className="project-form ro-form" onSubmit={openProject}>
            <DirectoryPickerField id="project-root" label="Project folder" value={openRoot}
              description="Choose an existing Research Observatory project folder, then select Open project. Choosing alone does not open it."
              buttonRef={openButton} disabled={busy !== null || folderBusy !== null || recoveryBusy} pending={folderBusy === "open-project"}
              onChoose={() => void chooseFolder("open-project")} />
            <Button tone="primary" type="submit" disabled={actionsDisabled || !openRoot}>Open project</Button>
          </form>
        </Panel>
      </div>

      <ProjectRecoveryRegion sourceRoot={openRoot} transport={transport} announce={announce}
        disabled={busy !== null || folderBusy !== null || !serviceReady} onBusyChange={recoveryBusyChanged}
        onRecovered={(next) => { setProject(next); setOpenRoot(next.root); setDeleteConfirmation(""); onProjectChange?.(next); }} />
      <Panel title="Current project" tone={project ? "success" : "neutral"}>
        {!project ? <p>No project is selected. Create one or open an existing local project.</p> : (
          <div className="current-project ro-card ro-stack" data-current-project={project.projectId}>
            {projectCompatibilityGuidance(project) ? (
              <Notification tone="warning" title={projectCompatibilityGuidance(project)?.title ?? "Read-only project"}>
                {projectCompatibilityGuidance(project)?.message}
              </Notification>
            ) : null}
            <div>
              <Typography as="h2" variant="section-title">{project.displayName}</Typography>
              <p><code>{project.root}</code></p>
              <div className="project-status-row ro-cluster">
                <StatusBadge tone={project.lifecycleState === "active" ? "success" : "warning"}>
                  {project.lifecycleState}
                </StatusBadge>
                <span>{project.accessMode === "read-write" ? "Exclusive local session open" : project.accessMode === "read-only" ? "Read-only inspection open" : "Closed"}</span>
                <span>{project.compatibilityState}</span>
                <span>Revision {project.revision}</span>
              </div>
            </div>
            <div className="project-actions ro-action-row" aria-label="Current project actions">
              {project.lifecycleState === "active" ? (
                <Button disabled={actionsDisabled} onClick={() => void run(
                  project.open ? "Close project" : "Open project",
                  () => project.open ? client.closeProject({ root: project.root }) : client.openProject({ root: project.root }),
                )}>{project.open ? "Close project" : project.compatibilityState === "compatible" ? "Open project" : "Open read-only"}</Button>
              ) : null}
              {project.lifecycleState === "active" && !project.open && project.compatibilityState === "compatible" ? (
                <Button disabled={actionsDisabled} onClick={() => void run("Archive project", () => client.archiveProject({ root: project.root }))}>
                  Archive project
                </Button>
              ) : null}
              {project.lifecycleState === "archived" && project.compatibilityState === "compatible" ? (
                <Button disabled={actionsDisabled} onClick={() => void run("Restore project", () => client.restoreProject({ root: project.root }))}>
                  Restore project
                </Button>
              ) : null}
            </div>
            {!project.open && project.lifecycleState !== "trash" && project.compatibilityState === "compatible" ? (
              <div className="project-delete-boundary ro-notice">
                <Typography as="h3" variant="section-title">Move to recoverable trash</Typography>
                <p>This moves only this project package. The shared model cache is not deleted.</p>
                <Field
                  id="project-delete-confirmation"
                  label="Exact deletion confirmation"
                  description={`Enter ${project.deleteConfirmation} to confirm.`}
                  input={{ value: deleteConfirmation, onChange: (event) => setDeleteConfirmation(event.currentTarget.value), autoComplete: "off" }}
                />
                <Button
                  disabled={actionsDisabled || deleteConfirmation !== project.deleteConfirmation}
                  onClick={() => void run("Move project to recoverable trash", () => client.deleteProject({
                    root: project.root,
                    confirmation: deleteConfirmation,
                  }))}
                >Move to recoverable trash</Button>
              </div>
            ) : null}
          </div>
        )}
      </Panel>
    </section>
  );
}
