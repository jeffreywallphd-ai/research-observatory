import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_APPLICATION_LOCK_SNAPSHOT } from "./applicationLock";
import { ApplicationSettingsWorkspace } from "./ApplicationSettingsWorkspace";

const inertTransport = { invoke: vi.fn(async () => undefined) };

describe("Application Settings workspace", () => {
  it("renders a separate application-wide sign-in destination with No login as the default", () => {
    const html = renderToStaticMarkup(
      <ApplicationSettingsWorkspace
        snapshot={DEFAULT_APPLICATION_LOCK_SNAPSHOT}
        announce={vi.fn()}
        onSnapshot={vi.fn()}
        onReturn={vi.fn()}
        transport={inertTransport}
      />,
    );

    expect(html).toContain('data-application-settings="true"');
    expect(html).toContain("Application Settings");
    expect(html).toContain("Security &amp; sign-in");
    expect(html).toContain("Application-wide · this Windows account");
    expect(html).toContain("No login is the default");
    expect(html).toContain("Current: No login");
    expect(html).toContain('name="sign-in-mode" checked=""');
    expect(html).toContain("Unavailable in No login");
    expect(html).toContain("Project protection</dt><dd>Unchanged");
    expect(html).toContain("Availability comes from Windows and is never inferred");
    expect(html).not.toContain("Project privacy &amp; egress");
    expect(html).not.toContain("application_lock_configure");
  });

  it("keeps unavailable Hello non-selectable and exposes explicit recovery without fallback", () => {
    const html = renderToStaticMarkup(
      <ApplicationSettingsWorkspace
        snapshot={{
          ...DEFAULT_APPLICATION_LOCK_SNAPSHOT,
          signInMode: "windows-hello",
          policyRevision: 2,
        }}
        announce={vi.fn()}
        onSnapshot={vi.fn()}
        onReturn={vi.fn()}
        transport={inertTransport}
      />,
    );

    expect(html).toContain("Current: Windows Hello");
    expect(html).toContain("Checking Windows Hello availability");
    expect(html).toContain("never falls back automatically");
    expect(html).toContain("Use Windows password recovery");
    expect(html).toContain("The app never receives or stores a PIN or biometric");
  });
});
