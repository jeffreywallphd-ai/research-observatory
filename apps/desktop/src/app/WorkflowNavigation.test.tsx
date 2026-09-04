import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { WorkflowProgressProjection } from "@research-observatory/contracts/core-api";

import { WorkflowNavigation } from "./WorkflowNavigation";
import {
  createSupportingReturn,
  type WorkflowAuthoritySnapshot,
} from "./workflowNavigationModel";

const authority: WorkflowAuthoritySnapshot = {
  projectId: "11111111-1111-4111-8111-111111111111",
  projectRoot: "C:/Research/current-project",
  intentRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
  intentRevisionContentHash: `sha256:${"a".repeat(64)}`,
  profileCatalogHash: `sha256:${"b".repeat(64)}`,
  profileCatalogVersion: "1.0.0",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
  referenceVersion: "1.5",
  intentGuidanceVersion: "1.0.0",
  intentGuidanceHash: `sha256:${"c".repeat(64)}`,
  profileId: "manuscript-review-revision",
  currentStageKey: "intent-contract-1",
  currentPageContractId: "intent-contract.html",
  profile: {
    profileId: "manuscript-review-revision",
    epistemicMode: "empirical",
    title: "Manuscript review & revision",
    purpose: "Challenge a manuscript while preserving researcher authority.",
    example: "Review a manuscript.",
    expectedOutputs: ["Review package", "Revised manuscript"],
    processForm: "revisitable",
    defaultEvidenceTypes: ["empirical-study"],
    defaultNoveltyStandard: "not-claimed",
    defaultAutonomyLevel: "suggest",
    defaultStoppingConditions: ["researcher-decision"],
    warning: "Claims remain bounded.",
    stages: [
      {
        stageKey: "intent-contract-1",
        order: 1,
        pageContractId: "intent-contract.html",
        label: "Research Intent",
        optional: false,
        rationale: "Bind the objective and authority.",
        checkpointState: "unknown",
        checkpointRationale: "No stage-specific checkpoint authority is declared.",
      },
      {
        stageKey: "manuscript-studio-1",
        order: 2,
        pageContractId: "manuscript-studio.html",
        label: "Manuscript Studio",
        optional: true,
        rationale: "Inspect the current manuscript.",
        checkpointState: "unknown",
        checkpointRationale: "No stage-specific checkpoint authority is declared.",
      },
      {
        stageKey: "audit-lineage-1",
        order: 3,
        pageContractId: "audit-lineage.html",
        label: "Audit & Lineage",
        optional: false,
        rationale: "Inspect source-to-output lineage.",
        checkpointState: "unknown",
        checkpointRationale: "No stage-specific checkpoint authority is declared.",
      },
    ],
  },
};

const primaryStage = {
  attentionReason: null,
  completionEvidenceIds: [],
  navigationRole: "primary" as const,
  pageContractId: authority.currentPageContractId,
  parentStateRevisionId: null,
  passNumber: 1,
  revision: 1,
  revisionContentHash: `sha256:${"d".repeat(64)}`,
  skipRationale: null,
  stageKey: authority.currentStageKey,
  stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d061",
  stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d062",
  staleCauseIds: [],
  status: "current" as const,
  updatedAt: "2026-09-03T12:00:00.000Z",
};

const supportingProgress: WorkflowProgressProjection & {
  readonly intentRevisionId: string;
  readonly intentRevisionContentHash: string;
} = {
  schemaVersion: "1.0",
  projectId: authority.projectId,
  intentRevisionId: authority.intentRevisionId,
  intentRevisionContentHash: authority.intentRevisionContentHash,
  selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d051",
  selectionRevisionContentHash: `sha256:${"e".repeat(64)}`,
  profileId: authority.profileId,
  profileTitle: authority.profile.title,
  processForm: authority.profile.processForm,
  bootstrapRequired: false,
  current: primaryStage,
  recommendedStageKey: authority.currentStageKey,
  recommendedPageContractId: authority.currentPageContractId,
  recommendedAction: "Continue the current stage.",
  checkpointState: "unknown",
  checkpointRationale: "No stage-specific checkpoint authority is declared.",
  supportingHandoff: {
    navigationRole: "supporting",
    pageContractId: "task-center.html",
    returnStageStateRevisionId: primaryStage.stageStateRevisionId,
    revisionContentHash: `sha256:${"f".repeat(64)}`,
    stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d071",
    stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d072",
  },
  staleOutputs: [],
  history: [],
};

