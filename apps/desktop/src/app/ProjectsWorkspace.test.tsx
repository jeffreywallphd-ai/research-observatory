import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { CoreApiResponse, ProjectProjection, ProjectRecoveryProjection, WorkflowProfileCatalogProjection } from "@research-observatory/contracts/core-api";

import { decodeProjectRecoveryProjection, projectActionLabels, projectCompatibilityGuidance, projectRecoveryActionLabels, projectRecoveryCanAdvance, ProjectsWorkspace, requestProjectRecovery } from "./ProjectsWorkspace";

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

const catalog: WorkflowProfileCatalogProjection = {
  schemaVersion: "1.0",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
  referenceVersion: "1.5",
  profileCatalogVersion: "1.0.0",
  profileCatalogHash: `sha256:${"a".repeat(64)}`,
  intentGuidanceVersion: "1.0.0",
  intentGuidanceHash: "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2",
  allToolsAccessible: true,
  evidenceRequirementsUnchanged: true,
  provenanceRequirementsUnchanged: true,
  registeredToolPageContractIds: ["intent-contract.html", "theory-map.html"],
  profiles: [{
    profileId: "theory-synthesis",
    epistemicMode: "theory",
    title: "Theory synthesis",
    purpose: "Reconcile competing mechanisms into a bounded conceptual model.",
    example: "Reconcile competing mechanisms into a bounded conceptual model.",
    expectedOutputs: ["Theory map", "Traceable synthesis"],
    processForm: "revisitable",
    defaultEvidenceTypes: ["theoretical-work", "empirical-study"],
    defaultNoveltyStandard: "theoretical",
    defaultAutonomyLevel: "suggest",
    defaultStoppingConditions: ["interpretive-saturation"],
    warning: "Conceptual integration must preserve disagreements and evidentiary limits.",
    stages: [
      { stageKey: "intent-contract-1", order: 1, pageContractId: "intent-contract.html", label: "Research Intent", optional: false, rationale: "Set authority.", checkpointState: "unknown", checkpointRationale: "Not specified." },
      { stageKey: "theory-map-1", order: 2, pageContractId: "theory-map.html", label: "Theory Map", optional: false, rationale: "Map theory.", checkpointState: "unknown", checkpointRationale: "Not specified." },
    ],
  }],
};

const recovery: ProjectRecoveryProjection = {
  previewId: "b".repeat(32), state: "preview-ready", reasonCodes: [], requiresConfirmation: true,
  sourceDisplayLabel: "Synthetic retained project", destinationDisplayLabel: "recovered-working-copy", verifiedFactSummary: null,
};
const recoveryResponse = (projection: ProjectRecoveryProjection): CoreApiResponse => ({
  status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(projection),
});

