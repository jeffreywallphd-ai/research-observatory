import { describe, expect, it } from "vitest";

import {
  decodeApplicationLockSnapshot,
  DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  failClosedApplicationLockSnapshot,
  normalizeLocalProfileName,
  reconcileApplicationLockSnapshot,
} from "./applicationLock";

describe("application-lock contract", () => {
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

    const explicitUnlock = reconcileApplicationLockSnapshot(
      ignoredStatus.displaySnapshot,
      ignoredStatus.nativeSnapshot,
      { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, auditSequence: 2 },
      true,
      "explicit-unlock",
    );
    expect(explicitUnlock.displaySnapshot.state).toBe("unlocked");
    expect(explicitUnlock.failClosed).toBe(false);
  });
});
