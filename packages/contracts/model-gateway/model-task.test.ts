import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  MODEL_TASK_SCHEMA_SHA256,
  assessModelTask,
  decodeModelResult,
  decodeModelTask,
  modelResultErrors,
  modelTaskErrors,
} from "./generated";

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8")) as unknown;
}

function baseTask(): Record<string, unknown> {
  return structuredClone(fixture("valid-generation-task.v1.json")) as Record<string, unknown>;
}

function reference(role: string): Record<string, unknown> {
  return {
    aggregateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9b1",
    revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9b2",
    contentHash: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    role,
  };
}

describe("provider-neutral model task and result contracts", () => {
  it("accepts each explicit task kind through its task-specific input envelope", () => {
    const schema = {
      schemaId: "extraction-output",
      schemaVersion: "1.0.0",
      schemaHash: "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    };
    const inputs: Record<string, Record<string, unknown>> = {
      embedding: { kind: "embedding", items: [reference("source")] },
      reranking: { kind: "reranking", query: reference("query"), candidates: [reference("candidate")], topK: 1 },
      classification: { kind: "classification", items: [reference("source")], labels: ["include", "exclude"] },
      nli: { kind: "nli", premise: reference("premise"), hypothesis: reference("hypothesis") },
      "structured-extraction": { kind: "structured-extraction", sources: [reference("source")], outputSchema: schema },
      generation: { kind: "generation", instruction: reference("instruction"), context: [reference("context")] },
      moderation: { kind: "moderation", items: [reference("source")], policyId: "research-content", policyVersion: "1.0.0" },
      "tool-call": { kind: "tool-call", toolId: "citation-lookup", toolVersion: "1.0.0", arguments: reference("tool-input"), inputSchema: schema },
    };
    for (const [taskKind, input] of Object.entries(inputs)) {
      const value = baseTask();
      value.taskKind = taskKind;
      value.input = input;
      expect(decodeModelTask(value), taskKind).not.toBeNull();
    }
    const impossibleRerank = baseTask();
    impossibleRerank.taskKind = "reranking";
    impossibleRerank.input = { kind: "reranking", query: reference("query"), candidates: [reference("candidate")], topK: 2 };
    expect(modelTaskErrors(impossibleRerank)).toContain("reranking-top-k-within-candidate-count");
  });

  it("accepts a complete pinned result and owns an immutable snapshot", () => {
    const task = baseTask();
    const result = fixture("valid-generation-result.v1.json") as Record<string, unknown>;
    const decoded = decodeModelResult(task, result);
    expect(modelResultErrors(task, result)).toEqual([]);
    expect(decoded?.route.selection).toBe("selected");
    expect(decoded?.usage.totalTokens).toBe(136);
    expect(decoded?.validation.outcome).toBe("accepted");
    expect(decoded?.citations).toHaveLength(1);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.route)).toBe(true);
    (result.latency as Record<string, unknown>).totalMs = 999;
    expect(decoded?.latency.totalMs).toBe(20);
  });

  it("reports unsupported required features explicitly without copying task content", () => {
    const task = baseTask();
    const assessment = assessModelTask(task, []);
    expect(assessment).toEqual({
      supported: false,
      diagnosticCode: "model-task-feature-unsupported",
      unsupportedFeatures: ["structured-output"],
    });
    expect(JSON.stringify(assessment)).not.toContain("aggregateId");

    const result = structuredClone(fixture("valid-generation-result.v1.json")) as Record<string, unknown>;
    result.status = "unsupported";
    result.route = {
      selection: "none",
      providerId: null,
      providerVersion: null,
      modelId: null,
      modelVersion: null,
      runtimeId: null,
      runtimeVersion: null,
      configurationHash: null,
      evaluationId: null,
      evaluationVersion: null,
      reasonCode: "required-feature-unsupported",
    };
    result.policyDecision = {
      decisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a6",
      policyVersion: "1.0.0",
      outcome: "denied",
      reasonCodes: ["required-feature-unsupported"],
    };
    result.usage = { reporting: "not-reported", inputTokens: null, outputTokens: null, totalTokens: null };
    result.validation = { outcome: "not-run", validatorVersion: "1.0.0", outputHash: null, errorCodes: [] };
    result.confidence = { kind: "not-applicable" };
    result.citationStatus = "not-supplied";
    result.citations = [];
    result.output = null;
    result.diagnostics = [{ code: "model-task-feature-unsupported", retryable: false, partialOutputDisposition: "none" }];
    expect(modelResultErrors(task, result)).toEqual([]);
  });

  it("fails closed on raw content, unknown fields, mismatches, bad accounting, citations, and pin substitution", () => {
    const raw = baseTask();
    (raw.input as Record<string, unknown>).prompt = "private research text";
    expect(decodeModelTask(raw)).toBeNull();
    expect(modelTaskErrors(raw)).toContain("$/input: alternatives");

    const task = baseTask();
    const result = fixture("valid-generation-result.v1.json") as Record<string, unknown>;
    result.requestHash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    (result.usage as Record<string, unknown>).totalTokens = 137;
    ((result.citations as Array<Record<string, unknown>>)[0]!).sourceContentHash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    (result.route as Record<string, unknown>).modelVersion = "substituted";
    expect(modelResultErrors(task, result)).toEqual(expect.arrayContaining([
      "result-request-hash-matches-task",
      "reported-token-total-equals-input-plus-output",
      "supplied-citations-close-over-task-input-references",
      "pinned-execution-route-matches-result-route",
    ]));
    expect(decodeModelResult(task, result)).toBeNull();
  });

  it("closes successful results over exact token, deadline, artifact, validation, and citation bounds", () => {
    const task = baseTask();
    const boundary = fixture("valid-generation-result.v1.json") as Record<string, unknown>;
    boundary.usage = { reporting: "reported", inputTokens: 4096, outputTokens: 512, totalTokens: 4608 };
    boundary.latency = { queueMs: 0, executionMs: 30000, totalMs: 30000 };
    expect(modelResultErrors(task, boundary)).toEqual([]);

    const invalid = structuredClone(boundary);
    invalid.usage = { reporting: "reported", inputTokens: 4097, outputTokens: 513, totalTokens: 4610 };
    invalid.latency = { queueMs: 1, executionMs: 30000, totalMs: 30001 };
    (invalid.validation as Record<string, unknown>).outputHash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    ((invalid.citations as Array<Record<string, unknown>>)[0]!).sourceContentHash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const optionalTask = structuredClone(task);
    (optionalTask.requirements as Record<string, unknown>).citationRequirement = "optional";
    expect(modelResultErrors(optionalTask, invalid)).toEqual(expect.arrayContaining([
      "reported-usage-within-task-bounds",
      "successful-result-within-task-deadline",
      "accepted-artifact-validation-hash-matches-output",
      "supplied-citations-close-over-task-input-references",
    ]));

    const rejected = structuredClone(fixture("valid-generation-result.v1.json")) as Record<string, unknown>;
    rejected.status = "failed";
    rejected.output = null;
    rejected.citationStatus = "not-supplied";
    rejected.citations = [];
    rejected.validation = {
      outcome: "rejected",
      validatorVersion: "1.0.0",
      outputHash: "sha256:5555555555555555555555555555555555555555555555555555555555555555",
      errorCodes: ["output-schema-invalid"],
    };
    expect(modelResultErrors(task, rejected)).toEqual([]);
    (rejected.validation as Record<string, unknown>).errorCodes = [];
    expect(modelResultErrors(task, rejected)).toContain("rejected-validation-has-output-hash-and-errors");
    rejected.validation = {
      outcome: "accepted",
      validatorVersion: "1.0.0",
      outputHash: "sha256:5555555555555555555555555555555555555555555555555555555555555555",
      errorCodes: [],
    };
    expect(modelResultErrors(task, rejected)).toContain("accepted-validation-requires-successful-output");
    const optionalWithoutCitations = structuredClone(fixture("valid-generation-result.v1.json")) as Record<string, unknown>;
    optionalWithoutCitations.citations = [];
    optionalWithoutCitations.citationStatus = "not-applicable";
    expect(modelResultErrors(optionalTask, optionalWithoutCitations)).toContain("citation-status-matches-task-requirement");
  });

  it("closes task-specific indexed outputs over their inputs, labels, and cardinality", () => {
    const cases = [
      {
        kind: "reranking",
        input: { kind: "reranking", query: reference("query"), candidates: [reference("candidate")], topK: 1 },
        output: { kind: "reranking", items: [{ inputIndex: 0, label: "relevance", score: 0.9 }] },
        mutate: (output: Record<string, unknown>) => { output.items = [{ inputIndex: 1, label: "relevance", score: 0.9 }]; },
        code: "reranking-output-closes-over-candidates",
      },
      {
        kind: "classification",
        input: { kind: "classification", items: [reference("source")], labels: ["include", "exclude"] },
        output: { kind: "classification", items: [{ inputIndex: 0, label: "include", score: 0.9 }] },
        mutate: (output: Record<string, unknown>) => { output.items = [{ inputIndex: 0, label: "unknown", score: 0.9 }]; },
        code: "classification-output-closes-over-items-and-labels",
      },
      {
        kind: "nli",
        input: { kind: "nli", premise: reference("premise"), hypothesis: reference("hypothesis") },
        output: { kind: "nli", label: "entailment", scores: [{ inputIndex: 0, label: "entailment", score: 0.9 }] },
        mutate: (output: Record<string, unknown>) => { output.scores = [{ inputIndex: 1, label: "entailment", score: 0.9 }]; },
        code: "nli-output-closes-over-task",
      },
      {
        kind: "moderation",
        input: { kind: "moderation", items: [reference("source")], policyId: "research-content", policyVersion: "1.0.0" },
        output: { kind: "moderation", items: [{ inputIndex: 0, label: "allowed", score: 0.9 }] },
        mutate: (output: Record<string, unknown>) => { output.items = [{ inputIndex: 1, label: "allowed", score: 0.9 }]; },
        code: "moderation-output-closes-over-items",
      },
    ];
    for (const testCase of cases) {
      const task = baseTask();
      task.taskKind = testCase.kind;
      task.input = testCase.input;
      (task.requirements as Record<string, unknown>).citationRequirement = "optional";
      const result = fixture("valid-generation-result.v1.json") as Record<string, unknown>;
      result.taskKind = testCase.kind;
      result.output = testCase.output;
      result.citationStatus = "not-supplied";
      result.citations = [];
      expect(modelResultErrors(task, result), testCase.kind).toEqual([]);
      testCase.mutate(result.output as Record<string, unknown>);
      expect(modelResultErrors(task, result), testCase.kind).toContain(testCase.code);
    }
    const mismatchedTask = baseTask();
    mismatchedTask.taskKind = "nli";
    mismatchedTask.input = { kind: "nli", premise: reference("premise"), hypothesis: reference("hypothesis") };
    (mismatchedTask.requirements as Record<string, unknown>).citationRequirement = "optional";
    const mismatchedResult = fixture("valid-generation-result.v1.json") as Record<string, unknown>;
    mismatchedResult.taskKind = "nli";
    mismatchedResult.output = { kind: "classification", items: [{ inputIndex: 0, label: "include", score: 0.9 }] };
    mismatchedResult.citations = [];
    mismatchedResult.citationStatus = "not-supplied";
    expect(modelResultErrors(mismatchedTask, mismatchedResult)).toContain("successful-result-output-kind-matches-task-kind");
  });

  it("binds generated runtimes to canonical language-neutral schema bytes", () => {
    const path = fileURLToPath(new URL("./model-task.schema.json", import.meta.url));
    const canonical = readFileSync(path, "utf8").replace(/\r\n?/g, "\n");
    expect(createHash("sha256").update(Buffer.from(canonical, "utf8")).digest("hex")).toBe(MODEL_TASK_SCHEMA_SHA256);
  });
});
