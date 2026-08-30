import {
  decodeApplicationLockSnapshot,
  decodePolicyTransitionResult,
  normalizeLocalProfileName,
  type ApplicationLockSnapshot,
  type PolicyTransitionResult,
  type SignInMode,
  type VerificationAvailability,
} from "./applicationLock";

export interface ApplicationSettingsDraft {
  readonly mode: SignInMode;
  readonly profileName: string;
  readonly inactivityTimeoutMinutes: 0 | 5 | 15 | 30 | 60;
}

export interface LockBehaviorPreview {
  readonly startup: string;
  readonly manual: string;
  readonly inactivity: string;
  readonly restart: string;
  readonly recovery: string;
  readonly projectProtection: "Unchanged";
}

export interface AvailabilityPresentation {
  readonly label: string;
  readonly detail: string;
  readonly selectable: boolean;
  readonly tone: "success" | "info" | "warning" | "danger";
}

export interface ApplicationSettingsTransport {
  invoke(command: string, arguments_?: Record<string, unknown>): Promise<unknown>;
}

export type TransitionControllerResult =
  | {
      readonly kind: "confirmation-required";
      readonly message: string;
      readonly prepared: PolicyTransitionResult;
    }
  | {
      readonly kind: "committed" | "reconciled-committed";
      readonly message: string;
      readonly snapshot: ApplicationLockSnapshot;
    }
  | {
      readonly kind: "cancelled" | "rejected" | "unchanged" | "busy";
      readonly message: string;
      readonly snapshot?: ApplicationLockSnapshot;
    };

export function applicationSettingsDraft(snapshot: ApplicationLockSnapshot): ApplicationSettingsDraft {
  return {
    mode: snapshot.signInMode,
    profileName: snapshot.profileName ?? "",
    inactivityTimeoutMinutes: snapshot.inactivityTimeoutMinutes,
  };
}

export function lockBehaviorPreview(draft: ApplicationSettingsDraft): LockBehaviorPreview {
  if (draft.mode === "none") {
    return {
      startup: "Open without an app prompt",
      manual: "Unavailable in No login",
      inactivity: "Unavailable in No login",
      restart: "Open without an app prompt",
      recovery: "Not required",
      projectProtection: "Unchanged",
    };
  }
  const provider = draft.mode === "windows-hello" ? "Windows Hello" : "Windows password";
  return {
    startup: `Require ${provider}`,
    manual: `Lock and require ${provider}`,
    inactivity: draft.inactivityTimeoutMinutes === 0
      ? "Disabled; manual lock remains available"
      : `Lock after ${draft.inactivityTimeoutMinutes} minutes`,
    restart: `Require ${provider}`,
    recovery: draft.mode === "windows-hello"
      ? "Explicit same-user Windows password recovery only"
      : "Use Windows password",
    projectProtection: "Unchanged",
  };
}

export function helloAvailabilityPresentation(
  availability: VerificationAvailability,
): AvailabilityPresentation {
  switch (availability) {
    case "checking":
      return { label: "Checking", detail: "Checking Windows Hello availability.", selectable: false, tone: "info" };
    case "available":
      return { label: "Ready", detail: "Available for this Windows account.", selectable: true, tone: "success" };
    case "not-present":
      return { label: "Not present", detail: "This device does not report a Windows Hello provider.", selectable: false, tone: "warning" };
    case "not-configured":
      return { label: "Not configured", detail: "Set up Windows Hello in Windows before selecting it here.", selectable: false, tone: "warning" };
    case "policy-disabled":
      return { label: "Disabled by policy", detail: "Windows policy has disabled Hello for this account.", selectable: false, tone: "warning" };
    case "busy":
      return { label: "Busy", detail: "Windows Hello is temporarily busy. Try again without changing modes.", selectable: false, tone: "info" };
    case "unavailable":
      return { label: "Unavailable", detail: "Windows Hello is unavailable for this session.", selectable: false, tone: "warning" };
    case "failed":
      return { label: "Check failed", detail: "Windows could not report Hello availability.", selectable: false, tone: "danger" };
  }
}

function transitionFailureMessage(result: PolicyTransitionResult): string {
  switch (result.outcome) {
    case "cancelled":
      return "The native verification or confirmation was cancelled. The prior setting remains active.";
    case "busy":
      return "Another native verification is already in progress. The prior setting remains active.";
    case "unavailable":
      return "The selected Windows verification provider is unavailable. No fallback was used.";
    case "conflict":
      return "The setting changed elsewhere before this request completed. Refresh and try again.";
    case "expired":
      return "The verified change expired before confirmation. The prior setting remains active.";
    case "denied":
      return result.reasonCode === "RO-SIGN-IN-TRANSITION-RECOVERY-REQUIRED"
        ? "The stored policy is invalid. Use explicit Windows password recovery."
        : "Windows did not authorize this sign-in change. The prior setting remains active.";
    case "failed":
      return "The sign-in change could not be persisted. The prior setting remains active.";
    default:
      return "The sign-in change did not complete. The prior setting remains active.";
  }
}

