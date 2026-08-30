export type ApplicationLockState = "locked" | "unlocked";
export type ApplicationLockReason =
  | "manual"
  | "inactivity"
  | "application-restart"
  | "configuration-invalid";
export type LockConfigurationState = "default" | "valid" | "invalid";

export interface ApplicationLockSnapshot {
  readonly schemaVersion: "1.0";
  readonly state: ApplicationLockState;
  readonly profileName: string | null;
  readonly inactivityTimeoutMinutes: 0 | 5 | 15 | 30 | 60;
  readonly configurationState: LockConfigurationState;
  readonly reason: ApplicationLockReason | null;
  readonly reauthentication: "windows-current-user-credentials-same-sid";
  readonly threatDisclosure: "Application-session protection only; this is not Windows-account isolation.";
  readonly retryAfterSeconds: number;
  readonly auditSequence: number;
}

export type VerificationOutcome =
  | "succeeded"
  | "cancelled"
  | "denied"
  | "unavailable"
  | "busy"
  | "failed";

export interface ApplicationUnlockAttempt {
  readonly schemaVersion: "1.0";
  readonly outcome: VerificationOutcome;
  readonly reasonCode: string;
  readonly snapshot: ApplicationLockSnapshot;
}

export const APPLICATION_LOCK_TIMEOUTS = [0, 5, 15, 30, 60] as const;

export const DEFAULT_APPLICATION_LOCK_SNAPSHOT: ApplicationLockSnapshot = Object.freeze({
  schemaVersion: "1.0",
  state: "unlocked",
  profileName: null,
  inactivityTimeoutMinutes: 0,
  configurationState: "default",
  reason: null,
  reauthentication: "windows-current-user-credentials-same-sid",
  threatDisclosure: "Application-session protection only; this is not Windows-account isolation.",
  retryAfterSeconds: 0,
  auditSequence: 0,
});

export type ApplicationLockSnapshotSource = "event" | "status" | "explicit-unlock";

export interface ApplicationLockReconciliation {
  readonly displaySnapshot: ApplicationLockSnapshot;
  readonly nativeSnapshot: ApplicationLockSnapshot | null;
  readonly failClosed: boolean;
  readonly applied: boolean;
}

const SNAPSHOT_KEYS = [
  "auditSequence",
  "configurationState",
  "inactivityTimeoutMinutes",
  "profileName",
  "reauthentication",
  "reason",
  "retryAfterSeconds",
  "schemaVersion",
  "state",
  "threatDisclosure",
] as const;