describe("reviewed project recovery boundary", () => {
  it("decodes canonical states and rejects authority fields, false confirmation and unverified facts", () => {
    expect(decodeProjectRecoveryProjection(recovery)).toEqual(recovery);
    expect(decodeProjectRecoveryProjection({ ...recovery, processId: 7 })).toBeNull();
    expect(decodeProjectRecoveryProjection({ ...recovery, requiresConfirmation: false })).toBeNull();
    expect(decodeProjectRecoveryProjection({ ...recovery, state: "copying", requiresConfirmation: false, verifiedFactSummary: "Verified" })).toBeNull();
    expect(decodeProjectRecoveryProjection({ ...recovery, reasonCodes: ["C:/private/host"] })).toBeNull();
    expect(decodeProjectRecoveryProjection({ ...recovery, sourceDisplayLabel: "\u0000" })).toBeNull();
    expect(decodeProjectRecoveryProjection({ ...recovery, state: "automatically-opened" })).toBeNull();
    const hostile = { ...recovery, get reasonCodes(): string[] { throw new Error("private exception"); } };
    expect(decodeProjectRecoveryProjection(hostile)).toBeNull();
  });

  it("keeps confirmation and opening separate and prevents stale status regression", () => {
    expect(projectRecoveryActionLabels("preview-ready")).toEqual(["Cancel", "Create verified recovery copy"]);
    expect(projectRecoveryActionLabels("copying")).toEqual(["Cancel before publication"]);
    expect(projectRecoveryActionLabels("verified-copy-ready")).toEqual(["Open verified recovery copy"]);
    expect(projectRecoveryActionLabels("open-failed")).toEqual(["Open verified recovery copy"]);
    for (const state of ["denied", "unavailable-proof", "cancelled", "verification-failed"] as const) {
      expect(projectRecoveryActionLabels(state)).not.toContain("Open verified recovery copy");
      expect(projectRecoveryActionLabels(state)).not.toContain("Create verified recovery copy");
    }
    expect(projectRecoveryCanAdvance("preview-ready", "verified-copy-ready")).toBe(true);
    expect(projectRecoveryCanAdvance("copying", "cancelled")).toBe(true);
    expect(projectRecoveryCanAdvance("copying", "recovered")).toBe(false);
    expect(projectRecoveryCanAdvance("verified-copy-ready", "copying")).toBe(false);
    expect(projectRecoveryCanAdvance("cancelled", "preview-ready")).toBe(false);
    expect(projectRecoveryCanAdvance("open-failed", "recovered")).toBe(true);
  });

  it("sends only the exact preview through Native transport with no implicit confirmation or open", async () => {
    const transport = vi.fn().mockResolvedValue(recoveryResponse(recovery));
    await expect(requestProjectRecovery(transport, "preview", { root: "C:/Research/original", destinationRoot: "C:/Research/recovered-working-copy" })).resolves.toEqual(recovery);
    expect(transport).toHaveBeenCalledOnce();
    expect(transport.mock.calls[0]?.[0]).toEqual({ method: "POST", path: "/projects/recovery/preview",
      body: JSON.stringify({ root: "C:/Research/original", destinationRoot: "C:/Research/recovered-working-copy" }), ifMatch: null, idempotencyKey: null });
    transport.mockClear();
    await expect(requestProjectRecovery(transport, "preview", { root: "C:/Research/original", destinationRoot: "C:/Research/copy", host: "asserted-host" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(requestProjectRecovery(transport, "preview", { root: "C:/../private", destinationRoot: "C:/Research/copy" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(requestProjectRecovery(transport, "confirm", { root: "C:/Research/original", previewId: recovery.previewId, confirmation: "automatic" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(transport).not.toHaveBeenCalled();
  });

  it("rejects switched previews, content types and impossible preview success", async () => {
    const command = { root: "C:/Research/original", previewId: recovery.previewId };
    await expect(requestProjectRecovery(async () => recoveryResponse({ ...recovery, previewId: "c".repeat(32) }), "status", command)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    await expect(requestProjectRecovery(async () => ({ ...recoveryResponse(recovery), contentType: "text/html" }), "status", command)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    await expect(requestProjectRecovery(async () => ({ ...recoveryResponse(recovery), traceId: null as unknown as string }), "status", command)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    await expect(requestProjectRecovery(async () => recoveryResponse({ ...recovery, state: "recovered", requiresConfirmation: false }), "preview", { root: command.root, destinationRoot: "C:/Research/copy" })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });
});

describe("functional local projects workspace", () => {
  it("offers explicit recovery review with a native-selected copy destination and original preservation", () => {
    const markup = renderToStaticMarkup(<ProjectsWorkspace announce={vi.fn()} initialCatalog={catalog} />);
    expect(markup).toContain("Recover a project");
    expect(markup).toContain("Review recovery");
    expect(markup).toContain("Recovery copy parent folder");
    expect(markup).toContain("The original project remains unchanged");
    expect(markup).not.toMatch(/<input[^>]+id="project-recovery-parent"/);
    expect(markup).not.toContain("Create verified recovery copy");
    expect(markup).not.toContain("Open verified recovery copy");
  });

  it("renders implemented create and open workflows without reference-only application pages", () => {
    const markup = renderToStaticMarkup(<ProjectsWorkspace announce={vi.fn()} initialCatalog={catalog} />);
    expect(markup).toContain('data-projects-workspace="true"');
    expect(markup).toContain("Create a local project");
    expect(markup).toContain("Open an existing project");
    expect(markup).toContain('id="project-parent-directory"');
    expect(markup).toContain('id="project-root"');
    expect(markup).not.toMatch(/<input[^>]+id="project-(parent-directory|directory-name|root)"/);
    expect(markup).toContain("New project destination");
    expect(markup).toContain("Choose folder…");
    expect(markup).toContain('id="project-research-objective"');
    expect(markup).toContain('id="project-primary-use-case"');
    expect(markup).toContain("Theory synthesis");
    expect(markup).toContain("Reconcile competing mechanisms");
    expect(markup).toContain("Theory map, Traceable synthesis");
    expect(markup).toContain("Revisitable process");
    expect(markup).toContain("Research Intent");
    expect(markup).toContain("Theory Map");
    expect(markup).toContain("All tools remain available");
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
    expect(projectActionLabels({
      ...newer,
      lifecycleState: "archived",
      open: false,
      accessMode: "closed",
    })).toEqual([]);
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
