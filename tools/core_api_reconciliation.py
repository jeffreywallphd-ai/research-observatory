# ruff: noqa: E501
"""Compile the bounded reconciliation DTO shapes from their authoritative OpenAPI.

Only these new client operations use these guards. Cross-field domain checks
remain explicit below; generated structure is not publication authority.
"""

from __future__ import annotations

import json
from typing import Any

OPERATIONS = (
    (
        "prepareScholarlyReconciliationBatch",
        "batches/prepare",
        "ReconciliationBatchPrepareRequest",
        "ReconciliationBatchPrepared",
    ),
    (
        "scheduleScholarlyReconciliationBatch",
        "batches/schedule",
        "ReconciliationBatchRequest",
        "ReconciliationBatchStatus",
    ),
    (
        "inspectScholarlyReconciliationBatch",
        "batches/status",
        "ReconciliationBatchJobRequest",
        "ReconciliationBatchStatus",
    ),
    (
        "cancelScholarlyReconciliationBatch",
        "batches/cancel",
        "ReconciliationBatchJobRequest",
        "ReconciliationBatchStatus",
    ),
    ("inspectScholarlyDuplicateCandidates", "candidates", "ReconciliationCandidateRequest", "CandidatePage"),
    ("reconcileScholarlySource", "exact", "ReconciliationRequest", "ReconciliationResult"),
    ("inspectScholarlyReconciliation", "inspect", "ReconciliationReadRequest", "ReconciliationInspection"),
    ("resolveScholarlyConnectorAddress", "connector-address", "ReconciliationConnectorAddressRequest", "SourceAddress"),
    ("inspectScholarlyReviewContext", "review/context", "ReconciliationContextRequest", "ReviewContext"),
    ("previewScholarlyReview", "review/preview", "ReconciliationReviewPreviewRequest", "ReviewPreview"),
    ("commitScholarlyReview", "review/commit", "ReconciliationReviewRequest", "ReviewOutcome"),
)


def _expression(schema: dict[str, Any], value: str, references: set[str]) -> str:
    known = {
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "default",
        "enum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "properties",
        "readOnly",
        "required",
        "title",
        "type",
    }
    if set(schema) - known:
        raise ValueError("Unsupported reconciliation schema keyword")
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        if not name.isidentifier():
            raise ValueError("Unsupported reconciliation schema reference")
        references.add(name)
        return f"reconciliationShape{name}({value})"
    if "const" in schema:
        return f"{value} === {json.dumps(schema['const'])}"
    if "enum" in schema:
        return "(" + " || ".join(f"{value} === {json.dumps(item)}" for item in schema["enum"]) + ")"
    if "anyOf" in schema:
        return "(" + " || ".join(_expression(item, value, references) for item in schema["anyOf"]) + ")"
    kind = schema["type"]
    if kind == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError("Reconciliation wire objects must be closed")
        fields = schema["properties"]
        predicates = [f"exactKeys(item, {json.dumps(list(fields))})"]
        predicates.extend(_expression(field, f"item[{json.dumps(key)}]", references) for key, field in fields.items())
        return "reconciliationObject(" + value + ", (item) => " + " && ".join(f"({p})" for p in predicates) + ")"
    if kind == "array":
        element = _expression(schema["items"], "element", references)
        return (
            f"(Array.isArray({value}) && {value}.length >= {schema.get('minItems', 0)} "
            f"&& {value}.length <= {schema.get('maxItems', 32768)} && {value}.every((element: unknown) => {element}))"
        )
    if kind == "string":
        # Pydantic string limits count Unicode code points, not UTF-16 units.
        result = f"importText({value}, {schema.get('maxLength', 65536)}, {schema.get('minLength', 0)})"
        if "pattern" in schema:
            result += f" && new RegExp({json.dumps(schema['pattern'])}, 'u').test({value} as string)"
        return "(" + result + ")"
    if kind == "integer":
        return (
            f"integer({value}, {schema.get('minimum', -9007199254740991)}, {schema.get('maximum', 9007199254740991)})"
        )
    if kind == "boolean":
        return f"typeof {value} === 'boolean'"
    if kind == "null":
        return f"{value} === null"
    raise ValueError("Unsupported reconciliation schema type")