describe("WorkflowNavigation", () => {
  it("renders an accessible ordered rail, context, unknown gate truth, outputs, and complete tool disclosure", () => {
    const html = renderToStaticMarkup(
      <WorkflowNavigation
        authority={authority}
        currentWorkspace="intent"
        loadState="ready"
        authoritativeStates={{ "audit-lineage-1": "attention-required" }}
        onSelectStage={() => undefined}
        onSelectWorkspace={() => undefined}
        onReturn={() => undefined}
      />,
    );

    expect(html).toContain('data-workflow-navigation="true"');
    expect(html).toContain('data-workflow-nav="true"');
    expect(html).toContain('aria-label="Ordered steps for the selected use case"');
    expect(html).toContain('aria-current="step"');
    expect(html).toContain("Step 1 of 3");
    expect(html).toContain("Current");
    expect(html).toContain("Attention required");
    expect(html).toContain("Optional");
    expect(html).toContain("Revisitable workflow");
    expect(html).toContain("Bind the objective and authority.");
    expect(html).toContain("Expected output");
    expect(html).toContain("Review package; Revised manuscript");
    expect(html).toContain("Quality gate · Unknown");
    expect(html).toContain("No stage-specific checkpoint authority is declared.");
    expect(html).toContain("Previous step · None");
    expect(html).toContain("Next step · Manuscript Studio");
    expect(html).toContain("Unavailable in this version");
    expect(html).toContain("<details");
    expect(html).toContain("All tools");
    expect(html).toContain("Local projects");
    expect(html).toContain("Diagnostics &amp; support");
    expect(html).not.toContain('href="manuscript-studio.html"');
  });

  it("can place the workflow context in the workspace without duplicating it in the rail", () => {
    const rail = renderToStaticMarkup(
      <WorkflowNavigation
        authority={authority}
        currentWorkspace="intent"
        loadState="ready"
        showContext={false}
        onSelectStage={() => undefined}
        onSelectWorkspace={() => undefined}
        onReturn={() => undefined}
      />,
    );

    expect(rail).toContain('data-workflow-nav="true"');
    expect(rail).not.toContain("Current guided workflow position");
  });

  it("labels a supporting tool and exposes one exact return action", () => {
    const supportingReturn = createSupportingReturn(authority, "tasks", supportingProgress);
    const html = renderToStaticMarkup(
      <WorkflowNavigation
        authority={authority}
        currentWorkspace="tasks"
        loadState="ready"
        supportingReturn={supportingReturn}
        onSelectStage={() => undefined}
        onSelectWorkspace={() => undefined}
        onReturn={() => undefined}
      />,
    );

    expect(html).toContain("Supporting tool · Task Center");
    expect(html.match(/Return to current step/g)).toHaveLength(1);
    expect(html).toContain("Return to current step · Research Intent");
  });

  it("keeps the functional tool inventory available without fabricating a selected workflow", () => {
    const html = renderToStaticMarkup(
      <WorkflowNavigation
        authority={null}
        currentWorkspace="home"
        loadState="unavailable"
        failure="Open a compatible local project with a current Research Intent to load guided workflow navigation."
        onSelectStage={() => undefined}
        onSelectWorkspace={() => undefined}
        onReturn={() => undefined}
      />,
    );

    expect(html).toContain("Guided workflow unavailable");
    expect(html).toContain("current Research Intent");
    expect(html).toContain("All tools");
    expect(html).not.toContain("Step 1 of");
    expect(html).not.toContain('aria-current="step"');
    expect(html).toContain('aria-current="page"');
  });

  it("denies an exact return after authority substitution", () => {
    const supportingReturn = createSupportingReturn(authority, "tasks", supportingProgress);
    const html = renderToStaticMarkup(
      <WorkflowNavigation
        authority={{ ...authority, intentRevisionContentHash: `sha256:${"c".repeat(64)}` }}
        currentWorkspace="tasks"
        loadState="ready"
        supportingReturn={supportingReturn}
        onSelectStage={() => undefined}
        onSelectWorkspace={() => undefined}
        onReturn={() => undefined}
      />,
    );

    expect(html).toContain("Supporting context expired");
    expect(html).not.toContain("Return to current step ·");
  });
});
