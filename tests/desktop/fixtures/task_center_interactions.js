(() => {
  const traceId = "0123456789abcdef0123456789abcdef";
  const projectAId = "11111111-1111-4111-8111-111111111111";
  const projectBId = "22222222-2222-4222-8222-222222222222";
  const runAId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d005";
  const runBId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d105";
  const jobAId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d006";
  const humanTaskBId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d130";
  let failNextCancel = false;
  let delayNextA = false;
  const pendingA = [];
  const project = (key, open = true) => ({
    schemaVersion: "1.0",
    projectId: key === "A" ? projectAId : projectBId,
    displayName: key === "A" ? "Study One" : "Study Two",
    templateId: "theory-synthesis",
    lifecycleState: "active",
    root: key === "A" ? "C:/Research/study-one" : "C:/Research/study-two",
    open,
    revision: 0,
    accessMode: open ? "read-write" : "closed",
    compatibilityState: "compatible",
    packageFormatVersion: "1.0.0",
    backupRequiredBeforeRepair: false,
    recoveryAction: "none",
    deleteConfirmation: `delete:${key === "A" ? projectAId : projectBId}`,
  });
  let runA = {
    schemaVersion: "1.0",
    workflowRunId: runAId,
    workflowKey: "project-a-extract",
    definitionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d002",
    definitionVersion: "1.0.0",
    snapshotId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d004",
    snapshotRevision: 1,
    continuationFromWorkflowRunId: null,
    continuationFromJobId: null,
    state: "running",
    activeCompute: true,
    progress: { kind: "quantified", unit: "steps", completedUnits: 0, totalUnits: 1 },
    revision: 11,
    interruptionKind: null,
    updatedAt: "2026-08-30T12:01:11.000Z",
    steps: [{
      stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
      stepKey: "extract",
      kind: "activity",
      state: "running",
      dependsOn: [],
    }],
    jobs: [{
      jobId: jobAId,
      state: "running",
      activityType: "source-extraction",
      resourcePool: "document",
      priority: 4,
      attemptCount: 1,
      maxAttempts: 3,
      currentAttemptId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d008",
      workerId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d009",
      progress: { kind: "quantified", unit: "records", completedUnits: 40, totalUnits: 100 },
      latestCheckpointId: null,
      latestCheckpointAt: null,
      diagnosticCode: null,
      updatedAt: "2026-08-30T12:01:11.000Z",
    }],
    humanTasks: [],
    retainedArtifacts: [],
    events: [{
      sequence: 11,
      entityType: "job",
      entityId: jobAId,
      toState: "running",
      occurredAt: "2026-08-30T12:01:11.000Z",
      reasonCode: "job-started",
    }],
  };
  let runB = {
    schemaVersion: "1.0",
    workflowRunId: runBId,
    workflowKey: "project-b-review",
    definitionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d102",
    definitionVersion: "1.1.0",
    snapshotId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d104",
    snapshotRevision: 1,
    continuationFromWorkflowRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d101",
    continuationFromJobId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d107",
    state: "waiting-human",
    activeCompute: false,
    progress: { kind: "quantified", unit: "steps", completedUnits: 1, totalUnits: 2 },
    revision: 22,
    interruptionKind: null,
    updatedAt: "2026-08-30T12:01:22.000Z",
    steps: [{
      stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d111",
      stepKey: "review",
      kind: "human-task",
      state: "waiting-human",
      dependsOn: [],
    }],
    jobs: [],
    humanTasks: [{
      humanTaskId: humanTaskBId,
      stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d111",
      state: "claimed",
      requiredRole: "researcher",
      assignedActorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d141",
      requestedAt: "2026-08-30T12:01:20.000Z",
      evidenceArtifactIds: [],
      allowedDispositions: ["approved", "rejected"],
      consequencesByDisposition: { approved: "resume-workflow", rejected: "end-workflow" },
      decisionId: null,
      disposition: null,
      decidedAt: null,
    }],
    retainedArtifacts: [],
    events: [{
      sequence: 22,
      entityType: "human-task",
      entityId: humanTaskBId,
      toState: "claimed",
      occurredAt: "2026-08-30T12:01:22.000Z",
      reasonCode: "human-task-claimed",
    }],
  };
  const response = (body, etag = null, status = 200) => ({
    status,
    contentType: "application/json",
    traceId,
    etag,
    body: JSON.stringify(body),
  });
  const workflowEtag = (run) =>
    `"workflow-${run.workflowRunId}-${run.revision}-${run.snapshotRevision}"`;
  window.__FAIL_NEXT_CANCEL__ = () => { failNextCancel = true; };
  window.__DELAY_NEXT_A__ = () => { delayNextA = true; };
  window.__RESOLVE_A__ = () => {
    for (const resolve of pendingA.splice(0)) {
      resolve(response({ schemaVersion: "1.0", items: [runA] }));
    }
  };
  window.__TAURI_INTERNALS__ = {
    transformCallback: () => 1,
    invoke: async (command, args) => {
      if (command === "application_lock_status") {
        return {
          schemaVersion: "1.0",
          state: "unlocked",
          signInMode: "none",
          policyRevision: 1,
          profileName: null,
          inactivityTimeoutMinutes: 0,
          configurationState: "valid",
          reason: null,
          threatDisclosure: "Application-session protection only; this is not Windows-account isolation.",
          retryAfterSeconds: 0,
          auditSequence: 0,
        };
      }
      if (command === "application_lock_activity" || command === "plugin:event|unlisten") return undefined;
      if (command === "plugin:event|listen") return 1;
      if (command === "core_runtime_start" || command === "core_runtime_status") {
        return { state: "ready", attempt: 1, retryAvailable: false, diagnosticReference: null };
      }
      if (command === "core_runtime_stop") return undefined;
      if (command !== "core_api_request") throw new Error(`unsupported command ${command}`);
      const request = args.request;
      if (request.path === "/projects") return response(project("A", false));
      if (request.path === "/projects/open") {
        const root = JSON.parse(request.body).root;
        return response(project(root.endsWith("study-two") ? "B" : "A"));
      }
      if (request.method === "GET" && request.path.startsWith("/projects/workflows/task-center?")) {
        const root = new URL(`http://local${request.path}`).searchParams.get("root");
        if (root === project("A").root && delayNextA) {
          delayNextA = false;
          return await new Promise((resolve) => pendingA.push(resolve));
        }
        return response({ schemaVersion: "1.0", items: [root === project("B").root ? runB : runA] });
      }
      if (request.path === `/projects/workflows/jobs/${jobAId}/cancel`) {
        if (failNextCancel) {
          failNextCancel = false;
          return response({
            type: "urn:research-observatory:problem:workflow-precondition-failed",
            title: "Workflow authority changed",
            status: 412,
            detail: "The workflow changed before cancellation.",
            code: "RO-CORE-WORKFLOW-PRECONDITION-FAILED",
            traceId,
            retryable: true,
            remediation: "Refresh Task Center and review the current workflow.",
          }, null, 412);
        }
        if (request.ifMatch !== workflowEtag(runA)) throw new Error("cancel ETag drifted");
        runA = {
          ...runA,
          state: "cancelling",
          revision: 12,
          jobs: [{ ...runA.jobs[0], state: "cancelling" }],
          events: [...runA.events, {
            sequence: 12,
            entityType: "job",
            entityId: jobAId,
            toState: "cancelling",
            occurredAt: "2026-08-30T12:01:12.000Z",
            reasonCode: "user-requested",
          }],
        };
        return response(runA, workflowEtag(runA));
      }
      if (request.path === `/projects/workflows/human-tasks/${humanTaskBId}/decide`) {
        if (request.ifMatch !== workflowEtag(runB) || JSON.parse(request.body).disposition !== "approved") {
          throw new Error("human decision authority drifted");
        }
        runB = {
          ...runB,
          state: "succeeded",
          snapshotRevision: 2,
          revision: 23,
          progress: { kind: "quantified", unit: "steps", completedUnits: 2, totalUnits: 2 },
          steps: [{ ...runB.steps[0], state: "succeeded" }],
          humanTasks: [{
            ...runB.humanTasks[0],
            state: "completed",
            decisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d131",
            disposition: "approved",
            decidedAt: "2026-08-30T12:01:23.000Z",
          }],
          events: [...runB.events, {
            sequence: 23,
            entityType: "human-task",
            entityId: humanTaskBId,
            toState: "completed",
            occurredAt: "2026-08-30T12:01:23.000Z",
            reasonCode: "human-decision-recorded",
          }],
        };
        return response(runB, workflowEtag(runB));
      }
      throw new Error(`unsupported Core API path ${request.path}`);
    },
  };
})();
