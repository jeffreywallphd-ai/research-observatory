#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate and verify the portable OpenAPI and TypeScript Core API client."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

GENERATOR_VERSION = "1.0.0"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _schema_type(schema: dict[str, Any]) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    variants = schema.get("anyOf", schema.get("oneOf"))
    if isinstance(variants, list):
        return " | ".join(_schema_type(item) for item in variants if isinstance(item, dict))
    enum = schema.get("enum")
    if isinstance(enum, list):
        return " | ".join(json.dumps(value) for value in enum)
    kind = schema.get("type")
    if kind == "array":
        items = schema.get("items")
        return f"ReadonlyArray<{_schema_type(items if isinstance(items, dict) else {})}>"
    if kind in {"integer", "number"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "object":
        values = schema.get("additionalProperties")
        if isinstance(values, dict):
            return f"Readonly<Record<string, {_schema_type(values)}>>"
        return "Readonly<Record<string, unknown>>"
    return "string"


def _interfaces(openapi: dict[str, Any]) -> str:
    components = openapi.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(schemas, dict):
        raise ValueError("OpenAPI components.schemas must be an object")
    blocks: list[str] = []
    for name in sorted(schemas):
        schema = schemas[name]
        if not isinstance(schema, dict):
            raise ValueError(f"OpenAPI schema {name} must be an object")
        if (
            "enum" in schema
            or "anyOf" in schema
            or "oneOf" in schema
            or schema.get("type") in {"string", "integer", "number", "boolean", "null", "array"}
        ):
            blocks.append(f"export type {name} = {_schema_type(schema)};\n")
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"OpenAPI schema {name} must declare properties or enum")
        lines = [f"export interface {name} {{"]
        for property_name in sorted(properties):
            property_schema = properties[property_name]
            if not isinstance(property_schema, dict):
                raise ValueError(f"OpenAPI property {name}.{property_name} must be an object")
            # FastAPI response serialization includes declared defaults and nulls;
            # generated response types therefore expose the exact wire object.
            key = (
                property_name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", property_name) else json.dumps(property_name)
            )
            # Additive request fields may explicitly preserve omission by older
            # clients. Response projections remain exact, including defaults.
            optional = "?" if property_schema.get("x-client-optional") is True else ""
            if optional and property_name in schema.get("required", []):
                raise ValueError(f"Required OpenAPI property {name}.{property_name} cannot be optional")
            lines.append(f"  readonly {key}{optional}: {_schema_type(property_schema)};")
        lines.append("}")
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def _operation_ids(openapi: dict[str, Any]) -> tuple[str, ...]:
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI paths must be an object")
    operation_ids: list[str] = []
    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            raise ValueError(f"OpenAPI path {path} must be an object")
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            if not isinstance(operation, dict) or not isinstance(operation.get("operationId"), str):
                raise ValueError(f"OpenAPI operation {method.upper()} {path} needs an operationId")
            operation_ids.append(operation["operationId"])
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("OpenAPI operation identifiers must be unique")
    return tuple(sorted(operation_ids))


