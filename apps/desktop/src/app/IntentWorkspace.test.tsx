import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { IntentDraftProjection, ProjectProjection, IntentWorkspaceProjection } from "@research-observatory/contracts/core-api";

import {
  INTENT_MODE_GUIDANCE,
  IntentWorkspace,
  intentAcceptanceAvailability,
  intentAcceptanceRequest,
  intentWorkspaceAvailability,
  selectedIntentGuidance,
} from "./IntentWorkspace";

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

const emptyWorkspace: IntentWorkspaceProjection = {
  schemaVersion: "1.0",
  projectId: project.projectId,
  current: null,
  history: [],
};

describe("guided research intent workspace", () => {
  it("keeps the governed fourteen-use-case catalog mode specific", () => {
    expect(INTENT_MODE_GUIDANCE).toHaveLength(14);
    expect(new Set(INTENT_MODE_GUIDANCE.map((item) => item.id)).size).toBe(14);
    expect(selectedIntentGuidance("systematic-review")).toMatchObject({
      epistemicMode: "systematic",
      defaultStoppingConditions: ["coverage-threshold"],
    });
    expect(selectedIntentGuidance("theory-synthesis").workflow).toContain("Theory Map");
    expect(selectedIntentGuidance("novelty-audit").warning).toContain("nearest prior work");
  });

  it("requires an open compatible writable project and exposes safe boundary states", () => {
    expect(intentWorkspaceAvailability(null)).toMatchObject({ available: false, state: "empty" });
    expect(intentWorkspaceAvailability({ ...project, open: false, accessMode: "closed" })).toMatchObject({
      available: false,
      state: "offline",
    });
    expect(intentWorkspaceAvailability({ ...project, accessMode: "read-only" })).toMatchObject({
      available: false,
      state: "denied",
    });
    expect(intentWorkspaceAvailability(project)).toEqual({
      available: true,
      state: null,
      message: "Research intent is available for this exclusive local project session.",
    });
  });

  it("renders approved intent regions, explicit impact review, and a disabled launch boundary", () => {
    const markup = renderToStaticMarkup(
      <IntentWorkspace
        project={project}
        announce={vi.fn()}
        initialWorkspace={emptyWorkspace}
      />,
    );
    expect(markup).toContain('data-intent-workspace="true"');
    expect(markup).toContain("Research Intent Contract");
    expect(markup).toContain("Purpose and intended contribution");
    expect(markup).toContain("Primary use case and guided workflow");
    expect(markup).toContain("Scope and evidence policy");
    expect(markup).toContain("AI authority profile");
    expect(markup).toContain("Novelty standard");
    expect(markup).toContain("Stopping logic");
    expect(markup).toContain("Preview revision effects");
    expect(markup).toContain("Workflow change has downstream effects");
    expect(markup).toContain("Save draft revision");
    expect(markup).toContain("Launch gated analysis");
    expect(markup).toMatch(/disabled=""[^>]*>Launch gated analysis/);
    expect(markup).toContain("Drafts never govern consequential analysis");
    expect(markup).toContain("Human acceptance rationale");
    expect(markup).toContain("Accept intent revision");
    expect(markup).toContain("I reviewed and confirm persisted revision");
  });

  it("binds human acceptance to the exact decision-complete draft", () => {
    const current = {
      status: "draft",
      revision: 3,
      revisionId: "019d5f72-5331-7000-8000-000000000003",
      revisionContentHash: "a".repeat(64),
      decisionComplete: true,
      canRequestAcceptance: true,
      launchReady: false,
    } as IntentDraftProjection;

    expect(intentAcceptanceAvailability(current)).toEqual({
      available: true,
      state: "ready",
      message: "Review and confirm this exact decision-complete draft before it can govern automation.",
    });
    expect(intentAcceptanceRequest(project.root, current, "Reviewed scope and authority.")).toEqual({
      root: project.root,
      expectedRevision: 3,
      expectedRevisionContentHash: "a".repeat(64),
      confirmed: true,
      decisionRationale: "Reviewed scope and authority.",
    });
    expect(intentAcceptanceAvailability({ ...current, decisionComplete: false, canRequestAcceptance: false })).toMatchObject({
      available: false,
      state: "incomplete",
    });
    expect(intentAcceptanceAvailability({ ...current, status: "accepted", canRequestAcceptance: false, launchReady: true })).toMatchObject({
      available: false,
      state: "accepted",
    });
  });
});
