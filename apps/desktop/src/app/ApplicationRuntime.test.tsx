import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ApplicationLockedView,
  ApplicationRuntime,
  nextTheme,
  SHORTCUTS,
  storedTheme,
} from "./ApplicationRuntime";
import { DEFAULT_APPLICATION_LOCK_SNAPSHOT, failClosedApplicationLockSnapshot } from "./applicationLock";

describe("functional desktop application", () => {
  it("renders implemented shell behavior and only functional workspace navigation", () => {
    const html = renderToStaticMarkup(<ApplicationRuntime />);

    expect(html).toContain('class="skip-link"');
    expect(html).toContain('id="main-content"');
    expect(html).toContain('id="shell-command"');
    expect(html).toContain('data-theme-toggle="true"');
    expect(html).toContain('data-local-profile="true"');
    expect(html).not.toContain('data-application-lock="true"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain(">Dark theme</button>");
    expect(html).not.toContain("Use dark theme");
    expect(html).not.toContain("Use light theme");
    expect(html).toContain('data-live-region="true"');
    expect(html).toContain('data-trust-footer="true"');
    expect(html).toContain('data-local-service-boundary="true"');
    expect(html).toContain('data-boundary-state="recovery-required"');
    expect(html).toContain("RO-CORE-SUPERVISOR-UNAVAILABLE");
    expect(html).not.toContain("does not yet package");
    expect(html).toContain("Copy diagnostic reference");
    expect(html).toContain("Only implemented capabilities appear here.");
    expect(html).toContain('data-workflow-navigation="true"');
    expect(html).toContain('data-all-tools="true"');
    expect(html).toContain("Guided workflow unavailable");
    expect(html).not.toContain('data-workflow-nav="true"');
    expect(html).not.toContain('data-workflow-context="true"');
    expect(html).toContain("Local projects");
    expect(html).toContain("Project settings");
    expect(html).toContain("Application settings");
    expect(html).toContain("Audit &amp; lineage");
    expect(html).toContain("Task Center");
    expect(html).toContain("Diagnostics &amp; support");
    expect(html).toContain("Open local projects");
    expect(html).toContain("Open project settings");
    expect(html).toContain("Open application settings");
    expect(html).toContain("Open audit &amp; lineage");
    expect(html).toContain("Open Task Center");
    expect(html).toContain("Open diagnostics &amp; support");
    expect(html).not.toContain("prototype-index.html");
    expect(html).not.toContain("data-workflow-select");
    expect(html).not.toContain("study-design.html");
  });

  it("renders only the bounded lock surface and no sensitive workspace content", () => {
    const html = renderToStaticMarkup(
      <ApplicationLockedView
        snapshot={{
          ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
          state: "locked",
          signInMode: "windows-password",
          policyRevision: 2,
          profileName: null,
          reason: "manual",
        }}
        busy={false}
        error={null}
        onUnlock={() => undefined}
      />,
    );

    expect(html).toContain('data-application-locked="true"');
    expect(html).toContain("Configured provider:</strong> Windows password");
    expect(html).toContain("Unlock with Windows password");
    expect(html).toContain("not Windows-account isolation");
    expect(html).toContain("No Research Observatory or cloud account is required");
    expect(html).not.toContain("Sensitive project");
    expect(html).not.toContain("Local projects");
    expect(html).not.toContain("Diagnostics &amp; support");
    expect(html).not.toContain('id="shell-command"');
    expect(html).not.toContain("data-local-service-boundary");
  });

  it("renders explicit same-user recovery without exposing protected application content", () => {
    const html = renderToStaticMarkup(
      <ApplicationLockedView
        snapshot={{
          ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
          state: "locked",
          signInMode: "windows-password",
          policyRevision: 2,
          profileName: null,
          configurationState: "invalid",
          reason: "configuration-invalid",
        }}
        busy={false}
        error={null}
        onUnlock={() => undefined}
        onRecovery={() => undefined}
      />,
    );

    expect(html).toContain("Recovery required");
    expect(html).toContain("Recover with Windows password");
    expect(html).not.toContain("Local projects");
    expect(html).not.toContain("Application settings");
    expect(html).not.toContain("Local researcher");
  });

  it("offers deliberate password recovery when configured Windows Hello is unavailable", () => {
    const html = renderToStaticMarkup(
      <ApplicationLockedView
        snapshot={{
          ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
          state: "locked",
          signInMode: "windows-hello",
          policyRevision: 2,
          profileName: null,
          reason: "application-restart",
        }}
        busy={false}
        error={null}
        helloAvailability="not-configured"
        onUnlock={() => undefined}
        onRecovery={() => undefined}
      />,
    );

    expect(html).toContain("Unlock with Windows Hello");
    expect(html).toContain("Use Windows password recovery");
    expect(html).toContain("Set up Windows Hello in Windows before selecting it here");
    expect(html).not.toContain("Local projects");
  });

  it.each(["none", null] as const)("offers only truthful restart guidance for unverified %s mode", (mode) => {
    const html = renderToStaticMarkup(<ApplicationLockedView
      snapshot={failClosedApplicationLockSnapshot(DEFAULT_APPLICATION_LOCK_SNAPSHOT)}
      monitoring={{ state: "unavailable", lastConfirmedMode: mode }}
      busy={false} error="Application-lock status is unavailable."
      onUnlock={() => undefined} onRecovery={() => undefined}
    />);
    expect(html).toContain("Recovery required");
    expect(html).toContain("Close Research Observatory completely");
    expect(html).toContain("persisted sign-in policy");
    expect(html).toContain(mode === "none" ? "Last confirmed sign-in mode:</strong> No login" : "Sign-in mode has not been confirmed");
    expect(html).not.toContain("locked manually");
    expect(html).not.toContain("configuration could not be validated");
    expect(html).not.toContain("Use the current Windows user credentials");
    expect(html).not.toContain("Unlock with");
    expect(html).not.toContain("Recover with");
    expect(html).not.toContain("<button");
  });

  it("does not present the unconfirmed initial default as a configured provider", () => {
    const html = renderToStaticMarkup(<ApplicationLockedView
      snapshot={failClosedApplicationLockSnapshot(DEFAULT_APPLICATION_LOCK_SNAPSHOT)}
      monitoring={{ state: "checking" }} busy={false} error={null} onUnlock={() => undefined}
    />);
    expect(html).toContain("Checking the application sign-in policy");
    expect(html).not.toContain("Configured provider");
    expect(html).not.toContain("No login");
    expect(html).not.toContain("<button");
  });

  it.each(["windows-password", "windows-hello"] as const)("preserves explicit %s unlock during status uncertainty", (mode) => {
    const native = { ...DEFAULT_APPLICATION_LOCK_SNAPSHOT, signInMode: mode };
    const html = renderToStaticMarkup(<ApplicationLockedView
      snapshot={failClosedApplicationLockSnapshot(native, native)}
      monitoring={{ state: "unavailable", lastConfirmedMode: mode }}
      busy={false} error="Application-lock status is unavailable."
      onUnlock={() => undefined} onRecovery={() => undefined}
    />);
    expect(html).toContain(`Unlock with ${mode === "windows-hello" ? "Windows Hello" : "Windows password"}`);
    expect(html).toContain("Last confirmed sign-in mode");
    expect(html).not.toContain("locked manually");
    expect(html).not.toContain("Recover with Windows password");
  });

  it("publishes a unique bounded shortcut registry and deterministic theme behavior", () => {
    expect(SHORTCUTS.map(({ id }) => id)).toEqual(["command", "help", "home"]);
    expect(new Set(SHORTCUTS.map(({ keys }) => keys)).size).toBe(SHORTCUTS.length);
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("light");
  });

  it("fails closed to light when stored theme state is absent, malformed, or unavailable", () => {
    expect(storedTheme(null)).toBe("light");
    expect(storedTheme({ getItem: () => "dark" })).toBe("dark");
    expect(storedTheme({ getItem: () => "future-theme" })).toBe("light");
    expect(storedTheme({ getItem: () => { throw new Error("unavailable"); } })).toBe("light");
  });
});