def render_reconciliation(openapi: dict[str, Any]) -> tuple[str, str]:
    schemas = openapi["components"]["schemas"]
    pending = {name for _, _, request, response in OPERATIONS for name in (request, response)}
    blocks = {}
    while pending:
        name = min(pending)
        pending.remove(name)
        references: set[str] = set()
        expression = _expression(schemas[name], "value", references)
        blocks[name] = (
            f"function reconciliationShape{name}(value: unknown): value is {name} {{\n"
            f"  return ({expression}) && reconciliationSemantics({json.dumps(name)}, value);\n}}\n"
        )
        pending.update(references - blocks.keys())
    methods = []
    for operation, route, request, response in OPERATIONS:
        path = "/projects/reconciliation/" + route
        if openapi["paths"][path]["post"]["operationId"] != operation:
            raise ValueError("Reconciliation operation identity differs")
        methods.append(f'''    async {operation}(value: {request}): Promise<{response}> {{
      const command = reconciliationOwned(value);
      if (!reconciliationShape{request}(command) || !projectRoot(command.root)) throw new Error("RO-CORE-REQUEST-INVALID");
      const body = JSON.stringify(command);
      if (new TextEncoder().encode(body).length > {262144 if route.startswith("review/") else 32768}) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, {{ method: "POST", path: "{path}", body, ifMatch: null, idempotencyKey: null }}, decode{response});
      if (!await reconciliationReply("{route}", command, result)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    }},''')
    decoders = []
    for name in sorted({response for _, _, _, response in OPERATIONS} | {"ReviewPlan"}):
        decoders.append(f"""export function decode{name}(value: unknown): {name} | null {{
  const owned = reconciliationOwned(value);
  return reconciliationShape{name}(owned) ? owned : null;
}}""")
    return "\n".join([RUNTIME, *[blocks[name] for name in sorted(blocks)], *decoders]), "\n".join(methods)


