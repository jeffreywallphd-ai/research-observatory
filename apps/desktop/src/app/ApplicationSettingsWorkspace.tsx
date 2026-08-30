import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";

import { Button, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import {
  APPLICATION_LOCK_TIMEOUTS,
  decodeVerificationAvailabilitySnapshot,
  type ApplicationLockSnapshot,
  type SignInMode,
  type VerificationAvailability,
} from "./applicationLock";
import {
  ApplicationSettingsController,
  applicationSettingsDraft,
  helloAvailabilityPresentation,
  lockBehaviorPreview,
  type ApplicationSettingsDraft,
  type ApplicationSettingsTransport,
  type TransitionControllerResult,
} from "./applicationSettings";

const NATIVE_TRANSPORT: ApplicationSettingsTransport = {
  invoke: (command, arguments_) => invoke(command, arguments_),
};

interface ApplicationSettingsWorkspaceProps {
  readonly snapshot: ApplicationLockSnapshot;
  readonly announce: (message: string) => void;
  readonly onSnapshot: (snapshot: ApplicationLockSnapshot, recovered: boolean) => void;
  readonly onReturn: () => void;
  readonly transport?: ApplicationSettingsTransport;
}

function modeLabel(mode: SignInMode): string {
  if (mode === "windows-password") return "Windows password";
  if (mode === "windows-hello") return "Windows Hello";
  return "No login";
}

function sameDraft(left: ApplicationSettingsDraft, right: ApplicationSettingsDraft): boolean {
  return left.mode === right.mode
    && left.profileName === right.profileName
    && left.inactivityTimeoutMinutes === right.inactivityTimeoutMinutes;
}

export function ApplicationSettingsWorkspace({
  snapshot,
  announce,
  onSnapshot,
  onReturn,
  transport = NATIVE_TRANSPORT,
}: ApplicationSettingsWorkspaceProps): ReactNode {
  const [draft, setDraft] = useState<ApplicationSettingsDraft>(() => applicationSettingsDraft(snapshot));
  const [helloAvailability, setHelloAvailability] = useState<VerificationAvailability>("checking");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "success" | "danger" | "info"; message: string } | null>(null);
  const [confirmation, setConfirmation] = useState<TransitionControllerResult & { kind: "confirmation-required" } | null>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const returnRef = useRef<HTMLButtonElement>(null);
  const warningCancelRef = useRef<HTMLButtonElement>(null);
  const warningConfirmRef = useRef<HTMLButtonElement>(null);
  const controller = useMemo(() => new ApplicationSettingsController(transport), [transport]);
  const currentDraft = applicationSettingsDraft(snapshot);
  const preview = lockBehaviorPreview(draft);
  const hello = helloAvailabilityPresentation(helloAvailability);
  const helloSelectable = hello.selectable || snapshot.signInMode === "windows-hello";
  const changed = !sameDraft(draft, currentDraft);

  useEffect(() => {
    let disposed = false;
    void transport.invoke("application_lock_hello_availability").then((value) => {
      if (!disposed) setHelloAvailability(decodeVerificationAvailabilitySnapshot(value).availability);
    }).catch(() => {
      if (!disposed) setHelloAvailability("failed");
    });
    return () => {
      disposed = true;
      if (controller.busy) void controller.confirm(false);
    };
  }, [controller, transport]);

  useEffect(() => {
    if (!busy && confirmation === null) setDraft(applicationSettingsDraft(snapshot));
  }, [busy, confirmation, snapshot]);

  function selectMode(mode: SignInMode): void {
    setFeedback(null);
    setDraft((current) => ({
      ...current,
      mode,
      profileName: mode === "none" ? "" : current.profileName,
      inactivityTimeoutMinutes: mode === "none" ? 0 : current.inactivityTimeoutMinutes,
    }));
  }

  function applyResult(result: TransitionControllerResult, recovered: boolean): void {
    if (result.kind === "confirmation-required") {
      setConfirmation(result);
      setFeedback({ tone: "info", message: result.message });
      announce(result.message);
      return;
    }
    if (result.snapshot) {
      onSnapshot(result.snapshot, recovered && (
        result.kind === "committed" || result.kind === "reconciled-committed"
      ));
    }
    const tone = result.kind === "committed" || result.kind === "reconciled-committed"
      ? "success"
      : result.kind === "cancelled" || result.kind === "unchanged" || result.kind === "busy"
        ? "info"
        : "danger";
    setFeedback({ tone, message: result.message });
    announce(result.message);
    queueMicrotask(() => saveRef.current?.focus());
  }

  async function save(): Promise<void> {
    setBusy(true);
    setFeedback(null);
    try {
      applyResult(await controller.prepare(draft), false);
    } catch {
      const message = "The sign-in draft is invalid. The prior setting remains active.";
      setFeedback({ tone: "danger", message });
      announce(message);
    } finally {
      setBusy(false);
    }
  }

  async function recover(): Promise<void> {
    setBusy(true);
    setFeedback(null);
    try {
      applyResult(await controller.prepareRecovery(), true);
    } finally {
      setBusy(false);
    }
  }

  async function decide(confirmed: boolean): Promise<void> {
    setBusy(true);
    try {
      const result = await controller.confirm(confirmed);
      setConfirmation(null);
      applyResult(result, confirmation?.prepared.reasonCode === "RO-SIGN-IN-RECOVERY-PREPARED");
    } finally {
      setBusy(false);
    }
  }

  async function returnToPreviousWorkspace(): Promise<void> {
    if (confirmation) await decide(false);
    onReturn();
  }

  return (
    <section className="application-settings-workspace" aria-labelledby="application-settings-title" data-application-settings>
      <header className="page-header">
        <div>
          <p className="eyebrow">Application Settings</p>
          <Typography id="application-settings-title" as="h1" variant="page-title">Security &amp; sign-in</Typography>
          <Typography className="page-subtitle">
            Choose whether Research Observatory adds an application-level prompt after Windows sign-in.
          </Typography>
        </div>
        <div className="page-actions">
          <Button ref={returnRef} disabled={busy} onClick={() => void returnToPreviousWorkspace()}>Return</Button>
          <Button ref={saveRef} tone="primary" disabled={busy || !changed || (draft.mode === "windows-hello" && !helloSelectable)} onClick={() => void save()}>
            {busy ? "Working…" : "Save change"}
          </Button>
        </div>
      </header>

      <Panel title="Application-wide · this Windows account">
        <p>This controls only the extra Research Observatory prompt. Windows account isolation, filesystem permissions, project privacy, and Core process protection remain unchanged.</p>
      </Panel>

      <section className="settings-card" aria-labelledby="sign-in-mode-title">
        <div className="settings-card-header">
          <div>
            <Typography id="sign-in-mode-title" as="h2" variant="section-title">App sign-in mode</Typography>
            <p>No login is the default. Windows remains responsible for account access.</p>
          </div>
          <StatusBadge tone="info">Current: {modeLabel(snapshot.signInMode)}</StatusBadge>
        </div>
        <fieldset className="choice-fieldset" disabled={busy}>
          <legend className="visually-hidden">Choose app sign-in mode</legend>
          <div className="mode-grid">
            <label className="mode-card">
              <span><input type="radio" name="sign-in-mode" checked={draft.mode === "none"} onChange={() => selectMode("none")} /> <strong>No login</strong> <StatusBadge tone="success">Default</StatusBadge></span>
              <span>Open directly after Windows sign-in. No app startup, manual, or inactivity reauthentication.</span>
              <small>Best for a typical single-user PC protected by Windows.</small>
            </label>
            <label className="mode-card">
              <span><input type="radio" name="sign-in-mode" checked={draft.mode === "windows-password"} onChange={() => selectMode("windows-password")} /> <strong>Windows password</strong></span>
              <span>Use the native Windows credential prompt for the same Windows account.</span>
              <small>Research Observatory never receives or stores the password.</small>
            </label>
            <label className={`mode-card${helloSelectable ? "" : " mode-card-disabled"}`}>
              <span><input type="radio" name="sign-in-mode" checked={draft.mode === "windows-hello"} disabled={!helloSelectable} onChange={() => selectMode("windows-hello")} /> <strong>Windows Hello</strong> <StatusBadge tone={hello.tone}>{hello.label}</StatusBadge></span>
              <span>Ask Windows Hello for current-user presence using a PIN, face, or fingerprint configured by Windows.</span>
              <small>The app never receives or stores a PIN or biometric.</small>
            </label>
          </div>
        </fieldset>
        <div className="settings-warning" role="note">
          <strong>Reducing protection requires proof first.</strong>
          <span> Switching a protected mode to No login verifies the current provider or an explicitly selected same-user Windows password recovery prompt before confirmation.</span>
        </div>
      </section>

      <div className="settings-grid">
        <section className="settings-card" aria-labelledby="behavior-preview-title">
          <div className="settings-card-header">
            <Typography id="behavior-preview-title" as="h2" variant="section-title">Lock behavior preview</Typography>
            <StatusBadge tone={draft.mode === "none" ? "info" : "success"}>{draft.mode === "none" ? "Disabled in No login" : "Preview"}</StatusBadge>
          </div>
          <label htmlFor="application-profile-name">Local profile name (optional)</label>
          <input
            id="application-profile-name"
            value={draft.profileName}
            maxLength={80}
            autoComplete="off"
            disabled={busy || draft.mode === "none"}
            onChange={(event) => setDraft({ ...draft, profileName: event.currentTarget.value })}
          />
          <label htmlFor="application-lock-timeout">Lock after inactivity</label>
          <select
            id="application-lock-timeout"
            value={draft.inactivityTimeoutMinutes}
            disabled={busy || draft.mode === "none"}
            onChange={(event) => setDraft({
              ...draft,
              inactivityTimeoutMinutes: Number(event.currentTarget.value) as ApplicationSettingsDraft["inactivityTimeoutMinutes"],
            })}
          >
            {APPLICATION_LOCK_TIMEOUTS.map((minutes) => (
              <option key={minutes} value={minutes}>{minutes === 0 ? "Disabled" : `${minutes} minutes`}</option>
            ))}
          </select>
          <dl className="settings-preview">
            <dt>Startup</dt><dd>{preview.startup}</dd>
            <dt>Manual lock</dt><dd>{preview.manual}</dd>
            <dt>Idle lock</dt><dd>{preview.inactivity}</dd>
            <dt>Restart</dt><dd>{preview.restart}</dd>
            <dt>Recovery</dt><dd>{preview.recovery}</dd>
            <dt>Project protection</dt><dd>{preview.projectProtection}</dd>
          </dl>
        </section>

        <section className="settings-card" aria-labelledby="provider-status-title">
          <div className="settings-card-header">
            <Typography id="provider-status-title" as="h2" variant="section-title">Provider status &amp; recovery</Typography>
            <StatusBadge tone={hello.tone}>{hello.label}</StatusBadge>
          </div>
          <p><strong>Windows Hello:</strong> {hello.detail}</p>
          <p>Availability comes from Windows and is never inferred. A non-success state never falls back automatically.</p>
          <p><strong>Windows password recovery:</strong> Explicit same-user recovery only; it is never a silent fallback.</p>
          {(snapshot.configurationState === "invalid" || snapshot.signInMode === "windows-hello") ? (
            <Button disabled={busy} onClick={() => void recover()}>Use Windows password recovery</Button>
          ) : null}
        </section>
      </div>

      <Panel title="Before a change is applied">
        <ol>
          <li>The native boundary verifies the configured and destination providers.</li>
          <li>Protection-reducing changes show a warning only after native proof.</li>
          <li>The versioned policy is published only after deliberate confirmation and atomic persistence.</li>
          <li>Cancellation, denial, busy, unavailability, write failure, conflict, or expiry keeps the prior policy active.</li>
        </ol>
      </Panel>

      {feedback ? <p className={`settings-feedback settings-feedback-${feedback.tone}`} role={feedback.tone === "danger" ? "alert" : "status"}>{feedback.message}</p> : null}

      {confirmation ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="protection-warning-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="protection-warning-title"
            aria-describedby="protection-warning-description"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                void decide(false);
              } else if (event.key === "Tab") {
                const first = warningCancelRef.current;
                const last = warningConfirmRef.current;
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
            <Typography id="protection-warning-title" as="h2" variant="section-title">Confirm reduced application protection</Typography>
            <p id="protection-warning-description">Windows verified the same user. No login removes Research Observatory startup, manual, and inactivity reauthentication; Windows and project protections remain unchanged.</p>
            <div className="dialog-actions">
              <Button ref={warningCancelRef} autoFocus disabled={busy} onClick={() => void decide(false)}>Keep current protection</Button>
              <Button ref={warningConfirmRef} tone="danger" disabled={busy} onClick={() => void decide(true)}>Confirm No login</Button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
