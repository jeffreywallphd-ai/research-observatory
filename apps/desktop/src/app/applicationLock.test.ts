import { describe, expect, it } from "vitest";

import {
  applicationUnlockFailureMessage,
  decodeApplicationUnlockAttempt,
  decodeApplicationLockSnapshot,
  decodePolicyTransitionResult,
  decodeVerificationAvailabilitySnapshot,
  DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  failClosedApplicationLockSnapshot,
  normalizeLocalProfileName,
  reconcileApplicationLockSnapshot,
} from "./applicationLock";

describe("application-lock contract", () => {
  const lockedSnapshot = {
    ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
    state: "locked",
    signInMode: "windows-password",
    policyRevision: 2,
    reason: "manual",
    auditSequence: 1,
  } as const;

  it("decodes the strict native snapshot", () => {
    expect(decodeApplicationLockSnapshot(DEFAULT_APPLICATION_LOCK_SNAPSHOT)).toEqual(
      DEFAULT_APPLICATION_LOCK_SNAPSHOT,
    );
  });

  it("denies unknown fields, unsupported timeouts, and profile disclosure while locked", () => {
    expect(() => decodeApplicationLockSnapshot({
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      unexpected: true,
    })).toThrow("Invalid application-lock response");
    expect(() => decodeApplicationLockSnapshot({
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      inactivityTimeoutMinutes: 7,
    })).toThrow("Invalid application-lock response");
    expect(() => decodeApplicationLockSnapshot({
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      state: "locked",
      profileName: "Sensitive profile",
      reason: "manual",
    })).toThrow("Invalid application-lock response");
  });

  it("rejects coercible objects and accessors for every snapshot enum", () => {
    for (const [field, primitive] of [
      ["state", "unlocked"],
      ["configurationState", "default"],
      ["reason", "manual"],
    ] as const) {
      expect(() => decodeApplicationLockSnapshot({
        ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
        [field]: { toString: () => primitive },
      })).toThrow("Invalid application-lock response");

      const accessorSnapshot = { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT } as Record<string, unknown>;
      Object.defineProperty(accessorSnapshot, field, {
        enumerable: true,
        get: () => primitive,
      });
      expect(() => decodeApplicationLockSnapshot(accessorSnapshot))
        .toThrow("Invalid application-lock response");
    }
  });

  it("reconstructs a trusted snapshot instead of returning the bridge object", () => {
    const bridgeSnapshot = { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT };
    const decoded = decodeApplicationLockSnapshot(bridgeSnapshot);

    expect(decoded).not.toBe(bridgeSnapshot);
    expect(decoded).toEqual(bridgeSnapshot);
  });

  it("normalizes optional local profile names and rejects unsafe boundaries", () => {
    expect(normalizeLocalProfileName("  Local researcher  ")).toBe("Local researcher");
    expect(normalizeLocalProfileName("   ")).toBeNull();
    expect(() => normalizeLocalProfileName("name\npath")).toThrow("control characters");
    expect(() => normalizeLocalProfileName("x".repeat(81))).toThrow("80 characters");
  });

  it("synthesizes a locked-only configuration-invalid state after malformed native data", () => {
    const unlocked = {
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      profileName: "Sensitive profile",
      auditSequence: 7,
    } as const;
    const failed = failClosedApplicationLockSnapshot(unlocked);

    expect(failed).toMatchObject({
      state: "locked",
      profileName: null,
      configurationState: "invalid",
      reason: "configuration-invalid",
      auditSequence: 7,
    });
  });

  it("does not let stale or conflicting unlocked snapshots reopen a locked tree", () => {
    const locked = {
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      state: "locked",
      reason: "manual",
      auditSequence: 4,
    } as const;
    const stale = reconcileApplicationLockSnapshot(
      locked,
      locked,
      { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, auditSequence: 3 },
      false,
      "status",
    );
    expect(stale.applied).toBe(false);
    expect(stale.displaySnapshot.state).toBe("locked");

    const conflicting = reconcileApplicationLockSnapshot(
      locked,
      locked,
      { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, auditSequence: 4 },
      false,
      "status",
    );
    expect(conflicting.failClosed).toBe(true);
    expect(conflicting.displaySnapshot).toMatchObject({
      state: "locked",
      configurationState: "invalid",
      reason: "configuration-invalid",
    });
  });

  it("requires an explicit native unlock result to recover from fail-closed reconciliation", () => {
    const display = failClosedApplicationLockSnapshot(DEFAULT_APPLICATION_LOCK_SNAPSHOT);
    const ignoredStatus = reconcileApplicationLockSnapshot(
      display,
      DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, auditSequence: 1 },
      true,
      "status",
    );
    expect(ignoredStatus.displaySnapshot.state).toBe("locked");
    expect(ignoredStatus.failClosed).toBe(true);

    const nativeAttempt = decodeApplicationUnlockAttempt({
      schemaVersion: "1.0",
      outcome: "succeeded",
      reasonCode: "RO-LOCK-UNLOCKED",
      snapshot: { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, auditSequence: 2 },
    });
    const explicitUnlock = reconcileApplicationLockSnapshot(
      ignoredStatus.displaySnapshot,
      ignoredStatus.nativeSnapshot,
      nativeAttempt.snapshot,
      true,
      "explicit-unlock",
    );
    expect(explicitUnlock.displaySnapshot.state).toBe("unlocked");
    expect(explicitUnlock.failClosed).toBe(false);
  });

  it("keeps every non-success verification outcome locked and rejects forged state combinations", () => {
    for (const [outcome, reasonCode] of [
      ["cancelled", "RO-LOCK-AUTH-CANCELLED"],
      ["denied", "RO-LOCK-AUTH-DENIED"],
      ["unavailable", "RO-LOCK-AUTH-UNAVAILABLE"],
      ["busy", "RO-LOCK-AUTH-BUSY"],
      ["failed", "RO-LOCK-AUTH-FAILED"],
    ] as const) {
      expect(decodeApplicationUnlockAttempt({
        schemaVersion: "1.0",
        outcome,
        reasonCode,
        snapshot: lockedSnapshot,
      })).toMatchObject({ outcome, snapshot: { state: "locked" } });
    }

    expect(() => decodeApplicationUnlockAttempt({
      schemaVersion: "1.0",
      outcome: "denied",
      reasonCode: "RO-LOCK-AUTH-DENIED",
      snapshot: DEFAULT_APPLICATION_LOCK_SNAPSHOT,
    })).toThrow("Invalid application-unlock response");
    expect(() => decodeApplicationUnlockAttempt({
      schemaVersion: "1.0",
      outcome: "succeeded",
      reasonCode: "RO-LOCK-UNLOCKED",
      snapshot: lockedSnapshot,
    })).toThrow("Invalid application-unlock response");
    expect(() => decodeApplicationUnlockAttempt({
      schemaVersion: "1.0",
      outcome: "toString",
      reasonCode: "RO-LOCK-UNLOCKED",
      snapshot: lockedSnapshot,
    })).toThrow("Invalid application-unlock response");
    expect(() => decodeApplicationUnlockAttempt({
      schemaVersion: "1.0",
      outcome: "failed",
      reasonCode: "RO-LOCK-AUTH-NOT-LOCKED",
      snapshot: DEFAULT_APPLICATION_LOCK_SNAPSHOT,
    })).toThrow("Invalid application-unlock response");

    const accessorAttempt = {
      schemaVersion: "1.0",
      outcome: "failed",
      reasonCode: "RO-LOCK-AUTH-FAILED",
      snapshot: lockedSnapshot,
    } as Record<string, unknown>;
    Object.defineProperty(accessorAttempt, "outcome", {
      enumerable: true,
      get: () => "failed",
    });
    expect(() => decodeApplicationUnlockAttempt(accessorAttempt))
      .toThrow("Invalid application-unlock response");
  });

  it("preserves redacted password-provider failure messages", () => {
    expect(applicationUnlockFailureMessage("cancelled", "RO-LOCK-AUTH-CANCELLED"))
      .toBe("Unlock cancelled. The application remains locked.");
    expect(applicationUnlockFailureMessage("busy", "RO-LOCK-AUTH-BUSY"))
      .toBe("Unlock is temporarily limited after a denied attempt.");
    expect(applicationUnlockFailureMessage("failed", "RO-LOCK-CORE-UNAVAILABLE"))
      .toBe("Credentials were accepted, but the local service could not start. The application remains locked.");
    for (const outcome of ["denied", "unavailable", "failed"] as const) {
      expect(applicationUnlockFailureMessage(outcome, "RO-LOCK-AUTH-FAILED"))
        .toBe("Windows could not verify the current user. The application remains locked.");
    }
  });

  it("decodes every approved Hello availability state without coercion", () => {
    for (const state of [
      "checking",
      "available",
      "not-present",
      "not-configured",
      "policy-disabled",
      "busy",
      "unavailable",
      "failed",
    ] as const) {
      expect(decodeVerificationAvailabilitySnapshot({
        schemaVersion: "1.0",
        provider: "windows-hello",
        availability: state,
      })).toEqual({
        schemaVersion: "1.0",
        provider: "windows-hello",
        availability: state,
      });
    }
    expect(() => decodeVerificationAvailabilitySnapshot({
      schemaVersion: "1.0",
      provider: "windows-hello",
      availability: { toString: () => "available" },
    }))
      .toThrow("Invalid verification-availability response");
    expect(() => decodeVerificationAvailabilitySnapshot({
      schemaVersion: "1.0",
      provider: "windows-hello",
      availability: "cancelled",
    }))
      .toThrow("Invalid verification-availability response");
    const accessorSnapshot = {
      schemaVersion: "1.0",
      provider: "windows-hello",
      availability: "available",
    } as Record<string, unknown>;
    Object.defineProperty(accessorSnapshot, "availability", {
      enumerable: true,
      get: () => "available",
    });
    expect(() => decodeVerificationAvailabilitySnapshot(accessorSnapshot))
      .toThrow("Invalid verification-availability response");
  });

  it("decodes opaque transition preparation and committed response-loss receipts", () => {
    const protectedSnapshot = {
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      signInMode: "windows-password",
      policyRevision: 2,
    } as const;
    const handle = "ab".repeat(32);
    expect(decodePolicyTransitionResult({
      schemaVersion: "1.0",
      outcome: "prepared",
      reasonCode: "RO-SIGN-IN-TRANSITION-PREPARED",
      handle,
      sourceMode: "windows-password",
      targetMode: "none",
      warningRequired: true,
      snapshot: protectedSnapshot,
    })).toMatchObject({ outcome: "prepared", handle, warningRequired: true });

    const committed = decodePolicyTransitionResult({
      schemaVersion: "1.0",
      outcome: "committed",
      reasonCode: "RO-SIGN-IN-TRANSITION-COMMITTED",
      handle: null,
      sourceMode: "windows-password",
      targetMode: "none",
      warningRequired: true,
      snapshot: { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, policyRevision: 3 },
    });
    expect(committed).toMatchObject({
      outcome: "committed",
      handle: null,
      snapshot: { signInMode: "none", policyRevision: 3 },
    });
  });

  it("rejects forged transition handles, outcomes, reason codes, and target receipts", () => {
    const base = {
      schemaVersion: "1.0",
      outcome: "prepared",
      reasonCode: "RO-SIGN-IN-TRANSITION-PREPARED",
      handle: "ab".repeat(32),
      sourceMode: "windows-password",
      targetMode: "none",
      warningRequired: true,
      snapshot: {
        ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
        signInMode: "windows-password",
        policyRevision: 2,
      },
    } as const;
    for (const changed of [
      { ...base, handle: "plain-token" },
      { ...base, outcome: "committed" },
      { ...base, reasonCode: "renderer-approved" },
      { ...base, outcome: "denied", reasonCode: "RO-SIGN-IN-TRANSITION-PREPARED", handle: null },
      { ...base, targetMode: "password" },
      { ...base, unexpected: true },
    ]) {
      expect(() => decodePolicyTransitionResult(changed))
        .toThrow("Invalid application sign-in transition response");
    }
    expect(() => decodePolicyTransitionResult({
      ...base,
      outcome: "committed",
      reasonCode: "RO-SIGN-IN-TRANSITION-COMMITTED",
      handle: null,
      targetMode: "windows-hello",
    })).toThrow("Invalid application sign-in transition response");
  });

  it("rejects illegal source, target, warning, and recovery combinations", () => {
    const protectedToNone = {
      schemaVersion: "1.0",
      outcome: "prepared",
      reasonCode: "RO-SIGN-IN-TRANSITION-PREPARED",
      handle: "ab".repeat(32),
      sourceMode: "windows-password",
      targetMode: "none",
      warningRequired: true,
      snapshot: {
        ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
        signInMode: "windows-password",
        policyRevision: 2,
      },
    } as const;
    const invalidSnapshot = {
      ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      state: "locked",
      signInMode: "windows-password",
      policyRevision: 2,
      configurationState: "invalid",
      reason: "configuration-invalid",
    } as const;
    for (const forged of [
      { ...protectedToNone, warningRequired: false },
      { ...protectedToNone, sourceMode: null },
      { ...protectedToNone, targetMode: "windows-hello", warningRequired: true },
      {
        ...protectedToNone,
        reasonCode: "RO-SIGN-IN-RECOVERY-PREPARED",
        sourceMode: null,
        warningRequired: false,
        snapshot: invalidSnapshot,
      },
      {
        ...protectedToNone,
        reasonCode: "RO-SIGN-IN-RECOVERY-PREPARED",
        sourceMode: null,
        snapshot: DEFAULT_APPLICATION_LOCK_SNAPSHOT,
      },
      {
        ...protectedToNone,
        outcome: "committed",
        reasonCode: "RO-SIGN-IN-TRANSITION-COMMITTED",
        handle: null,
        sourceMode: null,
        snapshot: { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, policyRevision: 3 },
      },
    ]) {
      expect(() => decodePolicyTransitionResult(forged))
        .toThrow("Invalid application sign-in transition response");
    }
  });
});
