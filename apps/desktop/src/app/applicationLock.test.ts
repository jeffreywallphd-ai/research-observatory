import { describe, expect, it } from "vitest";

import {
  decodeApplicationLockSnapshot,
  DEFAULT_APPLICATION_LOCK_SNAPSHOT,
  normalizeLocalProfileName,
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
});
