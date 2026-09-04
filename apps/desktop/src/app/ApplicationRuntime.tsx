import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import { Button, Field, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type IntentWorkspaceProjection,
  type ProjectProjection,
  type WorkflowProfileCatalogProjection,
  type WorkflowProgressProjection,
} from "@research-observatory/contracts/core-api";

import { LocalServiceBoundary } from "./LocalServiceBoundary";
import { ApplicationSettingsWorkspace } from "./ApplicationSettingsWorkspace";
import {
  ApplicationSettingsController,
  helloAvailabilityPresentation,
  type TransitionControllerResult,
} from "./applicationSettings";
import { DiagnosticsWorkspace } from "./DiagnosticsWorkspace";
import { AuditLineageWorkspace } from "./AuditLineageWorkspace";
import { ProjectSettingsWorkspace } from "./ProjectSettingsWorkspace";
import { ProjectHomeWorkspace } from "./ProjectHomeWorkspace";
import { packagedProjectTransport, ProjectsWorkspace } from "./ProjectsWorkspace";
import {
  IntentWorkspace,
  persistedIntentUpdateMatchesCurrentProject,
  type IntentProjectIdentity,
} from "./IntentWorkspace";
import { TaskCenterWorkspace } from "./TaskCenterWorkspace";
import {
  WorkflowContextBar,
  WorkflowNavigation,
  type WorkflowNavigationLoadState,
} from "./WorkflowNavigation";
import {
  WorkflowContextLoader,
  WorkflowRequestGuard,
  createSupportingReturn,
  implementedWorkspace,
  selectPrimaryStage,
  supportingReturnMatches,
  workflowCommandStageAuthority,
  workspaceClassification,
  type ApplicationWorkspace,
  type SupportingReturnContext,
  type WorkflowAuthoritySnapshot,
  type WorkflowProgressStage,
  type WorkflowStageAuthorityState,
} from "./workflowNavigationModel";
import {
  applicationUnlockFailureMessage,
  decodeApplicationUnlockAttempt,
  decodeApplicationLockSnapshot,
  decodeVerificationAvailabilitySnapshot,
  DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  failClosedApplicationLockSnapshot,
  reconcileApplicationLockSnapshot,
  type ApplicationLockSnapshot,
  type ApplicationLockSnapshotSource,
  type VerificationAvailability,
} from "./applicationLock";

export type ApplicationTheme = "light" | "dark";

export interface ShortcutDefinition {
  readonly id: "command" | "help" | "home";
  readonly keys: string;
  readonly label: string;
}

export const SHORTCUTS: readonly ShortcutDefinition[] = Object.freeze([
  { id: "command", keys: "Ctrl+K", label: "Focus the command search" },
  { id: "help", keys: "Ctrl+/", label: "Open keyboard shortcuts" },
  { id: "home", keys: "Alt+H", label: "Move focus to the project home" },
]);

export function nextTheme(theme: ApplicationTheme): ApplicationTheme {
  return theme === "light" ? "dark" : "light";
}

export function storedTheme(storage: Pick<Storage, "getItem"> | null): ApplicationTheme {
  if (!storage) return "light";
  try {
    return storage.getItem("research-observatory.theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function isShortcut(event: KeyboardEvent, key: string, modifier: "ctrl" | "alt"): boolean {
  return event.key.toLowerCase() === key && (modifier === "ctrl" ? event.ctrlKey : event.altKey)
    && !event.metaKey && !(modifier === "ctrl" && event.altKey) && !(modifier === "alt" && event.ctrlKey);
}

function hasNativeRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function invokeApplicationLockStatus(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const timer = globalThis.setTimeout(
      () => reject(new Error("Application-lock status timed out.")),
      1_500,
    );
    void invoke<unknown>("application_lock_status").then((value) => {
      globalThis.clearTimeout(timer);
      resolve(value);
    }, (error: unknown) => {
      globalThis.clearTimeout(timer);
      reject(error instanceof Error ? error : new Error(String(error)));
    });
  });
}

function registerApplicationLockListener(
  onPayload: (payload: unknown) => void,
): Promise<UnlistenFn> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = globalThis.setTimeout(() => {
      settled = true;
      reject(new Error("Application-lock listener registration timed out."));
    }, 1_500);
    void listen<unknown>("application-lock-changed", (event) => onPayload(event.payload)).then(
      (cleanup) => {
        globalThis.clearTimeout(timer);
        if (settled) void cleanup();
        else {
          settled = true;
          resolve(cleanup);
        }
      },
      (error: unknown) => {
        globalThis.clearTimeout(timer);
        if (!settled) {
          settled = true;
          reject(error instanceof Error ? error : new Error(String(error)));
        }
      },
    );
  });
}

interface ApplicationLockedViewProps {
  readonly snapshot: ApplicationLockSnapshot;
  readonly busy: boolean;
  readonly error: string | null;
  readonly onUnlock: () => void;
  readonly helloAvailability?: VerificationAvailability;
  readonly recoveryConfirmation?: boolean;
  readonly onRecovery?: () => void;
  readonly onRecoveryDecision?: (confirmed: boolean) => void;
}