export class ApplicationSettingsController {
  private operationInProgress = false;
  private pending: PolicyTransitionResult | null = null;

  public constructor(private readonly transport: ApplicationSettingsTransport) {}

  public get busy(): boolean {
    return this.operationInProgress || this.pending !== null;
  }

  public async prepare(draft: ApplicationSettingsDraft): Promise<TransitionControllerResult> {
    const profileName = draft.mode === "none" ? null : normalizeLocalProfileName(draft.profileName);
    const inactivityTimeoutMinutes = draft.mode === "none" ? 0 : draft.inactivityTimeoutMinutes;
    return this.prepareWith("application_sign_in_transition_prepare", {
      targetMode: draft.mode,
      profileName,
      inactivityTimeoutMinutes,
    });
  }

  public async prepareRecovery(): Promise<TransitionControllerResult> {
    return this.prepareWith("application_sign_in_password_recovery_prepare");
  }

  private async prepareWith(
    command: "application_sign_in_transition_prepare" | "application_sign_in_password_recovery_prepare",
    arguments_?: Record<string, unknown>,
  ): Promise<TransitionControllerResult> {
    if (this.operationInProgress || this.pending !== null) {
      return { kind: "busy", message: "A sign-in change is already awaiting native completion." };
    }
    this.operationInProgress = true;
    let result: PolicyTransitionResult;
    try {
      result = decodePolicyTransitionResult(await this.transport.invoke(command, arguments_));
    } catch {
      return {
        kind: "rejected",
        message: "Windows could not prepare the sign-in change. The prior setting remains active.",
      };
    } finally {
      this.operationInProgress = false;
    }
    if (result.outcome !== "prepared") {
      return { kind: result.outcome === "cancelled" ? "cancelled" : "rejected", message: transitionFailureMessage(result) };
    }
    this.pending = result;
    if (result.warningRequired) {
      return {
        kind: "confirmation-required",
        message: "Windows verified the current user. Confirm the protection-reducing change.",
        prepared: result,
      };
    }
    return this.confirm(true);
  }

  public async confirm(confirmed: boolean): Promise<TransitionControllerResult> {
    if (this.operationInProgress) {
      return { kind: "busy", message: "A sign-in change is already awaiting native completion." };
    }
    const prepared = this.pending;
    if (!prepared?.handle) {
      return { kind: "rejected", message: "No verified sign-in change is awaiting confirmation." };
    }
    this.operationInProgress = true;
    try {
      const result = decodePolicyTransitionResult(await this.transport.invoke(
        "application_sign_in_transition_commit",
        { handle: prepared.handle, confirmed },
      ));
      this.pending = null;
      if (result.outcome === "committed") {
        return {
          kind: "committed",
          message: "Application sign-in settings were saved by the native policy service.",
          snapshot: result.snapshot,
        };
      }
      return {
        kind: result.outcome === "cancelled" ? "cancelled" : "rejected",
        message: transitionFailureMessage(result),
        snapshot: result.snapshot,
      };
    } catch {
      return this.reconcileInterruptedCommit(prepared);
    } finally {
      this.operationInProgress = false;
    }
  }

  private async reconcileInterruptedCommit(
    prepared: PolicyTransitionResult,
  ): Promise<TransitionControllerResult> {
    try {
      const snapshot = decodeApplicationLockSnapshot(
        await this.transport.invoke("application_lock_status"),
      );
      if (
        snapshot.signInMode === prepared.targetMode
        && snapshot.configurationState === "valid"
        && snapshot.policyRevision > prepared.snapshot.policyRevision
      ) {
        this.pending = null;
        return {
          kind: "reconciled-committed",
          message: "The response was interrupted; native status confirms the sign-in change was saved.",
          snapshot,
        };
      }
      try {
        const cancellation = decodePolicyTransitionResult(await this.transport.invoke(
          "application_sign_in_transition_commit",
          { handle: prepared.handle, confirmed: false },
        ));
        this.pending = null;
        if (cancellation.outcome === "committed") {
          return {
            kind: "reconciled-committed",
            message: "The response was interrupted; the native receipt confirms the sign-in change was saved.",
            snapshot: cancellation.snapshot,
          };
        }
      } catch {
        this.pending = null;
        return {
          kind: "rejected",
          message: "Native sign-in status is unchanged, but transition cleanup could not be confirmed. Refresh before retrying.",
          snapshot,
        };
      }
      return {
        kind: "unchanged",
        message: "The response was interrupted; native status confirms the prior setting remains active.",
        snapshot,
      };
    } catch {
      this.pending = null;
      return {
        kind: "rejected",
        message: "The native response was interrupted and status could not be reconciled. Refresh before retrying.",
      };
    }
  }
}