const UNLOCK_ATTEMPT_KEYS = ["outcome", "reasonCode", "schemaVersion", "snapshot"] as const;
const UNLOCK_REASON_CODES: Readonly<Record<VerificationOutcome, readonly string[]>> = Object.freeze({
  succeeded: ["RO-LOCK-UNLOCKED"],
  cancelled: ["RO-LOCK-AUTH-CANCELLED"],
  denied: ["RO-LOCK-AUTH-DENIED"],
  unavailable: ["RO-LOCK-AUTH-UNAVAILABLE"],
  busy: ["RO-LOCK-AUTH-BUSY", "RO-LOCK-RATE-LIMITED"],
  failed: [
    "RO-LOCK-AUTH-FAILED",
    "RO-LOCK-AUTH-NOT-LOCKED",
    "RO-LOCK-AUTH-STALE",
    "RO-LOCK-CORE-UNAVAILABLE",
  ],
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function normalizeLocalProfileName(value: string): string | null {
  const normalized = value.trim();
  if (normalized.length === 0) return null;
  if ([...normalized].length > 80 || [...normalized].some((character) => /\p{Cc}/u.test(character))) {
    throw new Error("Profile name must be 80 characters or fewer and contain no control characters.");
  }
  return normalized;
}

export function failClosedApplicationLockSnapshot(
  current: ApplicationLockSnapshot,
): ApplicationLockSnapshot {
  return {
    ...current,
    state: "locked",
    profileName: null,
    configurationState: "invalid",
    reason: "configuration-invalid",
    retryAfterSeconds: 0,
  };
}

function sameNativeRevision(
  left: ApplicationLockSnapshot,
  right: ApplicationLockSnapshot,
): boolean {
  return left.schemaVersion === right.schemaVersion
    && left.state === right.state
    && left.profileName === right.profileName
    && left.inactivityTimeoutMinutes === right.inactivityTimeoutMinutes
    && left.configurationState === right.configurationState
    && left.reason === right.reason
    && left.reauthentication === right.reauthentication
    && left.threatDisclosure === right.threatDisclosure
    && left.auditSequence === right.auditSequence;
}

export function reconcileApplicationLockSnapshot(
  displaySnapshot: ApplicationLockSnapshot,
  previousNativeSnapshot: ApplicationLockSnapshot | null,
  incoming: ApplicationLockSnapshot,
  failClosed: boolean,
  source: ApplicationLockSnapshotSource,
): ApplicationLockReconciliation {
  if (previousNativeSnapshot && incoming.auditSequence < previousNativeSnapshot.auditSequence) {
    return {
      displaySnapshot,
      nativeSnapshot: previousNativeSnapshot,
      failClosed,
      applied: false,
    };
  }
  if (
    previousNativeSnapshot
    && incoming.auditSequence === previousNativeSnapshot.auditSequence
    && !sameNativeRevision(previousNativeSnapshot, incoming)
  ) {
    return {
      displaySnapshot: failClosedApplicationLockSnapshot(displaySnapshot),
      nativeSnapshot: previousNativeSnapshot,
      failClosed: true,
      applied: true,
    };
  }
  if (failClosed && incoming.state === "unlocked" && source !== "explicit-unlock") {
    return {
      displaySnapshot: failClosedApplicationLockSnapshot(displaySnapshot),
      nativeSnapshot: incoming,
      failClosed: true,
      applied: displaySnapshot.state !== "locked",
    };
  }
  return {
    displaySnapshot: incoming,
    nativeSnapshot: incoming,
    failClosed: false,
    applied: true,
  };
}

export function decodeApplicationLockSnapshot(value: unknown): ApplicationLockSnapshot {
  if (!isRecord(value) || Object.keys(value).sort().join("|") !== [...SNAPSHOT_KEYS].sort().join("|")) {
    throw new Error("Invalid application-lock response.");
  }
  const timeout = value.inactivityTimeoutMinutes;
  const state = value.state;
  const profileName = value.profileName;
  const reason = value.reason;
  if (
    value.schemaVersion !== "1.0"
    || (state !== "locked" && state !== "unlocked")
    || (profileName !== null && typeof profileName !== "string")
    || !APPLICATION_LOCK_TIMEOUTS.some((candidate) => candidate === timeout)
    || !["default", "valid", "invalid"].includes(String(value.configurationState))
    || (reason !== null && !["manual", "inactivity", "application-restart", "configuration-invalid"].includes(String(reason)))
    || value.reauthentication !== "windows-current-user-credentials-same-sid"
    || value.threatDisclosure !== "Application-session protection only; this is not Windows-account isolation."
    || !isNonNegativeInteger(value.retryAfterSeconds)
    || !isNonNegativeInteger(value.auditSequence)
    || (state === "locked" && profileName !== null)
  ) {
    throw new Error("Invalid application-lock response.");
  }
  return value as unknown as ApplicationLockSnapshot;
}

export function decodeApplicationUnlockAttempt(value: unknown): ApplicationUnlockAttempt {
  if (
    !isRecord(value)
    || Object.keys(value).sort().join("|") !== [...UNLOCK_ATTEMPT_KEYS].sort().join("|")
    || value.schemaVersion !== "1.0"
    || typeof value.outcome !== "string"
    || !Object.prototype.hasOwnProperty.call(UNLOCK_REASON_CODES, value.outcome)
    || typeof value.reasonCode !== "string"
  ) {
    throw new Error("Invalid application-unlock response.");
  }
  const outcome = value.outcome as VerificationOutcome;
  if (!UNLOCK_REASON_CODES[outcome].includes(value.reasonCode)) {
    throw new Error("Invalid application-unlock response.");
  }
  const snapshot = decodeApplicationLockSnapshot(value.snapshot);
  if (
    (outcome === "succeeded" && snapshot.state !== "unlocked")
    || (outcome !== "succeeded" && snapshot.state !== "locked")
  ) {
    throw new Error("Invalid application-unlock response.");
  }
  return { schemaVersion: "1.0", outcome, reasonCode: value.reasonCode, snapshot };
}

export function applicationUnlockFailureMessage(
  outcome: Exclude<VerificationOutcome, "succeeded">,
  reasonCode: string,
): string {
  if (outcome === "cancelled") {
    return "Unlock cancelled. The application remains locked.";
  }
  if (outcome === "busy") {
    return "Unlock is temporarily limited after a denied attempt.";
  }
  if (reasonCode === "RO-LOCK-CORE-UNAVAILABLE") {
    return "Credentials were accepted, but the local service could not start. The application remains locked.";
  }
  return "Windows could not verify the current user. The application remains locked.";
}
