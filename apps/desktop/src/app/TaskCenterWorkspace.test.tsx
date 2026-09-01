import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ProjectProjection, WorkflowTaskCenterRun } from "@research-observatory/contracts/core-api";

import { TaskCenterWorkspace } from "./TaskCenterWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "6f93073a-5af0-47ef-b9cf-d5027e0ded99",
  displayName: "Local study",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: true,
  revision: 4,
  accessMode: "read-write",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  deleteConfirmation: "delete:6f93073a-5af0-47ef-b9cf-d5027e0ded99",
};

const waiting: WorkflowTaskCenterRun = {
  schemaVersion: "1.0",
  workflowRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d005",
  workflowKey: "source-review",
  definitionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d002",
  definitionVersion: "1.0.0",
  snapshotId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d004",
  snapshotRevision: 1,
  state: "waiting-human",
  activeCompute: false,
  progress: { kind: "quantified", unit: "steps", completedUnits: 1, totalUnits: 2 },
  revision: 28,
  interruptionKind: null,
  updatedAt: "2026-08-30T12:01:28.000Z",
  steps: [{
    stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
    stepKey: "review-source",
    kind: "human-task",
    state: "waiting-human",
    dependsOn: ["extract-source"],
  }],
  jobs: [],
  humanTasks: [{
    humanTaskId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d030",
    stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
    state: "claimed",
    requiredRole: "researcher",
    assignedActorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
    requestedAt: "2026-08-30T12:01:25.000Z",
    evidenceArtifactIds: ["018f47a2-4d6b-7f78-9f2e-7fb76c86d026"],
    allowedDispositions: ["approved", "rejected"],
    consequencesByDisposition: {
      approved: "resume-workflow",
      rejected: "end-workflow",
    },
    decisionId: null,
    disposition: null,
    decidedAt: null,
  }],
  retainedArtifacts: [],
  events: [{
    sequence: 28,
    entityType: "human-task",
    entityId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d030",
    toState: "claimed",
    occurredAt: "2026-08-30T12:01:28.000Z",
    reasonCode: "human-task-claimed",
  }],
};

describe("Task Center workspace", () => {
  it("distinguishes a human wait from active compute and presents definition-bound choices", () => {
    const html = renderToStaticMarkup(
      <TaskCenterWorkspace project={project} announce={() => undefined} initialRuns={[waiting]} />,
    );
    expect(html).toContain("Task Center");
    expect(html).toContain("Waiting for review");
    expect(html).toContain("Compute is stopped while a human decision is required.");
    expect(html).toContain("The definition—not this screen—controls each consequence.");
    expect(html).toContain("approved — resume workflow</button>");
    expect(html).toContain("rejected — end workflow</button>");
  });

  it("keeps inspection available but disables commands for read-only projects", () => {
    const html = renderToStaticMarkup(
      <TaskCenterWorkspace project={{ ...project, accessMode: "read-only" }} announce={() => undefined} initialRuns={[waiting]} />,
    );
    expect(html).toContain("Read-only workflow view");
    expect(html).toContain("disabled");
  });

  it("shows explicit empty and offline states", () => {
    expect(renderToStaticMarkup(<TaskCenterWorkspace project={project} announce={() => undefined} initialRuns={[]} />))
      .toContain("No durable work");
    expect(renderToStaticMarkup(<TaskCenterWorkspace project={null} announce={() => undefined} initialRuns={[]} />))
      .toContain("No project open");
  });

  it("reports cancellation artifact disposition and offers continuation only for terminal work", () => {
    const cancelled: WorkflowTaskCenterRun = {
      ...waiting,
      state: "cancelled",
      humanTasks: [],
      retainedArtifacts: ["retained-incomplete"],
      jobs: [{
        jobId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d006",
        state: "cancelled",
        activityType: "extract-source",
        resourcePool: "document",
        priority: 4,
        attemptCount: 1,
        maxAttempts: 3,
        currentAttemptId: null,
        workerId: null,
        progress: { kind: "quantified", unit: "records", completedUnits: 40, totalUnits: 100 },
        latestCheckpointId: null,
        latestCheckpointAt: null,
        diagnosticCode: "user-requested",
        updatedAt: "2026-08-30T12:02:00.400Z",
      }],
    };
    const html = renderToStaticMarkup(
      <TaskCenterWorkspace project={project} announce={() => undefined} initialRuns={[cancelled]} />,
    );
    expect(html).toContain("Partial artifacts: retained-incomplete.");
    expect(html).toContain("Retry as continuation");
    expect(html).toContain("No compute is active.");
  });
});
