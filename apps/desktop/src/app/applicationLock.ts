export type ApplicationLockState = "locked" | "unlocked";
export type ApplicationLockReason =
  | "manual"
  | "inactivity"
  | "application-restart"
  | "configuration-invalid";
export type SignInMode = "none" | "windows-password" | "windows-hello";
export type LockConfigurationState = "valid" | "migrated" | "invalid";

export interface ApplicationLockSnapshot {
  readonly schemaVersion: "1.0";
  readonly state: ApplicationLockState;
  readonly signInMode: SignInMode;
  readonly policyRevision: number;
  readonly profileName: string | null;
  readonly inactivityTimeoutMinutes: 0 | 5 | 15 | 30 | 60;
  readonly configurationState: LockConfigurationState;
  readonly reason: ApplicationLockReason | null;
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

export type VerificationAvailability =
  | "checking"
  | "available"
  | "not-present"
  | "not-configured"
  | "policy-disabled"
  | "busy"
  | "unavailable"
  | "failed";

export interface VerificationAvailabilitySnapshot {
  readonly schemaVersion: "1.0";
  readonly provider: "windows-hello";
  readonly availability: VerificationAvailability;
}

export interface ApplicationUnlockAttempt {
  readonly schemaVersion: "1.0";
  readonly outcome: VerificationOutcome;
  readonly reasonCode: string;
  readonly snapshot: ApplicationLockSnapshot;
}

export type PolicyTransitionOutcome =
  | "prepared"
  | "committed"
  | "cancelled"
  | "denied"
  | "unavailable"
  | "busy"
  | "failed"
  | "conflict"
  | "expired";

export interface PolicyTransitionResult {
  readonly schemaVersion: "1.0";
  readonly outcome: PolicyTransitionOutcome;
  readonly reasonCode: string;
  readonly handle: string | null;
  readonly sourceMode: SignInMode | null;
  readonly targetMode: SignInMode;
  readonly warningRequired: boolean;
  readonly snapshot: ApplicationLockSnapshot;
}

export const APPLICATION_LOCK_TIMEOUTS = [0, 5, 15, 30, 60] as const;

export const DEFAULT_APPLICATION_LOCK_SNAPSHOT: ApplicationLockSnapshot = Object.freeze({
  schemaVersion: "1.0",
  state: "unlocked",
  signInMode: "none",
  policyRevision: 1,
  profileName: null,
  inactivityTimeoutMinutes: 0,
  configurationState: "valid",
  reason: null,
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
  "policyRevision",
  "profileName",
  "reason",
  "retryAfterSeconds",
  "schemaVersion",
  "signInMode",
  "state",
  "threatDisclosure",
] as const;

const UNLOCK_ATTEMPT_KEYS = ["outcome", "reasonCode", "schemaVersion", "snapshot"] as const;
const VERIFICATION_AVAILABILITY_KEYS = ["availability", "provider", "schemaVersion"] as const;
const POLICY_TRANSITION_KEYS = [
  "handle",
  "outcome",
  "reasonCode",
  "schemaVersion",
  "snapshot",
  "sourceMode",
  "targetMode",
  "warningRequired",
] as const;
const POLICY_TRANSITION_REASON_CODES: Readonly<
  Record<PolicyTransitionOutcome, readonly string[]>
> = Object.freeze({
  prepared: ["RO-SIGN-IN-TRANSITION-PREPARED", "RO-SIGN-IN-RECOVERY-PREPARED"],
  committed: ["RO-SIGN-IN-TRANSITION-COMMITTED", "RO-SIGN-IN-RECOVERY-COMMITTED"],
  cancelled: [
    "RO-SIGN-IN-TRANSITION-AUTH-CANCELLED",
    "RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED",
  ],
  denied: [
    "RO-SIGN-IN-TRANSITION-RECOVERY-REQUIRED",
    "RO-SIGN-IN-TRANSITION-APPLICATION-LOCKED",
    "RO-SIGN-IN-TRANSITION-AUTH-DENIED",
    "RO-SIGN-IN-RECOVERY-NOT-REQUIRED",
    "RO-SIGN-IN-TRANSITION-HANDLE-INVALID",
  ],
  unavailable: ["RO-SIGN-IN-TRANSITION-AUTH-UNAVAILABLE"],
  busy: ["RO-SIGN-IN-TRANSITION-BUSY", "RO-SIGN-IN-TRANSITION-AUTH-BUSY"],
  failed: [
    "RO-SIGN-IN-TRANSITION-AUTH-FAILED",
    "RO-SIGN-IN-TRANSITION-LOCK-FAILED",
    "RO-SIGN-IN-TRANSITION-WRITE-FAILED",
  ],
  conflict: ["RO-SIGN-IN-TRANSITION-STALE", "RO-SIGN-IN-TRANSITION-CONFLICT"],
  expired: ["RO-SIGN-IN-TRANSITION-EXPIRED"],
});
const UNLOCK_REASON_CODES: Readonly<Record<VerificationOutcome, readonly string[]>> = Object.freeze({
  succeeded: ["RO-LOCK-UNLOCKED"],
  cancelled: ["RO-LOCK-AUTH-CANCELLED"],
  denied: ["RO-LOCK-AUTH-DENIED"],
  unavailable: ["RO-LOCK-AUTH-UNAVAILABLE"],
  busy: ["RO-LOCK-AUTH-BUSY", "RO-LOCK-RATE-LIMITED"],
  failed: [
    "RO-LOCK-AUTH-FAILED",
    "RO-LOCK-AUTH-STALE",
    "RO-LOCK-CORE-UNAVAILABLE",
  ],
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readExactDataRecord(
  value: unknown,
  expectedKeys: readonly string[],
): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  const ownKeys = Reflect.ownKeys(value);
  if (
    ownKeys.some((key) => typeof key !== "string")
    || ownKeys.length !== expectedKeys.length
    || !expectedKeys.every((key) => ownKeys.includes(key))
  ) {
    return null;
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const result: Record<string, unknown> = {};
  for (const key of expectedKeys) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor)) return null;
    result[key] = descriptor.value;
  }
  return result;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isProtectedSignInMode(value: SignInMode | null): value is Exclude<SignInMode, "none"> {
  return value === "windows-password" || value === "windows-hello";
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
    && left.signInMode === right.signInMode
    && left.policyRevision === right.policyRevision
    && left.profileName === right.profileName
    && left.inactivityTimeoutMinutes === right.inactivityTimeoutMinutes
    && left.configurationState === right.configurationState
    && left.reason === right.reason
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
  const data = readExactDataRecord(value, SNAPSHOT_KEYS);
  if (!data) {
    throw new Error("Invalid application-lock response.");
  }
  const timeout = data.inactivityTimeoutMinutes;
  const state = data.state;
  const signInMode = data.signInMode;
  const profileName = data.profileName;
  const configurationState = data.configurationState;
  const reason = data.reason;
  if (
    data.schemaVersion !== "1.0"
    || (state !== "locked" && state !== "unlocked")
    || (signInMode !== "none" && signInMode !== "windows-password" && signInMode !== "windows-hello")
    || !isNonNegativeInteger(data.policyRevision)
    || data.policyRevision === 0
    || (profileName !== null && typeof profileName !== "string")
    || !APPLICATION_LOCK_TIMEOUTS.some((candidate) => candidate === timeout)
    || (configurationState !== "valid" && configurationState !== "migrated" && configurationState !== "invalid")
    || (reason !== null && reason !== "manual" && reason !== "inactivity" && reason !== "application-restart" && reason !== "configuration-invalid")
    || data.threatDisclosure !== "Application-session protection only; this is not Windows-account isolation."
    || !isNonNegativeInteger(data.retryAfterSeconds)
    || !isNonNegativeInteger(data.auditSequence)
    || (state === "locked" && profileName !== null)
    || (signInMode === "none"
      && configurationState !== "invalid"
      && (state !== "unlocked" || timeout !== 0))
    || (configurationState === "invalid" && (state !== "locked" || reason !== "configuration-invalid"))
  ) {
    throw new Error("Invalid application-lock response.");
  }
  return {
    schemaVersion: "1.0",
    state,
    signInMode,
    policyRevision: data.policyRevision,
    profileName,
    inactivityTimeoutMinutes: timeout as ApplicationLockSnapshot["inactivityTimeoutMinutes"],
    configurationState,
    reason,
    threatDisclosure: "Application-session protection only; this is not Windows-account isolation.",
    retryAfterSeconds: data.retryAfterSeconds,
    auditSequence: data.auditSequence,
  };
}

export function decodePolicyTransitionResult(value: unknown): PolicyTransitionResult {
  const data = readExactDataRecord(value, POLICY_TRANSITION_KEYS);
  if (
    !data
    || data.schemaVersion !== "1.0"
    || typeof data.outcome !== "string"
    || ![
      "prepared",
      "committed",
      "cancelled",
      "denied",
      "unavailable",
      "busy",
      "failed",
      "conflict",
      "expired",
    ].includes(data.outcome)
    || typeof data.reasonCode !== "string"
    || (data.handle !== null && (typeof data.handle !== "string" || !/^[0-9a-f]{64}$/.test(data.handle)))
    || (data.sourceMode !== null
      && data.sourceMode !== "none"
      && data.sourceMode !== "windows-password"
      && data.sourceMode !== "windows-hello")
    || (data.targetMode !== "none"
      && data.targetMode !== "windows-password"
      && data.targetMode !== "windows-hello")
    || typeof data.warningRequired !== "boolean"
  ) {
    throw new Error("Invalid application sign-in transition response.");
  }
  const outcome = data.outcome as PolicyTransitionOutcome;
  if (
    !POLICY_TRANSITION_REASON_CODES[outcome].includes(data.reasonCode)
    || (outcome === "prepared") !== (data.handle !== null)
  ) {
    throw new Error("Invalid application sign-in transition response.");
  }
  const targetMode = data.targetMode;
  const sourceMode = data.sourceMode;
  const warningRequired = data.warningRequired;
  const snapshot = decodeApplicationLockSnapshot(data.snapshot);
  const recoveryPrepared = outcome === "prepared" && data.reasonCode === "RO-SIGN-IN-RECOVERY-PREPARED";
  const recoveryCommitted = outcome === "committed" && data.reasonCode === "RO-SIGN-IN-RECOVERY-COMMITTED";
  const configuredPrepared = outcome === "prepared" && data.reasonCode === "RO-SIGN-IN-TRANSITION-PREPARED";
  const configuredCommitted = outcome === "committed" && data.reasonCode === "RO-SIGN-IN-TRANSITION-COMMITTED";
  const configuredWarning = isProtectedSignInMode(sourceMode) && targetMode === "none";
  if (
    (outcome === "committed" && (
      snapshot.signInMode !== targetMode
      || snapshot.configurationState !== "valid"
    ))
    || (outcome === "prepared"
      && sourceMode !== null
      && snapshot.signInMode !== sourceMode)
    || (warningRequired && targetMode !== "none")
    || (sourceMode === null
      && outcome === "prepared"
      && snapshot.configurationState !== "invalid")
    || ((recoveryPrepared || recoveryCommitted)
      && (targetMode !== "none" || !warningRequired))
    || ((configuredPrepared || configuredCommitted)
      && (sourceMode === null || warningRequired !== configuredWarning))
    || (outcome === "prepared" && !recoveryPrepared && !configuredPrepared)
    || (outcome === "committed" && !recoveryCommitted && !configuredCommitted)
  ) {
    throw new Error("Invalid application sign-in transition response.");
  }
  return {
    schemaVersion: "1.0",
    outcome,
    reasonCode: data.reasonCode,
    handle: data.handle,
    sourceMode,
    targetMode,
    warningRequired,
    snapshot,
  };
}

export function decodeApplicationUnlockAttempt(value: unknown): ApplicationUnlockAttempt {
  const data = readExactDataRecord(value, UNLOCK_ATTEMPT_KEYS);
  if (
    !data
    || data.schemaVersion !== "1.0"
    || typeof data.outcome !== "string"
    || !Object.prototype.hasOwnProperty.call(UNLOCK_REASON_CODES, data.outcome)
    || typeof data.reasonCode !== "string"
  ) {
    throw new Error("Invalid application-unlock response.");
  }
  const outcome = data.outcome as VerificationOutcome;
  if (!UNLOCK_REASON_CODES[outcome].includes(data.reasonCode)) {
    throw new Error("Invalid application-unlock response.");
  }
  const snapshot = decodeApplicationLockSnapshot(data.snapshot);
  if (
    (outcome === "succeeded" && snapshot.state !== "unlocked")
    || (outcome !== "succeeded" && snapshot.state !== "locked")
  ) {
    throw new Error("Invalid application-unlock response.");
  }
  return { schemaVersion: "1.0", outcome, reasonCode: data.reasonCode, snapshot };
}

function decodeVerificationAvailability(value: unknown): VerificationAvailability {
  if (
    value !== "checking"
    && value !== "available"
    && value !== "not-present"
    && value !== "not-configured"
    && value !== "policy-disabled"
    && value !== "busy"
    && value !== "unavailable"
    && value !== "failed"
  ) {
    throw new Error("Invalid verification-availability response.");
  }
  return value;
}

export function decodeVerificationAvailabilitySnapshot(
  value: unknown,
): VerificationAvailabilitySnapshot {
  const data = readExactDataRecord(value, VERIFICATION_AVAILABILITY_KEYS);
  if (!data || data.schemaVersion !== "1.0" || data.provider !== "windows-hello") {
    throw new Error("Invalid verification-availability response.");
  }
  return {
    schemaVersion: "1.0",
    provider: "windows-hello",
    availability: decodeVerificationAvailability(data.availability),
  };
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
