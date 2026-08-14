import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { ProjectProjection } from "@research-observatory/contracts/core-api";

import { projectActionLabels, projectCompatibilityGuidance, ProjectsWorkspace } from "./ProjectsWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "11111111-1111-4111-8111-111111111111",
  displayName: "Study One",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: false,
  accessMode: "closed",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  revision: 0,
  deleteConfirmation: "delete:11111111-1111-4111-8111-111111111111",
};

describe("functional local projects workspace", () => {
  it("renders implemented create and open workflows without reference-only application pages", () => {
    const markup = renderToStaticMarkup(<ProjectsWorkspace announce={vi.fn()} />);
    expect(markup).toContain('data-projects-workspace="true"');
    expect(markup).toContain("Create a local project");
    expect(markup).toContain("Open an existing project");
    expect(markup).toContain('id="project-parent-directory"');
    expect(markup).toContain('id="project-root"');
    expect(markup).toContain("No project is selected");
    expect(markup).not.toContain("ui-reference");
    expect(markup).not.toContain("illustrative research");
  });

  it("derives only state-valid project lifecycle actions", () => {
    expect(projectActionLabels(project)).toEqual([
      "Open project",
      "Archive project",
      "Move to recoverable trash",
    ]);
    expect(projectActionLabels({ ...project, open: true })).toEqual(["Close project"]);
    expect(projectActionLabels({ ...project, lifecycleState: "archived" })).toEqual([
      "Restore project",
      "Move to recoverable trash",
    ]);
    expect(projectActionLabels({ ...project, lifecycleState: "trash" })).toEqual([]);
  });

  it("keeps incompatible projects read-only and presents a backup-first recovery path", () => {
    const newer: ProjectProjection = {
      ...project,
      open: true,
      accessMode: "read-only",
      compatibilityState: "newer-unsupported",
      packageFormatVersion: "2.0.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-use-compatible-application",
    };
    expect(projectActionLabels(newer)).toEqual(["Close project"]);
    expect(projectActionLabels({ ...newer, open: false, accessMode: "closed" })).toEqual(["Open read-only"]);
    expect(projectCompatibilityGuidance(newer)).toEqual({
      title: "Newer project format · read-only",
      message: "Keep the original unchanged. First create and verify a complete backup, then use a compatible application version with the working copy.",
    });
    expect(projectCompatibilityGuidance({
      ...newer,
      compatibilityState: "migration-required",
      packageFormatVersion: "0.9.0",
      recoveryAction: "backup-then-migrate",
    })?.message).toContain("First create and verify a complete backup");
  });
});
