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
