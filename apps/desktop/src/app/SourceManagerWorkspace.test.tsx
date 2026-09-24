import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ConnectorCapabilitiesPage, ProjectProjection } from "@research-observatory/contracts/core-api";
import { SourceManagerWorkspace } from "./SourceManagerWorkspace";
import { implementedWorkspaceForStage } from "./workflowNavigationModel";

const project: ProjectProjection = { schemaVersion: "1.0", projectId: "01900000-0000-4000-8000-000000000001", displayName: "Synthetic", templateId: "theory-synthesis", lifecycleState: "active", root: "C:/Research/synthetic", open: true, revision: 1, accessMode: "read-write", compatibilityState: "compatible", packageFormatVersion: "1.0.0", backupRequiredBeforeRepair: false, recoveryAction: "none", deleteConfirmation: "delete:01900000-0000-4000-8000-000000000001" };
const capabilities: ConnectorCapabilitiesPage = { items: [{ schemaVersion: "1.0", providerId: "unpaywall", adapterVersion: "1.0.0", sourceApiVersion: "2", operations: ["oa-resolution"], identifierSchemes: ["doi"], maximumPageSize: 1, configuration: "not-configured", requiredSettings: ["contact"] }] };
describe("Source Manager", () => {
  it("maps the approved supporting page without changing the current workflow", () => {
    expect(implementedWorkspaceForStage({ pageContractId: "source-manager.html" })).toBe("sources");
  });
  it("does not expose configuration for absent or read-only projects", () => {
    expect(renderToStaticMarkup(<SourceManagerWorkspace project={null} announce={() => undefined} />)).toContain("No project open");
    expect(renderToStaticMarkup(<SourceManagerWorkspace project={{ ...project, accessMode: "read-only" }} announce={() => undefined} />)).not.toContain("Configure Unpaywall");
  });
  it("shows genuine configuration state without invented health or credential fields", () => {
    const html = renderToStaticMarkup(<SourceManagerWorkspace project={project} announce={() => undefined} initialCapabilities={capabilities} />);
    for (const text of ["Contact required", "Configuration unavailable", "Rights and egress", "Connection health", "Import and review references", "Private technical reports", "Manuscript drafts", "Licensed and reference-manager sources"]) expect(html).toContain(text);
    expect(html).not.toContain('type="password"'); expect(html).not.toContain('type="email"');
    expect(html).not.toContain("Connected"); expect(html).not.toContain("99.8%"); expect(html).not.toContain(project.root);
  });
});
