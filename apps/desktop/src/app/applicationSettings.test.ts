import { describe, expect, it } from "vitest";

import {
  DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  type ApplicationLockSnapshot,
} from "./applicationLock";
import {
  ApplicationSettingsController,
  helloAvailabilityPresentation,
  lockBehaviorPreview,
  type ApplicationSettingsDraft,
  type ApplicationSettingsTransport,
} from "./applicationSettings";

const HANDLE = "ab".repeat(32);
const PASSWORD_SNAPSHOT: ApplicationLockSnapshot = {
  ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  signInMode: "windows-password",
  policyRevision: 2,
  profileName: "Local researcher",
  inactivityTimeoutMinutes: 15,
  auditSequence: 2,
};

function transition(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    schemaVersion: "1.0",
    outcome: "prepared",
    reasonCode: "RO-SIGN-IN-TRANSITION-PREPARED",
    handle: HANDLE,
    sourceMode: "windows-password",
    targetMode: "none",
    warningRequired: true,
    snapshot: PASSWORD_SNAPSHOT,
    ...overrides,
  };
}

class QueueTransport implements ApplicationSettingsTransport {
  public readonly calls: Array<{ command: string; arguments_?: Record<string, unknown> }> = [];

  public constructor(private readonly queue: Array<unknown | Error | (() => Promise<unknown>)>) {}

  public async invoke(command: string, arguments_?: Record<string, unknown>): Promise<unknown> {
    this.calls.push(arguments_ === undefined ? { command } : { command, arguments_ });
    const next = this.queue.shift();
    if (next instanceof Error) throw next;
    if (typeof next === "function") return next();
    return next;
  }
}

describe("application settings model", () => {
  it("previews every lock boundary without turning a draft into current policy", () => {
    const none: ApplicationSettingsDraft = { mode: "none", profileName: "", inactivityTimeoutMinutes: 0 };
    expect(lockBehaviorPreview(none)).toEqual({
      startup: "Open without an app prompt",
      manual: "Unavailable in No login",
      inactivity: "Unavailable in No login",
      restart: "Open without an app prompt",
      recovery: "Not required",
      projectProtection: "Unchanged",
    });
    expect(lockBehaviorPreview({ mode: "windows-password", profileName: "", inactivityTimeoutMinutes: 0 }))
      .toMatchObject({
        startup: "Open without an app prompt; manual lock remains available",
        manual: "Lock and require Windows password",
        inactivity: "Disabled; manual lock remains available",
        restart: "Open without an app prompt; manual lock remains available",
      });
    expect(lockBehaviorPreview({ mode: "windows-hello", profileName: "", inactivityTimeoutMinutes: 30 }))
      .toMatchObject({ startup: "Require Windows Hello", inactivity: "Lock after 30 minutes", recovery: "Explicit same-user Windows password recovery only" });
  });

  it("maps every typed Hello availability without fallback", () => {
    for (const availability of [
      "checking",
      "not-present",
      "not-configured",
      "policy-disabled",
      "busy",
      "unavailable",
      "failed",
    ] as const) {
      expect(helloAvailabilityPresentation(availability).selectable).toBe(false);
    }
    expect(helloAvailabilityPresentation("available")).toMatchObject({ label: "Ready", selectable: true });
  });
});

