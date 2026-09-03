import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  createCoreApiClient,
  type CoreApiRequest,
  type CoreApiResponse,
  type IntentDraftProjection,
  type ProjectProjection,
  type IntentWorkspaceProjection,
  type WorkflowProfileCatalogProjection,
} from "@research-observatory/contracts/core-api";

import {
  IntentAcceptanceCoordinator,
  IntentWorkspace,
  acceptedIntentWorkspace,
  intentFieldAffectsImpact,
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

const catalog: WorkflowProfileCatalogProjection = {
  schemaVersion: "1.0",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
  referenceVersion: "1.5",
  profileCatalogVersion: "1.0.0",
  profileCatalogHash: `sha256:${"a".repeat(64)}`,
  allToolsAccessible: true,
  evidenceRequirementsUnchanged: true,
  provenanceRequirementsUnchanged: true,
  registeredToolPageContractIds: ["intent-contract.html", "theory-map.html"],
  profiles: [{
    profileId: "theory-synthesis",
    title: "Theory synthesis",
    purpose: "Integrate theories while retaining boundaries and disagreements.",
    expectedOutputs: ["Theory architecture and integration opportunities"],
    processForm: "revisitable",
    stages: [
      { stageKey: "intent-contract-1", order: 1, pageContractId: "intent-contract.html", label: "Research Intent", optional: false, rationale: "Set authority.", checkpointState: "unknown", checkpointRationale: "Not specified." },
      { stageKey: "theory-map-1", order: 2, pageContractId: "theory-map.html", label: "Theory Map", optional: false, rationale: "Map theory.", checkpointState: "unknown", checkpointRationale: "Not specified." },
    ],
  }],
};

const decisionCompleteDraft: IntentDraftProjection = {
  schemaVersion: "1.0",
  intentId: "019d5f72-5331-7000-8000-000000000001",
  revisionId: "019d5f72-5331-7000-8000-000000000003",
  revision: 3,
  revisionContentHash: `sha256:${"a".repeat(64)}`,
  createdAt: "2026-08-29T12:00:00Z",
  status: "draft",
  primaryUseCase: "theory-synthesis",
  epistemicMode: "theory",
  researchObjective: "Explain the bounded phenomenon.",
  contributionIntent: "Prepare a traceable theory synthesis.",
  phenomenon: "Evidence use",
  unitOfAnalysis: "Study",
  levelOfAnalysis: "Field",
  sourceKinds: ["peer-reviewed-article"],
  languageCodes: ["en"],
  startYear: 2020,
  endYear: 2026,
  includePrivateReports: false,
  evidenceTypes: ["theoretical-work"],
  noveltyStandard: "theoretical",
  noveltyRationale: "Compare the nearest theory syntheses.",
  autonomyLevel: "suggest",
  stoppingConditions: ["interpretive-saturation"],
  revisionRationale: "Decision-complete bounded draft.",
  unresolvedDecisions: [],
  decisionComplete: true,
  canRequestAcceptance: true,
  launchReady: false,
};

const decisionCompleteWorkspace: IntentWorkspaceProjection = {
  schemaVersion: "1.0",
  projectId: project.projectId,
  current: decisionCompleteDraft,
  history: [{
    revision: decisionCompleteDraft.revision,
    revisionId: decisionCompleteDraft.revisionId,
    revisionContentHash: decisionCompleteDraft.revisionContentHash,
    createdAt: decisionCompleteDraft.createdAt,
    status: decisionCompleteDraft.status,
    primaryUseCase: decisionCompleteDraft.primaryUseCase,
    unresolvedDecisionCount: 0,
  }],
};

const acceptedRevision: IntentDraftProjection = {
  ...decisionCompleteDraft,
  revisionId: "019d5f72-5331-7000-8000-000000000004",
  revision: 4,
  revisionContentHash: `sha256:${"d".repeat(64)}`,
  createdAt: "2026-08-29T12:01:00Z",
  status: "accepted",
  canRequestAcceptance: false,
  launchReady: true,
};

const traceId = "0123456789abcdef0123456789abcdef";

function response(status: number, body: unknown, contentType = "application/json"): CoreApiResponse {
  return { status, contentType, traceId, etag: null, body: JSON.stringify(body) };
}

describe("guided research intent workspace", () => {
  it("invalidates impact acknowledgement for every preview-bound field", () => {
    for (const field of [
      "primaryUseCase",
      "sourceKinds",
      "languageCodes",
      "startYear",
      "endYear",
      "includePrivateReports",
      "evidenceTypes",
      "noveltyStandard",
      "autonomyLevel",
      "stoppingConditions",
    ] as const) {
      expect(intentFieldAffectsImpact(field), field).toBe(true);
    }
    expect(intentFieldAffectsImpact("researchObjective")).toBe(false);
  });

  it("keeps intent-form defaults use-case specific without duplicating profile presentation", () => {
    expect(selectedIntentGuidance("systematic-review")).toMatchObject({
      epistemicMode: "systematic",
      defaultStoppingConditions: ["coverage-threshold"],
    });
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
        initialCatalog={catalog}
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
    expect(markup).toContain("Integrate theories while retaining boundaries");
    expect(markup).toContain("Theory architecture and integration opportunities");
    expect(markup).toContain("Revisitable process");
    expect(markup).toContain("All tools remain available");
    expect(markup).toContain("Save draft revision");
    expect(markup).toContain("Launch gated analysis");
    expect(markup).toMatch(/disabled=""[^>]*>Launch gated analysis/);
    expect(markup).toContain("Drafts never govern consequential analysis");
    expect(markup).toContain("Human acceptance rationale");
    expect(markup).toContain("Accept intent revision");
    expect(markup).toContain("I reviewed and confirm persisted revision");
  });

  it("binds human acceptance to the exact decision-complete draft", () => {
    const current = decisionCompleteDraft;

    expect(intentAcceptanceAvailability(current)).toEqual({
      available: true,
      state: "ready",
      message: "Review and confirm this exact decision-complete draft before it can govern automation.",
    });
    expect(intentAcceptanceRequest(project.root, current, "Reviewed scope and authority.")).toEqual({
      root: project.root,
      expectedRevision: 3,
      expectedRevisionContentHash: `sha256:${"a".repeat(64)}`,
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

  it("replays one frozen acceptance after response loss and converges on the authoritative revision", async () => {
    const requests: CoreApiRequest[] = [];
    let committed = false;
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      if (!committed) {
        committed = true;
        throw new Error("response lost after commit");
      }
      return response(200, acceptedRevision);
    });
    const coordinator = new IntentAcceptanceCoordinator(client, () => "f".repeat(32));
    const attempt = coordinator.prepare(project.root, decisionCompleteDraft, "  Reviewed scope and authority.  ");

    expect(attempt).toEqual({
      command: {
        root: project.root,
        expectedRevision: 3,
        expectedRevisionContentHash: `sha256:${"a".repeat(64)}`,
        confirmed: true,
        decisionRationale: "Reviewed scope and authority.",
      },
      idempotencyKey: "f".repeat(32),
      revisionId: decisionCompleteDraft.revisionId,
    });
    await expect(coordinator.execute()).resolves.toMatchObject({ status: "unresolved", attempt });
    expect(coordinator.pendingAttempt()).toBe(attempt);
    expect(coordinator.prepare(project.root, decisionCompleteDraft, "Changed after uncertainty")).toBe(attempt);

    const replay = await coordinator.execute();
    expect(replay).toMatchObject({ status: "accepted", accepted: acceptedRevision, attempt });
    expect(coordinator.pendingAttempt()).toBeNull();
    expect(requests).toHaveLength(2);
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[0]).toMatchObject({
      method: "POST",
      path: "/projects/intent/acceptances",
      idempotencyKey: "f".repeat(32),
    });
    expect(JSON.parse(requests[0]?.body ?? "null")).toEqual(attempt.command);

    const nextWorkspace = acceptedIntentWorkspace(decisionCompleteWorkspace, project.projectId, acceptedRevision);
    expect(nextWorkspace.current).toEqual(acceptedRevision);
    expect(nextWorkspace.history.filter((item) => item.status === "accepted")).toHaveLength(1);
    const markup = renderToStaticMarkup(
      <IntentWorkspace project={project} announce={vi.fn()} initialWorkspace={nextWorkspace} initialCatalog={catalog} />,
    );
    expect(markup).toContain("Revision 4 · accepted");
    expect(markup).toMatch(/disabled=""[^>]*>Launch gated analysis/);
  });

  it("clears a frozen attempt only after a definitive Core rejection", async () => {
    const requests: CoreApiRequest[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(409, {
        type: "urn:research-observatory:problem:intent-acceptance-revision-conflict",
        title: "Intent acceptance revision conflict",
        status: 409,
        detail: "The requested draft is no longer the current revision.",
        code: "RO-CORE-INTENT-ACCEPTANCE-REVISION-CONFLICT",
        traceId,
        retryable: false,
        remediation: "Reload the authoritative intent workspace and review the current revision.",
      }, "application/problem+json");
    });
    const coordinator = new IntentAcceptanceCoordinator(client, () => "e".repeat(32));
    const attempt = coordinator.prepare(project.root, decisionCompleteDraft, "Reviewed scope and authority.");

    const result = await coordinator.execute();
    expect(result).toMatchObject({ status: "rejected", attempt });
    expect(coordinator.pendingAttempt()).toBeNull();
    expect(requests).toHaveLength(1);
    expect(decisionCompleteWorkspace.current).toBe(decisionCompleteDraft);
    expect(decisionCompleteWorkspace.current?.status).toBe("draft");
  });
});