CLIENT_RUNTIME = r"""
export interface CoreApiRequest {
  readonly method: "GET" | "POST";
  readonly path: string;
  readonly body: string | null;
  readonly ifMatch: string | null;
  readonly idempotencyKey: string | null;
}

export interface CoreApiResponse {
  readonly status: number;
  readonly contentType: string;
  readonly traceId: string;
  readonly etag: string | null;
  readonly body: string;
}

export type CoreApiTransport = (request: CoreApiRequest) => Promise<CoreApiResponse>;

export interface CompatibilityResult {
  readonly ok: boolean;
  readonly code: "RO-CORE-API-COMPATIBLE" | "RO-CORE-API-INCOMPATIBLE";
  readonly remediation: string;
}

export interface OperationSnapshot {
  readonly operation: OperationStatus;
  readonly etag: string;
}

export function workflowEtag(value: WorkflowTaskCenterRun): string {
  return `"workflow-${value.workflowRunId}-${value.revision}-${value.snapshotRevision}"`;
}

export class CoreApiClientError extends Error {
  readonly problem: ProblemDetail;

  constructor(problem: ProblemDetail) {
    super(problem.code);
    this.name = "CoreApiClientError";
    this.problem = problem;
  }
}

function record(value: unknown): Readonly<Record<string, unknown>> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Readonly<Record<string, unknown>>
    : null;
}

function exactKeys(value: Readonly<Record<string, unknown>>, required: readonly string[], optional: readonly string[] = []): boolean {
  const keys = Object.keys(value).sort();
  const allowed = [...required, ...optional].sort();
  return keys.length >= required.length && keys.length <= allowed.length
    && required.every((key) => keys.includes(key))
    && keys.every((key) => allowed.includes(key));
}

function canonicalTraceId(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
}

function canonicalOperationId(value: unknown): value is string {
  return typeof value === "string" && /^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(value);
}

function integer(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= maximum;
}

function operationState(value: unknown): value is OperationState {
  return value === "queued" || value === "running" || value === "succeeded" || value === "failed" || value === "cancelled";
}

function projectLifecycleState(value: unknown): value is ProjectLifecycleState {
  return value === "active" || value === "archived" || value === "trash";
}

function projectAccessMode(value: unknown): value is ProjectAccessMode {
  return value === "closed" || value === "read-write" || value === "read-only";
}

function projectCompatibilityState(value: unknown): value is ProjectCompatibilityState {
  return value === "compatible" || value === "migration-required" || value === "newer-unsupported";
}

function projectRecoveryAction(value: unknown): value is ProjectRecoveryAction {
  return value === "none" || value === "backup-then-migrate" || value === "backup-then-use-compatible-application";
}

function privacyNetworkPolicy(value: unknown): value is PrivacyNetworkPolicy {
  return value === "offline" || value === "metadata-only" || value === "approved-providers";
}

function remoteModelApproval(value: unknown): value is RemoteModelApproval {
  return value === "preview-every-task";
}

function telemetryMode(value: unknown): value is TelemetryMode {
  return value === "off" || value === "local-diagnostics-only";
}

function documentRetentionPolicy(value: unknown): value is DocumentRetentionPolicy {
  return value === "project-lifetime" || value === "review-after-90-days" || value === "review-after-365-days";
}

function egressEnforcement(value: unknown): value is EgressEnforcement {
  return value === "deny" || value === "require-task-preview";
}

function safeReleaseVersion(value: unknown): value is string {
  return typeof value === "string"
    && /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(value)
    && value.split(".").every((part) => Number.isSafeInteger(Number(part)));
}

function boundedText(value: unknown, minimum: number, maximum: number): value is string {
  return typeof value === "string" && value.length >= minimum && value.length <= maximum && !/[\u0000-\u001f\u007f]/.test(value);
}

function projectRoot(value: unknown): value is string {
  if (!boundedText(value, 1, 4096)) return false;
  const normalized = value.replaceAll("\\", "/");
  if (!/^(?:[A-Za-z]:\/|\/\/[^/]+\/[^/]+\/|\/)/.test(normalized)) return false;
  return normalized.split("/").every((part) => part !== "..");
}

function canonicalProjectId(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
}

function canonicalUuid7(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
}

function contentHash(value: unknown): value is string {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function canonicalContractJson(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonicalContractJson).join(",") + "]";
  const candidate = record(value);
  if (candidate) {
    return "{" + Object.keys(candidate).sort().map(
      (key) => JSON.stringify(key) + ":" + canonicalContractJson(candidate[key]),
    ).join(",") + "}";
  }
  const rendered = JSON.stringify(value);
  if (rendered === undefined) throw new Error("Core contract value is not canonical JSON");
  return rendered.replace(/[\u0080-\uffff]/g, (character) => (
    "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0")
  ));
}

function sha256Hex(text: string): string {
  const constants = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
  ];
  const input = new TextEncoder().encode(text);
  const length = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(length);
  bytes.set(input);
  bytes[input.length] = 0x80;
  let bits = BigInt(input.length) * 8n;
  for (let index = 0; index < 8; index += 1) {
    bytes[length - 1 - index] = Number(bits & 0xffn);
    bits >>= 8n;
  }
  const hash = new Uint32Array([
    0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19,
  ]);
  const words = new Uint32Array(64);
  const rotate = (value: number, count: number): number => (value >>> count) | (value << (32 - count));
  for (let offset = 0; offset < length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      const base = offset + index * 4;
      words[index] = (
        ((bytes[base] ?? 0) << 24) | ((bytes[base + 1] ?? 0) << 16)
        | ((bytes[base + 2] ?? 0) << 8) | (bytes[base + 3] ?? 0)
      ) >>> 0;
    }
    for (let index = 16; index < 64; index += 1) {
      const a = words[index - 15] ?? 0;
      const b = words[index - 2] ?? 0;
      const s0 = rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3);
      const s1 = rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10);
      words[index] = ((words[index - 16] ?? 0) + s0 + (words[index - 7] ?? 0) + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,h] = Array.from(hash) as [number,number,number,number,number,number,number,number];
    for (let index = 0; index < 64; index += 1) {
      const s1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + choice + (constants[index] ?? 0) + (words[index] ?? 0)) >>> 0;
      const s0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + majority) >>> 0;
      h=g; g=f; f=e; e=(d+temp1)>>>0; d=c; c=b; b=a; a=(temp1+temp2)>>>0;
    }
    for (const [index, value] of [a,b,c,d,e,f,g,h].entries()) {
      hash[index] = ((hash[index] ?? 0) + value) >>> 0;
    }
  }
  return Array.from(hash).map((value) => value.toString(16).padStart(8, "0")).join("");
}

function utcInstant(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function boundedNarrative(value: unknown, minimum = 0): value is string {
  return typeof value === "string" && value.length >= minimum && value.length <= 4000
    && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value);
}

const INTENT_PRIMARY_USE_CASES = [
  "rapid-orientation", "systematic-review", "living-review", "theory-synthesis", "hermeneutic-inquiry",
  "critical-problematization", "technical-landscape", "novelty-audit", "empirical-study-design",
  "empirical-study-to-article", "empirical-results-to-article", "theory-article-development",
  "critical-article-development", "manuscript-review-revision",
] as const;
const INTENT_MODES = ["systematic", "theory", "technical", "hermeneutic", "critical", "novelty", "empirical"] as const;
const INTENT_SOURCE_KINDS = [
  "peer-reviewed-article", "conference-paper", "book", "chapter", "preprint", "technical-report", "dataset",
  "standard", "patent", "thesis", "web-resource", "private-report",
] as const;
const INTENT_EVIDENCE_TYPES = [
  "empirical-study", "systematic-review", "theoretical-work", "technical-evaluation", "standard", "dataset",
  "interpretive-text", "stakeholder-account", "critical-analysis", "private-report",
] as const;
const INTENT_NOVELTY_STANDARDS = [
  "bounded-comparative", "incremental", "theoretical", "methodological", "contextual", "critical", "interpretive", "not-claimed",
] as const;
const INTENT_AUTONOMY_LEVELS = ["human-only", "suggest", "prepare-reversible", "execute-reversible"] as const;
const INTENT_STOPPING_CONDITIONS = [
  "source-exhaustion", "coverage-threshold", "interpretive-saturation", "benchmark-complete",
  "nearest-prior-work-challenged", "protocol-complete", "resource-budget", "researcher-decision",
] as const;
const INTENT_CHANGE_CATEGORIES = ["primary-use-case", "corpus-scope", "novelty-scope", "egress-policy"] as const;
const INTENT_REVISION_STATUSES = ["draft", "accepted"] as const;
const INTENT_POLICY_SUBJECTS = ["human", "model", "system"] as const;
const INTENT_POLICY_ACTIONS = [
  "accept-intent", "propose-query", "recommend-stopping", "prepare-screening-batch", "prepare-draft-output",
  "execute-approved-query", "execute-approved-screening-batch", "change-scope", "external-egress",
  "adjudicate-evidence", "approve-claim", "publish-output", "confirm-stopping",
] as const;
const INTENT_POLICY_OUTCOMES = ["allow", "deny", "recommend-human", "require-confirmation"] as const;
const INTENT_HUMAN_GATES = [
  "intent-acceptance", "scope-change", "external-egress", "evidence-adjudication", "claim-approval", "publication",
] as const;
const INTENT_OUTPUT_LABELS = [
  "systematic-working-output", "theory-working-output", "technical-working-output",
  "hermeneutic-working-output", "critical-working-output", "novelty-working-output", "empirical-working-output",
] as const;

function member<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === "string" && values.some((candidate) => candidate === value);
}

function uniqueMembers<T extends string>(value: unknown, values: readonly T[], maximum: number, minimum = 0): value is T[] {
  return Array.isArray(value) && value.length >= minimum && value.length <= maximum
    && value.every((item) => member(item, values)) && new Set(value).size === value.length;
}

function languageCodes(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 32 && new Set(value).size === value.length
    && value.every((item) => typeof item === "string" && /^[a-z0-9][a-z0-9._-]{0,99}$/.test(item));
}

function stringList(value: unknown, maximum: number): value is string[] {
  return Array.isArray(value) && value.length <= maximum && new Set(value).size === value.length
    && value.every((item) => boundedText(item, 1, 240));
}

export function decodeVersionResponse(value: unknown): VersionResponse | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "service", "version", "apiVersion", "minimumClientApiVersion", "maximumClientApiVersionExclusive",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || candidate.service !== "research-observatory-core") return null;
  if (![candidate.version, candidate.apiVersion, candidate.minimumClientApiVersion, candidate.maximumClientApiVersionExclusive]
    .every((item) => typeof item === "string" && /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(item))) return null;
  return candidate as unknown as VersionResponse;
}

export function decodeProblemDetail(value: unknown): ProblemDetail | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["type", "title", "status", "detail", "code", "traceId", "retryable", "remediation"])) return null;
  if (typeof candidate.type !== "string" || !/^urn:research-observatory:problem:[a-z0-9-]+$/.test(candidate.type)) return null;
  if (typeof candidate.title !== "string" || !candidate.title || candidate.title.length > 120) return null;
  if (typeof candidate.detail !== "string" || !candidate.detail || candidate.detail.length > 500) return null;
  if (!integer(candidate.status, 400, 599) || typeof candidate.code !== "string" || !/^RO-CORE-[A-Z0-9-]+$/.test(candidate.code)) return null;
  if (candidate.type.slice("urn:research-observatory:problem:".length) !== candidate.code.slice("RO-CORE-".length).toLowerCase()) return null;
  if (!canonicalTraceId(candidate.traceId) || typeof candidate.retryable !== "boolean") return null;
  if (typeof candidate.remediation !== "string" || !candidate.remediation || candidate.remediation.length > 240) return null;
  return candidate as unknown as ProblemDetail;
}

export function decodeOperationStatus(value: unknown): OperationStatus | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "operationId", "kind", "state", "sequence", "progressPercent", "cancellationRequested",
    "createdAt", "updatedAt", "traceId",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalOperationId(candidate.operationId)) return null;
  if (typeof candidate.kind !== "string" || !/^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*$/.test(candidate.kind)) return null;
  if (!operationState(candidate.state) || !integer(candidate.sequence, 0, Number.MAX_SAFE_INTEGER)) return null;
  if (!integer(candidate.progressPercent, 0, 100) || typeof candidate.cancellationRequested !== "boolean") return null;
  if (typeof candidate.createdAt !== "string" || !Number.isFinite(Date.parse(candidate.createdAt))) return null;
  if (typeof candidate.updatedAt !== "string" || !Number.isFinite(Date.parse(candidate.updatedAt)) || !canonicalTraceId(candidate.traceId)) return null;
  return candidate as unknown as OperationStatus;
}

function decodeWorkflowProgress(value: unknown): WorkflowProgress | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["kind", "unit", "completedUnits", "totalUnits"])) return null;
  if (!member(candidate.kind, ["quantified", "unknown", "not-applicable"] as const)
    || typeof candidate.unit !== "string" || !/^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(candidate.unit)) return null;
  if (candidate.kind === "quantified") {
    if (!integer(candidate.completedUnits, 0, Number.MAX_SAFE_INTEGER)
      || !integer(candidate.totalUnits, 0, Number.MAX_SAFE_INTEGER)
      || candidate.completedUnits > candidate.totalUnits) return null;
  } else if (candidate.completedUnits !== null || candidate.totalUnits !== null) return null;
  return candidate as unknown as WorkflowProgress;
}

export function decodeWorkflowTaskCenterRun(value: unknown): WorkflowTaskCenterRun | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "workflowRunId", "workflowKey", "definitionRevisionId", "definitionVersion",
    "snapshotId", "snapshotRevision", "continuationFromWorkflowRunId", "continuationFromJobId",
    "state", "activeCompute", "progress", "revision",
    "interruptionKind", "updatedAt", "steps", "jobs", "humanTasks", "retainedArtifacts", "events",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.workflowRunId)
    || !canonicalUuid7(candidate.definitionRevisionId) || !canonicalUuid7(candidate.snapshotId)
    || typeof candidate.workflowKey !== "string" || typeof candidate.definitionVersion !== "string"
    || !integer(candidate.snapshotRevision, 1, Number.MAX_SAFE_INTEGER)
    || (candidate.continuationFromWorkflowRunId !== null && !canonicalUuid7(candidate.continuationFromWorkflowRunId))
    || (candidate.continuationFromJobId !== null && !canonicalUuid7(candidate.continuationFromJobId))
    || !member(candidate.state, ["queued", "running", "waiting-human", "cancelling", "cancelled", "failed", "succeeded", "paused"] as const)
    || typeof candidate.activeCompute !== "boolean" || decodeWorkflowProgress(candidate.progress) === null
    || !integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER) || !utcInstant(candidate.updatedAt)
    || (candidate.interruptionKind !== null && !member(candidate.interruptionKind, ["ordinary-restart", "user-cancel", "security-lock", "policy", "dependency"] as const))) return null;
  if (!Array.isArray(candidate.steps) || candidate.steps.length > 256 || !candidate.steps.every((value) => {
    const step = record(value);
    return !!step && exactKeys(step, ["stepRunId", "stepKey", "kind", "state", "dependsOn"])
      && canonicalUuid7(step.stepRunId) && typeof step.stepKey === "string"
      && member(step.kind, ["activity", "human-task"] as const) && typeof step.state === "string"
      && Array.isArray(step.dependsOn) && step.dependsOn.every((item) => typeof item === "string");
  })) return null;
  if (!Array.isArray(candidate.jobs) || candidate.jobs.length > 4096 || !candidate.jobs.every((value) => {
    const job = record(value);
    return !!job && exactKeys(job, ["jobId", "state", "activityType", "resourcePool", "priority", "attemptCount", "maxAttempts", "currentAttemptId", "workerId", "progress", "latestCheckpointId", "latestCheckpointAt", "diagnosticCode", "updatedAt"])
      && canonicalUuid7(job.jobId) && member(job.state, ["runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded"] as const)
      && typeof job.activityType === "string" && member(job.resourcePool, ["interactive", "document", "ai", "maintenance"] as const)
      && integer(job.priority, -1000, 1000) && integer(job.attemptCount, 0, 32) && integer(job.maxAttempts, 1, 32)
      && (job.currentAttemptId === null || canonicalUuid7(job.currentAttemptId))
      && (job.workerId === null || canonicalUuid7(job.workerId)) && decodeWorkflowProgress(job.progress) !== null
      && (job.latestCheckpointId === null || canonicalUuid7(job.latestCheckpointId))
      && (job.latestCheckpointAt === null || utcInstant(job.latestCheckpointAt))
      && (job.diagnosticCode === null || typeof job.diagnosticCode === "string") && utcInstant(job.updatedAt);
  })) return null;
  if (!Array.isArray(candidate.humanTasks) || candidate.humanTasks.length > 4096 || !candidate.humanTasks.every((value) => {
    const task = record(value);
    const consequences = record(task?.consequencesByDisposition);
    return !!task && exactKeys(task, ["humanTaskId", "stepRunId", "state", "requiredRole", "assignedActorId", "requestedAt", "evidenceArtifactIds", "allowedDispositions", "consequencesByDisposition", "decisionId", "disposition", "decidedAt"])
      && canonicalUuid7(task.humanTaskId) && canonicalUuid7(task.stepRunId)
      && member(task.state, ["requested", "claimed", "completed", "cancelled", "expired", "superseded"] as const)
      && typeof task.requiredRole === "string" && (task.assignedActorId === null || canonicalUuid7(task.assignedActorId))
      && utcInstant(task.requestedAt) && Array.isArray(task.evidenceArtifactIds) && task.evidenceArtifactIds.every(canonicalUuid7)
      && uniqueMembers(task.allowedDispositions, ["approved", "rejected", "deferred", "not-applicable"] as const, 4, 1)
      && consequences !== null && exactKeys(consequences, task.allowedDispositions as string[])
      && Object.values(consequences).every((item) => typeof item === "string" && /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(item))
      && (task.decisionId === null || canonicalUuid7(task.decisionId))
      && (task.disposition === null || member(task.disposition, ["approved", "rejected", "deferred", "not-applicable"] as const))
      && (task.decidedAt === null || utcInstant(task.decidedAt))
      && new Set(task.evidenceArtifactIds as string[]).size === (task.evidenceArtifactIds as string[]).length
      && ((task.state === "completed") === (task.decisionId !== null && task.disposition !== null && task.decidedAt !== null))
      && ((task.decisionId !== null || task.disposition !== null || task.decidedAt !== null)
        === (task.decisionId !== null && task.disposition !== null && task.decidedAt !== null))
      && (task.state !== "claimed" || task.assignedActorId !== null);
  })) return null;
  if (!Array.isArray(candidate.retainedArtifacts)
    || !uniqueMembers(candidate.retainedArtifacts, ["committed", "retained-incomplete", "quarantined", "discarded"] as const, 4)) return null;
  if (!Array.isArray(candidate.events) || candidate.events.length > 25 || !candidate.events.every((value) => {
    const event = record(value);
    return !!event && exactKeys(event, ["sequence", "entityType", "entityId", "toState", "occurredAt", "reasonCode"])
      && integer(event.sequence, 1, Number.MAX_SAFE_INTEGER) && typeof event.entityType === "string"
      && canonicalUuid7(event.entityId) && typeof event.toState === "string" && utcInstant(event.occurredAt)
      && typeof event.reasonCode === "string";
  })) return null;
  if (candidate.activeCompute !== candidate.jobs.some((job) => ["claimed", "running", "cancelling"].includes((job as Record<string, unknown>).state as string))) return null;
  const continuationPresent = candidate.continuationFromWorkflowRunId !== null
    && candidate.continuationFromJobId !== null;
  if ((candidate.continuationFromWorkflowRunId !== null || candidate.continuationFromJobId !== null) !== continuationPresent
    || (continuationPresent && (candidate.continuationFromWorkflowRunId === candidate.workflowRunId
      || candidate.jobs.some((job) => (job as Record<string, unknown>).jobId === candidate.continuationFromJobId)))) return null;
  if (candidate.state === "waiting-human" && !candidate.humanTasks.some((task) =>
    ["requested", "claimed"].includes((task as Record<string, unknown>).state as string))) return null;
  for (const identities of [
    candidate.steps.map((step) => (step as Record<string, unknown>).stepRunId),
    candidate.jobs.map((job) => (job as Record<string, unknown>).jobId),
    candidate.humanTasks.map((task) => (task as Record<string, unknown>).humanTaskId),
  ]) if (new Set(identities).size !== identities.length) return null;
  const events = candidate.events as unknown[];
  if (events.some((event, index) => index > 0
    && ((events[index - 1] as Record<string, unknown>).sequence as number)
      >= ((event as Record<string, unknown>).sequence as number))) return null;
  return candidate as unknown as WorkflowTaskCenterRun;
}

export function decodeWorkflowTaskCenterPage(value: unknown): WorkflowTaskCenterPage | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["schemaVersion", "items"]) || candidate.schemaVersion !== "1.0"
    || !Array.isArray(candidate.items) || candidate.items.length > 100
    || candidate.items.some((item) => decodeWorkflowTaskCenterRun(item) === null)) return null;
  return candidate as unknown as WorkflowTaskCenterPage;
}

export function decodeProjectProjection(value: unknown): ProjectProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "displayName", "templateId", "lifecycleState", "root", "open", "revision",
    "accessMode", "compatibilityState", "packageFormatVersion", "backupRequiredBeforeRepair", "recoveryAction",
    "deleteConfirmation",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)) return null;
  if (!boundedText(candidate.displayName, 1, 120) || !/^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(String(candidate.templateId))) return null;
  if (!projectLifecycleState(candidate.lifecycleState) || !projectRoot(candidate.root) || typeof candidate.open !== "boolean") return null;
  if (!projectAccessMode(candidate.accessMode) || !projectCompatibilityState(candidate.compatibilityState)) return null;
  if (!safeReleaseVersion(candidate.packageFormatVersion) || typeof candidate.backupRequiredBeforeRepair !== "boolean") return null;
  if (!projectRecoveryAction(candidate.recoveryAction)) return null;
  if (!integer(candidate.revision, 0, Number.MAX_SAFE_INTEGER)) return null;
  if (candidate.deleteConfirmation !== `delete:${candidate.projectId}`) return null;
  if (candidate.open !== (candidate.accessMode !== "closed")) return null;
  if (candidate.lifecycleState !== "active" && candidate.accessMode !== "closed") return null;
  if (candidate.compatibilityState === "compatible") {
    if (candidate.packageFormatVersion !== "1.0.0" || candidate.accessMode === "read-only"
      || candidate.backupRequiredBeforeRepair || candidate.recoveryAction !== "none") return null;
  } else if (candidate.compatibilityState === "migration-required") {
    if (candidate.accessMode === "read-write" || !candidate.backupRequiredBeforeRepair
      || candidate.recoveryAction !== "backup-then-migrate") return null;
  } else if (candidate.accessMode === "read-write" || !candidate.backupRequiredBeforeRepair
    || candidate.recoveryAction !== "backup-then-use-compatible-application") {
      return null;
  }
  return candidate as unknown as ProjectProjection;
}

function intentEgressPolicy(value: unknown): value is IntentEgressPolicy {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["mode", "approvedDestinationIds"])
    || !member(candidate.mode, ["local-only", "approved-redacted", "approved-content"] as const)
    || !Array.isArray(candidate.approvedDestinationIds) || candidate.approvedDestinationIds.length > 32
    || !candidate.approvedDestinationIds.every((item) => typeof item === "string"
      && /^[a-z0-9][a-z0-9._-]{0,99}$/.test(item))
    || new Set(candidate.approvedDestinationIds).size !== candidate.approvedDestinationIds.length) return false;
  return (candidate.mode === "local-only") === (candidate.approvedDestinationIds.length === 0);
}

export function decodeIntentDraftProjection(value: unknown): IntentDraftProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "intentId", "revisionId", "revision", "revisionContentHash", "createdAt", "status",
    "primaryUseCase", "epistemicMode", "researchObjective", "contributionIntent", "phenomenon", "unitOfAnalysis",
    "levelOfAnalysis", "sourceKinds", "languageCodes", "startYear", "endYear", "includePrivateReports",
    "evidenceTypes", "noveltyStandard", "noveltyRationale", "autonomyLevel", "stoppingConditions",
    "revisionRationale", "unresolvedDecisions", "decisionComplete", "canRequestAcceptance", "launchReady", "egressPolicy",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.intentId) || !canonicalUuid7(candidate.revisionId)
    || candidate.intentId === candidate.revisionId || !integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER)
    || !contentHash(candidate.revisionContentHash) || !utcInstant(candidate.createdAt)
    || !member(candidate.status, INTENT_REVISION_STATUSES)
    || !member(candidate.primaryUseCase, INTENT_PRIMARY_USE_CASES) || !member(candidate.epistemicMode, INTENT_MODES)
    || !boundedNarrative(candidate.researchObjective) || !boundedNarrative(candidate.contributionIntent)
    || !boundedNarrative(candidate.phenomenon) || !boundedNarrative(candidate.unitOfAnalysis)
    || !boundedNarrative(candidate.levelOfAnalysis)
    || !uniqueMembers(candidate.sourceKinds, INTENT_SOURCE_KINDS, 32) || !languageCodes(candidate.languageCodes)
    || (candidate.startYear !== null && !integer(candidate.startYear, 1000, 9999))
    || (candidate.endYear !== null && !integer(candidate.endYear, 1000, 9999))
    || ((candidate.startYear === null) !== (candidate.endYear === null))
    || (typeof candidate.startYear === "number" && typeof candidate.endYear === "number" && candidate.startYear > candidate.endYear)
    || typeof candidate.includePrivateReports !== "boolean"
    || !uniqueMembers(candidate.evidenceTypes, INTENT_EVIDENCE_TYPES, 32)
    || (candidate.noveltyStandard !== null && !member(candidate.noveltyStandard, INTENT_NOVELTY_STANDARDS))
    || !boundedNarrative(candidate.noveltyRationale) || !member(candidate.autonomyLevel, INTENT_AUTONOMY_LEVELS)
    || !uniqueMembers(candidate.stoppingConditions, INTENT_STOPPING_CONDITIONS, 3, 1)
    || !intentEgressPolicy(candidate.egressPolicy)
    || !boundedNarrative(candidate.revisionRationale, 1) || !stringList(candidate.unresolvedDecisions, 64)
    || typeof candidate.decisionComplete !== "boolean" || typeof candidate.canRequestAcceptance !== "boolean"
    || typeof candidate.launchReady !== "boolean") return null;
  if (candidate.decisionComplete !== (candidate.unresolvedDecisions.length === 0)
    || (candidate.status === "draft"
      && (candidate.canRequestAcceptance !== candidate.decisionComplete || candidate.launchReady))
    || (candidate.status === "accepted"
      && (!candidate.decisionComplete || candidate.canRequestAcceptance || !candidate.launchReady))) return null;
  return candidate as unknown as IntentDraftProjection;
}

function decodeIntentRevisionSummary(value: unknown): IntentRevisionSummary | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "revision", "revisionId", "revisionContentHash", "createdAt", "status", "primaryUseCase", "unresolvedDecisionCount",
  ])) return null;
  if (!integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER) || !canonicalUuid7(candidate.revisionId)
    || !contentHash(candidate.revisionContentHash) || !utcInstant(candidate.createdAt)
    || !member(candidate.status, INTENT_REVISION_STATUSES)
    || !member(candidate.primaryUseCase, INTENT_PRIMARY_USE_CASES)
    || !integer(candidate.unresolvedDecisionCount, 0, 64)) return null;
  return candidate as unknown as IntentRevisionSummary;
}

export function decodeIntentWorkspaceProjection(value: unknown): IntentWorkspaceProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["schemaVersion", "projectId", "current", "history"])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId) || !Array.isArray(candidate.history)
    || candidate.history.length > 100) return null;
  const current = candidate.current === null ? null : decodeIntentDraftProjection(candidate.current);
  const history = candidate.history.map(decodeIntentRevisionSummary);
  if ((candidate.current !== null && current === null) || history.some((item) => item === null)) return null;
  if (history.some((item, index) => index > 0 && (item?.revision ?? 0) >= (history[index - 1]?.revision ?? 0))) return null;
  if ((current === null) !== (history.length === 0)
    || (current && (current.revision !== history[0]?.revision
      || current.revisionId !== history[0]?.revisionId
      || current.revisionContentHash !== history[0]?.revisionContentHash
      || current.createdAt !== history[0]?.createdAt
      || current.primaryUseCase !== history[0]?.primaryUseCase
      || current.status !== history[0]?.status
      || current.unresolvedDecisions.length !== history[0]?.unresolvedDecisionCount))) return null;
  return { schemaVersion: "1.0", projectId: candidate.projectId, current, history: history as IntentRevisionSummary[] };
}

export function decodeIntentGoverningReference(value: unknown): IntentGoverningReference | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "documentType", "contractVersion", "intentId", "revisionId", "revision", "revisionContentHash",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || candidate.documentType !== "research-observatory-research-intent-reference"
    || !safeReleaseVersion(candidate.contractVersion) || !canonicalUuid7(candidate.intentId)
    || !canonicalUuid7(candidate.revisionId) || candidate.intentId === candidate.revisionId
    || !integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER) || !contentHash(candidate.revisionContentHash)) return null;
  return candidate as unknown as IntentGoverningReference;
}

export function decodeIntentPolicyDecision(value: unknown): IntentPolicyDecision | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "decisionId", "evaluatedAt", "action", "subjectType", "outcome", "reasonCode", "explanation",
    "governingIntent", "requiredGates", "outputLabel", "stoppingRequiresHumanConfirmation",
  ])) return null;
  const governing = candidate.governingIntent === null ? null : decodeIntentGoverningReference(candidate.governingIntent);
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.decisionId) || !utcInstant(candidate.evaluatedAt)
    || !member(candidate.action, INTENT_POLICY_ACTIONS) || !member(candidate.subjectType, INTENT_POLICY_SUBJECTS)
    || !member(candidate.outcome, INTENT_POLICY_OUTCOMES)
    || typeof candidate.reasonCode !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(candidate.reasonCode)
    || !boundedText(candidate.explanation, 1, 1000)
    || (candidate.governingIntent !== null && governing === null)
    || !uniqueMembers(candidate.requiredGates, INTENT_HUMAN_GATES, 6)
    || (candidate.outputLabel !== null && !member(candidate.outputLabel, INTENT_OUTPUT_LABELS))
    || typeof candidate.stoppingRequiresHumanConfirmation !== "boolean") return null;
  if (candidate.outcome === "deny" && candidate.outputLabel !== null) return null;
  return { ...candidate, governingIntent: governing } as unknown as IntentPolicyDecision;
}

export function decodeIntentImpactPreview(value: unknown): IntentImpactPreview | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "expectedRevision", "changeCategories", "affectedWorkflows", "affectedOutputs", "affectedSchemas",
    "affectedCheckpoints", "autonomyDefaultEffects", "stoppingLogicEffects", "staleArtifactIds", "allToolsAccessible",
    "evidenceRequirementsUnchanged", "provenanceRequirementsUnchanged", "warnings", "acknowledgementRequired",
    "acknowledgementToken",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !integer(candidate.expectedRevision, 0, Number.MAX_SAFE_INTEGER)
    || !uniqueMembers(candidate.changeCategories, INTENT_CHANGE_CATEGORIES, 4)
    || !stringList(candidate.affectedWorkflows, 32) || !stringList(candidate.affectedOutputs, 32)
    || !stringList(candidate.affectedSchemas, 16) || !stringList(candidate.affectedCheckpoints, 256)
    || !stringList(candidate.autonomyDefaultEffects, 8) || !stringList(candidate.stoppingLogicEffects, 8)
    || !stringList(candidate.staleArtifactIds, 256) || candidate.allToolsAccessible !== true
    || candidate.evidenceRequirementsUnchanged !== true || candidate.provenanceRequirementsUnchanged !== true
    || !stringList(candidate.warnings, 8) || typeof candidate.acknowledgementRequired !== "boolean"
    || (candidate.acknowledgementToken !== null
      && (typeof candidate.acknowledgementToken !== "string" || !/^[0-9a-f]{64}$/.test(candidate.acknowledgementToken)))) return null;
  if (candidate.acknowledgementRequired !== (candidate.acknowledgementToken !== null)
    || candidate.acknowledgementRequired !== (candidate.changeCategories.length > 0)) return null;
  return candidate as unknown as IntentImpactPreview;
}

function decodeWorkflowProfileStageProjection(value: unknown): WorkflowProfileStageProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "stageKey", "order", "pageContractId", "label", "optional", "rationale", "checkpointState", "checkpointRationale",
  ])) return null;
  if (typeof candidate.stageKey !== "string" || !/^[a-z0-9][a-z0-9._-]{0,99}$/.test(candidate.stageKey)
    || !integer(candidate.order, 1, 256) || typeof candidate.pageContractId !== "string"
    || !/^[a-z0-9][a-z0-9-]*\.html$/.test(candidate.pageContractId) || !boundedText(candidate.label, 1, 120)
    || typeof candidate.optional !== "boolean" || !boundedText(candidate.rationale, 1, 4000)
    || !member(candidate.checkpointState, ["unknown", "optional-human", "required-human", "not-applicable"] as const)
    || !boundedText(candidate.checkpointRationale, 1, 4000)) return null;
  return candidate as unknown as WorkflowProfileStageProjection;
}

function decodeWorkflowProfileProjection(value: unknown): WorkflowProfileProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "profileId", "epistemicMode", "title", "purpose", "example", "expectedOutputs", "processForm",
    "defaultEvidenceTypes", "defaultNoveltyStandard", "defaultAutonomyLevel", "defaultStoppingConditions",
    "warning", "stages",
  ])) return null;
  if (!member(candidate.profileId, INTENT_PRIMARY_USE_CASES) || !member(candidate.epistemicMode, INTENT_MODES)
    || !boundedText(candidate.title, 1, 200) || !boundedText(candidate.purpose, 1, 4000)
    || !boundedText(candidate.example, 1, 1000) || !stringList(candidate.expectedOutputs, 32)
    || candidate.expectedOutputs.length < 1 || !member(candidate.processForm, ["linear", "revisitable"] as const)
    || !uniqueMembers(candidate.defaultEvidenceTypes, INTENT_EVIDENCE_TYPES, 32, 1)
    || !member(candidate.defaultNoveltyStandard, INTENT_NOVELTY_STANDARDS)
    || !member(candidate.defaultAutonomyLevel, INTENT_AUTONOMY_LEVELS)
    || !uniqueMembers(candidate.defaultStoppingConditions, INTENT_STOPPING_CONDITIONS, 3, 1)
    || !boundedText(candidate.warning, 1, 1000)
    || !Array.isArray(candidate.stages) || candidate.stages.length < 1 || candidate.stages.length > 256) return null;
  const stages = candidate.stages.map(decodeWorkflowProfileStageProjection);
  if (stages.some((stage) => stage === null)) return null;
  const decoded = stages as WorkflowProfileStageProjection[];
  if (new Set(decoded.map((stage) => stage.stageKey)).size !== decoded.length
    || decoded.some((stage, index) => stage.order !== index + 1)) return null;
  return { ...candidate, stages: decoded } as unknown as WorkflowProfileProjection;
}

function workflowProfileGuidanceSha256(profiles: readonly WorkflowProfileProjection[]): string {
  const guidanceByProfile: Record<string, unknown> = {};
  for (const profile of profiles) {
    guidanceByProfile[profile.profileId] = {
      example: profile.example,
      evidenceTypes: profile.defaultEvidenceTypes,
      noveltyStandard: profile.defaultNoveltyStandard,
      autonomyLevel: profile.defaultAutonomyLevel,
      stoppingConditions: profile.defaultStoppingConditions,
      warning: profile.warning,
    };
  }
  const document = {
    schemaVersion: "1.0",
    documentType: "research-observatory-intent-profile-guidance",
    guidanceVersion: "1.0.0",
    profileCatalogHash: "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49",
    profiles: guidanceByProfile,
  };
  return "sha256:" + sha256Hex(canonicalContractJson(document));
}

export function decodeWorkflowProfileCatalogProjection(value: unknown): WorkflowProfileCatalogProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "referenceId", "referenceVersion", "profileCatalogVersion", "profileCatalogHash",
    "intentGuidanceVersion", "intentGuidanceHash",
    "allToolsAccessible", "evidenceRequirementsUnchanged", "provenanceRequirementsUnchanged",
    "registeredToolPageContractIds", "profiles",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || candidate.referenceId !== "RO-UI-ACADEMIC-MINIMAL-1.5"
    || candidate.referenceVersion !== "1.5" || candidate.profileCatalogVersion !== "1.0.0"
    || candidate.profileCatalogHash !== "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49"
    || candidate.intentGuidanceVersion !== "1.0.0"
    || candidate.intentGuidanceHash !== "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2"
    || candidate.allToolsAccessible !== true || candidate.evidenceRequirementsUnchanged !== true
    || candidate.provenanceRequirementsUnchanged !== true || !stringList(candidate.registeredToolPageContractIds, 256)
    || candidate.registeredToolPageContractIds.length < 1 || !Array.isArray(candidate.profiles)
    || candidate.profiles.length !== INTENT_PRIMARY_USE_CASES.length) return null;
  const profiles = candidate.profiles.map(decodeWorkflowProfileProjection);
  if (profiles.some((profile) => profile === null)) return null;
  const decoded = profiles as WorkflowProfileProjection[];
  const profileIds = decoded.map((profile) => profile.profileId);
  const registered = new Set(candidate.registeredToolPageContractIds);
  if (new Set(profileIds).size !== INTENT_PRIMARY_USE_CASES.length
    || INTENT_PRIMARY_USE_CASES.some((profileId) => !profileIds.includes(profileId))
    || decoded.some((profile) => profile.stages.some((stage) => !registered.has(stage.pageContractId)))
    || workflowProfileGuidanceSha256(decoded) !== candidate.intentGuidanceHash
    || "sha256:" + sha256Hex(canonicalContractJson({ ...candidate, profiles: decoded }))
      !== CORE_API_WORKFLOW_PROFILE_PROJECTION_SHA256) return null;
  return { ...candidate, profiles: decoded } as unknown as WorkflowProfileCatalogProjection;
}

function decodeWorkflowStageStateProjection(value: unknown): WorkflowStageStateProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "stageStateId", "stageStateRevisionId", "revision", "revisionContentHash", "parentStateRevisionId",
    "stageKey", "pageContractId", "navigationRole", "passNumber", "status", "completionEvidenceIds",
    "attentionReason", "staleCauseIds", "skipRationale", "updatedAt",
  ])) return null;
  if (!canonicalUuid7(candidate.stageStateId) || !canonicalUuid7(candidate.stageStateRevisionId)
    || !integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER) || !contentHash(candidate.revisionContentHash)
    || (candidate.parentStateRevisionId !== null && !canonicalUuid7(candidate.parentStateRevisionId))
    || typeof candidate.stageKey !== "string" || !/^[a-z0-9][a-z0-9._-]{0,99}$/.test(candidate.stageKey)
    || typeof candidate.pageContractId !== "string"
    || !/^[a-z0-9][a-z0-9-]{0,99}\.html$/.test(candidate.pageContractId)
    || !member(candidate.navigationRole, ["primary", "supporting"] as const)
    || !integer(candidate.passNumber, 1, Number.MAX_SAFE_INTEGER)
    || !member(candidate.status, [
      "not-started", "available", "current", "in-progress", "attention-required", "blocked", "completed",
      "stale", "skipped-with-rationale",
    ] as const) || !Array.isArray(candidate.completionEvidenceIds)
    || candidate.completionEvidenceIds.length > 256 || !candidate.completionEvidenceIds.every(canonicalUuid7)
    || new Set(candidate.completionEvidenceIds).size !== candidate.completionEvidenceIds.length
    || (candidate.attentionReason !== null && !boundedText(candidate.attentionReason, 1, 4000))
    || !Array.isArray(candidate.staleCauseIds) || candidate.staleCauseIds.length > 256
    || !candidate.staleCauseIds.every(canonicalUuid7)
    || new Set(candidate.staleCauseIds).size !== candidate.staleCauseIds.length
    || (candidate.skipRationale !== null && !boundedText(candidate.skipRationale, 1, 4000))
    || !utcInstant(candidate.updatedAt)) return null;
  if ((candidate.status === "completed") !== (candidate.completionEvidenceIds.length > 0)
    || member(candidate.status, ["attention-required", "blocked"] as const) !== (candidate.attentionReason !== null)
    || (candidate.status === "skipped-with-rationale") !== (candidate.skipRationale !== null)) return null;
  return candidate as unknown as WorkflowStageStateProjection;
}

function decodeWorkflowSupportingHandoffProjection(value: unknown): WorkflowSupportingHandoffProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "stageStateId", "stageStateRevisionId", "revisionContentHash", "pageContractId", "navigationRole",
    "returnStageStateRevisionId",
  ])) return null;
  if (!canonicalUuid7(candidate.stageStateId) || !canonicalUuid7(candidate.stageStateRevisionId)
    || !contentHash(candidate.revisionContentHash) || typeof candidate.pageContractId !== "string"
    || !/^[a-z0-9][a-z0-9-]{0,99}\.html$/.test(candidate.pageContractId)
    || candidate.navigationRole !== "supporting" || !canonicalUuid7(candidate.returnStageStateRevisionId)) return null;
  return candidate as unknown as WorkflowSupportingHandoffProjection;
}

function decodeWorkflowStaleOutputProjection(value: unknown): WorkflowStaleOutputProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "outputRevisionId", "disposition", "reason", "causeReferenceHash", "safestNextAction",
  ])) return null;
  if (!canonicalUuid7(candidate.outputRevisionId) || !member(candidate.disposition, ["stale", "unknown-impact"] as const)
    || !boundedText(candidate.reason, 1, 100) || !contentHash(candidate.causeReferenceHash)
    || !boundedText(candidate.safestNextAction, 1, 4000)) return null;
  return candidate as unknown as WorkflowStaleOutputProjection;
}

export function decodeWorkflowProgressProjection(value: unknown): WorkflowProgressProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "selectionRevisionId", "selectionRevisionContentHash", "intentRevisionId",
    "intentRevisionContentHash", "profileId", "profileTitle", "processForm", "bootstrapRequired", "current", "recommendedStageKey",
    "recommendedPageContractId", "recommendedAction", "checkpointState", "checkpointRationale",
    "supportingHandoff", "staleOutputs", "history",
  ])) return null;
  const current = candidate.current === null ? null : decodeWorkflowStageStateProjection(candidate.current);
  const supporting = candidate.supportingHandoff === null
    ? null : decodeWorkflowSupportingHandoffProjection(candidate.supportingHandoff);
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !canonicalUuid7(candidate.selectionRevisionId) || !contentHash(candidate.selectionRevisionContentHash)
    || !canonicalUuid7(candidate.intentRevisionId) || !contentHash(candidate.intentRevisionContentHash)
    || !member(candidate.profileId, INTENT_PRIMARY_USE_CASES) || !boundedText(candidate.profileTitle, 1, 200)
    || !member(candidate.processForm, ["linear", "revisitable"] as const)
    || typeof candidate.bootstrapRequired !== "boolean" || (candidate.current !== null && current === null)
    || typeof candidate.recommendedStageKey !== "string"
    || !/^[a-z0-9][a-z0-9._-]{0,99}$/.test(candidate.recommendedStageKey)
    || typeof candidate.recommendedPageContractId !== "string"
    || !/^[a-z0-9][a-z0-9-]{0,99}\.html$/.test(candidate.recommendedPageContractId)
    || !boundedText(candidate.recommendedAction, 1, 4000)
    || !member(candidate.checkpointState, ["unknown", "optional-human", "required-human", "not-applicable"] as const)
    || !boundedText(candidate.checkpointRationale, 1, 4000)
    || (candidate.supportingHandoff !== null && supporting === null)
    || !Array.isArray(candidate.staleOutputs) || candidate.staleOutputs.length > 256
    || candidate.staleOutputs.some((item) => decodeWorkflowStaleOutputProjection(item) === null)
    || !Array.isArray(candidate.history) || candidate.history.length > 512
    || candidate.history.some((item) => decodeWorkflowStageStateProjection(item) === null)) return null;
  if (candidate.bootstrapRequired !== (candidate.current === null && candidate.history.length === 0)
    || (supporting !== null && current?.stageStateRevisionId !== supporting.returnStageStateRevisionId)) return null;
  return { ...candidate, current, supportingHandoff: supporting } as unknown as WorkflowProgressProjection;
}

function decodeRecalculationCause(value: unknown): RecalculationCauseProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "causeId", "changeId", "disposition", "reason", "depth", "confidence", "reviewRequired", "pathRevisionIds",
  ])) return null;
  if (!canonicalUuid7(candidate.causeId) || !canonicalUuid7(candidate.changeId)
    || !member(candidate.disposition, ["stale", "unknown-impact"] as const)
    || !boundedText(candidate.reason, 1, 1000) || !integer(candidate.depth, 1, Number.MAX_SAFE_INTEGER)
    || !member(candidate.confidence, ["confirmed", "conditional", "unknown"] as const)
    || typeof candidate.reviewRequired !== "boolean" || !Array.isArray(candidate.pathRevisionIds)
    || candidate.pathRevisionIds.length > 256 || !candidate.pathRevisionIds.every(canonicalUuid7)) return null;
  return candidate as unknown as RecalculationCauseProjection;
}

export function decodeRecalculationPreview(value: unknown): RecalculationPreview | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "targetRevisionId", "planSha256", "policySha256", "changeIds",
    "replacementRevisionIds", "reusableRevisionIds", "causes", "deferPreservesStaleVisibility",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !canonicalUuid7(candidate.targetRevisionId) || !contentHash(candidate.planSha256)
    || !contentHash(candidate.policySha256) || !Array.isArray(candidate.changeIds)
    || candidate.changeIds.length > 10_000 || !candidate.changeIds.every(canonicalUuid7)
    || !Array.isArray(candidate.replacementRevisionIds) || candidate.replacementRevisionIds.length > 10_000
    || !candidate.replacementRevisionIds.every(canonicalUuid7) || !Array.isArray(candidate.reusableRevisionIds)
    || candidate.reusableRevisionIds.length > 10_000 || !candidate.reusableRevisionIds.every(canonicalUuid7)
    || !Array.isArray(candidate.causes) || candidate.causes.length > 10_000
    || candidate.causes.some((item) => decodeRecalculationCause(item) === null)
    || candidate.deferPreservesStaleVisibility !== true) return null;
  return candidate as unknown as RecalculationPreview;
}

export function decodeRecalculationSchedule(value: unknown): RecalculationScheduleProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "targetRevisionId", "planSha256", "workflowRunId", "jobId", "state",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !canonicalUuid7(candidate.targetRevisionId) || !contentHash(candidate.planSha256)
    || !canonicalUuid7(candidate.workflowRunId) || !canonicalUuid7(candidate.jobId)
    || !member(candidate.state, [
      "runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded",
    ] as const)) return null;
  return candidate as unknown as RecalculationScheduleProjection;
}

export function decodeRecalculationComparison(value: unknown): RecalculationComparisonProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "aggregateId", "beforeRevisionId", "afterRevisionId", "beforeRevision", "afterRevision",
    "changedFields",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.aggregateId)
    || !canonicalUuid7(candidate.beforeRevisionId) || !canonicalUuid7(candidate.afterRevisionId)
    || !integer(candidate.beforeRevision, 0, Number.MAX_SAFE_INTEGER)
    || !integer(candidate.afterRevision, 0, Number.MAX_SAFE_INTEGER)
    || candidate.afterRevision <= candidate.beforeRevision || !stringList(candidate.changedFields, 256)) return null;
  return candidate as unknown as RecalculationComparisonProjection;
}

export function decodeRecalculationRestoreReview(value: unknown): RecalculationRestoreReviewProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "workflowRunId", "humanTaskId", "snapshotRevision", "historySequence", "policySha256",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.workflowRunId)
    || !canonicalUuid7(candidate.humanTaskId) || !integer(candidate.snapshotRevision, 1, Number.MAX_SAFE_INTEGER)
    || !integer(candidate.historySequence, 1, Number.MAX_SAFE_INTEGER) || !contentHash(candidate.policySha256)) return null;
  return candidate as unknown as RecalculationRestoreReviewProjection;
}

export function decodeRecalculationRestoredRevision(value: unknown): RecalculationRestoredRevision | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "aggregateId", "revisionId", "revision", "knowledgeStatus", "rightsStatus",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !canonicalUuid7(candidate.aggregateId) || !canonicalUuid7(candidate.revisionId)
    || !integer(candidate.revision, 1, Number.MAX_SAFE_INTEGER)
    || !member(candidate.knowledgeStatus, [
      "observed", "extracted", "inferred", "verified", "disputed", "adjudicated", "stale", "unknown",
      "not-reported", "not-applicable", "ambiguous", "unavailable",
    ] as const) || !member(candidate.rightsStatus, ["allowed", "denied", "unknown", "not-applicable"] as const)) return null;
  return candidate as unknown as RecalculationRestoredRevision;
}

function decodeDeletionDisclosure(value: unknown): DeletionDisclosure | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "disclosureVersion", "scope", "logicalRemoval", "physicalErasureGuaranteed",
    "canonicalProjectDataExcluded", "limitations",
  ])) return null;
  if (candidate.disclosureVersion !== "secure-deletion-disclosure-v1" || candidate.scope !== "project-cache-only") return null;
  if (candidate.logicalRemoval !== true || candidate.physicalErasureGuaranteed !== false
    || candidate.canonicalProjectDataExcluded !== true || !Array.isArray(candidate.limitations)
    || candidate.limitations.length < 4 || candidate.limitations.length > 8
    || candidate.limitations.some((item) => !boundedText(item, 1, 240))) return null;
  return candidate as unknown as DeletionDisclosure;
}

function registryOwnedValue(value: unknown): unknown {
  let remaining = 80000;
  function own(item: unknown, depth: number): unknown {
    if (--remaining < 0 || depth > 12) throw new Error("registry-value-bound");
    if (item === null || typeof item === "string" || typeof item === "boolean") return item;
    if (typeof item === "number" && Number.isSafeInteger(item)) return item;
    if (typeof item !== "object" || item === null) throw new Error("registry-value-type");
    const prototype = Object.getPrototypeOf(item);
    if (Array.isArray(item)) {
      if (prototype !== Array.prototype || item.length > 1000) throw new Error("registry-array-bound");
      const descriptors = Object.getOwnPropertyDescriptors(item);
      if (Reflect.ownKeys(item).length !== item.length + 1) throw new Error("registry-array-shape");
      return Object.freeze(Array.from({ length: item.length }, (_, index) => {
        const descriptor = descriptors[String(index)];
        if (!descriptor || !("value" in descriptor)) throw new Error("registry-array-accessor");
        return own(descriptor.value, depth + 1);
      }));
    }
    if (prototype !== Object.prototype && prototype !== null) throw new Error("registry-object-prototype");
    const owned: Record<string, unknown> = Object.create(null);
    const descriptors = Object.getOwnPropertyDescriptors(item);
    for (const key of Reflect.ownKeys(item)) {
      if (typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key)) throw new Error("registry-object-key");
      const descriptor = descriptors[key];
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) throw new Error("registry-object-accessor");
      owned[key] = own(descriptor.value, depth + 1);
    }
    return Object.freeze(owned);
  }
  return own(value, 0);
}

function registryCode(value: unknown): value is string {
  return typeof value === "string" && value.length <= 128 && /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(value);
}

function registryEnum(value: unknown, choices: readonly string[]): boolean {
  return typeof value === "string" && choices.includes(value);
}

function registrySet(value: unknown, choices: readonly string[] | null, maximum: number, minimum = 0): value is readonly string[] {
  return Array.isArray(value) && value.length >= minimum && value.length <= maximum
    && value.every((item, index) => registryCode(item) && (choices === null || choices.includes(item))
      && (index === 0 || value[index - 1] < item));
}

const REGISTRY_TASK_KINDS = ["embedding", "reranking", "classification", "nli", "structured-extraction", "generation", "moderation", "tool-call"];
const REGISTRY_MODALITIES = ["text", "image", "audio", "video"];

function registryManifest(value: unknown): value is ModelManifest {
  const item = record(value);
  if (!item || !exactKeys(item, ["schemaVersion", "manifestId", "revision", "identity", "deployment", "licenseId",
    "capabilities", "features", "modalities", "contextTokens", "maxOutputTokens", "supportsCitations", "platforms",
    "minimumMemoryMiB", "accelerator", "qualityTier", "allowedDataClasses", "costMicrounitsPerThousandTokens",
    "declaredAvailability", "retired"])) return false;
  const identity = record(item.identity);
  if (!identity || !exactKeys(identity, ["providerId", "providerVersion", "modelId", "modelVersion", "runtimeId",
    "runtimeVersion", "configurationHash", "evaluationId", "evaluationVersion"])) return false;
  const version = (value: unknown): boolean => typeof value === "string" && value.length <= 128
    && /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/.test(value);
  if (!registryCode(identity.providerId) || !registryCode(identity.modelId) || !registryCode(identity.runtimeId)
    || !version(identity.providerVersion) || !version(identity.runtimeVersion) || !contentHash(identity.configurationHash)
    || typeof identity.modelVersion !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/.test(identity.modelVersion)
    || !((identity.evaluationId === null && identity.evaluationVersion === null)
      || (registryCode(identity.evaluationId) && version(identity.evaluationVersion)))) return false;
  return item.schemaVersion === "1.0" && registryCode(item.manifestId) && integer(item.revision, 1, 2147483647)
    && registryEnum(item.deployment, ["local", "remote", "institutional"]) && registryCode(item.licenseId)
    && registrySet(item.capabilities, REGISTRY_TASK_KINDS, 8, 1) && registrySet(item.features, null, 32)
    && registrySet(item.modalities, REGISTRY_MODALITIES, 4, 1)
    && integer(item.contextTokens, 1, 11000000) && integer(item.maxOutputTokens, 0, 1000000)
    && typeof item.supportsCitations === "boolean" && typeof item.retired === "boolean"
    && registrySet(item.platforms, ["windows-x64", "macos-arm64", "linux-x64", "linux-arm64"], 4, 1)
    && integer(item.minimumMemoryMiB, 0, 10000000) && registryEnum(item.accelerator, ["none", "gpu"])
    && registryEnum(item.qualityTier, ["unrated", "economy", "balanced", "quality"])
    && registrySet(item.allowedDataClasses, ["public", "internal", "confidential", "restricted"], 4)
    && (item.costMicrounitsPerThousandTokens === null || integer(item.costMicrounitsPerThousandTokens, 0, 1000000000000))
    && registryEnum(item.declaredAvailability, ["available", "unavailable", "unknown"]);
}

export function decodeModelCatalogProjection(value: unknown): ModelCatalogProjection | null {
  let item: Readonly<Record<string, unknown>> | null;
  try { item = record(registryOwnedValue(value)); } catch { return null; }
  if (!item || !exactKeys(item, ["schemaVersion", "projectId", "revision", "latestRevision", "catalogHash", "modelCount",
    "inventoryState", "entries", "nextManifestId", "history", "nextHistoryRevision", "executionAvailable"])) return null;
  if (item.schemaVersion !== "1.0" || !canonicalProjectId(item.projectId) || !integer(item.revision, 0, 2147483647)
    || !integer(item.latestRevision, item.revision as number, 2147483647) || !integer(item.modelCount, 0, 1000)
    || (item.revision === 0 ? item.catalogHash !== null || item.latestRevision !== 0 || item.modelCount !== 0 : !contentHash(item.catalogHash))
    || !registryEnum(item.inventoryState, ["not-configured", "available", "unavailable"]) || item.executionAvailable !== false
    || !Array.isArray(item.entries) || item.entries.length > 50 || item.entries.length > Number(item.modelCount)
    || !Array.isArray(item.history) || item.history.length > 20) return null;
  let previousId = "";
  for (const raw of item.entries) {
    const entry = record(raw);
    if (!entry || !exactKeys(entry, ["manifest", "manifestHash", "availability", "qualifiedTaskKinds", "reasonCodes", "eligibility"])
      || !registryManifest(entry.manifest) || entry.manifest.manifestId <= previousId
      || entry.manifestHash !== `sha256:${sha256Hex(canonicalContractJson(entry.manifest))}`
      || !registryEnum(entry.availability, ["ready", "unavailable", "unknown", "stale"]) || entry.eligibility !== "not-evaluated"
      || !registrySet(entry.qualifiedTaskKinds, REGISTRY_TASK_KINDS, 8)
      || !registrySet(entry.reasonCodes, null, 32) || !entry.reasonCodes.includes("task-policy-check-required")
      || entry.qualifiedTaskKinds.some((kind) => !(entry.manifest as ModelManifest).capabilities.includes(kind as ModelTaskKind))
      || (entry.qualifiedTaskKinds.length > 0 && (entry.availability !== "ready" || entry.manifest.identity.evaluationId === null))) return null;
    previousId = entry.manifest.manifestId;
  }
  if (item.nextManifestId !== null && (!registryCode(item.nextManifestId) || item.entries.length !== 50 || item.nextManifestId !== previousId)) return null;
  let previousRevision = Number(item.latestRevision) + 1;
  for (const raw of item.history) {
    const summary = record(raw);
    if (!summary || !exactKeys(summary, ["revision", "catalogHash", "recordHash", "previousHash", "occurredAt", "modelCount"])
      || !integer(summary.revision, 1, previousRevision - 1) || !contentHash(summary.catalogHash) || !contentHash(summary.recordHash)
      || (summary.revision === 1 ? summary.previousHash !== null : !contentHash(summary.previousHash))
      || !integer(summary.modelCount, 0, 1000) || typeof summary.occurredAt !== "string"
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(summary.occurredAt) || !Number.isFinite(Date.parse(summary.occurredAt))
      || (summary.revision === item.revision && (summary.catalogHash !== item.catalogHash || summary.modelCount !== item.modelCount))) return null;
    previousRevision = Number(summary.revision);
  }
  if (item.nextHistoryRevision !== null && (!integer(item.nextHistoryRevision, 2, Number(item.latestRevision))
    || item.history.length === 0 || item.nextHistoryRevision !== previousRevision)) return null;
  return item as unknown as ModelCatalogProjection;
}

export function decodePrivacyPolicyProjection(value: unknown): PrivacyPolicyProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "revision", "defaultsApplied", "networkPolicy",
    "remoteModelApproval", "telemetryMode", "logRetentionDays", "documentRetention",
    "cacheRetentionDays", "egressConsentRecorded", "egressEnforcement", "deletionDisclosure",
  ])) return null;
  const disclosure = decodeDeletionDisclosure(candidate.deletionDisclosure);
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !integer(candidate.revision, 0, Number.MAX_SAFE_INTEGER)
    || candidate.defaultsApplied !== (candidate.revision === 0)
    || !privacyNetworkPolicy(candidate.networkPolicy) || !remoteModelApproval(candidate.remoteModelApproval)
    || !telemetryMode(candidate.telemetryMode) || !integer(candidate.logRetentionDays, 1, 90)
    || !documentRetentionPolicy(candidate.documentRetention) || !integer(candidate.cacheRetentionDays, 1, 90)
    || typeof candidate.egressConsentRecorded !== "boolean" || !egressEnforcement(candidate.egressEnforcement)
    || disclosure === null) return null;
  if (candidate.egressConsentRecorded !== (candidate.networkPolicy !== "offline")) return null;
  if (candidate.egressEnforcement !== (candidate.networkPolicy === "approved-providers" ? "require-task-preview" : "deny")) return null;
  return { ...candidate, deletionDisclosure: disclosure } as unknown as PrivacyPolicyProjection;
}

export function decodeCacheClearPreview(value: unknown): CacheClearPreview | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "policyRevision", "previewToken", "confirmation", "expiresAt",
    "itemCount", "byteCount", "deletionDisclosure",
  ])) return null;
  const disclosure = decodeDeletionDisclosure(candidate.deletionDisclosure);
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || !integer(candidate.policyRevision, 0, Number.MAX_SAFE_INTEGER)
    || typeof candidate.previewToken !== "string" || !/^[0-9a-f]{32}$/.test(candidate.previewToken)
    || candidate.confirmation !== `clear-cache:${candidate.previewToken}`
    || typeof candidate.expiresAt !== "string" || !Number.isFinite(Date.parse(candidate.expiresAt))
    || !integer(candidate.itemCount, 0, 100000) || !integer(candidate.byteCount, 0, Number.MAX_SAFE_INTEGER)
    || disclosure === null) return null;
  return { ...candidate, deletionDisclosure: disclosure } as unknown as CacheClearPreview;
}

export function decodeCacheClearResult(value: unknown): CacheClearResult | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "projectId", "state", "itemCount", "byteCount", "cleanupPending", "deletionDisclosure",
  ])) return null;
  const disclosure = decodeDeletionDisclosure(candidate.deletionDisclosure);
  if (candidate.schemaVersion !== "1.0" || !canonicalProjectId(candidate.projectId)
    || (candidate.state !== "cleared" && candidate.state !== "cleared-cleanup-pending")
    || !integer(candidate.itemCount, 0, 100000) || !integer(candidate.byteCount, 0, Number.MAX_SAFE_INTEGER)
    || typeof candidate.cleanupPending !== "boolean"
    || candidate.cleanupPending !== (candidate.state === "cleared-cleanup-pending") || disclosure === null) return null;
  return { ...candidate, deletionDisclosure: disclosure } as unknown as CacheClearResult;
}

function decodeProvenanceLineageNode(value: unknown): ProvenanceLineageNode | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "factId", "relationType", "entityDirection", "revisionId", "entityId", "entityKind",
    "relatedRevisionId", "knowledgeStatus", "rightsStatus", "depth", "eventId", "eventType",
    "activityId", "activityType", "activityStatus", "configurationId", "configurationVersion",
    "configurationHash", "agentId", "agentType", "agentRole", "occurredAt",
  ])) return null;
  if (!canonicalUuid7(candidate.factId)
    || !member(candidate.relationType, ["used", "wasGeneratedBy", "wasAssociatedWith", "wasDerivedFrom", "wasInvalidatedBy", "wasAttributedTo"] as const)
    || !member(candidate.entityDirection, ["input", "output"] as const)
    || !canonicalUuid7(candidate.revisionId) || !canonicalUuid7(candidate.entityId)
    || !boundedText(candidate.entityKind, 1, 128)
    || !/^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$/.test(candidate.entityKind)
    || (candidate.relatedRevisionId !== null && !canonicalUuid7(candidate.relatedRevisionId))
    || !member(candidate.knowledgeStatus, ["observed", "extracted", "inferred", "verified", "disputed", "adjudicated", "stale", "unknown", "not-reported", "not-applicable", "ambiguous", "unavailable"] as const)
    || !member(candidate.rightsStatus, ["allowed", "denied", "unknown", "not-applicable"] as const)
    || !integer(candidate.depth, 0, 16) || !canonicalUuid7(candidate.eventId)
    || !boundedText(candidate.eventType, 1, 160)
    || !/^org\.research-observatory\..+\.v[1-9][0-9]{0,5}$/.test(candidate.eventType)
    || !canonicalUuid7(candidate.activityId) || !boundedText(candidate.activityType, 1, 128)
    || !/^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$/.test(candidate.activityType)
    || !member(candidate.activityStatus, ["succeeded", "failed", "cancelled", "denied"] as const)
    || !boundedText(candidate.configurationId, 1, 128)
    || !/^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$/.test(candidate.configurationId)
    || !safeReleaseVersion(candidate.configurationVersion) || !contentHash(candidate.configurationHash)
    || !canonicalUuid7(candidate.agentId)
    || !member(candidate.agentType, ["human", "model", "software", "system"] as const)
    || !boundedText(candidate.agentRole, 1, 128)
    || !/^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$/.test(candidate.agentRole)
    || !utcInstant(candidate.occurredAt)) return null;
  const outputRelation = member(candidate.relationType, ["wasGeneratedBy", "wasDerivedFrom", "wasAttributedTo"] as const);
  const inputRelation = member(candidate.relationType, ["used", "wasInvalidatedBy"] as const);
  if ((outputRelation && candidate.entityDirection !== "output")
    || (inputRelation && candidate.entityDirection !== "input")
    || (candidate.relationType === "wasDerivedFrom") !== (candidate.relatedRevisionId !== null)) return null;
  return candidate as unknown as ProvenanceLineageNode;
}

export function decodeProvenanceLineagePage(value: unknown): ProvenanceLineagePage | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "revisionId", "direction", "items", "missingRevisionIds",
    "nextCursor", "truncated", "truncationReason", "integrityState", "legacyEventCount",
    "exportAllowed", "exportDenialReason",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.revisionId)
    || !member(candidate.direction, ["ancestors", "descendants"] as const)
    || !Array.isArray(candidate.items) || candidate.items.length > 100
    || !Array.isArray(candidate.missingRevisionIds) || candidate.missingRevisionIds.length > 256
    || (candidate.nextCursor !== null && !integer(candidate.nextCursor, 0, 10_000))
    || typeof candidate.truncated !== "boolean"
    || (candidate.truncationReason !== null
      && !member(candidate.truncationReason, ["cursor-limit", "scan-limit"] as const))
    || candidate.truncated !== (candidate.truncationReason !== null)
    || !member(candidate.integrityState, ["verified", "integrity-review"] as const)
    || !integer(candidate.legacyEventCount, 0, Number.MAX_SAFE_INTEGER)
    || typeof candidate.exportAllowed !== "boolean"
    || (candidate.exportDenialReason !== null
      && !member(candidate.exportDenialReason, ["integrity-review", "rights-restricted"] as const))
    || candidate.exportAllowed !== (candidate.exportDenialReason === null)) return null;
  const items = candidate.items.map(decodeProvenanceLineageNode);
  if (items.some((item) => item === null)
    || candidate.missingRevisionIds.some((item) => !canonicalUuid7(item))
    || new Set(candidate.missingRevisionIds).size !== candidate.missingRevisionIds.length) return null;
  return {
    schemaVersion: "1.0",
    revisionId: candidate.revisionId,
    direction: candidate.direction,
    items: items as ProvenanceLineageNode[],
    missingRevisionIds: candidate.missingRevisionIds as string[],
    nextCursor: candidate.nextCursor as number | null,
    truncated: candidate.truncated,
    truncationReason: candidate.truncationReason as "cursor-limit" | "scan-limit" | null,
    integrityState: candidate.integrityState,
    legacyEventCount: candidate.legacyEventCount,
    exportAllowed: candidate.exportAllowed,
    exportDenialReason: candidate.exportDenialReason as "integrity-review" | "rights-restricted" | null,
  };
}

export function decodeOperationPage(value: unknown): OperationPage | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["schemaVersion", "items", "nextCursor"])) return null;
  if (candidate.schemaVersion !== "1.0" || !Array.isArray(candidate.items)) return null;
  const items = candidate.items.map(decodeOperationStatus);
  if (items.length > 100 || items.some((item) => item === null)) return null;
  const identities = items.map((item) => item?.operationId ?? "");
  if (new Set(identities).size !== identities.length || identities.some((item, index) => index > 0 && item <= (identities[index - 1] ?? ""))) return null;
  if (candidate.nextCursor !== null && (!canonicalOperationId(candidate.nextCursor) || candidate.nextCursor !== identities.at(-1))) return null;
  return { schemaVersion: "1.0", items: items as OperationStatus[], nextCursor: candidate.nextCursor as string | null };
}

export function decodeOperationProgressEvent(value: unknown): OperationProgressEvent | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["schemaVersion", "operationId", "sequence", "state", "progressPercent", "terminal", "traceId"])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalOperationId(candidate.operationId)) return null;
  if (!integer(candidate.sequence, 1, Number.MAX_SAFE_INTEGER) || !operationState(candidate.state)) return null;
  if (!integer(candidate.progressPercent, 0, 100) || typeof candidate.terminal !== "boolean" || !canonicalTraceId(candidate.traceId)) return null;
  if (candidate.terminal !== (candidate.state === "succeeded" || candidate.state === "failed" || candidate.state === "cancelled")) return null;
  return candidate as unknown as OperationProgressEvent;
}

function semver(value: string): readonly [number, number, number] | null {
  const match = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.exec(value);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

function compare(left: readonly [number, number, number], right: readonly [number, number, number]): number {
  for (let index = 0; index < 3; index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

export function evaluateCoreApiCompatibility(version: VersionResponse): CompatibilityResult {
  const client = semver(CORE_API_CLIENT_VERSION);
  const minimum = semver(version.minimumClientApiVersion);
  const maximum = semver(version.maximumClientApiVersionExclusive);
  const api = semver(version.apiVersion);
  const compatible = version.schemaVersion === "1.0"
    && version.service === "research-observatory-core"
    && client !== null && minimum !== null && maximum !== null && api !== null
    && api[0] === client[0] && compare(client, minimum) >= 0 && compare(client, maximum) < 0;
  return compatible
    ? { ok: true, code: "RO-CORE-API-COMPATIBLE", remediation: "No action is required." }
    : {
      ok: false,
      code: "RO-CORE-API-INCOMPATIBLE",
      remediation: "Repair or reinstall the matching Research Observatory desktop and Core package.",
    };
}

function parseJson(body: string): unknown {
  if (body.length > 1_048_576) throw new Error("RO-CORE-RESPONSE-INVALID");
  try { return JSON.parse(body) as unknown; } catch { throw new Error("RO-CORE-RESPONSE-INVALID"); }
}

async function requestJson<T>(
  transport: CoreApiTransport,
  request: CoreApiRequest,
  decode: (value: unknown) => T | null,
): Promise<T> {
  return (await requestJsonResponse(transport, request, decode)).value;
}

async function requestJsonResponse<T>(
  transport: CoreApiTransport,
  request: CoreApiRequest,
  decode: (value: unknown) => T | null,
): Promise<{ readonly value: T; readonly response: CoreApiResponse }> {
  const response = await transport(request);
  if (!integer(response.status, 100, 599) || !canonicalTraceId(response.traceId) || typeof response.body !== "string") {
    throw new Error("RO-CORE-RESPONSE-INVALID");
  }
  if (response.status >= 400) {
    if (response.contentType !== "application/problem+json") throw new Error("RO-CORE-RESPONSE-INVALID");
    const value = parseJson(response.body);
    const problem = decodeProblemDetail(value);
    if (!problem || problem.status !== response.status || problem.traceId !== response.traceId) throw new Error("RO-CORE-RESPONSE-INVALID");
    throw new CoreApiClientError(problem);
  }
  if (response.status !== 200 || response.contentType !== "application/json") throw new Error("RO-CORE-RESPONSE-INVALID");
  const value = parseJson(response.body);
  const decoded = decode(value);
  if (!decoded) throw new Error("RO-CORE-RESPONSE-INVALID");
  return { value: decoded, response };
}

function pathOperationId(operationId: string): string {
  if (!canonicalOperationId(operationId)) throw new Error("RO-CORE-REQUEST-INVALID");
  return operationId;
}

function projectBody(value: ProjectRootRequest): string {
  if (!projectRoot(value.root)) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify({ root: value.root });
}

function privacyUpdateBody(command: PrivacyPolicyUpdateRequest): string {
  if (!projectRoot(command.root) || !integer(command.expectedRevision, 0, Number.MAX_SAFE_INTEGER)
    || !privacyNetworkPolicy(command.networkPolicy) || !remoteModelApproval(command.remoteModelApproval)
    || !telemetryMode(command.telemetryMode) || !integer(command.logRetentionDays, 1, 90)
    || !documentRetentionPolicy(command.documentRetention) || !integer(command.cacheRetentionDays, 1, 90)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  if ((command.networkPolicy === "offline" && command.egressConsentToken !== null)
    || (command.networkPolicy !== "offline" && command.egressConsentToken !== "acknowledge-egress-preview-v1")) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify({
    root: command.root, expectedRevision: command.expectedRevision, networkPolicy: command.networkPolicy,
    remoteModelApproval: command.remoteModelApproval, telemetryMode: command.telemetryMode,
    logRetentionDays: command.logRetentionDays, documentRetention: command.documentRetention,
    cacheRetentionDays: command.cacheRetentionDays, egressConsentToken: command.egressConsentToken,
  });
}

function provenanceLineageBody(command: ProvenanceLineageRequest): string {
  if (!projectRoot(command.root) || !canonicalUuid7(command.revisionId)
    || !member(command.direction, ["ancestors", "descendants"] as const)
    || !integer(command.cursor, 0, 10_000) || !integer(command.pageSize, 1, 100)
    || !integer(command.maxDepth, 1, 16)) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify({
    root: command.root,
    revisionId: command.revisionId,
    direction: command.direction,
    cursor: command.cursor,
    pageSize: command.pageSize,
    maxDepth: command.maxDepth,
  });
}

function recalculationPreviewBody(command: RecalculationPreviewRequest): string {
  if (!projectRoot(command.root) || !canonicalUuid7(command.targetRevisionId)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify({ root: command.root, targetRevisionId: command.targetRevisionId });
}

function recalculationScheduleBody(command: RecalculationScheduleRequest): string {
  recalculationPreviewBody(command);
  if (!canonicalUuid7(command.changeId) || !contentHash(command.expectedPlanSha256)
    || !canonicalUuid7(command.intentId) || !canonicalUuid7(command.intentRevisionId)
    || !contentHash(command.intentSha256) || !utcInstant(command.requestedAt)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify({
    root: command.root,
    targetRevisionId: command.targetRevisionId,
    changeId: command.changeId,
    expectedPlanSha256: command.expectedPlanSha256,
    intentId: command.intentId,
    intentRevisionId: command.intentRevisionId,
    intentSha256: command.intentSha256,
    requestedAt: command.requestedAt,
  });
}

function recalculationComparisonBody(command: RecalculationComparisonRequest): string {
  if (!projectRoot(command.root) || !canonicalUuid7(command.beforeRevisionId)
    || !canonicalUuid7(command.afterRevisionId) || command.beforeRevisionId === command.afterRevisionId) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify({
    root: command.root,
    beforeRevisionId: command.beforeRevisionId,
    afterRevisionId: command.afterRevisionId,
  });
}

function recalculationRestoreReviewBody(command: RecalculationRestoreReviewRequest): string {
  recalculationComparisonBody(command);
  if (!canonicalUuid7(command.intentId) || !canonicalUuid7(command.intentRevisionId)
    || !contentHash(command.intentSha256) || !utcInstant(command.requestedAt)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify({
    root: command.root,
    beforeRevisionId: command.beforeRevisionId,
    afterRevisionId: command.afterRevisionId,
    intentId: command.intentId,
    intentRevisionId: command.intentRevisionId,
    intentSha256: command.intentSha256,
    requestedAt: command.requestedAt,
  });
}

function recalculationRestoreBody(command: RecalculationRestoreRequest): string {
  const identities = [
    command.priorAdjudicatedRevisionId,
    command.expectedCurrentRevisionId,
    command.workflowRunId,
    command.humanTaskId,
    command.decisionId,
  ];
  if (!projectRoot(command.root) || !identities.every(canonicalUuid7)
    || command.priorAdjudicatedRevisionId === command.expectedCurrentRevisionId
    || !utcInstant(command.modifiedAt)) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify({
    root: command.root,
    priorAdjudicatedRevisionId: command.priorAdjudicatedRevisionId,
    expectedCurrentRevisionId: command.expectedCurrentRevisionId,
    workflowRunId: command.workflowRunId,
    humanTaskId: command.humanTaskId,
    decisionId: command.decisionId,
    modifiedAt: command.modifiedAt,
  });
}

function intentImpactBody(command: IntentImpactRequest): string {
  if (!projectRoot(command.root) || !integer(command.expectedRevision, 0, Number.MAX_SAFE_INTEGER)
    || (command.egressPolicy !== undefined && command.egressPolicy !== null && !intentEgressPolicy(command.egressPolicy))
    || !member(command.primaryUseCase, INTENT_PRIMARY_USE_CASES)
    || !uniqueMembers(command.sourceKinds, INTENT_SOURCE_KINDS, 32) || !languageCodes(command.languageCodes)
    || (command.startYear !== null && !integer(command.startYear, 1000, 9999))
    || (command.endYear !== null && !integer(command.endYear, 1000, 9999))
    || ((command.startYear === null) !== (command.endYear === null))
    || (typeof command.startYear === "number" && typeof command.endYear === "number" && command.startYear > command.endYear)
    || typeof command.includePrivateReports !== "boolean"
    || (command.noveltyStandard !== null && !member(command.noveltyStandard, INTENT_NOVELTY_STANDARDS))) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify(command);
}

function intentDraftBody(command: IntentDraftRequest): string {
  intentImpactBody(command);
  if (!boundedNarrative(command.researchObjective) || !boundedNarrative(command.contributionIntent)
    || !boundedNarrative(command.phenomenon) || !boundedNarrative(command.unitOfAnalysis)
    || !boundedNarrative(command.levelOfAnalysis) || !uniqueMembers(command.evidenceTypes, INTENT_EVIDENCE_TYPES, 32)
    || !boundedNarrative(command.noveltyRationale) || !member(command.autonomyLevel, INTENT_AUTONOMY_LEVELS)
    || !uniqueMembers(command.stoppingConditions, INTENT_STOPPING_CONDITIONS, 3, 1)
    || !boundedNarrative(command.revisionRationale, 1)
    || (command.impactAcknowledgement !== null && !/^[0-9a-f]{64}$/.test(command.impactAcknowledgement))) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify(command);
}

function intentAcceptBody(command: IntentAcceptRequest): string {
  if (!projectRoot(command.root) || !integer(command.expectedRevision, 1, Number.MAX_SAFE_INTEGER)
    || !contentHash(command.expectedRevisionContentHash) || typeof command.confirmed !== "boolean"
    || !boundedNarrative(command.decisionRationale, 1)) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify(command);
}

function intentPolicyBody(command: IntentPolicyRequest): string {
  if (!projectRoot(command.root) || !member(command.action, INTENT_POLICY_ACTIONS)
    || (command.destinationId !== undefined && command.destinationId !== null
      && (typeof command.destinationId !== "string" || !/^[a-z0-9][a-z0-9._-]{0,99}$/.test(command.destinationId)))
    || !member(command.subjectType, INTENT_POLICY_SUBJECTS)
    || (command.stoppingCondition !== null
      && !member(command.stoppingCondition, INTENT_STOPPING_CONDITIONS))) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify(command);
}

function workflowProgressBody(command: WorkflowProgressCommand): string {
  const hasStagePrecondition = command.expectedStageStateRevisionId !== null
    && command.expectedStageStateRevisionContentHash !== null;
  const hasRevisitSource = command.revisitSourceStageStateRevisionId !== null
    && command.revisitSourceStageStateRevisionContentHash !== null;
  if (!projectRoot(command.root) || !member(command.action, [
    "start", "complete", "mark-attention", "block", "skip", "resume", "revisit", "open-supporting",
  ] as const) || typeof command.stageKey !== "string"
    || !/^[a-z0-9][a-z0-9._-]{0,99}$/.test(command.stageKey)
    || !canonicalUuid7(command.expectedSelectionRevisionId)
    || !contentHash(command.expectedSelectionRevisionContentHash)
    || ((command.expectedStageStateRevisionId === null)
      !== (command.expectedStageStateRevisionContentHash === null))
    || (command.expectedStageStateRevisionId !== null && !canonicalUuid7(command.expectedStageStateRevisionId))
    || (command.expectedStageStateRevisionContentHash !== null
      && !contentHash(command.expectedStageStateRevisionContentHash))
    || ((command.revisitSourceStageStateRevisionId === null)
      !== (command.revisitSourceStageStateRevisionContentHash === null))
    || (command.revisitSourceStageStateRevisionId !== null
      && !canonicalUuid7(command.revisitSourceStageStateRevisionId))
    || (command.revisitSourceStageStateRevisionContentHash !== null
      && !contentHash(command.revisitSourceStageStateRevisionContentHash))
    || !Array.isArray(command.completionEvidenceRevisionIds)
    || command.completionEvidenceRevisionIds.length > 256
    || !command.completionEvidenceRevisionIds.every(canonicalUuid7)
    || new Set(command.completionEvidenceRevisionIds).size !== command.completionEvidenceRevisionIds.length
    || (command.supportingPageContractId !== null
      && (typeof command.supportingPageContractId !== "string"
        || !/^[a-z0-9][a-z0-9-]{0,99}\.html$/.test(command.supportingPageContractId)))
    || (command.rationale !== null && !boundedText(command.rationale, 1, 4000))) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  if ((command.action === "start" && (hasStagePrecondition || hasRevisitSource))
    || (command.action === "revisit" && !hasRevisitSource)
    || (command.action !== "start" && command.action !== "revisit" && !hasStagePrecondition)
    || (command.action !== "revisit" && hasRevisitSource)
    || (command.action === "complete") !== (command.completionEvidenceRevisionIds.length > 0)
    || (command.action === "open-supporting") !== (command.supportingPageContractId !== null)
    || member(command.action, ["mark-attention", "block", "skip"] as const) !== (command.rationale !== null)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return JSON.stringify(command);
}

export function parseOperationEventStream(body: string): readonly OperationProgressEvent[] {
  if (body.length > 1_048_576) throw new Error("RO-CORE-RESPONSE-INVALID");
  if (!body) return [];
  const frames = body.split("\n\n").filter(Boolean);
  if (frames.length > 256) throw new Error("RO-CORE-RESPONSE-INVALID");
  const events: OperationProgressEvent[] = [];
  for (const frame of frames) {
    const lines = frame.split("\n");
    if (lines.length !== 3 || !lines[0]?.startsWith("id: ") || lines[1] !== "event: operation-progress" || !lines[2]?.startsWith("data: ")) {
      throw new Error("RO-CORE-RESPONSE-INVALID");
    }
    const decoded = decodeOperationProgressEvent(parseJson(lines[2].slice(6)));
    if (!decoded || String(decoded.sequence) !== lines[0].slice(4)) throw new Error("RO-CORE-RESPONSE-INVALID");
    if (events.length && decoded.sequence <= (events.at(-1)?.sequence ?? 0)) throw new Error("RO-CORE-RESPONSE-INVALID");
    events.push(decoded);
  }
  return events;
}

const IMPORT_FIELDS = ["title", "doi", "year", "author", "container"];
const IMPORT_RIGHTS = ["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"];
const IMPORT_BODY_BYTES = 900_000;

function importText(value: unknown, maximum: number, minimum = 0): value is string {
  return typeof value === "string" && value.length <= maximum * 2
    && [...value].length >= minimum && [...value].length <= maximum;
}

function importOwned(value: unknown): Readonly<Record<string, unknown>> | null {
  try {
    const owned = record(registryOwnedValue(value));
    return owned && new TextEncoder().encode(JSON.stringify(owned)).length <= IMPORT_BODY_BYTES ? owned : null;
  } catch { return null; }
}

function importDigest(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function importWarnings(value: unknown): boolean {
  return Array.isArray(value) && value.length <= 64 && value.every((item) => typeof item === "string"
    && item.length <= 64 && /^[a-z]+(?:-[a-z]+)*$/.test(item));
}

export function decodeImportPreviewItem(value: unknown): ImportPreviewItem | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "state", "sourceName", "formatName", "encoding", "byteLength", "chunkCount", "jobId", "jobState"])
    || !canonicalUuid7(item.previewId) || !importText(item.sourceName, 255, 1)
    || /[\\/\x00-\x1f\x7f]/.test(item.sourceName as string) || [".", ".."].includes(item.sourceName as string)
    || !registryEnum(item.formatName, ["ris", "bibtex", "csl-json", "doi-list", "csv"])
    || !registryEnum(item.encoding, ["utf-8", "cp1252"])
    || item.formatName === "csl-json" && item.encoding !== "utf-8"
    || !registryEnum(item.state, ["created", "source-sealed", "parse-started", "parse-completed", "draft-revised", "cancelled", "failed", "security-interrupted"])
    || !integer(item.byteLength, 0, 268435456) || !integer(item.chunkCount, 0, 2048)
    || (item.jobId === null ? item.jobState !== null : !canonicalUuid7(item.jobId)
      || !registryEnum(item.jobState, ["runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded"]))) return null;
  return item as unknown as ImportPreviewItem;
}

export function decodeImportPreviewPage(value: unknown): ImportPreviewPage | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["items", "nextAfter", "complete"]) || !Array.isArray(item.items) || item.items.length > 25
    || typeof item.complete !== "boolean" || item.nextAfter !== null && !canonicalUuid7(item.nextAfter)
    || !item.complete && item.nextAfter === null) return null;
  let previous: string | null = null;
  for (const entry of item.items) {
    const preview = decodeImportPreviewItem(entry);
    if (!preview || previous !== null && preview.previewId <= previous || item.nextAfter === null || preview.previewId > (item.nextAfter as string)) return null;
    previous = preview.previewId;
  }
  return item as unknown as ImportPreviewPage;
}

export function decodeReviewSummary(value: unknown): ReviewSummary | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "revision", "predecessorRevision", "attemptId", "recordCount",
    "mappingId", "mappingRevision", "mappingHighWater", "mappingMode", "rights", "options", "delimiter", "undoTargetRevision"])
    || !canonicalUuid7(item.previewId) || !canonicalUuid7(item.attemptId) || !canonicalUuid7(item.mappingId)
    || !integer(item.revision, 1, 2147483647) || item.predecessorRevision !== (item.revision === 1 ? null : item.revision - 1)
    || !integer(item.recordCount, 0, 200000) || !integer(item.mappingRevision, 1, 2147483647)
    || !integer(item.mappingHighWater, item.mappingRevision, 2147483647)
    || !member(item.delimiter, [",", "\t", ";"] as const)
    || (item.undoTargetRevision !== null && !integer(item.undoTargetRevision, 1, (item.revision as number) - 1))
    || !registryEnum(item.mappingMode, ["automatic", "columns"])) return null;
  const rights = record(item.rights), options = record(item.options);
  if (!rights || !exactKeys(rights, IMPORT_RIGHTS) || !IMPORT_RIGHTS.every((name) => {
    const right = record(rights[name]);
    return right && exactKeys(right, ["value", "basis"]) && registryEnum(right.value, ["unknown", "permitted", "denied"])
      && registryEnum(right.basis, ["not-reported", "researcher-confirmed"])
      && (right.value === "unknown" || right.basis === "researcher-confirmed");
  }) || !options || !exactKeys(options, ["duplicatePolicy", "malformedPolicy"])
    || options.duplicatePolicy !== "review" || options.malformedPolicy !== "exclude-and-report") return null;
  return item as unknown as ReviewSummary;
}

export function decodeReviewPage(value: unknown): ReviewPage | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["revision", "records", "nextAfter", "complete"])
    || !integer(item.revision, 1, 2147483647) || !integer(item.nextAfter, 0, 200000) || typeof item.complete !== "boolean"
    || !Array.isArray(item.records) || item.records.length > 100 || (!item.complete && item.records.length === 0)) return null;
  let previous = 0;
  const short = (value: unknown): boolean => {
    if (value === null) return true;
    const text = record(value);
    return !!text && exactKeys(text, ["text", "truncated"]) && importText(text.text, 256, 1) && typeof text.truncated === "boolean";
  };
  for (const value of item.records) {
    const row = record(value);
    if (!row || !exactKeys(row, ["ordinal", "recordKey", "kind", "status", "included", "title", "doi", "fieldCount", "warnings"])
      || !integer(row.ordinal, 1, 200000) || previous !== 0 && row.ordinal !== previous + 1
      || !importDigest(row.recordKey) || !registryEnum(row.kind, ["record", "header", "directive"])
      || !registryEnum(row.status, ["parsed", "malformed"]) || typeof row.included !== "boolean"
      || row.included && (row.kind !== "record" || row.status !== "parsed")
      || !integer(row.fieldCount, 0, 4096) || !short(row.title) || !short(row.doi) || !importWarnings(row.warnings)) return null;
    previous = row.ordinal;
  }
  if (item.records.length && item.nextAfter !== previous) return null;
  return item as unknown as ReviewPage;
}

export function decodeImportSummaryStatus(value: unknown): ImportSummaryStatus | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "revision", "algorithm", "jobId", "jobState", "diagnosticCode", "counts"])
    || !canonicalUuid7(item.previewId) || !integer(item.revision, 1, 2147483647) || item.algorithm !== "draft-summary/1"
    || (item.diagnosticCode !== null && (typeof item.diagnosticCode !== "string" || !/^[a-z][a-z0-9.-]{0,95}$/.test(item.diagnosticCode)))
    || (item.jobId === null ? item.jobState !== null || item.diagnosticCode !== null || item.counts !== null
      : !canonicalUuid7(item.jobId) || !registryEnum(item.jobState, ["runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded"]))) return null;
  if (item.counts !== null) {
    const c = record(item.counts), coverage = c && record(c.coverage);
    const keys = ["sourceRows", "recordRows", "contextRows", "malformedRows", "includedRecords", "excludedRecords", "warningRows", "warningCount", "coverage", "rawDuplicateGroups", "doiDuplicateGroups", "candidateRecords"];
    if (item.jobState !== "succeeded" || !c || !exactKeys(c, keys) || !coverage || !exactKeys(coverage, IMPORT_FIELDS)
      || !keys.filter((key) => key !== "coverage").every((key) => integer(c[key], 0, key === "warningCount" ? 12800000 : 200000))) return null;
    const counts = c as unknown as SummaryCounts;
    if (counts.recordRows + counts.contextRows !== counts.sourceRows || counts.includedRecords + counts.excludedRecords !== counts.recordRows
      || counts.malformedRows > counts.sourceRows - counts.includedRecords || counts.warningRows > counts.sourceRows
      || counts.warningCount < counts.warningRows || counts.warningCount > 64 * counts.warningRows
      || !IMPORT_FIELDS.every((key) => integer(coverage[key], 0, counts.includedRecords))
      || counts.candidateRecords > counts.includedRecords || counts.candidateRecords === 1
      || Boolean(counts.rawDuplicateGroups || counts.doiDuplicateGroups) !== Boolean(counts.candidateRecords)
      || Math.max(counts.rawDuplicateGroups, counts.doiDuplicateGroups) * 2 > counts.candidateRecords) return null;
  }
  return item as unknown as ImportSummaryStatus;
}

export function decodeImportManifest(value: unknown): ImportManifestView | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["projectId", "revisionId", "aggregateId", "previewId", "draftRevision", "sourceSha256", "identitySha256", "effectiveDraftSha256", "parserVersion", "mappingId", "mappingRevision", "previousManifestRevisionId", "recordCount", "selectedCount", "createdCount", "reusedCount", "membersSha256", "createdAt"])
    || !(canonicalProjectId(item.projectId) || canonicalUuid7(item.projectId))
    || ![item.revisionId, item.aggregateId, item.previewId, item.mappingId].every(canonicalUuid7)
    || !integer(item.draftRevision, 1, 2147483647) || !integer(item.mappingRevision, 1, 2147483647)
    || ![item.sourceSha256, item.identitySha256, item.effectiveDraftSha256, item.membersSha256].every(importDigest)
    || !importText(item.parserVersion, 96, 1) || item.previousManifestRevisionId !== null && !canonicalUuid7(item.previousManifestRevisionId)
    || ![item.recordCount, item.selectedCount, item.createdCount, item.reusedCount].every((value) => integer(value, 0, 200000))
    || typeof item.createdAt !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(item.createdAt) || !Number.isFinite(Date.parse(item.createdAt))) return null;
  const manifest = item as unknown as ImportManifestView;
  return manifest.selectedCount <= manifest.recordCount && manifest.createdCount + manifest.reusedCount === manifest.selectedCount ? manifest : null;
}

export function decodeImportCommitStatus(value: unknown): ImportCommitStatus | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "requestId", "jobId", "jobState", "diagnosticCode", "manifest"])
    || !canonicalUuid7(item.previewId) || !canonicalUuid7(item.requestId)
    || item.diagnosticCode !== null && (typeof item.diagnosticCode !== "string" || !/^[a-z][a-z0-9.-]{0,95}$/.test(item.diagnosticCode))
    || (item.jobId === null ? item.jobState !== null || item.diagnosticCode !== null
      : !canonicalUuid7(item.jobId) || !registryEnum(item.jobState, ["runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded"]))
    || (item.jobState === "succeeded" ? !decodeImportManifest(item.manifest) : item.manifest !== null)) return null;
  return item as unknown as ImportCommitStatus;
}

export function decodeImportManifestPage(value: unknown): ImportManifestPage | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "revisionId", "records", "nextAfter", "complete"])
    || !canonicalUuid7(item.previewId) || !canonicalUuid7(item.revisionId) || !integer(item.nextAfter, 0, 200000)
    || typeof item.complete !== "boolean" || !Array.isArray(item.records) || item.records.length > 100 || !item.complete && !item.records.length) return null;
  let previous = 0;
  for (const value of item.records) {
    const row = record(value);
    if (!row || !exactKeys(row, ["ordinal", "recordKey", "included", "sourceRecordRevisionId", "warnings", "comparison", "previousRecordRevisionId"])
      || !integer(row.ordinal, 1, 200000) || previous !== 0 && row.ordinal !== previous + 1 || !importDigest(row.recordKey)
      || typeof row.included !== "boolean" || (row.included ? !canonicalUuid7(row.sourceRecordRevisionId) : row.sourceRecordRevisionId !== null)
      || !Array.isArray(row.warnings) || row.warnings.length > 64 || !row.warnings.every((value) => importText(value, 96))
      || !registryEnum(row.comparison, ["not-compared", "added", "unchanged", "updated", "ambiguous"])
      || (["unchanged", "updated"].includes(row.comparison as string) ? !canonicalUuid7(row.previousRecordRevisionId) : row.previousRecordRevisionId !== null)) return null;
    previous = row.ordinal;
  }
  if (item.records.length && item.nextAfter !== previous) return null;
  return item as unknown as ImportManifestPage;
}

export function decodeImportDuplicateGroups(value: unknown): ImportDuplicateGroups | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "revision", "reason", "groups", "nextAfter", "complete"])
    || !canonicalUuid7(item.previewId) || !integer(item.revision, 1, 2147483647) || !registryEnum(item.reason, ["raw", "doi"])
    || !Array.isArray(item.groups) || item.groups.length > 100 || typeof item.complete !== "boolean"
    || item.nextAfter !== null && !importDigest(item.nextAfter) || !item.complete && !item.groups.length) return null;
  let previous = "";
  for (const value of item.groups) {
    const group = record(value);
    if (!group || !exactKeys(group, ["groupKey", "memberCount", "firstOrdinal"]) || !importDigest(group.groupKey)
      || (group.groupKey as string) <= previous || !integer(group.memberCount, 2, 200000) || !integer(group.firstOrdinal, 1, 200000)) return null;
    previous = group.groupKey as string;
  }
  if (item.groups.length && item.nextAfter !== previous) return null;
  return item as unknown as ImportDuplicateGroups;
}

export function decodeImportDuplicateMembers(value: unknown): ImportDuplicateMembers | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["previewId", "revision", "reason", "groupKey", "records", "nextAfter", "complete"])
    || !canonicalUuid7(item.previewId) || !integer(item.revision, 1, 2147483647) || !registryEnum(item.reason, ["raw", "doi"])
    || !importDigest(item.groupKey) || !Array.isArray(item.records) || item.records.length > 100
    || !integer(item.nextAfter, 0, 200000) || typeof item.complete !== "boolean" || !item.complete && !item.records.length) return null;
  let previous = 0;
  for (const value of item.records) {
    const row = record(value);
    if (!row || !integer(row.ordinal, previous + 1, 200000) || !row.included
      || !decodeReviewPage({ revision: item.revision, records: [row], nextAfter: row.ordinal, complete: true })) return null;
    previous = row.ordinal as number;
  }
  if (item.records.length && item.nextAfter !== previous) return null;
  return item as unknown as ImportDuplicateMembers;
}

export function decodeReviewDetail(value: unknown): ReviewDetail | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["revision", "ordinal", "recordKey", "section", "fields", "nextIndex", "complete"])
    || !integer(item.revision, 1, 2147483647) || !integer(item.ordinal, 1, 200000) || !importDigest(item.recordKey)
    || !registryEnum(item.section, ["raw", "candidates", "effective"]) || !integer(item.nextIndex, 0, 4096)
    || typeof item.complete !== "boolean" || !Array.isArray(item.fields) || item.fields.length > 100
    || (!item.complete && item.fields.length === 0)) return null;
  let previous = -1;
  for (const value of item.fields) {
    const field = record(value);
    if (!field || !exactKeys(field, ["index", "name", "value", "sourceFieldIndex", "origin", "target", "warnings"])
      || !integer(field.index, 0, 4095) || previous >= 0 && field.index !== previous + 1
      || !importText(field.name, 65536) || !importText(field.value, 65536)
      || !registryEnum(field.origin, ["raw", "candidate", "mapping", "correction"])
      || !importWarnings(field.warnings) || field.target !== null && !registryEnum(field.target, IMPORT_FIELDS)
      || (field.origin === "correction" ? field.sourceFieldIndex !== null : !integer(field.sourceFieldIndex, 0, 4095))
      || (item.section === "raw" ? field.origin !== "raw" || field.sourceFieldIndex !== field.index
        : field.origin === "raw" || field.target !== null || !registryEnum(field.name, IMPORT_FIELDS))
      || item.section === "candidates" && field.origin !== "candidate") return null;
    previous = field.index;
  }
  if (item.fields.length && item.nextIndex !== previous + 1) return null;
  return item as unknown as ReviewDetail;
}

export function decodeDiagnosticPage(value: unknown): DiagnosticPage | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["revision", "csv", "nextAfter", "complete"])
    || !integer(item.revision, 1, 2147483647) || !integer(item.nextAfter, 0, 200000) || typeof item.complete !== "boolean"
    || !importText(item.csv, IMPORT_BODY_BYTES)) return null;
  const csv = item.csv.replace(/^ordinal,line_start,line_end,status,diagnostic\r\n/, "");
  if (csv && !csv.endsWith("\r\n")) return null;
  let previous = 0;
  for (const line of csv.split("\r\n").slice(0, -1)) {
    if (!/^[1-9][0-9]*,[1-9][0-9]*,[1-9][0-9]*,(parsed|malformed),[a-z]+(?:-[a-z]+)*$/.test(line)) return null;
    const ordinal = Number(line.split(",")[0]);
    if (!integer(ordinal, 1, 200000) || ordinal < previous || previous && ordinal > previous + 1) return null;
    previous = ordinal;
  }
  if (previous && item.nextAfter !== previous || !item.complete && !previous) return null;
  return item as unknown as DiagnosticPage;
}

function importBody(value: unknown): string {
  const item = importOwned(value);
  if (!item || !projectRoot(item.root) || !canonicalUuid7(item.previewId)) throw new Error("RO-CORE-REQUEST-INVALID");
  return JSON.stringify(item);
}

function importCommand<T extends ImportAddress>(value: T): T & Readonly<Record<string, unknown>> {
  const owned = importOwned(value);
  if (!owned || !projectRoot(owned.root) || !canonicalUuid7(owned.previewId)) throw new Error("RO-CORE-REQUEST-INVALID");
  return owned as unknown as T & Readonly<Record<string, unknown>>;
}

function importPageBody(command: ImportPageRequest): string {
  if (!integer(command.revision, 1, 2147483647) || !integer(command.after, 0, 200000) || !integer(command.limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
  return importBody({ root: command.root, previewId: command.previewId, revision: command.revision, after: command.after, limit: command.limit });
}

async function importSummaryCall(transport: CoreApiTransport, route: "summary" | "summary/start" | "summary/cancel", value: ImportSummaryRequest | ImportSummaryCancelRequest): Promise<ImportSummaryStatus> {
  const command = importCommand(value);
  if (!exactKeys(command, route === "summary/cancel" ? ["root", "previewId", "revision", "jobId"] : ["root", "previewId", "revision"])
    || !integer(command.revision, 1, 2147483647) || route === "summary/cancel" && !canonicalUuid7((command as ImportSummaryCancelRequest).jobId)) throw new Error("RO-CORE-REQUEST-INVALID");
  const result = await requestJson(transport, { method: "POST", path: `/projects/imports/${route}`, body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportSummaryStatus);
  if (result.previewId !== command.previewId || result.revision !== command.revision) throw new Error("RO-CORE-RESPONSE-INVALID");
  return result;
}

async function importCommitCall(transport: CoreApiTransport, route: "status" | "start" | "cancel", value: ImportCommitRequest | ImportCommitStartRequest | ImportCommitCancelRequest): Promise<ImportCommitStatus> {
  const command = importCommand(value);
  const keys = ["root", "previewId", "requestId", ...(route === "start" ? ["revision", "previousManifestRevisionId"] : route === "cancel" ? ["jobId"] : [])];
  if (!exactKeys(command, keys) || !canonicalUuid7(command.requestId)
    || route === "start" && (!integer(command.revision, 1, 2147483647) || command.previousManifestRevisionId !== null && !canonicalUuid7(command.previousManifestRevisionId))
    || route === "cancel" && !canonicalUuid7(command.jobId)) throw new Error("RO-CORE-REQUEST-INVALID");
  const result = await requestJson(transport, { method: "POST", path: `/projects/imports/commit/${route}`, body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportCommitStatus);
  if (result.previewId !== command.previewId || result.requestId !== command.requestId || route === "cancel" && result.jobId !== command.jobId) throw new Error("RO-CORE-RESPONSE-INVALID");
  return result;
}

export const SCHOLARLY_PROVIDER_TERMS = Object.freeze({
  openalex: "https://help.openalex.org/", crossref: "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
  unpaywall: "https://data.unpaywall.org/products/api", "semantic-scholar": "https://www.semanticscholar.org/product/api",
});

export function decodeConnectorCapabilities(value: unknown): ConnectorCapabilitiesPage | null {
  const page = importOwned(value);
  if (!page || !exactKeys(page, ["items"]) || !Array.isArray(page.items) || page.items.length > 32) return null;
  const providers = new Set<string>();
  for (const raw of page.items) {
    const item = record(raw);
    if (!item || !exactKeys(item, ["schemaVersion", "providerId", "adapterVersion", "sourceApiVersion", "operations", "identifierSchemes", "maximumPageSize", "configuration", "requiredSettings"])
      || item.schemaVersion !== "1.0" || typeof item.providerId !== "string" || !/^[a-z][a-z0-9.-]{0,127}$/.test(item.providerId)
      || providers.has(item.providerId) || typeof item.adapterVersion !== "string" || !semver(item.adapterVersion)
      || item.sourceApiVersion !== null && (typeof item.sourceApiVersion !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$/.test(item.sourceApiVersion))
      || !integer(item.maximumPageSize, 1, 1000) || !["ready", "not-configured", "unavailable"].includes(item.configuration as string)
      || !Array.isArray(item.operations) || !item.operations.length || item.operations.length > 5
      || !item.operations.every((v) => ["search", "lookup", "citations", "recommendations", "oa-resolution"].includes(v))
      || new Set(item.operations).size !== item.operations.length
      || !Array.isArray(item.identifierSchemes) || item.identifierSchemes.length > 32 || !item.identifierSchemes.every((v) => typeof v === "string" && /^[a-z][a-z0-9.-]{0,127}$/.test(v))
      || !Array.isArray(item.requiredSettings) || item.requiredSettings.length > 2 || !item.requiredSettings.every((v) => v === "contact" || v === "provider-key")) return null;
    providers.add(item.providerId);
  }
  return page as unknown as ConnectorCapabilitiesPage;
}

export function sourceTestCommand(root: string, projectId: string, provider: ConnectorCapabilities, doi: string, invocationId: string): ConnectorPreviewRequest {
  const decoded = decodeConnectorCapabilities({ items: [provider] })?.items[0];
  if (!decoded || decoded.configuration !== "ready" || !projectRoot(root) || !canonicalProjectId(projectId)
    || !canonicalUuid7(invocationId) || !["openalex", "crossref", "unpaywall", "semantic-scholar"].includes(decoded.providerId)
    || !/^10\.[0-9]{4,9}\/[^\s\u0000-\u001f\u007f]+$/i.test(doi) || doi.length > 2048) throw new Error("RO-CORE-REQUEST-INVALID");
  const rights = Object.fromEntries(["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"].map((action) => [action,
    action === "store" || action === "inspect" ? { value: "permitted", basis: "researcher-confirmed" } : { value: "unknown", basis: "not-reported" }])) as unknown as ImportRights;
  const identifier = { scheme: "doi", value: doi };
  return { root, request: { schemaVersion: "1.0", projectId, invocationId, providerId: decoded.providerId,
    adapterVersion: decoded.adapterVersion, sourceApiVersion: decoded.sourceApiVersion, pageSize: 1, cursor: null,
    query: decoded.providerId === "unpaywall" ? { kind: "oa-resolution", identifier } : { kind: "lookup", identifiers: [identifier] },
    policy: { maxInflight: 1, minimumIntervalMs: 1000, maximumAttempts: 1, timeoutMs: 10000, maximumResponseBytes: 2097152,
      maximumRetryAfterMs: 10000, cacheMode: "bypass", maximumFreshAgeMs: 0, rawRetention: "if-permitted" } },
    retention: { rights, retainBody: true, permittedFields: [] } };
}

function connectorJob(value: unknown): ConnectorJobStatus | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["jobId", "workflowRunId", "state", "diagnosticCode"]) || !canonicalUuid7(item.jobId) || !canonicalUuid7(item.workflowRunId)
    || !["runnable", "claimed", "running", "retry-scheduled", "cancelling", "cancelled", "failed", "succeeded"].includes(item.state as string)
    || item.diagnosticCode !== null && (typeof item.diagnosticCode !== "string" || !/^[a-zA-Z0-9-]{1,96}$/.test(item.diagnosticCode))) return null;
  return item as unknown as ConnectorJobStatus;
}

function connectorPreview(value: unknown, command: ConnectorPreviewRequest): ConnectorPreview | null {
  const item = importOwned(value);
  const hosts: Record<string, string> = { openalex: "api.openalex.org", crossref: "api.crossref.org", unpaywall: "api.unpaywall.org", "semantic-scholar": "api.semanticscholar.org" };
  if (!item || !exactKeys(item, ["previewId", "request", "requestSha256", "destinationHost", "retention", "terms", "intentRevisionId", "intentSha256", "policySha256", "expiresAt", "confirmation"])
    || !canonicalUuid7(item.previewId) || !canonicalUuid7(item.intentRevisionId) || !contentHash(item.requestSha256) || !contentHash(item.intentSha256) || !contentHash(item.policySha256)
    || !utcInstant(item.expiresAt) || typeof item.confirmation !== "string" || item.confirmation.length < 1 || item.confirmation.length > 128
    || item.destinationHost !== hosts[command.request.providerId]
    || canonicalContractJson(item.request) !== canonicalContractJson(command.request)
    || canonicalContractJson(item.retention) !== canonicalContractJson(command.retention)) return null;
  const terms = record(item.terms);
  if (!terms || !exactKeys(terms, ["access", "license", "terms"]) || !["open", "closed", "unknown", "not-reported"].includes(terms.access as string)) return null;
  for (const raw of [terms.license, terms.terms]) {
    const observation = record(raw);
    if (!observation || !exactKeys(observation, ["state", "value"]) || !["reported", "not-reported", "unknown", "not-applicable"].includes(observation.state as string)
      || (observation.state === "reported" ? !importText(observation.value, 8192, 1) : observation.value !== null)) return null;
  }
  return item as unknown as ConnectorPreview;
}

async function sourceJobCall(transport: CoreApiTransport, route: "status" | "cancel", command: ConnectorJobRequest): Promise<ConnectorJobStatus> {
  if (!projectRoot(command.root) || !canonicalUuid7(command.jobId)) throw new Error("RO-CORE-REQUEST-INVALID");
  const result = await requestJson(transport, { method: "POST", path: `/projects/connectors/jobs/${route}`,
    body: JSON.stringify({ root: command.root, jobId: command.jobId }), ifMatch: null, idempotencyKey: null }, connectorJob);
  if (result.jobId !== command.jobId) throw new Error("RO-CORE-RESPONSE-INVALID");
  return result;
}

function connectorRun(value: unknown): ConnectorRunSummary | null {
  const item = record(value);
  if (!item || !exactKeys(item, ["previewId", "invocationId", "jobId", "workflowRunId", "providerId", "operation", "state", "updatedAt", "diagnosticCode"])
    || !canonicalUuid7(item.previewId) || !canonicalUuid7(item.invocationId) || !utcInstant(item.updatedAt)
    || !["openalex", "crossref", "semantic-scholar", "unpaywall"].includes(item.providerId as string)
    || !["search", "lookup", "citations", "recommendations", "oa-resolution"].includes(item.operation as string)
    || !connectorJob({ jobId: item.jobId, workflowRunId: item.workflowRunId, state: item.state, diagnosticCode: item.diagnosticCode })) return null;
  return item as unknown as ConnectorRunSummary;
}

export function decodeConnectorRecentRuns(value: unknown): ConnectorRecentRuns | null {
  const page = importOwned(value);
  if (!page || !exactKeys(page, ["items", "scope"]) || page.scope !== "latest-20-source-jobs-within-100-workflows"
    || !Array.isArray(page.items) || page.items.length > 20 || !page.items.every(connectorRun)
    || new Set(page.items.map((item) => item.previewId)).size !== page.items.length) return null;
  return page as unknown as ConnectorRecentRuns;
}

function sourceIdentifier(value: unknown): boolean {
  const item = record(value);
  return !!item && exactKeys(item, ["scheme", "value"]) && typeof item.scheme === "string" && /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(item.scheme) && item.scheme.length <= 128 && importText(item.value, 4096, 1);
}
function sourceTerms(value: unknown): boolean {
  const item = record(value);
  if (!item || !exactKeys(item, ["license", "terms", "access"]) || !["open", "closed", "unknown", "not-reported"].includes(item.access as string)) return false;
  return [item.license, item.terms].every((raw) => {
    const field = record(raw);
    return field && exactKeys(field, ["state", "value"]) && ["reported", "unknown", "not-reported", "not-applicable"].includes(field.state as string)
      && (field.state === "reported" ? importText(field.value, 65536, 1) : field.value === null);
  });
}

export function decodeConnectorInspection(value: unknown): ConnectorInspection | null {
  const item = importOwned(value);
  if (!item || !exactKeys(item, ["job", "queryJson", "scientificRequestSha256", "observation", "recordOffset", "nextRecordOffset"])
    || !connectorRun(item.job) || !importText(item.queryJson, 262144, 1) || !contentHash(item.scientificRequestSha256)
    || !integer(item.recordOffset, 0, 999) || item.nextRecordOffset !== null && item.nextRecordOffset !== (item.recordOffset as number) + 1) return null;
  const job = item.job as ConnectorRunSummary;
  try { if (record(JSON.parse(item.queryJson as string))?.kind !== job.operation) return null; } catch { return null; }
  if (item.observation === null) {
    if (item.recordOffset !== 0 || item.nextRecordOffset !== null) return null;
  } else {
    const page = record(item.observation);
    if (!page || !exactKeys(page, ["observationId", "observedAt", "retrievedAt", "outcome", "continuation", "recordCount", "records", "fieldProjection"])
      || !canonicalUuid7(page.observationId) || !utcInstant(page.observedAt) || page.retrievedAt !== null && !utcInstant(page.retrievedAt)
      || !["complete", "partial", "failed"].includes(page.outcome as string) || !["exhausted", "next-page", "retry-current", "unavailable"].includes(page.continuation as string)
      || !integer(page.recordCount, 0, 1000) || !Array.isArray(page.records) || page.records.length !== (page.recordCount ? 1 : 0)
      || (item.recordOffset as number) >= Math.max(1, page.recordCount as number)
      || item.nextRecordOffset !== ((item.recordOffset as number) + 1 < (page.recordCount as number) ? (item.recordOffset as number) + 1 : null)
      || page.fieldProjection !== "title-oa-locations-discovery") return null;
    for (const raw of page.records) {
      const row = record(raw);
      if (!row || !exactKeys(row, ["providerId", "rawIdentifier", "identifiers", "retrievedAt", "fields", "terms"])
        || row.providerId !== job.providerId || row.retrievedAt !== page.retrievedAt || !sourceIdentifier(row.rawIdentifier)
        || !Array.isArray(row.identifiers) || row.identifiers.length > 64 || !row.identifiers.every(sourceIdentifier)
        || !sourceTerms(row.terms) || !Array.isArray(row.fields) || row.fields.length > 3) return null;
      const names = new Set<string>();
      for (const entry of row.fields) {
        const field = record(entry);
        if (!field || !exactKeys(field, ["namespace", "name", "encoding", "value"]) || field.namespace !== job.providerId
          || !["candidate.title", "candidate.oa-locations", "candidate.discovery"].includes(field.name as string) || names.has(field.name as string)
          || !["text", "json"].includes(field.encoding as string) || !importText(field.value, 65536, 0)) return null;
        names.add(field.name as string);
        if (field.encoding === "json") { try { JSON.parse(field.value as string); } catch { return null; } }
      }
    }
  }
  return item as unknown as ConnectorInspection;
}

export function createCoreApiClient(transport: CoreApiTransport) {
  return Object.freeze({
    async recentSourceRequests(command: ConnectorProjectRequest): Promise<ConnectorRecentRuns> {
      if (!projectRoot(command.root)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, { method: "POST", path: "/projects/connectors/recent", body: JSON.stringify({ root: command.root }), ifMatch: null, idempotencyKey: null }, decodeConnectorRecentRuns);
    },
    async inspectSourceRequest(command: ConnectorInspectionRequest): Promise<ConnectorInspection | null> {
      if (!projectRoot(command.root) || !canonicalUuid7(command.previewId) || !integer(command.recordOffset, 0, 999)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/connectors/inspect", body: JSON.stringify({ root: command.root, previewId: command.previewId, recordOffset: command.recordOffset }), ifMatch: null, idempotencyKey: null }, (value) => {
        if (value === null) return { inspection: null };
        const inspection = decodeConnectorInspection(value);
        return inspection ? { inspection } : null;
      });
      if (result.inspection && (result.inspection.job.previewId !== command.previewId || result.inspection.recordOffset !== command.recordOffset)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.inspection;
    },
    async connectorCapabilities(): Promise<ConnectorCapabilitiesPage> {
      return await requestJson(transport, { method: "GET", path: "/projects/connectors/capabilities", body: null, ifMatch: null, idempotencyKey: null }, decodeConnectorCapabilities);
    },
    async previewSourceTest(command: ConnectorPreviewRequest): Promise<ConnectorPreview> {
      const owned = importOwned(command);
      if (!owned || !exactKeys(owned, ["root", "request", "retention"]) || !projectRoot(owned.root)) throw new Error("RO-CORE-REQUEST-INVALID");
      const snapshot = owned as unknown as ConnectorPreviewRequest;
      return await requestJson(transport, { method: "POST", path: "/projects/connectors/previews", body: JSON.stringify(snapshot), ifMatch: null, idempotencyKey: null }, (value) => connectorPreview(value, snapshot));
    },
    async confirmSourceTest(command: ConnectorConfirmationRequest): Promise<ConnectorJobStatus> {
      if (!projectRoot(command.root) || !canonicalUuid7(command.previewId) || typeof command.confirmation !== "string" || !command.confirmation.length || command.confirmation.length > 128) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, { method: "POST", path: "/projects/connectors/confirmations", body: JSON.stringify({ root: command.root, previewId: command.previewId, confirmation: command.confirmation }), ifMatch: null, idempotencyKey: null }, connectorJob);
    },
    async sourceTestStatus(command: ConnectorJobRequest): Promise<ConnectorJobStatus> { return await sourceJobCall(transport, "status", command); },
    async cancelSourceTest(command: ConnectorJobRequest): Promise<ConnectorJobStatus> { return await sourceJobCall(transport, "cancel", command); },
    async latestImportCommit(value: ImportAddress): Promise<ImportCommitStatus | null> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId"])) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/commit/latest", body: importBody(command), ifMatch: null, idempotencyKey: null }, (value) => {
        if (value === null) return { status: null };
        const status = decodeImportCommitStatus(value);
        return status ? { status } : null;
      });
      if (result.status && result.status.previewId !== command.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.status;
    },
    async prepareImportCommit(value: ImportCommitPrepareRequest): Promise<ImportCommitStatus> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId", "revision", "previousManifestRevisionId"]) || !integer(command.revision, 1, 2147483647)
        || command.previousManifestRevisionId !== null && !canonicalUuid7(command.previousManifestRevisionId)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/commit/prepare", body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportCommitStatus);
      if (result.previewId !== command.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importCommitStatus(value: ImportCommitRequest): Promise<ImportCommitStatus> { return importCommitCall(transport, "status", value); },
    async startImportCommit(value: ImportCommitStartRequest): Promise<ImportCommitStatus> { return importCommitCall(transport, "start", value); },
    async cancelImportCommit(value: ImportCommitCancelRequest): Promise<ImportCommitStatus> { return importCommitCall(transport, "cancel", value); },
    async importManifest(value: ImportManifestRequest): Promise<ImportManifestView | null> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId", "revisionId"]) || command.revisionId !== null && !canonicalUuid7(command.revisionId)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/manifest", body: importBody(command), ifMatch: null, idempotencyKey: null }, (value) => {
        if (value === null) return { manifest: null };
        const manifest = decodeImportManifest(value);
        return manifest ? { manifest } : null;
      });
      if (result.manifest && (result.manifest.previewId !== command.previewId || command.revisionId !== null && result.manifest.revisionId !== command.revisionId)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.manifest;
    },
    async importManifestMembers(value: ImportManifestPageRequest): Promise<ImportManifestPage> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId", "revisionId", "after", "limit"]) || !canonicalUuid7(command.revisionId)
        || !integer(command.after, 0, 200000) || !integer(command.limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/manifest/members", body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportManifestPage);
      if (result.previewId !== command.previewId || result.revisionId !== command.revisionId || result.records.length > command.limit
        || (result.records.length ? result.records[0]!.ordinal !== command.after + 1 : result.nextAfter !== command.after)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importSummary(value: ImportSummaryRequest): Promise<ImportSummaryStatus> { return importSummaryCall(transport, "summary", value); },
    async startImportSummary(value: ImportSummaryRequest): Promise<ImportSummaryStatus> { return importSummaryCall(transport, "summary/start", value); },
    async cancelImportSummary(value: ImportSummaryCancelRequest): Promise<ImportSummaryStatus> { return importSummaryCall(transport, "summary/cancel", value); },
    async importDuplicateGroups(value: ImportDuplicateGroupsRequest): Promise<ImportDuplicateGroups> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId", "revision", "reason", "after", "limit"]) || !integer(command.revision, 1, 2147483647)
        || !registryEnum(command.reason, ["raw", "doi"]) || command.after !== null && !importDigest(command.after) || !integer(command.limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/summary/groups", body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportDuplicateGroups);
      if (result.previewId !== command.previewId || result.revision !== command.revision || result.reason !== command.reason || result.groups.length > command.limit
        || (result.groups.length ? result.groups[0]!.groupKey <= (command.after ?? "") : result.nextAfter !== command.after)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importDuplicateMembers(value: ImportDuplicateMembersRequest): Promise<ImportDuplicateMembers> {
      const command = importCommand(value);
      if (!exactKeys(command, ["root", "previewId", "revision", "reason", "groupKey", "after", "limit"]) || !integer(command.revision, 1, 2147483647)
        || !registryEnum(command.reason, ["raw", "doi"]) || !importDigest(command.groupKey) || !integer(command.after, 0, 200000) || !integer(command.limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/summary/members", body: importBody(command), ifMatch: null, idempotencyKey: null }, decodeImportDuplicateMembers);
      if (result.previewId !== command.previewId || result.revision !== command.revision || result.reason !== command.reason || result.groupKey !== command.groupKey
        || result.records.length > command.limit || (result.records.length ? result.records[0]!.ordinal <= command.after : result.nextAfter !== command.after)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importPreviews(value: ImportListRequest): Promise<ImportPreviewPage> {
      const command = importOwned(value);
      if (!command || !exactKeys(command, ["root", "after", "limit"]) || !projectRoot(command.root)
        || command.after !== null && !canonicalUuid7(command.after) || !integer(command.limit, 1, 25)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/list",
        body: JSON.stringify(command), ifMatch: null, idempotencyKey: null }, decodeImportPreviewPage);
      if (result.items.length > command.limit || command.after !== null && (
        result.nextAfter === null || result.nextAfter < (command.after as string)
        || !result.complete && result.nextAfter === command.after
        || result.items.some((item) => item.previewId <= (command.after as string)))) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importPreviewStatus(value: ImportAddress): Promise<ImportPreviewItem> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/status",
        body: importBody({ root: command.root, previewId: command.previewId }), ifMatch: null, idempotencyKey: null }, decodeImportPreviewItem);
      if (result.previewId !== command.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async cancelImportPreview(value: ImportAddress): Promise<ImportPreviewItem> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/cancel",
        body: importBody({ root: command.root, previewId: command.previewId }), ifMatch: null, idempotencyKey: null }, decodeImportPreviewItem);
      if (result.previewId !== command.previewId || !["cancelled", "failed", "security-interrupted"].includes(result.state)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async beginImportReview(value: ImportAddress): Promise<ReviewSummary> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/begin-review",
        body: importBody({ root: command.root, previewId: command.previewId }), ifMatch: null, idempotencyKey: null }, decodeReviewSummary);
      if (result.previewId !== command.previewId || result.revision !== 1) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importReview(value: ImportAddress): Promise<ReviewSummary> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/review",
        body: importBody({ root: command.root, previewId: command.previewId }), ifMatch: null, idempotencyKey: null }, decodeReviewSummary);
      if (result.previewId !== command.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importReviewPage(value: ImportPageRequest): Promise<ReviewPage> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/records",
        body: importPageBody(command), ifMatch: null, idempotencyKey: null }, decodeReviewPage);
      if (result.revision !== command.revision || result.nextAfter < command.after || result.records.length > command.limit
        || (result.records.length ? result.records[0]!.ordinal !== command.after + 1 : result.nextAfter !== command.after)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importReviewDetail(value: ImportDetailRequest): Promise<ReviewDetail> {
      const command = importCommand(value);
      if (!integer(command.revision, 1, 2147483647) || !integer(command.ordinal, 1, 200000) || !importDigest(command.recordKey)
        || !registryEnum(command.section, ["raw", "candidates", "effective"]) || !integer(command.start, 0, 4096)
        || !integer(command.limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/detail", body: importBody({
        root: command.root, previewId: command.previewId, revision: command.revision, ordinal: command.ordinal,
        recordKey: command.recordKey, section: command.section, start: command.start, limit: command.limit,
      }), ifMatch: null, idempotencyKey: null }, decodeReviewDetail);
      if (result.revision !== command.revision || result.ordinal !== command.ordinal || result.recordKey !== command.recordKey
        || result.section !== command.section || result.nextIndex < command.start || result.fields.length > command.limit
        || (result.fields.length ? result.fields[0]!.index !== command.start : result.nextIndex !== command.start)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async mapImportReview(value: ImportMappingRequest): Promise<ReviewSummary> {
      const command = importCommand(value);
      if (!integer(command.expectedRevision, 1, 2147483646) || !registryEnum(command.mode, ["automatic", "columns"])
        || !Array.isArray(command.columns) || command.columns.length > 256 || command.mode === "automatic" && command.columns.length !== 0
        || new Set(command.columns.map((c) => c.index)).size !== command.columns.length
        || command.columns.some((c) => !integer(c.index, 0, 4095) || !registryEnum(c.target, IMPORT_FIELDS))) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/mapping", body: importBody({
        root: command.root, previewId: command.previewId, expectedRevision: command.expectedRevision, mode: command.mode,
        columns: command.columns.map((c) => ({ index: c.index, target: c.target })),
      }), ifMatch: null, idempotencyKey: null }, decodeReviewSummary);
      if (result.previewId !== command.previewId || result.revision !== command.expectedRevision + 1) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async editImportReview(value: ImportGroupRequest): Promise<ReviewSummary> {
      const command = importCommand(value);
      if (!integer(command.expectedRevision, 1, 2147483646) || !Array.isArray(command.records)
        || command.records.length < 1 || command.records.length > 100 || !Array.isArray(command.corrections) || command.corrections.length > 64
        || !(typeof command.included === "boolean" || command.included === null && command.corrections.length > 0)
        || new Set(command.records.map((r) => r.ordinal)).size !== command.records.length
        || command.records.some((r) => !integer(r.ordinal, 1, 200000) || !importDigest(r.recordKey))
        || command.corrections.some((c) => !registryEnum(c.name, IMPORT_FIELDS) || !importText(c.value, 65536, 1)
          || !c.value.trim() || /[\u0000-\u001f\u007f]/.test(c.value) || new TextEncoder().encode(c.value).length > 65536)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/edit", body: importBody({
        root: command.root, previewId: command.previewId, expectedRevision: command.expectedRevision,
        records: command.records.map((r) => ({ ordinal: r.ordinal, recordKey: r.recordKey })), included: command.included,
        corrections: command.corrections.map((c) => ({ name: c.name, value: c.value })),
      }), ifMatch: null, idempotencyKey: null }, decodeReviewSummary);
      if (result.previewId !== command.previewId || result.revision !== command.expectedRevision + 1) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async undoImportReview(value: ImportUndoRequest): Promise<ReviewSummary> {
      const command = importCommand(value);
      if (!integer(command.expectedRevision, 1, 2147483646)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/undo",
        body: importBody({ root: command.root, previewId: command.previewId, expectedRevision: command.expectedRevision }),
        ifMatch: null, idempotencyKey: null }, decodeReviewSummary);
      if (result.previewId !== command.previewId || result.revision !== command.expectedRevision + 1) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async importDiagnosticPage(value: ImportPageRequest): Promise<DiagnosticPage> {
      const command = importCommand(value);
      const result = await requestJson(transport, { method: "POST", path: "/projects/imports/report",
        body: importPageBody(command), ifMatch: null, idempotencyKey: null }, decodeDiagnosticPage);
      const header = "ordinal,line_start,line_end,status,diagnostic\r\n";
      const lines = result.csv.startsWith(header) ? result.csv.slice(header.length) : result.csv;
      if (result.revision !== command.revision || result.nextAfter < command.after || result.nextAfter > command.after + command.limit
        || result.csv.startsWith(header) !== (command.after === 0) || (lines ? Number(lines.split(",")[0]) !== command.after + 1 : result.nextAfter !== command.after)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async version(): Promise<VersionResponse> {
      return await requestJson(transport, {
        method: "GET", path: "/runtime/version", body: null, ifMatch: null, idempotencyKey: null,
      }, decodeVersionResponse);
    },
    async createProject(command: ProjectCreateRequest): Promise<ProjectProjection> {
      if (!projectRoot(command.parentDirectory)
        || typeof command.directoryName !== "string"
        || !/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(command.directoryName)
        || !boundedText(command.displayName, 1, 120)
        || !member(command.primaryUseCase, INTENT_PRIMARY_USE_CASES)
        || !boundedNarrative(command.researchObjective, 1)
        || !command.researchObjective.trim()) {
        throw new Error("RO-CORE-REQUEST-INVALID");
      }
      return await requestJson(transport, {
        method: "POST", path: "/projects",
        body: JSON.stringify({
          parentDirectory: command.parentDirectory, directoryName: command.directoryName,
          displayName: command.displayName, primaryUseCase: command.primaryUseCase,
          researchObjective: command.researchObjective,
        }),
        ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async workflowProfileCatalog(): Promise<WorkflowProfileCatalogProjection> {
      return await requestJson(transport, {
        method: "GET", path: "/workflow-profiles/catalog", body: null, ifMatch: null, idempotencyKey: null,
      }, decodeWorkflowProfileCatalogProjection);
    },
    async openProject(command: ProjectRootRequest): Promise<ProjectProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/open", body: projectBody(command), ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async closeProject(command: ProjectRootRequest): Promise<ProjectProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/close", body: projectBody(command), ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async archiveProject(command: ProjectRootRequest): Promise<ProjectProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/archive", body: projectBody(command), ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async restoreProject(command: ProjectRootRequest): Promise<ProjectProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/restore", body: projectBody(command), ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async deleteProject(command: ProjectDeleteRequest): Promise<ProjectProjection> {
      if (!projectRoot(command.root)
        || typeof command.confirmation !== "string"
        || !/^delete:[0-9a-f-]{36}$/.test(command.confirmation)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, {
        method: "POST", path: "/projects/delete",
        body: JSON.stringify({ root: command.root, confirmation: command.confirmation }),
        ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
    },
    async intent(command: ProjectRootRequest): Promise<IntentWorkspaceProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/intent", body: projectBody(command), ifMatch: null, idempotencyKey: null,
      }, decodeIntentWorkspaceProjection);
    },
    async previewIntent(command: IntentImpactRequest): Promise<IntentImpactPreview> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/intent/preview", body: intentImpactBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeIntentImpactPreview);
    },
    async saveIntentDraft(command: IntentDraftRequest, idempotencyKey: string): Promise<IntentDraftProjection> {
      if (!/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, {
        method: "POST", path: "/projects/intent/drafts", body: intentDraftBody(command),
        ifMatch: null, idempotencyKey,
      }, decodeIntentDraftProjection);
    },
    async acceptIntent(command: IntentAcceptRequest, idempotencyKey: string): Promise<IntentDraftProjection> {
      if (!/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, {
        method: "POST", path: "/projects/intent/acceptances", body: intentAcceptBody(command),
        ifMatch: null, idempotencyKey,
      }, decodeIntentDraftProjection);
    },
    async evaluateIntentPolicy(command: IntentPolicyRequest): Promise<IntentPolicyDecision> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/intent/policy/evaluations", body: intentPolicyBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeIntentPolicyDecision);
    },
    async workflowProgress(command: ProjectRootRequest): Promise<WorkflowProgressProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/workflow-progress", body: projectBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeWorkflowProgressProjection);
    },
    async commandWorkflowProgress(
      command: WorkflowProgressCommand, idempotencyKey: string,
    ): Promise<WorkflowProgressProjection> {
      if (!/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, {
        method: "POST", path: "/projects/workflow-progress/commands", body: workflowProgressBody(command),
        ifMatch: null, idempotencyKey,
      }, decodeWorkflowProgressProjection);
    },
    async modelCatalog(command: ModelCatalogReadRequest): Promise<ModelCatalogProjection> {
      if (!projectRoot(command.root) || (command.revision !== null && !integer(command.revision, 1, 2147483647))
        || (command.afterManifestId !== null && !registryCode(command.afterManifestId))
        || (command.beforeHistoryRevision !== null && !integer(command.beforeHistoryRevision, 1, 2147483647))) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, { method: "POST", path: "/projects/models", body: JSON.stringify({
        root: command.root, revision: command.revision, afterManifestId: command.afterManifestId,
        beforeHistoryRevision: command.beforeHistoryRevision,
      }), ifMatch: null, idempotencyKey: null }, decodeModelCatalogProjection);
    },
    async refreshModelCatalog(command: ModelCatalogRefreshRequest, idempotencyKey: string): Promise<ModelCatalogProjection> {
      if (!projectRoot(command.root) || !integer(command.expectedRevision, 0, 2147483646)
        || !/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, { method: "POST", path: "/projects/models/refresh",
        body: JSON.stringify({ root: command.root, expectedRevision: command.expectedRevision }),
        ifMatch: null, idempotencyKey }, decodeModelCatalogProjection);
    },
    async privacy(command: ProjectPrivacyRequest): Promise<PrivacyPolicyProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/privacy", body: projectBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodePrivacyPolicyProjection);
    },
    async updatePrivacy(command: PrivacyPolicyUpdateRequest): Promise<PrivacyPolicyProjection> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/privacy/update", body: privacyUpdateBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodePrivacyPolicyProjection);
    },
    async previewCache(command: CacheClearPreviewRequest): Promise<CacheClearPreview> {
      return await requestJson(transport, {
        method: "POST", path: "/projects/privacy/cache/preview", body: projectBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeCacheClearPreview);
    },
    async clearCache(command: CacheClearRequest): Promise<CacheClearResult> {
      if (!projectRoot(command.root) || typeof command.previewToken !== "string"
        || !/^[0-9a-f]{32}$/.test(command.previewToken)
        || command.confirmation !== `clear-cache:${command.previewToken}`) {
        throw new Error("RO-CORE-REQUEST-INVALID");
      }
      return await requestJson(transport, {
        method: "POST", path: "/projects/privacy/cache/clear",
        body: JSON.stringify({ root: command.root, previewToken: command.previewToken, confirmation: command.confirmation }),
        ifMatch: null, idempotencyKey: null,
      }, decodeCacheClearResult);
    },
    async lineage(command: ProvenanceLineageRequest): Promise<ProvenanceLineagePage> {
      const result = await requestJson(transport, {
        method: "POST", path: "/projects/provenance/lineage", body: provenanceLineageBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeProvenanceLineagePage);
      const factIds = result.items.map((item) => item.factId);
      const rootResolved = result.items.some(
        (item) => item.revisionId === command.revisionId && item.depth === 0,
      );
      const rootUnavailable = result.items.length === 0
        && result.integrityState === "integrity-review"
        && result.missingRevisionIds.includes(command.revisionId)
        && !result.exportAllowed
        && result.exportDenialReason === "integrity-review";
      const visibleIntegrityDebt = result.missingRevisionIds.length > 0
        || result.legacyEventCount > 0
        || result.truncated;
      if (result.revisionId !== command.revisionId || result.direction !== command.direction
        || result.items.length > command.pageSize
        || result.items.some((item) => item.depth > command.maxDepth)
        || result.items.some((item, index) => index > 0 && item.depth < (result.items[index - 1]?.depth ?? 0))
        || new Set(factIds).size !== factIds.length
        || (command.cursor === 0 && !rootResolved && !rootUnavailable)
        || (visibleIntegrityDebt && (
          result.integrityState !== "integrity-review"
          || result.exportAllowed
          || result.exportDenialReason !== "integrity-review"
        ))
        || (result.integrityState === "integrity-review" && (
          result.exportAllowed || result.exportDenialReason !== "integrity-review"
        ))
        || (result.integrityState === "verified" && result.exportDenialReason === "integrity-review")
        || (result.truncated && (
          result.integrityState !== "integrity-review"
          || result.exportAllowed
          || result.exportDenialReason !== "integrity-review"
        ))
        || (result.nextCursor !== null && (
          result.items.length === 0
          || result.nextCursor <= command.cursor
          || result.nextCursor !== command.cursor + result.items.length
        ))) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return result;
    },
    async previewRecalculation(command: RecalculationPreviewRequest): Promise<RecalculationPreview> {
      const result = await requestJson(transport, {
        method: "POST", path: "/projects/recalculation/preview", body: recalculationPreviewBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeRecalculationPreview);
      if (result.targetRevisionId !== command.targetRevisionId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async scheduleRecalculation(
      command: RecalculationScheduleRequest,
      idempotencyKey: string,
    ): Promise<RecalculationScheduleProjection> {
      if (!/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, {
        method: "POST", path: "/projects/recalculation/schedules", body: recalculationScheduleBody(command),
        ifMatch: null, idempotencyKey,
      }, decodeRecalculationSchedule);
      if (result.targetRevisionId !== command.targetRevisionId
        || result.planSha256 !== command.expectedPlanSha256) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async compareRecalculation(command: RecalculationComparisonRequest): Promise<RecalculationComparisonProjection> {
      const result = await requestJson(transport, {
        method: "POST", path: "/projects/recalculation/comparisons", body: recalculationComparisonBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeRecalculationComparison);
      if (result.beforeRevisionId !== command.beforeRevisionId || result.afterRevisionId !== command.afterRevisionId) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return result;
    },
    async requestRecalculationRestoreReview(
      command: RecalculationRestoreReviewRequest,
      idempotencyKey: string,
    ): Promise<RecalculationRestoreReviewProjection> {
      if (!/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      return await requestJson(transport, {
        method: "POST", path: "/projects/recalculation/restore-reviews",
        body: recalculationRestoreReviewBody(command), ifMatch: null, idempotencyKey,
      }, decodeRecalculationRestoreReview);
    },
    async restoreRecalculationRevision(command: RecalculationRestoreRequest): Promise<RecalculationRestoredRevision> {
      const result = await requestJson(transport, {
        method: "POST", path: "/projects/recalculation/restorations", body: recalculationRestoreBody(command),
        ifMatch: null, idempotencyKey: null,
      }, decodeRecalculationRestoredRevision);
      if (result.revisionId === command.priorAdjudicatedRevisionId
        || result.revisionId === command.expectedCurrentRevisionId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
    async taskCenter(root: string, limit = 50): Promise<WorkflowTaskCenterPage> {
      if (!projectRoot(root) || !integer(limit, 1, 100)) throw new Error("RO-CORE-REQUEST-INVALID");
      const query = new URLSearchParams({ root, limit: String(limit) });
      return await requestJson(transport, {
        method: "GET", path: `/projects/workflows/task-center?${query.toString()}`, body: null,
        ifMatch: null, idempotencyKey: null,
      }, decodeWorkflowTaskCenterPage);
    },
    async cancelWorkflowJob(root: string, jobId: string, workflow: WorkflowTaskCenterRun, reasonCode = "user-requested"): Promise<WorkflowTaskCenterRun> {
      if (!projectRoot(root) || !canonicalUuid7(jobId) || typeof reasonCode !== "string"
        || !/^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(reasonCode)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJsonResponse(transport, {
        method: "POST", path: `/projects/workflows/jobs/${jobId}/cancel`,
        body: JSON.stringify({ root, reasonCode }), ifMatch: workflowEtag(workflow), idempotencyKey: null,
      }, decodeWorkflowTaskCenterRun);
      if (result.response.etag !== workflowEtag(result.value)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.value;
    },
    async retryWorkflowJob(root: string, jobId: string, workflow: WorkflowTaskCenterRun, idempotencyKey: string): Promise<WorkflowTaskCenterRun> {
      if (!projectRoot(root) || !canonicalUuid7(jobId) || !/^[0-9a-f]{32}$/.test(idempotencyKey)) {
        throw new Error("RO-CORE-REQUEST-INVALID");
      }
      const result = await requestJsonResponse(transport, {
        method: "POST", path: `/projects/workflows/jobs/${jobId}/retry`,
        body: JSON.stringify({ root }), ifMatch: workflowEtag(workflow), idempotencyKey,
      }, decodeWorkflowTaskCenterRun);
      if (result.response.etag !== workflowEtag(result.value)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.value;
    },
    async decideWorkflowHumanTask(root: string, humanTaskId: string, workflow: WorkflowTaskCenterRun, disposition: WorkflowHumanDecisionRequest["disposition"], idempotencyKey: string): Promise<WorkflowTaskCenterRun> {
      if (!projectRoot(root) || !canonicalUuid7(humanTaskId)
        || !member(disposition, ["approved", "rejected", "deferred", "not-applicable"] as const)
        || !/^[0-9a-f]{32}$/.test(idempotencyKey)) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJsonResponse(transport, {
        method: "POST", path: `/projects/workflows/human-tasks/${humanTaskId}/decide`,
        body: JSON.stringify({ root, disposition }), ifMatch: workflowEtag(workflow), idempotencyKey,
      }, decodeWorkflowTaskCenterRun);
      if (result.response.etag !== workflowEtag(result.value)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result.value;
    },
    async operations(after: string | null = null, limit = 50): Promise<OperationPage> {
      if (!integer(limit, 1, 100) || (after !== null && !canonicalOperationId(after))) throw new Error("RO-CORE-REQUEST-INVALID");
      const query = new URLSearchParams({ limit: String(limit) });
      if (after !== null) query.set("after", after);
      return await requestJson(transport, {
        method: "GET", path: `/runtime/operations?${query.toString()}`, body: null, ifMatch: null, idempotencyKey: null,
      }, decodeOperationPage);
    },
    async operation(operationId: string): Promise<OperationSnapshot> {
      const result = await requestJsonResponse(transport, {
        method: "GET", path: `/runtime/operations/${pathOperationId(operationId)}`, body: null,
        ifMatch: null, idempotencyKey: null,
      }, decodeOperationStatus);
      if (result.response.etag !== `"${result.value.operationId}-${result.value.sequence}"`) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return { operation: result.value, etag: result.response.etag };
    },
    async cancel(operationId: string, ifMatch: string, idempotencyKey: string): Promise<OperationSnapshot> {
      if (!/^"op-[a-z0-9-]+-[0-9]+"$/.test(ifMatch) || !/^[0-9a-f]{32}$/.test(idempotencyKey)) {
        throw new Error("RO-CORE-REQUEST-INVALID");
      }
      const result = await requestJsonResponse(transport, {
        method: "POST", path: `/runtime/operations/${pathOperationId(operationId)}/cancel`, body: null,
        ifMatch, idempotencyKey,
      }, decodeOperationStatus);
      if (result.response.etag !== `"${result.value.operationId}-${result.value.sequence}"`) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return { operation: result.value, etag: result.response.etag };
    },
    async events(operationId: string, afterSequence = 0): Promise<readonly OperationProgressEvent[]> {
      if (!integer(afterSequence, 0, Number.MAX_SAFE_INTEGER)) throw new Error("RO-CORE-REQUEST-INVALID");
      const response = await transport({
        method: "GET",
        path: `/runtime/operations/${pathOperationId(operationId)}/events?afterSequence=${afterSequence}`,
        body: null,
        ifMatch: null,
        idempotencyKey: null,
      });
      if (!integer(response.status, 100, 599) || !canonicalTraceId(response.traceId) || typeof response.body !== "string") {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      if (response.status >= 400) {
        if (response.contentType !== "application/problem+json") throw new Error("RO-CORE-RESPONSE-INVALID");
        const problem = decodeProblemDetail(parseJson(response.body));
        if (!problem || problem.status !== response.status || problem.traceId !== response.traceId) throw new Error("RO-CORE-RESPONSE-INVALID");
        throw new CoreApiClientError(problem);
      }
      if (response.status !== 200 || response.contentType !== "text/event-stream" || !canonicalTraceId(response.traceId)) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      const events = parseOperationEventStream(response.body);
      if (events.some((event) => event.operationId !== operationId || event.sequence <= afterSequence)) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return events;
    },
  });
}
"""