RUNTIME = r"""
function reconciliationOwned(value: unknown): unknown {
  try {
    const owned = registryOwnedValue(value, 32768, 1000000);
    return new TextEncoder().encode(JSON.stringify(owned)).length <= 4194304 ? owned : null;
  } catch { return null; }
}

function reconciliationObject(value: unknown, check: (item: Readonly<Record<string, unknown>>) => boolean): boolean {
  const item = record(value);
  return item !== null && check(item);
}

const RECONCILIATION_CONFIGURATION = "b3e04c16bcfbb8588a718d55a94217a21a02ba1877fa9ea6ba187ebcdfc98dfc";
const RECONCILIATION_ALGORITHM = "scholarly-duplicate-ranking/1.0.0";
const RECONCILIATION_FEATURES = "scholarly-duplicate-features/1.0.0";
const RECONCILIATION_NORMALIZER = "scholarly-identifiers/1.0.0";

function reconciliationSorted(values: readonly string[]): boolean {
  return values.every((value, index) => index === 0 || values[index - 1]! < value);
}
function reconciliationSameSet(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && new Set(left).size === left.length
    && new Set(right).size === right.length && left.every((item) => right.includes(item));
}
function reconciliationSameAddress(left: SourceAddress, right: SourceAddress): boolean {
  return left.kind === right.kind && left.contextId === right.contextId && left.revisionId === right.revisionId
    && left.ordinal === right.ordinal && left.recordKey === right.recordKey;
}

function reconciliationSemantics(name: string, value: unknown): boolean {
  // These cases run only after the complete generated structural guard passes.
  switch (name) {
    case "ImportPermission": {
      const item = value as ImportPermission;
      return item.value === "unknown" || item.basis === "researcher-confirmed";
    }
    case "SourceAddress": {
      const item = value as SourceAddress;
      return item.kind === "import-member" ? item.ordinal >= 1 && item.recordKey !== null : item.ordinal <= 999 && item.recordKey === null;
    }
    case "SourceAssertion": return new TextEncoder().encode(JSON.stringify(value)).length <= 1048576;
    case "NormalizedIdentifier": {
      const item = value as NormalizedIdentifier;
      return (item.status === "valid") === (item.canonical !== null) && item.issues.length <= 1
        && (item.status === "valid" ? item.issues.length === 0 : item.issues[0] === (item.status === "invalid" ? "invalid-identifier" : "unsupported-scheme"));
    }
    case "ReconciliationBatchStatus": {
      const item = value as ReconciliationBatchStatus;
      return (item.state === "succeeded") === (item.setRevisionId !== null);
    }
    case "ReconciliationResult": {
      const item = value as ReconciliationResult, review = item.disposition === "review-required";
      return review === (item.workId === null) && review === (item.workRevisionId === null)
        && review === Boolean(item.flags.length) && review === (item.knowledgeStatus === "disputed");
    }
    case "ReconciliationInspection": {
      const item = value as ReconciliationInspection;
      return item.result.projectId === item.assertion.projectId && reconciliationSameAddress(item.result.source, item.assertion.address)
        && item.normalizedIdentifiers.length === item.assertion.identifiers.length
        && item.normalizedIdentifiers.every((identifier, index) => identifier.observed === item.assertion.identifiers[index]!.observed
          && identifier.scheme === item.assertion.identifiers[index]!.scheme);
    }
    case "WorkState": {
      const item = value as WorkState;
      return reconciliationSorted(item.assertionRevisionIds) && item.previousRevisionId !== item.revisionId && item.workId !== item.revisionId
        && (item.disposition === "active" ? item.assertionRevisionIds.length > 0 && item.aliasTarget === null
          : item.assertionRevisionIds.length === 0 && item.aliasTarget !== null && item.aliasTarget !== item.workId
            && item.previousRevisionId !== null && item.decisionRevisionId !== null);
    }
    case "SourcePartition": return reconciliationSorted((value as SourcePartition).assertionRevisionIds);
    case "ReviewPlan": return reconciliationPlan(value as ReviewPlan);
    case "ReviewContext": {
      const item = value as ReviewContext;
      const members = [...item.works.flatMap((work) => work.assertionRevisionIds), ...item.unassignedAssertionRevisionIds];
      const aliases = new Map(item.inboundAliases.map((work) => [work.workId, work.aliasTarget!]));
      const workIds = item.works.map((work) => work.workId);
      return item.algorithm === RECONCILIATION_ALGORITHM && item.featureVersion === RECONCILIATION_FEATURES
        && item.configurationSha256 === RECONCILIATION_CONFIGURATION && importDigest(item.evidenceSha256)
        && reconciliationSorted(item.unassignedAssertionRevisionIds) && new Set(workIds).size === workIds.length
        && item.works.every((work) => work.disposition === "active")
        && item.inboundAliases.every((work) => work.disposition === "alias" && !workIds.includes(work.workId))
        && aliases.size === item.inboundAliases.length && [...aliases.keys()].every((id) => {
          const seen = new Set<string>();
          while (aliases.has(id)) { if (seen.has(id)) return false; seen.add(id); id = aliases.get(id)!; }
          return workIds.includes(id);
        })
        && reconciliationSameSet(members, item.sources.map((source) => source.assertionRevisionId))
        && item.sources.every((source) => source.assertion.projectId === item.sources[0]!.assertion.projectId);
    }
    case "ReviewOutcome": {
      const item = value as ReviewOutcome;
      return new Set(item.workStates.map((work) => work.workId)).size === item.workStates.length
        && new Set(item.dependencyRunIds).size === item.dependencyRunIds.length
        && item.workStates.every((work) => work.decisionRevisionId === item.decisionRevisionId);
    }
    case "ReviewPreview": {
      const item = value as ReviewPreview;
      return reconciliationSorted(item.affectedOutputRevisionIds) && reconciliationSorted(item.unknownImpactRevisionIds);
    }
    case "CandidateFeature": {
      const item = value as CandidateFeature;
      return !(item.state === "available" && item.score === null || item.state === "not-reported" && (item.score !== null || item.conflict)
        || item.state === "disputed" && !item.conflict)
        && (item.name === "identifiers" || item.conflict === (item.state === "disputed" || item.score !== null && item.score < 10000));
    }
    case "CandidateExplanation": return reconciliationCandidate(value as CandidateExplanation);
    case "CandidatePage": {
      const item = value as CandidatePage, end = item.after + item.items.length;
      return item.configurationSha256 === RECONCILIATION_CONFIGURATION && item.identifierNormalizer === RECONCILIATION_NORMALIZER
        && end <= item.candidateCount && item.candidateCount <= item.comparedPairs && item.comparedPairs <= item.recordCount * (item.recordCount - 1) / 2
        && item.nextAfter === (end < item.candidateCount ? end : null) && (item.nextAfter === null || item.items.length > 0)
        && item.inventoryState === (item.inventorySha256 === item.currentInventorySha256 ? "unchanged" : "changed")
        && new Set(item.items.map((pair) => `${pair.left}/${pair.right}`)).size === item.items.length;
    }
    default: return true;
  }
}

function reconciliationPlan(plan: ReviewPlan): boolean {
  const workIds = plan.works.map((work) => work.workId), workSet = new Set(workIds);
  const members = [...plan.works.flatMap((work) => work.assertionRevisionIds), ...plan.unassignedAssertionRevisionIds];
  const partitions = plan.partitions.flatMap((part) => part.assertionRevisionIds);
  const groups = new Map(plan.partitions.map((part) => [part.group, part]));
  const survivors = plan.partitions.flatMap((part) => part.existingWorkId ? [part.existingWorkId] : []);
  const aliases = new Map(plan.aliases.map((alias) => [alias.workId, alias]));
  if (workSet.size !== workIds.length || plan.works.some((work) => work.disposition !== "active")
    || !reconciliationSorted(plan.unassignedAssertionRevisionIds) || members.length < 1 || members.length > 512
    || !reconciliationSameSet(members, partitions) || groups.size !== plan.partitions.length || new Set(survivors).size !== survivors.length
    || survivors.some((id) => !workSet.has(id) || aliases.has(id)) || aliases.size !== plan.aliases.length
    || workIds.some((id) => !survivors.includes(id) && !aliases.has(id)) || plan.aliases.some((alias) => {
      const target = groups.get(alias.targetGroup), source = plan.works.find((work) => work.workId === alias.workId);
      return !target || target.existingWorkId === alias.workId || source !== undefined && source.revisionId !== alias.revisionId;
    })) return false;
  return plan.action === "merge" ? plan.works.length + plan.unassignedAssertionRevisionIds.length >= 2 && plan.partitions.length === 1
    : plan.action === "split" ? plan.works.length === 1 && plan.unassignedAssertionRevisionIds.length === 0 && plan.partitions.length >= 2
      : plan.works.length <= 1 && plan.unassignedAssertionRevisionIds.length > 0 && plan.partitions.length === 1;
}

function reconciliationCandidate(item: CandidateExplanation): boolean {
  const names = ["title", "authors", "year", "venue", "pages", "abstract", "identifiers"], weights = [7000, 1500, 800, 400, 200, 100, 2000];
  if (item.left >= item.right || item.configurationFingerprint !== RECONCILIATION_CONFIGURATION || item.identifierNormalizer !== RECONCILIATION_NORMALIZER
    || item.features.some((feature, index) => feature.name !== names[index] || feature.weight !== weights[index])) return false;
  const denominator = item.features.reduce((sum, feature) => sum + (feature.score === null ? 0 : feature.weight), 0);
  const score = denominator ? Math.floor(item.features.reduce((sum, feature) => sum + (feature.score ?? 0) * feature.weight, 0) / denominator) : 0;
  const flags = [item.features.slice(0, -1).some((feature) => feature.state === "disputed") ? "competing-source-fields" : null,
    item.features[2]!.score === 0 ? "year-disagreement" : null, item.features[6]!.conflict ? "conflicting-identifiers" : null].filter((flag) => flag !== null).sort();
  return item.score === score && item.flags.length === flags.length && item.flags.every((flag, index) => flag === flags[index]);
}

async function reconciliationFingerprint(value: unknown): Promise<string> {
  function canonical(item: unknown): string {
    if (Array.isArray(item)) return "[" + item.map(canonical).join(",") + "]";
    const object = record(item);
    if (object) return "{" + Object.keys(object).sort().map((key) => canonical(key) + ":" + canonical(object[key])).join(",") + "}";
    return JSON.stringify(item).replace(/[\u007f-\uffff]/g, (char) => "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"));
  }
  const bytes = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function reconciliationOutcome(plan: ReviewPlan, reply: ReviewOutcome): boolean {
  const active = reply.workStates.filter((work) => work.disposition === "active");
  const aliases = reply.workStates.filter((work) => work.disposition === "alias");
  const previous = new Map(plan.works.map((work) => [work.workId, work]));
  const priorIds = new Set([...previous.keys(), ...plan.aliases.map((alias) => alias.workId)]);
  const priorRevisions = new Set([...plan.works.map((work) => work.revisionId), ...plan.aliases.map((alias) => alias.revisionId)]);
  const groups = new Map<string, string>();
  if (active.length !== plan.partitions.length || aliases.length !== plan.aliases.length
    || new Set(reply.workStates.map((work) => work.revisionId)).size !== reply.workStates.length
    || reply.workStates.some((work) => priorRevisions.has(work.revisionId) || work.revisionId === reply.decisionRevisionId)
    || reply.dependencyRunIds.length !== plan.partitions.filter((part) => part.existingWorkId !== null).length + plan.aliases.length) return false;
  for (const part of plan.partitions) {
    const state = active.find((work) => reconciliationSameSet(work.assertionRevisionIds, part.assertionRevisionIds));
    if (!state) return false;
    if (part.existingWorkId !== null) {
      if (state.workId !== part.existingWorkId || state.previousRevisionId !== previous.get(part.existingWorkId)?.revisionId) return false;
    } else if (state.previousRevisionId !== null || priorIds.has(state.workId)) return false;
    groups.set(part.group, state.workId);
  }
  return plan.aliases.every((alias) => {
    const state = aliases.find((work) => work.workId === alias.workId);
    return state !== undefined && state.previousRevisionId === alias.revisionId && state.aliasTarget === groups.get(alias.targetGroup);
  });
}

async function reconciliationReply(route: string, command: unknown, result: unknown): Promise<boolean> {
  switch (route) {
    case "batches/prepare": return true;
    case "batches/schedule": return (result as ReconciliationBatchStatus).requestId === (command as ReconciliationBatchRequest).requestId;
    case "batches/status": case "batches/cancel": {
      const request = command as ReconciliationBatchJobRequest, reply = result as ReconciliationBatchStatus;
      return request.requestId === reply.requestId && request.jobId === reply.jobId;
    }
    case "candidates": {
      const request = command as ReconciliationCandidateRequest, reply = result as CandidatePage;
      return request.setRevisionId === reply.setRevisionId && request.after === reply.after && reply.items.length <= request.limit;
    }
    case "exact": return reconciliationSameAddress((command as ReconciliationRequest).source, (result as ReconciliationResult).source);
    case "inspect": return (command as ReconciliationReadRequest).assertionRevisionId === (result as ReconciliationInspection).result.assertionRevisionId;
    case "connector-address": {
      const request = command as ReconciliationConnectorAddressRequest, reply = result as SourceAddress;
      return reply.kind === "connector-record" && reply.contextId === request.previewId && reply.ordinal === request.ordinal;
    }
    case "review/context": {
      const request = command as ReconciliationContextRequest, reply = result as ReviewContext;
      const { evidenceSha256, ...evidence } = reply;
      return reconciliationSameSet(request.workIds, reply.works.map((work) => work.workId))
        && reconciliationSameSet(request.unassignedAssertionRevisionIds, reply.unassignedAssertionRevisionIds)
        && evidenceSha256 === await reconciliationFingerprint(evidence);
    }
    case "review/preview": {
      const request = command as ReconciliationReviewPreviewRequest, reply = result as ReviewPreview;
      return reply.evidenceSha256 === request.plan.evidenceSha256 && reply.planSha256 === await reconciliationFingerprint(request.plan);
    }
    case "review/commit": {
      const request = (command as ReconciliationReviewRequest).command, reply = result as ReviewOutcome;
      return reply.commandId === request.commandId && reply.planSha256 === await reconciliationFingerprint(request.plan)
        && reconciliationOutcome(request.plan, reply);
    }
    default: return false;
  }
}
"""
