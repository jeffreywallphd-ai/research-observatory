import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { ProjectProjection } from "@research-observatory/contracts/core-api";

import {
  egressBoundary,
  projectSettingsAvailability,
  ProjectSettingsWorkspace,
} from "./ProjectSettingsWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "11111111-1111-4111-8111-111111111111",
  displayName: "Study One",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: true,
  accessMode: "read-write",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  revision: 0,
  deleteConfirmation: "delete:11111111-1111-4111-8111-111111111111",
};

describe("project privacy settings workspace", () => {
  it("keeps settings behind an open compatible local project session", () => {
    expect(projectSettingsAvailability(null)).toMatchObject({ available: false });
    expect(projectSettingsAvailability({ ...project, open: false, accessMode: "closed" })).toMatchObject({
      available: false,
    });
    expect(projectSettingsAvailability({ ...project, accessMode: "read-only" })).toMatchObject({
      available: false,
      message: expect.stringContaining("read-only"),
    });
    expect(projectSettingsAvailability(project)).toEqual({
      available: true,
      message: "Project settings are available for this exclusive local session.",
    });

    const markup = renderToStaticMarkup(<ProjectSettingsWorkspace project={null} announce={vi.fn()} />);
    expect(markup).toContain('data-project-settings-workspace="true"');
    expect(markup).toContain("Defaults are offline with usage telemetry off");
    expect(markup).toContain("Open a compatible local project");
    expect(markup).not.toContain("Save project settings");
  });

  it("states exact offline, metadata-only, and provider-preview boundaries", () => {
    expect(egressBoundary("offline")).toEqual({
      sends: "Nothing. Offline is enforced as a denial at the object-access boundary.",
      excludes: "Documents, document metadata, prompts, citations, identifiers, and telemetry remain local.",
    });
    expect(egressBoundary("metadata-only").excludes).toContain("Document bytes");
    expect(egressBoundary("approved-providers").excludes).toContain("task preview and confirmation");
    for (const network of ["metadata-only", "approved-providers"] as const) {
      expect(egressBoundary(network).sends).toContain("does not send data by itself");
    }
  });
});