export function ApplicationLockedView({
  snapshot,
  busy,
  error,
  onUnlock,
  helloAvailability = "checking",
  recoveryConfirmation = false,
  onRecovery,
  onRecoveryDecision,
}: ApplicationLockedViewProps): ReactNode {
  const recoveryCancelRef = useRef<HTMLButtonElement>(null);
  const recoveryConfirmRef = useRef<HTMLButtonElement>(null);
  const recoveryTriggerRef = useRef<HTMLButtonElement>(null);
  const previousRecoveryConfirmation = useRef(recoveryConfirmation);
  const reason = snapshot.reason === "inactivity"
    ? "The inactivity interval elapsed."
    : snapshot.reason === "application-restart"
      ? "The configured lock was restored when the application started."
      : snapshot.reason === "configuration-invalid"
        ? "The local lock configuration could not be validated."
        : "The application was locked manually.";
  const provider = snapshot.signInMode === "windows-hello"
    ? "Windows Hello"
    : snapshot.signInMode === "windows-password"
      ? "Windows password"
      : "Windows";
  const hello = helloAvailabilityPresentation(helloAvailability);
  const recoveryRequired = snapshot.configurationState === "invalid";
  const helloRecoveryOffered = snapshot.signInMode === "windows-hello"
    && new Set<VerificationAvailability>([
      "not-present",
      "not-configured",
      "policy-disabled",
      "unavailable",
      "failed",
    ]).has(helloAvailability);
  useEffect(() => {
    if (busy) return;
    if (recoveryConfirmation) recoveryCancelRef.current?.focus();
    else if (previousRecoveryConfirmation.current) recoveryTriggerRef.current?.focus();
    previousRecoveryConfirmation.current = recoveryConfirmation;
  }, [busy, recoveryConfirmation]);
  return (
    <div className="locked-application" data-application-locked="true">
      <main className="locked-card ro-card ro-stack" aria-labelledby="locked-title">
        <div
          className="locked-surface-content ro-stack"
          aria-hidden={recoveryConfirmation || undefined}
          inert={recoveryConfirmation || undefined}
        >
        <span className="brand-mark" aria-hidden="true">RO</span>
        <Typography id="locked-title" as="h1" variant="page-title">Research Observatory is locked</Typography>
        <p>{reason}</p>
        <p>
          Protected work was stopped and cleared from this view. Unlocking starts a fresh local
          service session and does not reopen a project.
        </p>
        <Panel title="Protection boundary">
          <p>{snapshot.threatDisclosure}</p>
          <p>Use the current Windows user credentials. No Research Observatory or cloud account is required.</p>
        </Panel>
        <p><strong>Configured provider:</strong> {recoveryRequired ? "Recovery required" : provider}</p>
        {snapshot.signInMode === "windows-hello" ? <p role="status"><strong>Windows Hello:</strong> {hello.detail}</p> : null}
        {error ? <p className="locked-error" role="alert">{error}</p> : null}
        {snapshot.retryAfterSeconds > 0 ? (
          <p role="status">Try again in about {snapshot.retryAfterSeconds} seconds.</p>
        ) : null}
        {recoveryRequired ? (
          <Button ref={recoveryTriggerRef} tone="primary" autoFocus disabled={busy || recoveryConfirmation || !onRecovery} onClick={onRecovery}>
            {busy ? "Preparing Windows recovery…" : "Recover with Windows password"}
          </Button>
        ) : (
          <>
            <Button tone="primary" autoFocus disabled={busy || recoveryConfirmation} onClick={onUnlock}>
              {busy ? `Checking ${provider}…` : `Unlock with ${provider}`}
            </Button>
            {helloRecoveryOffered ? (
              <Button ref={recoveryTriggerRef} disabled={busy || recoveryConfirmation || !onRecovery} onClick={onRecovery}>
                Use Windows password recovery
              </Button>
            ) : null}
          </>
        )}
        </div>
        {recoveryConfirmation ? (
          <div
            className="locked-recovery-confirmation ro-notice"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="locked-recovery-title"
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) {
                event.preventDefault();
                onRecoveryDecision?.(false);
              } else if (event.key === "Tab") {
                const first = recoveryCancelRef.current;
                const last = recoveryConfirmRef.current;
                if (!first || !last) return;
                if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first.focus();
                }
              }
            }}
          >
            <Typography id="locked-recovery-title" as="h2" variant="section-title">Confirm recovery to No login</Typography>
            <p>Windows verified the same user. This changes Research Observatory sign-in to No login{recoveryRequired ? " and replaces the invalid app policy" : " after the unavailable Hello provider"}; project protections remain unchanged.</p>
            <div className="dialog-actions ro-action-row">
              <Button ref={recoveryCancelRef} autoFocus disabled={busy} onClick={() => onRecoveryDecision?.(false)}>Keep application locked</Button>
              <Button ref={recoveryConfirmRef} tone="danger" disabled={busy} onClick={() => onRecoveryDecision?.(true)}>Confirm recovery</Button>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}

interface CommandDefinition {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly run: () => void;
}

interface ApplicationRuntimeProps {
  readonly workflowTransport?: CoreApiTransport;
}

function workflowCommandId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function workflowCommandFailure(error: unknown): string {
  if (error instanceof CoreApiClientError) {
    return `${error.problem.title} (${error.problem.code}). ${error.problem.remediation}`;
  }
  return "The workflow action did not complete. Reload Project Home before retrying.";
}