def render_typescript(openapi_bytes: bytes, workflow_profile_projection_sha256: str) -> bytes:
    openapi = json.loads(openapi_bytes)
    if not isinstance(openapi, dict) or openapi.get("openapi") != "3.1.0":
        raise ValueError("Core contract must be OpenAPI 3.1.0")
    operation_ids = _operation_ids(openapi)
    required = {
        "version_runtime_version_get",
        "list_operations_runtime_operations_get",
        "operation_status_runtime_operations__operation_id__get",
        "cancel_operation_runtime_operations__operation_id__cancel_post",
        "operation_events_runtime_operations__operation_id__events_get",
        "create_project_projects_post",
        "workflow_profile_catalog_workflow_profiles_catalog_get",
        "open_project_projects_open_post",
        "close_project_projects_close_post",
        "archive_project_projects_archive_post",
        "restore_project_projects_restore_post",
        "delete_project_projects_delete_post",
        "project_intent_projects_intent_post",
        "preview_intent_projects_intent_preview_post",
        "save_intent_draft_projects_intent_drafts_post",
        "accept_intent_projects_intent_acceptances_post",
        "evaluate_intent_policy_projects_intent_policy_evaluations_post",
        "project_privacy_projects_privacy_post",
        "update_project_privacy_projects_privacy_update_post",
        "preview_project_cache_projects_privacy_cache_preview_post",
        "clear_project_cache_projects_privacy_cache_clear_post",
        "provenance_lineage_projects_provenance_lineage_post",
        "workflow_task_center_projects_workflows_task_center_get",
        "cancel_workflow_job_projects_workflows_jobs__job_id__cancel_post",
        "retry_workflow_job_projects_workflows_jobs__job_id__retry_post",
        "decide_workflow_human_task_projects_workflows_human_tasks__human_task_id__decide_post",
    }
    if not required.issubset(operation_ids):
        raise ValueError(
            f"Core OpenAPI is missing generated-client operations: {sorted(required - set(operation_ids))}"
        )
    digest = hashlib.sha256(openapi_bytes).hexdigest()
    operation_union = " | ".join(json.dumps(item) for item in operation_ids)
    header = (
        "// Generated by tools/core_api_contract.py; DO NOT EDIT.\n"
        f"export const CORE_API_GENERATOR_VERSION = {json.dumps(GENERATOR_VERSION)} as const;\n"
        f"const schemaDigest = {json.dumps(digest)} as const;\n"
        "export const CORE_API_OPENAPI_SHA256 = schemaDigest;\n"
        f"export const CORE_API_WORKFLOW_PROFILE_PROJECTION_SHA256 = {json.dumps(workflow_profile_projection_sha256)} as const;\n"
        'export const CORE_API_CLIENT_VERSION = "1.0.0" as const;\n'
        f"export type CoreApiOperationId = {operation_union};\n\n"
    )
    return (header + _interfaces(openapi) + "\n" + CLIENT_RUNTIME.strip() + "\n").encode()


