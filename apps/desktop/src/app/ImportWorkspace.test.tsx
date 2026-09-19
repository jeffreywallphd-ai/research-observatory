import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ImportPreviewItem, ProjectProjection } from "@research-observatory/contracts/core-api";
import { ImportWorkspace } from "./ImportWorkspace";
import { importStatusLabel } from "./ImportReviewPane";
import { implementedWorkspaceForStage } from "./workflowNavigationModel";

const project: ProjectProjection = { schemaVersion: "1.0", projectId: "01900000-0000-4000-8000-000000000001", displayName: "Synthetic", templateId: "theory-synthesis", lifecycleState: "active", root: "C:/Research/synthetic", open: true, revision: 1, accessMode: "read-write", compatibilityState: "compatible", packageFormatVersion: "1.0.0", backupRequiredBeforeRepair: false, recoveryAction: "none", deleteConfirmation: "delete:01900000-0000-4000-8000-000000000001" };
const preview: ImportPreviewItem = { previewId: "01900000-0000-7000-8000-000000000001", sourceName: "<script>synthetic.csv", formatName: "csv", encoding: "utf-8", byteLength: 20, chunkCount: 1, jobId: null, jobState: null, state: "created" };

describe("import workspace", () => {
  it("maps the approved page into the existing workflow navigation", () => {
    expect(implementedWorkspaceForStage({ pageContractId: "ingestion-reconciliation.html" })).toBe("imports");
  });
  it("requires an open writable project before retaining source data", () => {
    expect(renderToStaticMarkup(<ImportWorkspace project={null} announce={() => undefined} />)).toContain("No project open");
    const html = renderToStaticMarkup(<ImportWorkspace project={{ ...project, accessMode: "read-only" }} announce={() => undefined} />);
    expect(html).toContain("read-only mode"); expect(html).not.toContain("Choose reference file");
  });
  it("starts with explicit restrictive rights, a native chooser and truthful empty state", () => {
    const html = renderToStaticMarkup(<ImportWorkspace project={project} announce={() => undefined} initialPreviews={{ items: [], nextAfter: null, complete: true }} />);
    expect(html).toContain("Choose reference file…"); expect(html).toContain("disabled");
    expect(html).toContain("No accessible previews"); expect(html).toContain("no path typing is required");
    expect(html).not.toContain('type="file"'); expect(html).not.toContain(project.root);
    expect(html).not.toContain("1,936"); expect(html).not.toContain("Apply reviewed merges");
  });
  it("renders filenames inertly and never labels an incomplete parse ready", () => {
    const html = renderToStaticMarkup(<ImportWorkspace project={project} announce={() => undefined} initialPreviews={{ items: [preview], nextAfter: preview.previewId, complete: true }} />);
    expect(html).toContain("&lt;script&gt;synthetic.csv"); expect(html).not.toContain("<script>");
    expect(html).toContain("Source intake incomplete");
    expect(importStatusLabel({ ...preview, state: "parse-completed", jobState: "running" })).not.toBe("Ready for review");
    expect(importStatusLabel({ ...preview, state: "parse-completed", jobState: "succeeded" })).toBe("Ready for review");
  });
});