export function ApplicationRuntime({ workflowTransport = packagedProjectTransport }: ApplicationRuntimeProps = {}): ReactNode {
  const [theme, setTheme] = useState<ApplicationTheme>(() => storedTheme(globalThis.window?.localStorage ?? null));
  const [query, setQuery] = useState("");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("Desktop shell ready. No project is open.");
  const [workspace, setWorkspace] = useState<ApplicationWorkspace>("home");
  const [currentProject, setCurrentProject] = useState<ProjectProjection | null>(null);
  const workflowClient = useMemo(() => createCoreApiClient(workflowTransport), [workflowTransport]);
  const [workflowCatalog, setWorkflowCatalog] = useState<WorkflowProfileCatalogProjection | null>(null);
  const [workflowIntent, setWorkflowIntent] = useState<IntentWorkspaceProjection | null>(null);
  const [workflowAuthority, setWorkflowAuthority] = useState<WorkflowAuthoritySnapshot | null>(null);
  const [workflowProgress, setWorkflowProgress] = useState<WorkflowProgressProjection | null>(null);
  const [workflowCommandBusy, setWorkflowCommandBusy] = useState(false);
  const currentProjectRef = useRef<ProjectProjection | null>(currentProject);
  const workflowAuthorityRef = useRef<WorkflowAuthoritySnapshot | null>(workflowAuthority);
  const workflowProgressRef = useRef<WorkflowProgressProjection | null>(workflowProgress);
  const workflowCommandBusyRef = useRef(false);
  const [workflowLoadState, setWorkflowLoadState] = useState<WorkflowNavigationLoadState>("unavailable");
  const [workflowFailure, setWorkflowFailure] = useState<string | null>(null);
  const [supportingReturn, setSupportingReturn] = useState<SupportingReturnContext | null>(null);
  const [applicationLock, setApplicationLock] = useState<ApplicationLockSnapshot>(() => hasNativeRuntime()
    ? {
        ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
        state: "locked",
        reason: "application-restart",
      }
    : DEFAULT_APPLICATION_LOCK_SNAPSHOT);
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const [lockedHelloAvailability, setLockedHelloAvailability] = useState<VerificationAvailability>("checking");
  const [lockedRecoveryConfirmation, setLockedRecoveryConfirmation] = useState(false);
  const [applicationSettingsBlocked, setApplicationSettingsBlocked] = useState(false);
  const commandRef = useRef<HTMLInputElement>(null);
  const homeRef = useRef<HTMLElement>(null);
  const shortcutTriggerRef = useRef<HTMLButtonElement>(null);
  const shortcutCloseRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const applicationSettingsTriggerRef = useRef<HTMLButtonElement>(null);
  const applicationSettingsRestoreFocusRef = useRef<HTMLElement | null>(null);
  const previousWorkspaceRef = useRef<ApplicationWorkspace>("home");
  const workspaceRef = useRef<ApplicationWorkspace>("home");
  const workflowContextLoaderRef = useRef(new WorkflowContextLoader());
  const workflowRequestGuardRef = useRef(new WorkflowRequestGuard());
  const applicationLockRef = useRef(applicationLock);
  const nativeLockSnapshotRef = useRef<ApplicationLockSnapshot | null>(null);
  const lockFailClosedRef = useRef(false);
  const lockedRecoveryControllerRef = useRef<ApplicationSettingsController | null>(null);
  currentProjectRef.current = currentProject;
  workflowAuthorityRef.current = workflowAuthority;
  workflowProgressRef.current = workflowProgress;
  if (lockedRecoveryControllerRef.current === null) {
    lockedRecoveryControllerRef.current = new ApplicationSettingsController({
      invoke: (command, arguments_) => invoke(command, arguments_),
    });
  }

  const applyLockSnapshot = useCallback((snapshot: ApplicationLockSnapshot) => {
    applicationLockRef.current = snapshot;
    setApplicationLock(snapshot);
    if (snapshot.state === "locked") {
      workflowContextLoaderRef.current.invalidate();
      workflowRequestGuardRef.current.invalidate();
      workflowCommandBusyRef.current = false;
      setCurrentProject(null);
      setWorkflowCatalog(null);
      setWorkflowIntent(null);
      setWorkflowAuthority(null);
      setWorkflowProgress(null);
      setWorkflowCommandBusy(false);
      setWorkflowLoadState("unavailable");
      setWorkflowFailure(null);
      setSupportingReturn(null);
      setQuery("");
      setWorkspace("home");
      setShortcutsOpen(false);
    }
  }, []);

  const failClosedApplicationLock = useCallback((message: string) => {
    lockFailClosedRef.current = true;
    applyLockSnapshot(failClosedApplicationLockSnapshot(
      applicationLockRef.current,
      nativeLockSnapshotRef.current,
    ));
    setUnlockError(message);
  }, [applyLockSnapshot]);

  const applyNativeLockSnapshot = useCallback((
    snapshot: ApplicationLockSnapshot,
    source: ApplicationLockSnapshotSource,
  ) => {
    const reconciliation = reconcileApplicationLockSnapshot(
      applicationLockRef.current,
      nativeLockSnapshotRef.current,
      snapshot,
      lockFailClosedRef.current,
      source,
    );
    nativeLockSnapshotRef.current = reconciliation.nativeSnapshot;
    lockFailClosedRef.current = reconciliation.failClosed;
    if (reconciliation.applied) applyLockSnapshot(reconciliation.displaySnapshot);
  }, [applyLockSnapshot]);

  useEffect(() => {
    if (!hasNativeRuntime()) return;
    let disposed = false;
    let unlisten: UnlistenFn | null = null;
    let statusTimer: ReturnType<typeof setInterval> | null = null;
    let statusPending = false;
    const reconcileStatus = (): void => {
      if (disposed || statusPending) return;
      statusPending = true;
      void invokeApplicationLockStatus().then((value) => {
        if (!disposed) {
          try {
            applyNativeLockSnapshot(decodeApplicationLockSnapshot(value), "status");
          } catch {
            failClosedApplicationLock("The application-lock status was invalid. Protected work remains unavailable.");
          }
        }
      }).catch(() => {
        if (!disposed) {
          failClosedApplicationLock("Application-lock status is unavailable. Protected work was not opened.");
        }
      }).finally(() => {
        statusPending = false;
      });
    };
    void registerApplicationLockListener((payload) => {
      if (disposed) return;
      try {
        applyNativeLockSnapshot(decodeApplicationLockSnapshot(payload), "event");
      } catch {
        failClosedApplicationLock("The application-lock response was invalid. Protected work remains unavailable.");
      }
    }).then((cleanup) => {
      if (disposed) {
        void cleanup();
        return;
      }
      unlisten = cleanup;
      reconcileStatus();
      statusTimer = globalThis.setInterval(reconcileStatus, 1_000);
    }).catch(() => {
      if (disposed) return;
      failClosedApplicationLock("Application-lock monitoring is unavailable. Protected work was not opened.");
      reconcileStatus();
      statusTimer = globalThis.setInterval(reconcileStatus, 1_000);
    });
    return () => {
      disposed = true;
      if (statusTimer) globalThis.clearInterval(statusTimer);
      if (unlisten) void unlisten();
    };
  }, [applyNativeLockSnapshot, failClosedApplicationLock]);

  useEffect(() => {
    if (!hasNativeRuntime() || applicationLock.state !== "locked" || applicationLock.signInMode !== "windows-hello") {
      setLockedHelloAvailability("checking");
      return;
    }
    let disposed = false;
    setLockedHelloAvailability("checking");
    void invoke<unknown>("application_lock_hello_availability").then((value) => {
      if (!disposed) setLockedHelloAvailability(decodeVerificationAvailabilitySnapshot(value).availability);
    }).catch(() => {
      if (!disposed) setLockedHelloAvailability("failed");
    });
    return () => { disposed = true; };
  }, [applicationLock.signInMode, applicationLock.state]);

  useEffect(() => {
    if (!hasNativeRuntime() || applicationLock.state === "locked") return;
    let lastForwarded = 0;
    const activity = (): void => {
      const now = Date.now();
      if (now - lastForwarded < 1_000) return;
      lastForwarded = now;
      void invoke("application_lock_activity");
    };
    document.addEventListener("keydown", activity);
    document.addEventListener("pointerdown", activity);
    return () => {
      document.removeEventListener("keydown", activity);
      document.removeEventListener("pointerdown", activity);
    };
  }, [applicationLock.state]);

  const announce = useCallback((message: string) => {
    setAnnouncement("");
    globalThis.window?.requestAnimationFrame(() => setAnnouncement(message));
  }, []);

  const replaceCurrentProject = useCallback((next: ProjectProjection) => {
    workflowRequestGuardRef.current.invalidate();
    currentProjectRef.current = next;
    workflowProgressRef.current = null;
    workflowCommandBusyRef.current = false;
    setWorkflowCommandBusy(false);
    setCurrentProject(next);
  }, []);

  useEffect(() => {
    workspaceRef.current = workspace;
  }, [workspace]);

  useEffect(() => {
    workflowContextLoaderRef.current.invalidate();
    workflowRequestGuardRef.current.invalidate();
    workflowCommandBusyRef.current = false;
    setWorkflowCatalog(null);
    setWorkflowIntent(null);
    setWorkflowAuthority(null);
    setWorkflowProgress(null);
    setWorkflowCommandBusy(false);
    setSupportingReturn(null);
    setWorkflowFailure(null);
    if (!currentProject) {
      setWorkflowLoadState("unavailable");
      return;
    }
    if (!currentProject.open || currentProject.compatibilityState !== "compatible") {
      setWorkflowLoadState("unavailable");
      setWorkflowFailure("Open a compatible local project before loading its guided workflow.");
      return;
    }
    setWorkflowLoadState("loading");
    void workflowContextLoaderRef.current.load(currentProject, workflowClient).then((result) => {
      if (result.kind === "stale") return;
      if (result.kind === "error") {
        setWorkflowLoadState("error");
        setWorkflowFailure(result.message);
        return;
      }
      if (result.kind === "unavailable") {
        setWorkflowLoadState("unavailable");
        setWorkflowFailure(result.reason === "no-current-intent"
          ? "This project has no current Research Intent. Define and save it before guided workflow navigation can begin."
          : result.reason === "project-unavailable"
            ? "Open a compatible local project before loading its guided workflow."
            : "The local Core service returned workflow context for a different project or an unknown profile. Guided navigation remains unavailable.");
        return;
      }
      setWorkflowCatalog(result.catalog);
      setWorkflowIntent(result.intent);
      setWorkflowAuthority(result.authority);
      setWorkflowProgress(result.progress);
      setWorkflowLoadState("ready");
      setWorkflowFailure(null);
      if (workspaceClassification(result.authority, workspaceRef.current).role === "supporting") {
        setSupportingReturn(createSupportingReturn(result.authority, workspaceRef.current, result.progress));
      }
    });
    return () => {
      workflowContextLoaderRef.current.invalidate();
      workflowRequestGuardRef.current.invalidate();
    };
  }, [currentProject, workflowClient]);

  const applyPersistedIntentWorkspace = useCallback((
    next: IntentWorkspaceProjection,
    sourceProject: IntentProjectIdentity,
  ) => {
    const project = currentProjectRef.current;
    if (!project || !persistedIntentUpdateMatchesCurrentProject(project, sourceProject, next)) return;
    workflowContextLoaderRef.current.invalidate();
    workflowRequestGuardRef.current.invalidate();
    workflowCommandBusyRef.current = false;
    setWorkflowIntent(next);
    setWorkflowProgress(null);
    setWorkflowCommandBusy(false);
    setWorkflowLoadState("loading");
    setWorkflowFailure(null);
    setSupportingReturn(null);
    void workflowContextLoaderRef.current.load(project, workflowClient).then((result) => {
      if (result.kind === "stale") return;
      if (result.kind === "error") {
        setWorkflowAuthority(null);
        setWorkflowLoadState("error");
        setWorkflowFailure(result.message);
        return;
      }
      if (result.kind === "unavailable") {
        setWorkflowAuthority(null);
        setWorkflowLoadState("unavailable");
        setWorkflowFailure("The saved Research Intent did not resolve to coherent workflow progress authority.");
        return;
      }
      setWorkflowCatalog(result.catalog);
      setWorkflowIntent(result.intent);
      setWorkflowAuthority(result.authority);
      setWorkflowProgress(result.progress);
      setWorkflowLoadState("ready");
    });
  }, [workflowClient]);

  const authoritativeWorkflowStates = useMemo(() => {
    const states: Record<string, WorkflowStageAuthorityState> = {};
    for (const item of [...(workflowProgress?.history ?? [])].reverse()) {
      if (item.navigationRole === "primary") states[item.stageKey] = item.status;
    }
    if (workflowProgress?.current?.navigationRole === "primary") {
      states[workflowProgress.current.stageKey] = workflowProgress.current.status;
    }
    return states;
  }, [workflowProgress]);

  const applyWorkflowProgress = useCallback((next: WorkflowProgressProjection): WorkflowAuthoritySnapshot | null => {
    workflowProgressRef.current = next;
    setWorkflowProgress(next);
    const authority = workflowAuthorityRef.current;
    let nextAuthority = authority;
    if (authority) {
      const selected = selectPrimaryStage(
        authority,
        next.current?.stageKey ?? next.recommendedStageKey,
      );
      if (selected) {
        workflowAuthorityRef.current = selected.authority;
        setWorkflowAuthority(selected.authority);
        nextAuthority = selected.authority;
      }
    }
    setSupportingReturn(null);
    return nextAuthority;
  }, []);

  const commandWorkflowProgress = useCallback(async (
    action: "start" | "resume" | "revisit",
    revisitSource: WorkflowProgressStage | null = null,
  ) => {
    const project = currentProjectRef.current;
    const progress = workflowProgressRef.current;
    if (!project || !progress || workflowCommandBusyRef.current) return null;
    const commandAuthority = workflowCommandStageAuthority(action, progress, revisitSource);
    if (!commandAuthority) return null;
    const ticket = workflowRequestGuardRef.current.begin(
      action,
      project,
      progress,
      commandAuthority.sourceStage,
    );
    if (!ticket) return null;
    workflowCommandBusyRef.current = true;
    setWorkflowCommandBusy(true);
    try {
      const command = {
        root: project.root,
        action,
        stageKey: commandAuthority.stageKey,
        expectedSelectionRevisionId: progress.selectionRevisionId,
        expectedSelectionRevisionContentHash: progress.selectionRevisionContentHash,
        expectedStageStateRevisionId: commandAuthority.expectedStageStateRevisionId,
        expectedStageStateRevisionContentHash: commandAuthority.expectedStageStateRevisionContentHash,
        revisitSourceStageStateRevisionId: commandAuthority.revisitSourceStageStateRevisionId,
        revisitSourceStageStateRevisionContentHash: commandAuthority.revisitSourceStageStateRevisionContentHash,
        completionEvidenceRevisionIds: [],
        supportingPageContractId: null,
        rationale: null,
      };
      const next = await workflowClient.commandWorkflowProgress(command, workflowCommandId());
      if (!workflowRequestGuardRef.current.acceptsResult(
        ticket,
        currentProjectRef.current,
        workflowProgressRef.current,
        next,
      )) return null;
      applyWorkflowProgress(next);
      announce(action === "start"
        ? "Guided workflow started."
        : action === "resume"
          ? "The workflow step was resumed by the researcher."
          : "A new workflow pass was recorded.");
      return next;
    } catch (error) {
      if (!workflowRequestGuardRef.current.matchesSource(
        ticket,
        currentProjectRef.current,
        workflowProgressRef.current,
      )) return null;
      const message = workflowCommandFailure(error);
      setWorkflowFailure(message);
      announce(message);
      return null;
    } finally {
      if (workflowRequestGuardRef.current.owns(ticket, currentProjectRef.current)) {
        workflowCommandBusyRef.current = false;
        setWorkflowCommandBusy(false);
      }
    }
  }, [announce, applyWorkflowProgress, workflowClient]);

  const navigateWorkspaceState = useCallback((nextWorkspace: ApplicationWorkspace) => {
    workspaceRef.current = nextWorkspace;
    const authority = workflowAuthority;
    if (!authority) {
      setSupportingReturn(null);
      setWorkspace(nextWorkspace);
      return;
    }
    const classification = workspaceClassification(authority, nextWorkspace);
    if (classification.role === "supporting") {
      setSupportingReturn(null);
      const progress = workflowProgress;
      const project = currentProjectRef.current;
      const pageContractId = implementedWorkspace(nextWorkspace).pageContractIds[0];
      if (progress?.current && project && pageContractId) {
        const ticket = workflowRequestGuardRef.current.begin(
          "open-supporting",
          project,
          progress,
          progress.current,
        );
        if (!ticket) {
          setWorkspace(nextWorkspace);
          return;
        }
        const command = {
          root: project.root,
          action: "open-supporting",
          stageKey: progress.current.stageKey,
          expectedSelectionRevisionId: progress.selectionRevisionId,
          expectedSelectionRevisionContentHash: progress.selectionRevisionContentHash,
          expectedStageStateRevisionId: progress.current.stageStateRevisionId,
          expectedStageStateRevisionContentHash: progress.current.revisionContentHash,
          revisitSourceStageStateRevisionId: null,
          revisitSourceStageStateRevisionContentHash: null,
          completionEvidenceRevisionIds: [],
          supportingPageContractId: pageContractId,
          rationale: null,
        } as const;
        void workflowClient.commandWorkflowProgress(command, workflowCommandId()).then((next) => {
          if (!workflowRequestGuardRef.current.acceptsResult(
            ticket,
            currentProjectRef.current,
            workflowProgressRef.current,
            next,
          )) return;
          const nextAuthority = applyWorkflowProgress(next);
          if (
            workspaceRef.current === nextWorkspace
            && nextAuthority
            && workflowRequestGuardRef.current.owns(ticket, currentProjectRef.current)
          ) {
            setSupportingReturn(createSupportingReturn(nextAuthority, nextWorkspace, next));
          }
        }).catch((error: unknown) => {
          if (!workflowRequestGuardRef.current.matchesSource(
            ticket,
            currentProjectRef.current,
            workflowProgressRef.current,
          )) return;
          setSupportingReturn(null);
          const message = workflowCommandFailure(error);
          setWorkflowFailure(message);
          announce(message);
        });
      }
    } else {
      setSupportingReturn(null);
    }
    setWorkspace(nextWorkspace);
  }, [announce, applyWorkflowProgress, workflowAuthority, workflowClient, workflowProgress]);

  const navigateToStage = useCallback((stageKey: string) => {
    if (!workflowAuthority) return;
    const selected = selectPrimaryStage(workflowAuthority, stageKey);
    if (!selected?.workspace) {
      announce("That workflow step is not implemented in this version. The current primary step did not change.");
      return;
    }
    setSupportingReturn(null);
    workspaceRef.current = selected.workspace;
    setWorkspace(selected.workspace);
    announce(`${selected.authority.profile.stages.find((stage) => stage.stageKey === stageKey)?.label ?? "Workflow step"} opened. No completion or checkpoint was recorded.`);
    globalThis.window?.requestAnimationFrame(() => homeRef.current?.focus());
  }, [announce, workflowAuthority]);

  const returnToCurrentWorkflowStage = useCallback(() => {
    if (!supportingReturn || !workflowAuthority) return;
    const selected = supportingReturnMatches(supportingReturn, workflowAuthority, workflowProgress)
      ? selectPrimaryStage(workflowAuthority, workflowAuthority.currentStageKey)
      : null;
    if (!selected?.workspace) {
      announce("The supporting context is stale. Reopen a primary workflow step before returning.");
      return;
    }
    setSupportingReturn(null);
    workspaceRef.current = selected.workspace;
    setWorkspace(selected.workspace);
    announce(`Returned to current workflow step: ${selected.authority.profile.stages.find((stage) => stage.stageKey === selected.authority.currentStageKey)?.label ?? "current step"}.`);
    globalThis.window?.requestAnimationFrame(() => homeRef.current?.focus());
  }, [announce, supportingReturn, workflowAuthority, workflowProgress]);

  const applyTheme = useCallback((next: ApplicationTheme) => {
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("research-observatory.theme", next);
    } catch {
      // Theme persistence is optional; the in-memory selection remains usable.
    }
    announce(`${next === "dark" ? "Dark" : "Light"} theme active.`);
  }, [announce]);

  const openShortcuts = useCallback((trigger?: HTMLElement | null) => {
    if (!restoreFocusRef.current) {
      restoreFocusRef.current = trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    }
    setShortcutsOpen(true);
  }, []);

  const closeShortcuts = useCallback(() => {
    setShortcutsOpen(false);
    const restore = restoreFocusRef.current;
    restoreFocusRef.current = null;
    globalThis.window?.requestAnimationFrame(() => {
      if (restore?.isConnected) restore.focus();
      else shortcutTriggerRef.current?.focus();
    });
  }, []);

  const containShortcutFocus = useCallback((event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Tab") return;
    event.preventDefault();
    shortcutCloseRef.current?.focus();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.body.dataset.applicationReady = "true";
    return () => {
      delete document.body.dataset.applicationReady;
    };
  }, [theme]);

  useEffect(() => {
    if (shortcutsOpen) shortcutCloseRef.current?.focus();
  }, [shortcutsOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const commandShortcut = isShortcut(event, "k", "ctrl");
      const helpShortcut = isShortcut(event, "/", "ctrl");
      const homeShortcut = isShortcut(event, "h", "alt");
      if (applicationSettingsBlocked || lockedRecoveryConfirmation) {
        if (commandShortcut || helpShortcut || homeShortcut) event.preventDefault();
        return;
      }
      if (shortcutsOpen) {
        if (event.key === "Escape") {
          event.preventDefault();
          closeShortcuts();
        } else if (commandShortcut || helpShortcut || homeShortcut) {
          event.preventDefault();
          shortcutCloseRef.current?.focus();
        }
        return;
      }
      if (commandShortcut) {
        event.preventDefault();
        navigateWorkspaceState("home");
        globalThis.window?.requestAnimationFrame(() => commandRef.current?.focus());
      } else if (helpShortcut) {
        event.preventDefault();
        openShortcuts();
      } else if (homeShortcut) {
        event.preventDefault();
        navigateWorkspaceState("home");
        globalThis.window?.requestAnimationFrame(() => homeRef.current?.focus());
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [applicationSettingsBlocked, closeShortcuts, lockedRecoveryConfirmation, navigateWorkspaceState, openShortcuts, shortcutsOpen]);

  const lockNow = useCallback(() => {
    const locked: ApplicationLockSnapshot = {
      ...applicationLock,
      state: "locked",
      profileName: null,
      reason: "manual",
      auditSequence: applicationLock.auditSequence + 1,
    };
    applyLockSnapshot(locked);
    setUnlockError(null);
    if (hasNativeRuntime()) {
      void invoke<unknown>("application_lock_now")
        .then((value) => applyNativeLockSnapshot(decodeApplicationLockSnapshot(value), "status"))
        .catch(() => failClosedApplicationLock("The native lock could not confirm Core shutdown. Keep the application closed until diagnostics are available."));
    }
  }, [applicationLock, applyLockSnapshot, applyNativeLockSnapshot, failClosedApplicationLock]);

  const unlock = useCallback(() => {
    if (!hasNativeRuntime()) return;
    setUnlockBusy(true);
    setUnlockError(null);
    void invoke<unknown>("application_lock_unlock")
      .then((value) => {
        const attempt = decodeApplicationUnlockAttempt(value);
        if (attempt.outcome === "succeeded") {
          applyNativeLockSnapshot(attempt.snapshot, "explicit-unlock");
          setAnnouncement("Application unlocked. No project is open.");
          return;
        }
        applyNativeLockSnapshot(attempt.snapshot, "status");
        if (applicationLockRef.current.signInMode === "windows-hello" && attempt.outcome === "unavailable") {
          setLockedHelloAvailability("unavailable");
        }
        setUnlockError(applicationUnlockFailureMessage(attempt.outcome, attempt.reasonCode));
      })
      .catch(() => {
        setUnlockError("Windows could not verify the current user. The application remains locked.");
        void invokeApplicationLockStatus()
          .then((value) => applyNativeLockSnapshot(decodeApplicationLockSnapshot(value), "status"))
          .catch(() => failClosedApplicationLock("Application-lock status is unavailable. The application remains locked."));
      })
      .finally(() => setUnlockBusy(false));
  }, [applyNativeLockSnapshot, failClosedApplicationLock]);

  const applyLockedRecoveryResult = useCallback((result: TransitionControllerResult) => {
    if (result.kind === "confirmation-required") {
      setLockedRecoveryConfirmation(true);
      setUnlockError(null);
      setAnnouncement(result.message);
      return;
    }
    if (!lockedRecoveryControllerRef.current?.busy) setLockedRecoveryConfirmation(false);
    if (result.snapshot) {
      applyNativeLockSnapshot(
        result.snapshot,
        result.kind === "committed" || result.kind === "reconciled-committed"
          ? "explicit-unlock"
          : "status",
      );
    }
    if (result.kind === "committed" || result.kind === "reconciled-committed") {
      setUnlockError(null);
      setAnnouncement(result.message);
    } else {
      setUnlockError(result.message);
    }
  }, [applyNativeLockSnapshot]);

  const prepareLockedRecovery = useCallback(() => {
    if (!hasNativeRuntime()) return;
    setUnlockBusy(true);
    setUnlockError(null);
    void lockedRecoveryControllerRef.current?.prepareRecovery()
      .then(applyLockedRecoveryResult)
      .finally(() => setUnlockBusy(false));
  }, [applyLockedRecoveryResult]);

  const decideLockedRecovery = useCallback((confirmed: boolean) => {
    setUnlockBusy(true);
    void lockedRecoveryControllerRef.current?.confirm(confirmed)
      .then(applyLockedRecoveryResult)
      .finally(() => setUnlockBusy(false));
  }, [applyLockedRecoveryResult]);

  const openApplicationSettings = useCallback((trigger?: HTMLElement | null) => {
    if (workspace !== "application-settings") {
      previousWorkspaceRef.current = workspace;
      applicationSettingsRestoreFocusRef.current = trigger
        ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    }
    navigateWorkspaceState("application-settings");
    announce("Application Security and sign-in settings opened.");
  }, [announce, navigateWorkspaceState, workspace]);

  const returnFromApplicationSettings = useCallback(() => {
    navigateWorkspaceState(previousWorkspaceRef.current === "application-settings" ? "home" : previousWorkspaceRef.current);
    announce("Returned to the previous workspace.");
    const restore = applicationSettingsRestoreFocusRef.current;
    applicationSettingsRestoreFocusRef.current = null;
    globalThis.window?.requestAnimationFrame(() => {
      if (restore?.isConnected) restore.focus();
      else applicationSettingsTriggerRef.current?.focus();
    });
  }, [announce, navigateWorkspaceState]);

  const commands = useMemo<readonly CommandDefinition[]>(() => [
    {
      id: "open-projects",
      label: "Open local projects",
      description: "Create, open, archive, restore, or delete a governed local project package.",
      run: () => {
        navigateWorkspaceState("projects");
        announce("Local projects workspace opened.");
      },
    },
    {
      id: "open-research-intent",
      label: "Open research intent",
      description: "Define the governed research objective, scope, evidence policy, novelty standard, and stopping logic.",
      run: () => {
        navigateWorkspaceState("intent");
        announce("Research Intent Contract workspace opened.");
      },
    },
    {
      id: "open-project-settings",
      label: "Open project settings",
      description: "Review local privacy, egress, retention, and cache cleanup controls.",
      run: () => {
        navigateWorkspaceState("settings");
        announce("Project privacy and retention settings opened.");
      },
    },
    {
      id: "open-task-center",
      label: "Open Task Center",
      description: "Inspect durable local workflows, resource pools, progress, decisions, retry, cancellation, and logs.",
      run: () => {
        navigateWorkspaceState("tasks");
        announce("Task Center opened.");
      },
    },
    {
      id: "open-application-settings",
      label: "Open application settings",
      description: "Review application-wide Security and sign-in controls for this Windows account.",
      run: () => openApplicationSettings(),
    },
    {
      id: "open-audit-lineage",
      label: "Open audit & lineage",
      description: "Trace exact output revisions through sources, transformations, configurations, actors, and audit events.",
      run: () => {
        navigateWorkspaceState("audit");
        announce("Audit and lineage workspace opened.");
      },
    },
    {
      id: "open-diagnostics",
      label: "Open diagnostics & support",
      description: "Review local health and a redacted support bundle before export.",
      run: () => {
        navigateWorkspaceState("diagnostics");
        announce("Diagnostics and support workspace opened.");
      },
    },
    {
      id: "toggle-theme",
      label: "Toggle color theme",
      description: "Switch between the approved light and dark themes.",
      run: () => applyTheme(nextTheme(theme)),
    },
    {
      id: "keyboard-shortcuts",
      label: "Show keyboard shortcuts",
      description: "Open the keyboard command reference.",
      run: () => openShortcuts(commandRef.current),
    },
  ], [announce, applyTheme, navigateWorkspaceState, openApplicationSettings, openShortcuts, theme]);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleCommands = commands.filter(({ label, description }) =>
    !normalizedQuery || `${label} ${description}`.toLowerCase().includes(normalizedQuery));

  if (applicationLock.state === "locked") {
    return (
      <ApplicationLockedView
        snapshot={applicationLock}
        busy={unlockBusy}
        error={unlockError}
        onUnlock={unlock}
        helloAvailability={lockedHelloAvailability}
        recoveryConfirmation={lockedRecoveryConfirmation}
        onRecovery={prepareLockedRecovery}
        onRecoveryDecision={decideLockedRecovery}
      />
    );
  }

  return (
    <div className="application-shell" data-application-ready="true">
      <a className="skip-link" href="#main-content" onClick={() => homeRef.current?.focus()}>Skip to project home</a>
      <header className="topbar" aria-label="Application">
        <a className="brand" href="#main-content" onClick={() => homeRef.current?.focus()} aria-label="Research Observatory project home">
          <span className="brand-mark" aria-hidden="true">RO</span>
          <span>Research Observatory</span>
        </a>
        <div className="topbar-actions ro-cluster">
          <span className="project-context" data-project-context>
            {currentProject ? `${currentProject.displayName} · ${currentProject.accessMode === "read-only" ? "Read-only" : currentProject.open ? "Open" : currentProject.lifecycleState}` : "No project open"}
          </span>
          <Button ref={applicationSettingsTriggerRef} disabled={applicationSettingsBlocked} onClick={(event) => openApplicationSettings(event.currentTarget)} data-local-profile data-application-settings-trigger>
            {applicationLock.profileName ?? "Local profile"}
          </Button>
          {applicationLock.signInMode === "none" ? null : <Button onClick={lockNow} data-application-lock>Lock</Button>}
          <Button ref={shortcutTriggerRef} disabled={applicationSettingsBlocked} onClick={() => openShortcuts(shortcutTriggerRef.current)} aria-haspopup="dialog" data-shortcut-help>
            Shortcuts
          </Button>
          <Button disabled={applicationSettingsBlocked} onClick={() => applyTheme(nextTheme(theme))} aria-pressed={theme === "dark"} data-theme-toggle>
            Dark theme
          </Button>
        </div>
      </header>

      <div className="shell-body">
        <aside className="sidebar" aria-label="Available workspaces">
          <WorkflowNavigation
            authority={workflowAuthority}
            currentWorkspace={workspace}
            loadState={workflowLoadState}
            failure={workflowFailure}
            authoritativeStates={authoritativeWorkflowStates}
            supportingReturn={supportingReturn}
            disabled={applicationSettingsBlocked || workflowLoadState === "loading"}
            showContext={false}
            onSelectStage={navigateToStage}
            onSelectWorkspace={(nextWorkspace) => {
              if (nextWorkspace === "application-settings") openApplicationSettings();
              else {
                navigateWorkspaceState(nextWorkspace);
                announce(`${nextWorkspace === "home" ? "Project home" : nextWorkspace} opened.`);
              }
            }}
            onReturn={returnToCurrentWorkflowStage}
          />
          <p>Only implemented capabilities appear here.</p>
        </aside>

        <main id="main-content" ref={homeRef} tabIndex={-1}>
          <WorkflowContextBar
            authority={workflowAuthority}
            currentWorkspace={workspace}
            authoritativeStates={authoritativeWorkflowStates}
            supportingReturn={supportingReturn}
            disabled={applicationSettingsBlocked || workflowLoadState === "loading"}
            onSelectStage={navigateToStage}
            onReturn={returnToCurrentWorkflowStage}
          />
          <div
            className="workspace-layer"
            hidden={workspace === "application-settings"}
            aria-hidden={workspace === "application-settings" || undefined}
            inert={workspace === "application-settings" || undefined}
          >
          {(workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "projects" ? (
            <ProjectsWorkspace
              announce={announce}
              selectedProject={currentProject}
              onProjectChange={replaceCurrentProject}
            />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "intent" ? (
            <IntentWorkspace
              project={currentProject}
              announce={announce}
              initialCatalog={workflowCatalog ?? undefined}
              initialWorkspace={workflowIntent ?? undefined}
              onWorkspaceChange={applyPersistedIntentWorkspace}
            />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "tasks" ? (
            <TaskCenterWorkspace project={currentProject} announce={announce} />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "audit" ? (
            <AuditLineageWorkspace project={currentProject} announce={announce} />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "home" ? <>
          <ProjectHomeWorkspace
            project={currentProject}
            progress={workflowProgress}
            loadState={workflowLoadState}
            failure={workflowFailure}
            busy={workflowCommandBusy}
            onStart={() => {
              void commandWorkflowProgress("start").then((next) => {
                if (next) navigateToStage(next.current?.stageKey ?? next.recommendedStageKey);
              });
            }}
            onResume={() => {
              void commandWorkflowProgress("resume").then((next) => {
                if (next) navigateToStage(next.current?.stageKey ?? next.recommendedStageKey);
              });
            }}
            onOpenCurrent={() => {
              if (workflowProgress) {
                navigateToStage(workflowProgress.current?.stageKey ?? workflowProgress.recommendedStageKey);
              }
            }}
            onRevisit={(source) => {
              void commandWorkflowProgress("revisit", source).then((next) => {
                if (next) navigateToStage(next.current?.stageKey ?? next.recommendedStageKey);
              });
            }}
          />

          <section className="command-area ro-card ro-stack" aria-labelledby="command-title">
            <Typography id="command-title" as="h2" variant="section-title">Application commands</Typography>
            <Field
              id="shell-command"
              label="Find a command"
              description="Press Ctrl+K from anywhere in the application."
              inputRef={commandRef}
              input={{
                type: "search",
                value: query,
                onChange: (event) => setQuery(event.currentTarget.value),
                autoComplete: "off",
              }}
            />
            <ul className="command-results" aria-label="Matching commands">
              {visibleCommands.map((command) => (
                <li key={command.id}>
                  <Button data-command-id={command.id} onClick={command.run}>{command.label}</Button>
                  <span>{command.description}</span>
                </li>
              ))}
            </ul>
            {visibleCommands.length === 0 ? <p role="status">No application commands match.</p> : null}
          </section>

          <div className="status-grid ro-grid">
            <Panel title="Desktop shell" tone="success">
              <StatusBadge tone="success">Ready</StatusBadge>
              <p>The signed-development Tauri window and React renderer are running locally.</p>
            </Panel>
            <LocalServiceBoundary announce={announce} />
          </div>
          </> : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "settings" ? (
            <ProjectSettingsWorkspace project={currentProject} announce={announce} />
          ) : (
            <DiagnosticsWorkspace announce={announce} />
          )}
          </div>
          {workspace === "application-settings" ? (
            <ApplicationSettingsWorkspace
              snapshot={applicationLock}
              announce={announce}
              onSnapshot={(snapshot, recovered) => applyNativeLockSnapshot(
                snapshot,
                recovered ? "explicit-unlock" : "status",
              )}
              onReturn={returnFromApplicationSettings}
              onOperationStateChange={setApplicationSettingsBlocked}
            />
          ) : null}
        </main>
      </div>

      <footer className="trust-footer" data-trust-footer>
        This shell runs locally and makes no network requests. Reference prototypes and illustrative research data are not shipped as application screens.
      </footer>

      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-live-region>{announcement}</div>

      {shortcutsOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="shortcut-dialog ro-dialog-surface"
            role="dialog"
            aria-modal="true"
            aria-labelledby="shortcut-title"
            onKeyDown={containShortcutFocus}
          >
            <Typography id="shortcut-title" as="h2" variant="section-title">Keyboard shortcuts</Typography>
            <dl>
              {SHORTCUTS.map((shortcut) => (
                <div key={shortcut.id}><dt><kbd>{shortcut.keys}</kbd></dt><dd>{shortcut.label}</dd></div>
              ))}
            </dl>
            <Button ref={shortcutCloseRef} tone="primary" onClick={closeShortcuts}>Close shortcuts</Button>
          </section>
        </div>
      ) : null}

    </div>
  );
}
