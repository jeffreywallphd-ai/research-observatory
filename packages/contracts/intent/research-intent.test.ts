import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  decodeResearchIntentReference,
  decodeResearchIntentRevision,
  governingResearchIntentReference,
  researchIntentReferenceErrors,
  researchIntentRevisionErrors,
  researchIntentSnapshotJson,
} from "./generated.js";

const root = resolve(import.meta.dirname, "fixtures");
const fixture = (name: string): Record<string, unknown> =>
  JSON.parse(readFileSync(resolve(root, name), "utf8")) as Record<string, unknown>;

describe("research intent contract", () => {
  it("accepts an immutable systematic revision and produces an exact governing reference", () => {
    const input = fixture("valid-systematic-intent.v1.json");
    expect(researchIntentRevisionErrors(input)).toEqual([]);
    const decoded = decodeResearchIntentRevision(input);
    expect(decoded).not.toBeNull();
    const before = researchIntentSnapshotJson(decoded!);
    (input.researchQuestion as Record<string, unknown>).value = "mutated";
    expect(researchIntentSnapshotJson(decoded!)).toBe(before);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.autonomy)).toBe(true);
    expect(governingResearchIntentReference(decoded!)).toEqual(
      decodeResearchIntentReference(fixture("valid-systematic-reference.v1.json")),
    );
  });

  it("accepts the mode-specific contract branches and their valid stopping boundaries", () => {
    const cases = [
      ["systematic", "systematic-review", { kind: "systematic", protocol: "systematic-review", inclusionLogic: "Predeclared criteria.", comprehensivenessTarget: "exhaustive" }, ["coverage-threshold", "resource-budget"]],
      ["theory", "theory-synthesis", { kind: "theory", synthesisApproach: "integrative", theoreticalLenses: ["institutional theory"] }, ["interpretive-saturation", "resource-budget"]],
      ["technical", "technical-landscape", { kind: "technical", evaluationTargets: ["local inference runtime"], benchmarkDimensions: ["latency"] }, ["benchmark-complete", "resource-budget"]],
      ["hermeneutic", "hermeneutic-inquiry", { kind: "hermeneutic", interpretiveTradition: "hermeneutic circle", iterationLogic: "Reading revises search and interpretation." }, ["interpretive-saturation", "resource-budget"]],
      ["critical", "critical-problematization", { kind: "critical", criticalTradition: "critical information systems", affectedStakeholders: ["research participants"], reflexivityCommitment: "Retain standpoint and exclusion memos." }, ["researcher-decision", "resource-budget"]],
      ["novelty", "novelty-audit", { kind: "novelty", opportunityTypes: ["theory-gap"], nearestPriorWorkChallenge: true }, ["nearest-prior-work-challenged", "resource-budget"]],
      ["empirical", "empirical-study-design", { kind: "empirical", studyType: "mixed-methods", designConstraints: ["local ethics review"] }, ["protocol-complete", "resource-budget"]],
    ] as const;
    for (const [mode, useCase, requirements, conditions] of cases) {
      const revision = fixture("valid-systematic-intent.v1.json");
      revision.epistemicMode = mode;
      revision.primaryUseCase = useCase;
      revision.modeRequirements = requirements;
      (revision.stoppingRule as Record<string, unknown>).conditions = conditions;
      expect(researchIntentRevisionErrors(revision), mode).toEqual([]);
    }
    const theory = fixture("valid-systematic-intent.v1.json");
    theory.epistemicMode = "theory";
    theory.primaryUseCase = "theory-synthesis";
    theory.modeRequirements = { kind: "theory", synthesisApproach: "conceptual", theoreticalLenses: ["practice theory"] };
    theory.unitOfAnalysis = { state: "not-applicable", rationale: "The synthesis is construct-centered." };
    theory.levelOfAnalysis = { state: "not-applicable", rationale: "No single empirical level governs the synthesis." };
    (theory.stoppingRule as Record<string, unknown>).conditions = ["researcher-decision"];
    expect(researchIntentRevisionErrors(theory)).toEqual([]);
    theory.epistemicMode = "systematic";
    theory.primaryUseCase = "systematic-review";
    theory.modeRequirements = { kind: "systematic", protocol: "systematic-review", inclusionLogic: "Predeclared.", comprehensivenessTarget: "bounded" };
    (theory.stoppingRule as Record<string, unknown>).conditions = ["coverage-threshold"];
    expect(researchIntentRevisionErrors(theory)).toContain("accepted-revision-is-decision-complete");
  });

  it("fails closed on unknown and unsafe fields", () => {
    const unknown = fixture("valid-systematic-intent.v1.json");
    unknown.credential = "secret";
    expect(decodeResearchIntentRevision(unknown)).toBeNull();
    const hostile = JSON.parse(
      JSON.stringify(fixture("valid-systematic-intent.v1.json")).replace(
        "{",
        '{"__proto__":{"credential":"secret"},',
      ),
    ) as Record<string, unknown>;
    expect(decodeResearchIntentRevision(hostile)).toBeNull();
  });

  it("requires mode-specific requirements and stopping logic", () => {
    const mismatch = fixture("valid-systematic-intent.v1.json");
    (mismatch.modeRequirements as Record<string, unknown>).kind = "hermeneutic";
    expect(researchIntentRevisionErrors(mismatch)).toContain("mode-requirements-match-epistemic-mode");
    const stopping = fixture("valid-systematic-intent.v1.json");
    (stopping.stoppingRule as Record<string, unknown>).conditions = ["researcher-decision"];
    expect(researchIntentRevisionErrors(stopping)).toContain("stopping-rule-matches-epistemic-mode");
  });

  it("requires immediate immutable revision lineage", () => {
    const revision = fixture("valid-systematic-intent.v1.json");
    revision.revision = 3;
    revision.parentRevision = {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5",
      revision: 1,
      revisionContentHash: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
    };
    expect(researchIntentRevisionErrors(revision)).toContain("revision-lineage-is-immediate");
  });

  it("accepts an immediate later revision while retaining its predecessor identity and rationale", () => {
    const revision = fixture("valid-systematic-intent.v1.json");
    revision.revision = 2;
    revision.revisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5";
    revision.revisionContentHash = "sha256:3333333333333333333333333333333333333333333333333333333333333333";
    revision.parentRevision = {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2",
      revision: 1,
      revisionContentHash: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    };
    revision.revisionRationale = "Refine the source boundary without rewriting revision one.";
    expect(researchIntentRevisionErrors(revision)).toEqual([]);
    expect(governingResearchIntentReference(revision)?.revision).toBe(2);
  });

  it("keeps intent acceptance and scope authority human", () => {
    const authority = fixture("valid-systematic-intent.v1.json");
    (authority.decision as Record<string, unknown>).actorType = "model";
    const autonomy = authority.autonomy as Record<string, unknown>;
    autonomy.mayAcceptIntent = true;
    autonomy.mayChangeScope = true;
    expect(researchIntentRevisionErrors(authority)).toEqual(
      expect.arrayContaining(["intent-acceptance-is-human", "autonomy-retains-researcher-authority"]),
    );
  });

  it("bounds autonomous actions by vocabulary and autonomy level", () => {
    for (const reserved of ["accept-intent", "change-scope", "external-egress"]) {
      const revision = fixture("valid-systematic-intent.v1.json");
      (revision.autonomy as Record<string, unknown>).allowedActions = [reserved];
      expect(decodeResearchIntentRevision(revision), reserved).toBeNull();
    }
    const humanOnly = fixture("valid-systematic-intent.v1.json");
    (humanOnly.autonomy as Record<string, unknown>).level = "human-only";
    expect(researchIntentRevisionErrors(humanOnly)).toContain("autonomy-actions-match-level");
    (humanOnly.autonomy as Record<string, unknown>).allowedActions = [];
    expect(researchIntentRevisionErrors(humanOnly)).toEqual([]);
    const suggest = fixture("valid-systematic-intent.v1.json");
    (suggest.autonomy as Record<string, unknown>).level = "suggest";
    (suggest.autonomy as Record<string, unknown>).allowedActions = ["prepare-screening-batch"];
    expect(researchIntentRevisionErrors(suggest)).toContain("autonomy-actions-match-level");
    (suggest.autonomy as Record<string, unknown>).allowedActions = ["propose-query", "recommend-stopping"];
    expect(researchIntentRevisionErrors(suggest)).toEqual([]);
    const execution = fixture("valid-systematic-intent.v1.json");
    (execution.autonomy as Record<string, unknown>).allowedActions = ["execute-approved-query"];
    expect(researchIntentRevisionErrors(execution)).toContain("autonomy-actions-match-level");
    (execution.autonomy as Record<string, unknown>).level = "execute-reversible";
    expect(researchIntentRevisionErrors(execution)).toEqual([]);
  });

  it("requires mode-closed stopping sets and human-gated approved egress", () => {
    const mixed = fixture("valid-systematic-intent.v1.json");
    (mixed.stoppingRule as Record<string, unknown>).conditions = ["coverage-threshold", "benchmark-complete"];
    expect(researchIntentRevisionErrors(mixed)).toContain("stopping-rule-matches-epistemic-mode");

    const missingGate = fixture("valid-systematic-intent.v1.json");
    missingGate.egressPolicy = { mode: "approved-redacted", approvedDestinationIds: ["approved-provider"] };
    expect(researchIntentRevisionErrors(missingGate)).toContain("egress-policy-is-consistent");
    const gates = (missingGate.autonomy as Record<string, unknown>).requiredHumanGates as string[];
    gates.push("external-egress");
    expect(researchIntentRevisionErrors(missingGate)).toEqual([]);

    const contradictoryGate = fixture("valid-systematic-intent.v1.json");
    ((contradictoryGate.autonomy as Record<string, unknown>).requiredHumanGates as string[]).push("external-egress");
    expect(researchIntentRevisionErrors(contradictoryGate)).toContain("egress-policy-is-consistent");
  });

  it("denies accepted revisions with unresolved or unspecified core intent", () => {
    const incomplete = fixture("valid-systematic-intent.v1.json");
    incomplete.researchQuestion = { state: "unknown", rationale: "Not yet resolved." };
    incomplete.unresolvedDecisions = ["research-question"];
    expect(researchIntentRevisionErrors(incomplete)).toContain("accepted-revision-is-decision-complete");
    expect(governingResearchIntentReference(incomplete)).toBeNull();
  });

  it("allows an explicitly incomplete draft but never exposes it as governing", () => {
    const draft = fixture("valid-systematic-intent.v1.json");
    draft.status = "draft";
    draft.decision = null;
    draft.researchQuestion = { state: "unknown", rationale: "The researcher is still refining it." };
    draft.sourceScope = { state: "unknown", rationale: "Source boundaries are not decided." };
    draft.noveltyStandard = { state: "unknown", rationale: "No novelty claim is ready." };
    draft.evidenceTypes = [];
    draft.unresolvedDecisions = ["research-question", "source-scope", "novelty-standard"];
    expect(researchIntentRevisionErrors(draft)).toEqual([]);
    expect(governingResearchIntentReference(draft)).toBeNull();
  });

  it("validates downstream governing references independently", () => {
    const reference = fixture("valid-systematic-reference.v1.json");
    expect(researchIntentReferenceErrors(reference)).toEqual([]);
    reference.revision = 0;
    expect(decodeResearchIntentReference(reference)).toBeNull();
  });

  it("rejects incompatible use cases, reversed scope years, and inconsistent egress", () => {
    const revision = fixture("valid-systematic-intent.v1.json");
    revision.primaryUseCase = "critical-problematization";
    const scope = revision.sourceScope as Record<string, unknown>;
    scope.temporalCoverage = { kind: "bounded", startYear: 2026, endYear: 2000 };
    revision.egressPolicy = { mode: "approved-redacted", approvedDestinationIds: [] };
    expect(researchIntentRevisionErrors(revision)).toEqual(expect.arrayContaining([
      "primary-use-case-matches-epistemic-mode",
      "source-temporal-range-is-ordered",
      "egress-policy-is-consistent",
    ]));
  });

  it("rejects invalid calendar time, control text, undecided accepted scope, and reused predecessor content", () => {
    const timestamp = fixture("valid-systematic-intent.v1.json");
    timestamp.createdAt = "2026-02-31T12:00:00Z";
    expect(researchIntentRevisionErrors(timestamp)).toContain("$/createdAt: format");
    const control = fixture("valid-systematic-intent.v1.json");
    control.revisionRationale = "unsafe\u0000text";
    expect(decodeResearchIntentRevision(control)).toBeNull();
    const undecided = fixture("valid-systematic-intent.v1.json");
    (undecided.sourceScope as Record<string, unknown>).privateReports = "undecided";
    expect(researchIntentRevisionErrors(undecided)).toContain("accepted-revision-is-decision-complete");
    const reused = fixture("valid-systematic-intent.v1.json");
    reused.revision = 2;
    reused.revisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5";
    reused.parentRevision = {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2",
      revision: 1,
      revisionContentHash: reused.revisionContentHash,
    };
    expect(researchIntentRevisionErrors(reused)).toContain("revision-lineage-is-immediate");
  });
});
