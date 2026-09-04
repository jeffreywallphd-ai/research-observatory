import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ProjectProjection, WorkflowProgressProjection } from "@research-observatory/contracts/core-api";

import { ProjectHomeWorkspace } from "./ProjectHomeWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "01890f47-eae3-4cc0-98c4-dc0c0c073981",
  displayName: "Interpretive study",
  templateId: "hermeneutic-inquiry",
  lifecycleState: "active",
  root: "C:/Research/interpretive-study",
  open: true,
  accessMode: "read-write",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  revision: 1,
  deleteConfirmation: `delete:01890f47-eae3-4cc0-98c4-dc0c0c073981`,
};

const progress: WorkflowProgressProjection = {
  schemaVersion: "1.0",
  projectId: project.projectId,
  selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d071",
  selectionRevisionContentHash: `sha256:${"a".repeat(64)}`,
  intentRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d070",
  intentRevisionContentHash: `sha256:${"d".repeat(64)}`,
  profileId: "hermeneutic-inquiry",
  profileTitle: "Hermeneutic inquiry",
  processForm: "revisitable",
  bootstrapRequired: false,
  current: {
    stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d072",
    stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d073",
    revision: 1,
    revisionContentHash: `sha256:${"b".repeat(64)}`,
    parentStateRevisionId: null,
    stageKey: "interpretive-loop-1",
    pageContractId: "synthesis-studio.html",
    navigationRole: "primary",
    passNumber: 1,
    status: "current",
    completionEvidenceIds: [],
    attentionReason: null,
    staleCauseIds: [],
    skipRationale: null,
    updatedAt: "2026-09-04T02:00:00.000Z",
  },
  recommendedStageKey: "interpretive-loop-1",
  recommendedPageContractId: "synthesis-studio.html",
  recommendedAction: "Continue the current stage; completion requires explicit human evidence.",
  checkpointState: "unknown",
  checkpointRationale: "No checkpoint authority has been approved for this stage.",
  supportingHandoff: null,
  staleOutputs: [{
    outputRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d074",
    disposition: "unknown-impact",
    reason: "dependency-coverage-incomplete",
    causeReferenceHash: `sha256:${"c".repeat(64)}`,
    safestNextAction: "Review the exact dependency change before recomputing or accepting this output.",
  }],
  history: [],
};

const completedEarlierStage: NonNullable<WorkflowProgressProjection["current"]> = {
  ...progress.current!,
  stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d080",
  stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d081",
  revision: 2,
  revisionContentHash: `sha256:${"e".repeat(64)}`,
  stageKey: "intent-contract-1",
  pageContractId: "intent-contract.html",
  status: "completed",
  completionEvidenceIds: ["018f47a2-4d6b-7f78-9f2e-7fb76c86d082"],
  updatedAt: "2026-09-04T01:00:00.000Z",
};

describe("ProjectHomeWorkspace", () => {
  it("shows persisted position, unknown gate truth, stale impact, and one route back", () => {
    const html = renderToStaticMarkup(
      <ProjectHomeWorkspace
        project={project}
        progress={progress}
        loadState="ready"
        failure={null}
        busy={false}
        onStart={() => undefined}
        onResume={() => undefined}
        onOpenCurrent={() => undefined}
        onRevisit={() => undefined}
      />,
    );

    expect(html).toContain('data-project-home-state="ready"');
    expect(html).toContain('data-workflow-profile="hermeneutic-inquiry"');
    expect(html).toContain("Interpretive study");
    expect(html).toContain("Hermeneutic inquiry · Revisitable workflow");
    expect(html).toContain("interpretive-loop-1");
    expect(html).toContain("Open current step");
    expect(html).toContain("Not yet governed");
    expect(html).toContain("No checkpoint authority has been approved");
    expect(html).toContain("Impact unknown");
    expect(html).toContain("dependency-coverage-incomplete");
    expect(html).not.toContain("gate passed");
  });

  it.each(["attention-required", "blocked"] as const)(
    "offers an explicit researcher resume for a %s current head",
    (status) => {
      const html = renderToStaticMarkup(
        <ProjectHomeWorkspace
          project={project}
          progress={{
            ...progress,
            current: {
              ...progress.current!,
              status,
              attentionReason: `${status} requires an explicit researcher decision.`,
            },
          }}
          loadState="ready"
          failure={null}
          busy={false}
          onStart={() => undefined}
          onResume={() => undefined}
          onOpenCurrent={() => undefined}
          onRevisit={() => undefined}
        />,
      );

      expect(html).toContain(status);
      expect(html).toContain("Resume current step");
      expect(html).not.toContain("Workflow complete");
      expect(html).not.toContain("Begin another pass");
    },
  );

  it("offers an explicit exact-source revisit while a later stage remains current", () => {
    const html = renderToStaticMarkup(
      <ProjectHomeWorkspace
        project={project}
        progress={{ ...progress, history: [completedEarlierStage] }}
        loadState="ready"
        failure={null}
        busy={false}
        onStart={() => undefined}
        onResume={() => undefined}
        onOpenCurrent={() => undefined}
        onRevisit={() => undefined}
      />,
    );

    expect(html).toContain('data-workflow-revisit-options="true"');
    expect(html).toContain("Revisit completed steps");
    expect(html).toContain("Revisit intent-contract-1");
    expect(html).toContain("another step is current, it remains recorded in progress");
    expect(html).not.toContain("Begin another pass");
  });

  it("keeps loading, error, and no-project states explicit", () => {
    const loading = renderToStaticMarkup(
      <ProjectHomeWorkspace
        project={project}
        progress={null}
        loadState="loading"
        failure={null}
        busy={false}
        onStart={() => undefined}
        onResume={() => undefined}
        onOpenCurrent={() => undefined}
        onRevisit={() => undefined}
      />,
    );
    expect(loading).toContain('role="status"');
    expect(loading).toContain("Loading the persisted workflow position");

    const error = renderToStaticMarkup(
      <ProjectHomeWorkspace
        project={project}
        progress={null}
        loadState="error"
        failure="Persisted workflow authority could not be validated."
        busy={false}
        onStart={() => undefined}
        onResume={() => undefined}
        onOpenCurrent={() => undefined}
        onRevisit={() => undefined}
      />,
    );
    expect(error).toContain('role="alert"');
    expect(error).toContain("Persisted workflow authority could not be validated");

    const empty = renderToStaticMarkup(
      <ProjectHomeWorkspace
        project={null}
        progress={null}
        loadState="unavailable"
        failure={null}
        busy={false}
        onStart={() => undefined}
        onResume={() => undefined}
        onOpenCurrent={() => undefined}
        onRevisit={() => undefined}
      />,
    );
    expect(empty).toContain('data-project-home-state="empty"');
  });
});
