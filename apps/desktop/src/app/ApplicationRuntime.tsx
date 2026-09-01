import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import { Button, Field, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";

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
import { ProjectsWorkspace } from "./ProjectsWorkspace";
import { IntentWorkspace } from "./IntentWorkspace";
import { TaskCenterWorkspace } from "./TaskCenterWorkspace";
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
      <main className="locked-card" aria-labelledby="locked-title">
        <div
          className="locked-surface-content"
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
            className="locked-recovery-confirmation"
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
            <div className="dialog-actions">
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

type ApplicationWorkspace = "projects" | "home" | "intent" | "tasks" | "audit" | "settings" | "application-settings" | "diagnostics";

export function ApplicationRuntime(): ReactNode {
  const [theme, setTheme] = useState<ApplicationTheme>(() => storedTheme(globalThis.window?.localStorage ?? null));
  const [query, setQuery] = useState("");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("Desktop shell ready. No project is open.");
  const [workspace, setWorkspace] = useState<ApplicationWorkspace>("home");
  const [currentProject, setCurrentProject] = useState<ProjectProjection | null>(null);
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
  const applicationLockRef = useRef(applicationLock);
  const nativeLockSnapshotRef = useRef<ApplicationLockSnapshot | null>(null);
  const lockFailClosedRef = useRef(false);
  const lockedRecoveryControllerRef = useRef<ApplicationSettingsController | null>(null);
  if (lockedRecoveryControllerRef.current === null) {
    lockedRecoveryControllerRef.current = new ApplicationSettingsController({
      invoke: (command, arguments_) => invoke(command, arguments_),
    });
  }

  const applyLockSnapshot = useCallback((snapshot: ApplicationLockSnapshot) => {
    applicationLockRef.current = snapshot;
    setApplicationLock(snapshot);
    if (snapshot.state === "locked") {
      setCurrentProject(null);
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
        setWorkspace("home");
        globalThis.window?.requestAnimationFrame(() => commandRef.current?.focus());
      } else if (helpShortcut) {
        event.preventDefault();
        openShortcuts();
      } else if (homeShortcut) {
        event.preventDefault();
        setWorkspace("home");
        globalThis.window?.requestAnimationFrame(() => homeRef.current?.focus());
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [applicationSettingsBlocked, closeShortcuts, lockedRecoveryConfirmation, openShortcuts, shortcutsOpen]);

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
    setWorkspace("application-settings");
    announce("Application Security and sign-in settings opened.");
  }, [announce, workspace]);

  const returnFromApplicationSettings = useCallback(() => {
    setWorkspace(previousWorkspaceRef.current === "application-settings" ? "home" : previousWorkspaceRef.current);
    announce("Returned to the previous workspace.");
    const restore = applicationSettingsRestoreFocusRef.current;
    applicationSettingsRestoreFocusRef.current = null;
    globalThis.window?.requestAnimationFrame(() => {
      if (restore?.isConnected) restore.focus();
      else applicationSettingsTriggerRef.current?.focus();
    });
  }, [announce]);

  const commands = useMemo<readonly CommandDefinition[]>(() => [
    {
      id: "open-projects",
      label: "Open local projects",
      description: "Create, open, archive, restore, or delete a governed local project package.",
      run: () => {
        setWorkspace("projects");
        announce("Local projects workspace opened.");
      },
    },
    {
      id: "open-research-intent",
      label: "Open research intent",
      description: "Define the governed research objective, scope, evidence policy, novelty standard, and stopping logic.",
      run: () => {
        setWorkspace("intent");
        announce("Research Intent Contract workspace opened.");
      },
    },
    {
      id: "open-project-settings",
      label: "Open project settings",
      description: "Review local privacy, egress, retention, and cache cleanup controls.",
      run: () => {
        setWorkspace("settings");
        announce("Project privacy and retention settings opened.");
      },
    },
    {
      id: "open-task-center",
      label: "Open Task Center",
      description: "Inspect durable local workflows, resource pools, progress, decisions, retry, cancellation, and logs.",
      run: () => {
        setWorkspace("tasks");
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
        setWorkspace("audit");
        announce("Audit and lineage workspace opened.");
      },
    },
    {
      id: "open-diagnostics",
      label: "Open diagnostics & support",
      description: "Review local health and a redacted support bundle before export.",
      run: () => {
        setWorkspace("diagnostics");
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
  ], [announce, applyTheme, openApplicationSettings, openShortcuts, theme]);
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
        <div className="topbar-actions">
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
          <nav>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "projects" ? "page" : undefined} onClick={() => setWorkspace("projects")}>Local projects</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "home" ? "page" : undefined} onClick={() => setWorkspace("home")}>Project home</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "intent" ? "page" : undefined} onClick={() => setWorkspace("intent")}>Research intent</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "tasks" ? "page" : undefined} onClick={() => setWorkspace("tasks")}>Task Center</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "audit" ? "page" : undefined} onClick={() => setWorkspace("audit")}>Audit &amp; lineage</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "settings" ? "page" : undefined} onClick={() => setWorkspace("settings")}>Project settings</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "application-settings" ? "page" : undefined} onClick={(event) => openApplicationSettings(event.currentTarget)}>Application settings</button>
            <button type="button" disabled={applicationSettingsBlocked} aria-current={workspace === "diagnostics" ? "page" : undefined} onClick={() => setWorkspace("diagnostics")}>Diagnostics &amp; support</button>
          </nav>
          <p>Only implemented capabilities appear here.</p>
        </aside>

        <main id="main-content" ref={homeRef} tabIndex={-1}>
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
              onProjectChange={setCurrentProject}
            />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "intent" ? (
            <IntentWorkspace project={currentProject} announce={announce} />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "tasks" ? (
            <TaskCenterWorkspace project={currentProject} announce={announce} />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "audit" ? (
            <AuditLineageWorkspace project={currentProject} announce={announce} />
          ) : (workspace === "application-settings" ? previousWorkspaceRef.current : workspace) === "home" ? <><div className="page-header">
            <Typography as="h1" variant="page-title">Desktop foundation</Typography>
            <Typography className="page-subtitle">
              A local, offline application shell. Research workspaces appear only when their capability is implemented.
            </Typography>
          </div>

          <section className="command-area" aria-labelledby="command-title">
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

          <div className="status-grid">
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
            className="shortcut-dialog"
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
