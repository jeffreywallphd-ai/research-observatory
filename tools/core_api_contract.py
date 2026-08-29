#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate and verify the portable OpenAPI and TypeScript Core API client."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

GENERATOR_VERSION = "1.0.0"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _schema_type(schema: dict[str, Any]) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]
    variants = schema.get("anyOf")
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
        if "enum" in schema:
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
            lines.append(f"  readonly {property_name}: {_schema_type(property_schema)};")
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
const INTENT_CHANGE_CATEGORIES = ["primary-use-case", "corpus-scope", "novelty-scope"] as const;
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

export function decodeIntentDraftProjection(value: unknown): IntentDraftProjection | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, [
    "schemaVersion", "intentId", "revisionId", "revision", "revisionContentHash", "createdAt", "status",
    "primaryUseCase", "epistemicMode", "researchObjective", "contributionIntent", "phenomenon", "unitOfAnalysis",
    "levelOfAnalysis", "sourceKinds", "languageCodes", "startYear", "endYear", "includePrivateReports",
    "evidenceTypes", "noveltyStandard", "noveltyRationale", "autonomyLevel", "stoppingConditions",
    "revisionRationale", "unresolvedDecisions", "decisionComplete", "canRequestAcceptance", "launchReady",
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
    "schemaVersion", "expectedRevision", "changeCategories", "affectedWorkflows", "affectedOutputs", "warnings",
    "acknowledgementRequired", "acknowledgementToken",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !integer(candidate.expectedRevision, 0, Number.MAX_SAFE_INTEGER)
    || !uniqueMembers(candidate.changeCategories, INTENT_CHANGE_CATEGORIES, 3)
    || !stringList(candidate.affectedWorkflows, 32) || !stringList(candidate.affectedOutputs, 32)
    || !stringList(candidate.warnings, 8) || typeof candidate.acknowledgementRequired !== "boolean"
    || (candidate.acknowledgementToken !== null
      && (typeof candidate.acknowledgementToken !== "string" || !/^[0-9a-f]{64}$/.test(candidate.acknowledgementToken)))) return null;
  if (candidate.acknowledgementRequired !== (candidate.acknowledgementToken !== null)
    || candidate.acknowledgementRequired !== (candidate.changeCategories.length > 0)) return null;
  return candidate as unknown as IntentImpactPreview;
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
    "nextCursor", "integrityState", "legacyEventCount", "exportAllowed", "exportDenialReason",
  ])) return null;
  if (candidate.schemaVersion !== "1.0" || !canonicalUuid7(candidate.revisionId)
    || !member(candidate.direction, ["ancestors", "descendants"] as const)
    || !Array.isArray(candidate.items) || candidate.items.length > 100
    || !Array.isArray(candidate.missingRevisionIds) || candidate.missingRevisionIds.length > 256
    || (candidate.nextCursor !== null && !integer(candidate.nextCursor, 0, 10_000))
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

function intentImpactBody(command: IntentImpactRequest): string {
  if (!projectRoot(command.root) || !integer(command.expectedRevision, 0, Number.MAX_SAFE_INTEGER)
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
    || !member(command.subjectType, INTENT_POLICY_SUBJECTS)
    || (command.stoppingCondition !== null
      && !member(command.stoppingCondition, INTENT_STOPPING_CONDITIONS))) throw new Error("RO-CORE-REQUEST-INVALID");
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

export function createCoreApiClient(transport: CoreApiTransport) {
  return Object.freeze({
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
        || typeof command.templateId !== "string"
        || !/^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(command.templateId)) {
        throw new Error("RO-CORE-REQUEST-INVALID");
      }
      return await requestJson(transport, {
        method: "POST", path: "/projects",
        body: JSON.stringify({
          parentDirectory: command.parentDirectory, directoryName: command.directoryName,
          displayName: command.displayName, templateId: command.templateId,
        }),
        ifMatch: null, idempotencyKey: null,
      }, decodeProjectProjection);
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
      if (result.revisionId !== command.revisionId || result.direction !== command.direction
        || result.items.length > command.pageSize
        || result.items.some((item) => item.depth > command.maxDepth)
        || result.items.some((item, index) => index > 0 && item.depth < (result.items[index - 1]?.depth ?? 0))
        || new Set(factIds).size !== factIds.length
        || (command.cursor === 0 && !rootResolved && !rootUnavailable)
        || (result.nextCursor !== null && (
          result.items.length === 0
          || result.nextCursor <= command.cursor
          || result.nextCursor !== command.cursor + result.items.length
        ))) {
        throw new Error("RO-CORE-RESPONSE-INVALID");
      }
      return result;
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


def render_typescript(openapi_bytes: bytes) -> bytes:
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
        f"export const CORE_API_OPENAPI_SHA256 = {json.dumps(digest)} as const;\n"
        'export const CORE_API_CLIENT_VERSION = "1.0.0" as const;\n'
        f"export type CoreApiOperationId = {operation_union};\n\n"
    )
    return (header + _interfaces(openapi) + "\n" + CLIENT_RUNTIME.strip() + "\n").encode()


def generated_artifacts(repo: Path) -> dict[Path, bytes]:
    source = repo / "services" / "core-api" / "src"
    sys.path.insert(0, str(source))
    try:
        from research_observatory_core.contract import canonical_openapi_bytes

        openapi = canonical_openapi_bytes()
    finally:
        sys.path.remove(str(source))
    return {
        repo / "packages" / "contracts" / "core-api" / "openapi.json": openapi,
        repo / "packages" / "contracts" / "core-api" / "generated.ts": render_typescript(openapi),
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
