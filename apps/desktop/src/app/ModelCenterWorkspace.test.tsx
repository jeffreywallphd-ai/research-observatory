import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ModelCatalogProjection, ProjectProjection } from "@research-observatory/contracts/core-api";

import { ModelCenterWorkspace, modelCenterAvailability, modelCenterResultMatches } from "./ModelCenterWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0", projectId: "11111111-1111-4111-8111-111111111111", displayName: "Fixture Project",
  templateId: "theory-synthesis", lifecycleState: "active", root: "C:/Research/fixture", open: true,
  accessMode: "read-write", compatibilityState: "compatible", packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false, recoveryAction: "none", revision: 0,
  deleteConfirmation: "delete:11111111-1111-4111-8111-111111111111",
};
const empty: ModelCatalogProjection = {
  schemaVersion: "1.0", projectId: project.projectId, revision: 0, latestRevision: 0, catalogHash: null,
  modelCount: 0, entries: [], history: [], nextManifestId: null, nextHistoryRevision: null,
  inventoryState: "not-configured", executionAvailable: false,
};

describe("Model Center", () => {
  it("keeps a closed project distinct from a verified empty inventory", () => {
    expect(modelCenterAvailability(null).readable).toBe(false);
    expect(modelCenterAvailability({ ...project, open: false }).readable).toBe(false);
    expect(modelCenterAvailability({ ...project, accessMode: "read-only" })).toMatchObject({ readable: true, writable: false });
    const closed = renderToStaticMarkup(<ModelCenterWorkspace project={null} announce={vi.fn()} />);
    expect(closed).toContain("Open a local project");
    expect(closed).not.toContain("No models are recorded");
    const loaded = renderToStaticMarkup(<ModelCenterWorkspace project={project} initialProjection={empty} announce={vi.fn()} />);
    expect(loaded).toContain("No models are recorded");
    expect(loaded).toContain("No model runtime adapter is configured");
    expect(loaded).toContain("No model is executed");
    expect(loaded).not.toContain("Add provider");
    expect(loaded).not.toContain("Run evaluation");
  });

  it("rejects late or foreign project results and explains supporting-tool authority", () => {
    expect(modelCenterResultMatches(project, project.root, empty)).toBe(true);
    expect(modelCenterResultMatches(project, "C:/Research/different", empty)).toBe(false);
    expect(modelCenterResultMatches({ ...project, open: false }, project.root, empty)).toBe(false);
    expect(modelCenterResultMatches(project, project.root, { ...empty, projectId: "22222222-2222-4222-8222-222222222222" })).toBe(false);
    const markup = renderToStaticMarkup(<ModelCenterWorkspace project={project} initialProjection={empty} announce={vi.fn()} />);
    expect(markup).toContain("Capability matching does not grant permission");
    expect(markup).toContain("Project settings");
    expect(markup).toContain("Inventory history");
    expect(markup).toContain('data-model-center-workspace="true"');
    expect(markup).toContain("ro-panel");
  });
});