describe("native application settings controller", () => {
  it("requires native proof before warning and sends commit(false) on cancellation", async () => {
    const transport = new QueueTransport([
      transition({}),
      transition({
        outcome: "cancelled",
        reasonCode: "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
        handle: null,
      }),
    ]);
    const controller = new ApplicationSettingsController(transport);

    const prepared = await controller.prepare({ mode: "none", profileName: "ignored", inactivityTimeoutMinutes: 0 });
    expect(prepared).toMatchObject({ kind: "confirmation-required" });
    expect(transport.calls).toEqual([{
      command: "application_sign_in_transition_prepare",
      arguments_: { targetMode: "none", profileName: null, inactivityTimeoutMinutes: 0 },
    }]);

    const cancelled = await controller.confirm(false);
    expect(cancelled).toMatchObject({ kind: "cancelled" });
    expect(transport.calls[1]).toEqual({
      command: "application_sign_in_transition_commit",
      arguments_: { handle: HANDLE, confirmed: false },
    });
  });

  it("auto-commits a non-reducing change only after native preparation", async () => {
    const prepared = transition({
      sourceMode: "none",
      targetMode: "windows-password",
      warningRequired: false,
      snapshot: DEFAULT_APPLICATION_LOCK_SNAPSHOT,
    });
    const committedSnapshot = {
      ...PASSWORD_SNAPSHOT,
      profileName: null,
      inactivityTimeoutMinutes: 5,
    };
    const transport = new QueueTransport([
      prepared,
      transition({
        outcome: "committed",
        reasonCode: "RO-SIGN-IN-TRANSITION-COMMITTED",
        handle: null,
        sourceMode: "none",
        targetMode: "windows-password",
        warningRequired: false,
        snapshot: committedSnapshot,
      }),
    ]);
    const result = await new ApplicationSettingsController(transport).prepare({
      mode: "windows-password",
      profileName: "",
      inactivityTimeoutMinutes: 5,
    });

    expect(result).toMatchObject({ kind: "committed", snapshot: { signInMode: "windows-password" } });
    expect(transport.calls.map(({ command }) => command)).toEqual([
      "application_sign_in_transition_prepare",
      "application_sign_in_transition_commit",
    ]);
    expect(transport.calls[1]?.arguments_).toMatchObject({ confirmed: true });
  });

  it("excludes overlapping transitions while native preparation is unresolved", async () => {
    let resolvePrepare: ((value: unknown) => void) | undefined;
    const pending = new Promise<unknown>((resolve) => { resolvePrepare = resolve; });
    const transport = new QueueTransport([() => pending]);
    const controller = new ApplicationSettingsController(transport);
    const first = controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });
    const second = await controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });

    expect(second).toMatchObject({ kind: "busy" });
    expect(transport.calls).toHaveLength(1);
    resolvePrepare?.(transition({}));
    await expect(first).resolves.toMatchObject({ kind: "confirmation-required" });
  });

  it("cancels a handle that arrives after the settings session is disposed", async () => {
    let resolvePrepare: ((value: unknown) => void) | undefined;
    const pending = new Promise<unknown>((resolve) => { resolvePrepare = resolve; });
    const transport = new QueueTransport([
      () => pending,
      transition({
        outcome: "cancelled",
        reasonCode: "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
        handle: null,
      }),
    ]);
    const controller = new ApplicationSettingsController(transport);
    const preparation = controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });
    await controller.dispose();
    resolvePrepare?.(transition({}));

    await expect(preparation).resolves.toMatchObject({ kind: "cancelled" });
    expect(controller.busy).toBe(false);
    expect(transport.calls.map(({ command }) => command)).toEqual([
      "application_sign_in_transition_prepare",
      "application_sign_in_transition_commit",
    ]);
    expect(transport.calls[1]?.arguments_).toMatchObject({ confirmed: false });
  });

  it("reconciles native status before claiming success after commit-response loss", async () => {
    const committedSnapshot = { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, policyRevision: 3, auditSequence: 3 };
    const transport = new QueueTransport([
      transition({}),
      new Error("response lost"),
      committedSnapshot,
    ]);
    const controller = new ApplicationSettingsController(transport);
    await controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });
    const result = await controller.confirm(true);

    expect(result).toMatchObject({ kind: "reconciled-committed", snapshot: committedSnapshot });
    expect(transport.calls.map(({ command }) => command)).toEqual([
      "application_sign_in_transition_prepare",
      "application_sign_in_transition_commit",
      "application_lock_status",
    ]);
  });

  it("uses only the explicit same-user recovery command and still requires confirmation", async () => {
    const invalidSnapshot: ApplicationLockSnapshot = {
      ...PASSWORD_SNAPSHOT,
      state: "locked",
      profileName: null,
      configurationState: "invalid",
      reason: "configuration-invalid",
    };
    const transport = new QueueTransport([
      transition({
        reasonCode: "RO-SIGN-IN-RECOVERY-PREPARED",
        sourceMode: null,
        snapshot: invalidSnapshot,
      }),
      transition({
        outcome: "committed",
        reasonCode: "RO-SIGN-IN-RECOVERY-COMMITTED",
        handle: null,
        sourceMode: null,
        snapshot: { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, policyRevision: 3, auditSequence: 3 },
      }),
    ]);
    const controller = new ApplicationSettingsController(transport);

    await expect(controller.prepareRecovery()).resolves.toMatchObject({ kind: "confirmation-required" });
    await expect(controller.confirm(true)).resolves.toMatchObject({ kind: "committed" });
    expect(transport.calls.map(({ command }) => command)).toEqual([
      "application_sign_in_password_recovery_prepare",
      "application_sign_in_transition_commit",
    ]);
  });

  it("clears typed native commit failure authority before allowing a fresh retry", async () => {
    const transport = new QueueTransport([
      transition({}),
      transition({
        outcome: "failed",
        reasonCode: "RO-SIGN-IN-TRANSITION-WRITE-FAILED",
        handle: null,
      }),
      transition({
        outcome: "cancelled",
        reasonCode: "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
        handle: null,
      }),
    ]);
    const controller = new ApplicationSettingsController(transport);
    await controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });

    await expect(controller.confirm(true)).resolves.toMatchObject({
      kind: "rejected",
      message: expect.stringContaining("retry is safe"),
    });
    expect(controller.busy).toBe(false);
    expect(transport.calls[2]?.arguments_).toMatchObject({ confirmed: false });
  });

  it("retains an uncertain handle until later cancellation is confirmed", async () => {
    const transport = new QueueTransport([
      transition({}),
      new Error("commit response lost"),
      new Error("status unavailable"),
      transition({
        outcome: "cancelled",
        reasonCode: "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
        handle: null,
      }),
    ]);
    const controller = new ApplicationSettingsController(transport);
    await controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });

    await expect(controller.confirm(true)).resolves.toMatchObject({
      kind: "rejected",
      message: expect.stringContaining("Retry cancellation"),
    });
    expect(controller.busy).toBe(true);
    await expect(controller.confirm(false)).resolves.toMatchObject({ kind: "cancelled" });
    expect(controller.busy).toBe(false);
  });

  it("rejects malformed native payloads without creating renderer policy authority", async () => {
    const controller = new ApplicationSettingsController(new QueueTransport([{ outcome: "prepared" }]));
    await expect(controller.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 }))
      .resolves.toMatchObject({ kind: "rejected" });
  });
});
