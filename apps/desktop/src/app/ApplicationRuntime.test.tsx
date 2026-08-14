import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApplicationRuntime, nextTheme, SHORTCUTS, storedTheme } from "./ApplicationRuntime";

describe("functional desktop application", () => {
  it("renders implemented shell behavior and only functional workspace navigation", () => {
    const html = renderToStaticMarkup(<ApplicationRuntime />);

    expect(html).toContain('class="skip-link"');
    expect(html).toContain('id="main-content"');
    expect(html).toContain('id="shell-command"');
    expect(html).toContain('data-theme-toggle="true"');
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
    expect(html).toContain("Local projects");
    expect(html).toContain("Diagnostics &amp; support");
    expect(html).toContain("Open local projects");
    expect(html).toContain("Open diagnostics &amp; support");
    expect(html).not.toContain("prototype-index.html");
    expect(html).not.toContain("data-workflow-select");
    expect(html).not.toContain("study-design.html");
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
