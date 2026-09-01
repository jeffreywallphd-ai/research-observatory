import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  canonicalWorkflowJson,
  decodeLegacyOperationBridge,
  decodeWorkflowDefinition,
  decodeWorkflowSnapshot,
  reconstructWorkflowState,
  legacyOperationBridgeErrors,
  workflowDefinitionErrors,
  workflowSnapshotErrors,
  workflowTransitionAllowed,
  workflowRecordSha256,
} from "./generated";

const root = dirname(fileURLToPath(import.meta.url));
const fixture = (name: string): Record<string, unknown> =>
  JSON.parse(readFileSync(resolve(root, "fixtures", name), "utf8")) as Record<
    string,
    unknown
  >;
const clone = (value: Record<string, unknown>): Record<string, unknown> =>
  JSON.parse(JSON.stringify(value));

describe("portable workflow contract", () => {
  it("uses one immutable definition across local and server executors", () => {
    const definition = fixture("valid-workflow-definition.v1.json");
    expect(workflowDefinitionErrors(definition)).toEqual([]);
    expect(decodeWorkflowDefinition(definition)).not.toBeNull();
    for (const profile of ["local", "server"] as const) {
      const snapshot = fixture("valid-local-workflow-snapshot.v1.json");
      if (profile === "server") {
        snapshot.snapshotId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d007";
        snapshot.executor = {
          profile: "server",
          adapterId: "server-conformant-workflow",
          adapterVersion: "1.0.0",
          contractVersion: "1.0.0",
        };
      }
      expect(workflowSnapshotErrors(definition, snapshot)).toEqual([]);
      expect(decodeWorkflowSnapshot(definition, snapshot)).not.toBeNull();
    }
    const polluted = clone(definition);
    polluted.executor = "sqlite";
    expect(decodeWorkflowDefinition(polluted)).toBeNull();

    const pathSmuggling = clone(definition);
    (
      (pathSmuggling.steps as Array<Record<string, unknown>>)[0] as Record<
        string,
        unknown
      >
    ).activityType = "C:\\tools\\run.exe";
    expect(decodeWorkflowDefinition(pathSmuggling)).toBeNull();

    const futureVersion = clone(definition);
    futureVersion.contractVersion = "2.0.0";
    expect(decodeWorkflowDefinition(futureVersion)).toBeNull();
  });

  it("reconstructs exact state from canonical history after restart", () => {
    const definition = fixture("valid-workflow-definition.v1.json");
    const snapshot = fixture("valid-local-workflow-snapshot.v1.json");
    const restarted = JSON.parse(canonicalWorkflowJson(snapshot)) as Record<
      string,
      unknown
    >;
    expect(workflowSnapshotErrors(definition, restarted)).toEqual([]);
    const state = reconstructWorkflowState(definition, restarted);
    expect(state?.["workflow-run"]?.[snapshot.workflowRunId as string]).toBe(
      snapshot.state,
    );
    const jobs = snapshot.jobs as Array<Record<string, unknown>>;
    const job = jobs[0];
    expect(job).toBeDefined();
    if (job === undefined) throw new Error("fixture job missing");
    expect(state?.job?.[job.jobId as string]).toBe(job.state);
  });

  it("fails closed on illegal transition, decreasing progress, and human-decision substitution", () => {
    const definition = fixture("valid-workflow-definition.v1.json");
    const snapshot = fixture("valid-local-workflow-snapshot.v1.json");
    expect(
      workflowTransitionAllowed("workflow-run", "succeeded", "running"),
    ).toBe(false);
    expect(workflowTransitionAllowed("job", "running", "retry-scheduled")).toBe(
      true,
    );

    const decreasing = clone(snapshot);
    const attemptEvents = (
      decreasing.history as Array<Record<string, unknown>>
    ).filter(
      (event) => event.entityType === "job-attempt" && event.progress !== null,
    );
    (attemptEvents.at(-1)?.progress as Record<string, unknown>).completedUnits =
      40;
    expect(workflowSnapshotErrors(definition, decreasing)).toContain(
      "attempt-progress-is-monotonic",
    );

    const substituted = clone(snapshot);
    const task = (substituted.humanTasks as Array<Record<string, unknown>>)[0];
    if (task === undefined) throw new Error("fixture human task missing");
    (task.decision as Record<string, unknown>).decisionId =
      "018f47a2-4d6b-7f78-9f2e-7fb76c86e099";
    expect(workflowSnapshotErrors(definition, substituted)).toContain(
      "human-decision-is-audit-bound",
    );

    const changedCommand = clone(snapshot);
    const jobs = changedCommand.jobs as Array<Record<string, unknown>>;
    const duplicateJob = clone(jobs[0] as Record<string, unknown>);
    duplicateJob.jobId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d099";
    duplicateJob.commandFingerprint = `sha256:${"d".repeat(64)}`;
    duplicateJob.attemptIds = [];
    duplicateJob.currentAttemptId = null;
    duplicateJob.state = "pending";
    jobs.push(duplicateJob);
    expect(workflowSnapshotErrors(definition, changedCommand)).toContain(
      "job-idempotency-binds-command-fingerprint",
    );

    const securityLocked = clone(snapshot);
    securityLocked.cancellation = {
      requestedAt: "2026-08-30T12:01:26.500Z",
      reasonCode: "application-locked",
      interruptionKind: "security-lock",
    };
    expect(workflowSnapshotErrors(definition, securityLocked)).toContain(
      "security-lock-does-not-auto-resume",
    );
  });

  it("keeps the legacy operation ID as an exact projection bridge", () => {
    const snapshot = fixture("valid-local-workflow-snapshot.v1.json");
    const bridge = fixture("valid-legacy-operation-bridge.v1.json");
    expect(legacyOperationBridgeErrors(snapshot, bridge)).toEqual([]);
    expect(decodeLegacyOperationBridge(snapshot, bridge)).not.toBeNull();
    const wrong = clone(bridge);
    wrong.etag = '"op-source-review-31"';
    expect(legacyOperationBridgeErrors(snapshot, wrong)).toContain(
      "legacy-operation-bridge-etag-is-exact",
    );
    const wrongSequence = clone(bridge);
    wrongSequence.operationSequence = 31;
    wrongSequence.etag = '"op-source-review-31"';
    expect(legacyOperationBridgeErrors(snapshot, wrongSequence)).toContain(
      "legacy-operation-bridge-binds-exact-workflow-projection",
    );
  });

  it("closes references, checkpoints, cancellation, and decision evidence across runtimes", () => {
    const definition = fixture("valid-workflow-definition.v1.json");
    const snapshot = fixture("valid-local-workflow-snapshot.v1.json");

    const wrongStep = clone(snapshot);
    (wrongStep.stepRuns as Array<Record<string, unknown>>)[0]!.stepKey =
      "substituted-step";
    expect(workflowSnapshotErrors(definition, wrongStep)).toContain(
      "references-close-over-snapshot",
    );

    const checkpointGap = clone(snapshot);
    (
      checkpointGap.checkpoints as Array<Record<string, unknown>>
    )[0]!.checkpointSequence = 2;
    expect(workflowSnapshotErrors(definition, checkpointGap)).toContain(
      "checkpoint-order-and-owner-are-consistent",
    );

    const partialCancellation = clone(snapshot);
    partialCancellation.cancellation = {
      requestedAt: "2026-08-30T12:01:26.500Z",
      reasonCode: null,
      interruptionKind: "ordinary-cancellation",
    };
    expect(workflowSnapshotErrors(definition, partialCancellation)).not.toEqual(
      [],
    );
    expect(decodeWorkflowSnapshot(definition, partialCancellation)).toBeNull();

    const missingEvidence = clone(snapshot);
    const task = (
      missingEvidence.humanTasks as Array<Record<string, unknown>>
    )[0]!;
    (task.decision as Record<string, unknown>).evidenceArtifactIds = [
      "018f47a2-4d6b-7f78-9f2e-7fb76c86e099",
    ];
    expect(workflowSnapshotErrors(definition, missingEvidence)).toContain(
      "human-decision-is-audit-bound",
    );

    const excludedDefinition = clone(definition);
    const humanStep = (
      excludedDefinition.steps as Array<Record<string, unknown>>
    ).find((step) => step.kind === "human-task");
    if (humanStep === undefined) throw new Error("fixture human step missing");
    const excludedHumanDefinition = humanStep.humanTask as Record<string, unknown>;
    excludedHumanDefinition.allowedDispositions = [
      "rejected",
    ];
    excludedHumanDefinition.consequencesByDisposition = {
      rejected: "end-workflow",
    };
    const excludedDisposition = clone(snapshot);
    (excludedDisposition.definition as Record<string, unknown>).contentHash =
      workflowRecordSha256(excludedDefinition);
    expect(
      workflowSnapshotErrors(excludedDefinition, excludedDisposition),
    ).toContain("human-decision-is-audit-bound");

    const unboundDefinition = clone(definition);
    const unboundStep = (
      unboundDefinition.steps as Array<Record<string, unknown>>
    ).find((step) => step.kind === "human-task");
    if (unboundStep === undefined) throw new Error("fixture human step missing");
    (unboundStep.humanTask as Record<string, unknown>).consequencesByDisposition = {
      approved: "resume-workflow",
    };
    expect(workflowDefinitionErrors(unboundDefinition)).toContain(
      "human-task-consequences-are-definition-bound",
    );

    const substitutedConsequence = clone(snapshot);
    const substitutedConsequenceTask = (
      substitutedConsequence.humanTasks as Array<Record<string, unknown>>
    )[0]!;
    (substitutedConsequenceTask.decision as Record<string, unknown>).consequenceCode =
      "end-workflow";
    expect(workflowSnapshotErrors(definition, substitutedConsequence)).toContain(
      "human-decision-is-audit-bound",
    );

    for (const [field, replacement] of [
      [
        "requestedBy",
        {
          actorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86e099",
          actorType: "system",
          role: "workflow-coordinator",
        },
      ],
      ["requestedAt", "2026-08-30T12:01:24.500Z"],
    ] as const) {
      const substitutedRequest = clone(snapshot);
      const substitutedTask = (
        substitutedRequest.humanTasks as Array<Record<string, unknown>>
      )[0]!;
      substitutedTask[field] = replacement;
      expect(workflowSnapshotErrors(definition, substitutedRequest)).toContain(
        "human-decision-is-audit-bound",
      );
    }

    const substitutedClaim = clone(snapshot);
    const claimEvent = (
      substitutedClaim.history as Array<Record<string, unknown>>
    ).find(
      (event) =>
        event.entityType === "human-task" && event.toState === "claimed",
    );
    if (claimEvent === undefined) throw new Error("fixture claim event missing");
    (claimEvent.actor as Record<string, unknown>).actorId =
      "018f47a2-4d6b-7f78-9f2e-7fb76c86e099";
    expect(workflowSnapshotErrors(definition, substitutedClaim)).toContain(
      "human-decision-is-audit-bound",
    );

    const duplicateRequest = clone(snapshot);
    const history = duplicateRequest.history as Array<Record<string, unknown>>;
    const requestEvent = history.find(
      (event) =>
        event.entityType === "human-task" && event.toState === "requested",
    );
    if (requestEvent === undefined) throw new Error("fixture request event missing");
    history[25] = {
      ...clone(requestEvent),
      eventId: "018f47a2-4d6b-7f78-9f2e-7fb76c86e026",
      sequence: 26,
    };
    expect(workflowSnapshotErrors(definition, duplicateRequest)).toContain(
      "human-decision-is-audit-bound",
    );
  });

  it("rejects duplicate transition identities without changing valid restart replay", () => {
    const definition = fixture("valid-workflow-definition.v1.json");
    const snapshot = fixture("valid-local-workflow-snapshot.v1.json");
    const duplicate = clone(snapshot);
    const history = duplicate.history as Array<Record<string, unknown>>;
    history[1]!.eventId = history[0]!.eventId;
    expect(workflowSnapshotErrors(definition, duplicate)).toContain(
      "history-event-identities-are-unique",
    );
    expect(decodeWorkflowSnapshot(definition, duplicate)).toBeNull();
    expect(decodeWorkflowSnapshot(definition, clone(snapshot))).not.toBeNull();
  });
});