def generated_artifacts(repo: Path) -> dict[Path, bytes]:
    source = repo / "services" / "core-api" / "src"
    sys.path.insert(0, str(source))
    try:
        from research_observatory_core.connectors.contracts import (
            ConnectorCapabilities,
            ConnectorRequest,
            ConnectorResultPage,
        )
        from research_observatory_core.contract import canonical_openapi_bytes
        from research_observatory_core.model_registry_contracts import ModelManifest
        from research_observatory_core.model_routing_contracts import RoutingPolicy
        from research_observatory_core.research_intents import approved_workflow_catalog_projection

        openapi = canonical_openapi_bytes()
        manifest_schema = (
            json.dumps(
                ModelManifest.model_json_schema(by_alias=True)
                | {
                    "$id": "https://research-observatory.local/contracts/model-gateway/model-manifest.schema.json",
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        routing_schema = (
            json.dumps(
                RoutingPolicy.model_json_schema(by_alias=True)
                | {
                    "$id": "https://research-observatory.local/contracts/model-gateway/routing-policy.schema.json",
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        connector_schemas = {
            repo / "packages/contracts/connectors" / filename: (
                json.dumps(
                    model.model_json_schema(by_alias=True)
                    | {
                        "$id": f"https://research-observatory.local/contracts/connectors/{filename}",
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            for filename, model in (
                ("connector-request.schema.json", ConnectorRequest),
                ("connector-page.schema.json", ConnectorResultPage),
                ("connector-capabilities.schema.json", ConnectorCapabilities),
            )
        }
        workflow_profile_projection = approved_workflow_catalog_projection().model_dump(mode="json", by_alias=True)
        workflow_profile_projection_bytes = json.dumps(
            workflow_profile_projection,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        workflow_profile_projection_sha256 = "sha256:" + hashlib.sha256(workflow_profile_projection_bytes).hexdigest()
    finally:
        sys.path.remove(str(source))
    return {
        **connector_schemas,
        repo / "packages" / "contracts" / "model-gateway" / "model-manifest.schema.json": manifest_schema,
        repo / "packages" / "contracts" / "model-gateway" / "routing-policy.schema.json": routing_schema,
        repo / "packages" / "contracts" / "core-api" / "openapi.json": openapi,
        repo / "packages" / "contracts" / "core-api" / "generated.ts": render_typescript(
            openapi,
            workflow_profile_projection_sha256,
        ),
    }


def synchronize(repo: Path, *, check: bool) -> list[str]:
    errors: list[str] = []
    for path, expected in generated_artifacts(repo).items():
        if check:
            if not path.is_file() or path.read_bytes() != expected:
                errors.append(f"STALE {path.relative_to(repo).as_posix()}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    errors = synchronize(args.repo.resolve(), check=args.check)
    if errors:
        print("\n".join(errors))
        return 1
    print("Core API contract: PASS" if args.check else "Core API contract: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
