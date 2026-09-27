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
    ("listScholarlyVersionWorks", "versions/works", "VersionWorksRequest", "VersionWorkPage"),
    ("inspectScholarlyVersionContext", "versions/context", "VersionContextRequest", "VersionContext"),
    ("inspectScholarlyVersion", "versions/inspect", "VersionInspectRequest", "WorkVersion"),
    ("previewScholarlyVersionDecision", "versions/preview", "VersionPreviewRequest", "VersionPreview"),
    ("commitScholarlyVersionDecision", "versions/commit", "VersionCommitRequest", "VersionOutcome"),
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
      if (new TextEncoder().encode(body).length > {262144 if route.startswith(("review/", "versions/")) else 32768}) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, {{ method: "POST", path: "{path}", body, ifMatch: null, idempotencyKey: null }}, decode{response});
      if (!await reconciliationReply("{route}", command, result)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    }},''')
    decoders = []
    for name in sorted({response for _, _, _, response in OPERATIONS} | {"ReviewPlan", "VersionPlan"}):
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
    case "VersionDate": {
      const item = value as VersionDate;
      if (item.precision === "unknown" || item.precision === "not-reported") return item.value === null;
      const pattern = item.precision === "year" ? /^\d{4}$/ : item.precision === "month" ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/;
      if (item.value === null || !pattern.test(item.value)) return false;
      const full = item.value + (item.precision === "year" ? "-01-01" : item.precision === "month" ? "-01" : "");
      const parsed = new Date(full + "T00:00:00Z");
      return Number(full.slice(0, 4)) >= 1 && Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === full;
    }
    case "VersionReference": return (value as VersionReference).versionId !== (value as VersionReference).revisionId;
    case "VersionDefinition": return reconciliationSorted((value as VersionDefinition).assertionRevisionIds);
    case "UpdateRelationDraft": {
      const item = value as UpdateRelationDraft;
      return new Set([item.source.versionId, item.source.revisionId, item.target.versionId, item.target.revisionId]).size === 4
        && new Set(item.evidence.map((e) => JSON.stringify([e.assertionRevisionId, e.category, e.selector]))).size === item.evidence.length;
    }
    case "WorkVersion": {
      const item = value as WorkVersion, ids = [item.versionId, item.revisionId, item.decisionRevisionId];
      return new Set(ids).size === 3 && (item.previousRevisionId === null || !ids.includes(item.previousRevisionId));
    }
    case "VersionRelation": {
      const item = value as VersionRelation, own = [item.relationId, item.revisionId, item.decisionRevisionId];
      const endpoints = [item.assertion.source.versionId, item.assertion.source.revisionId, item.assertion.target.versionId, item.assertion.target.revisionId];
      return new Set(own).size === 3 && own.every((id) => !endpoints.includes(id));
    }
    case "VersionPreference": {
      const item = value as VersionPreference, ids = [item.decisionId, item.revisionId, item.workId, item.workRevisionId, item.commandDecisionRevisionId, item.selected.versionId, item.selected.revisionId];
      return new Set(ids).size === ids.length && (item.previousRevisionId === null || !ids.includes(item.previousRevisionId));
    }
    case "VersionPlacement": {
      const item = value as VersionPlacement;
      return reconciliationSorted(item.workIds) && !item.workIds.includes(item.versionId) && (item.state === "assigned") === (item.workIds.length === 1);
    }
    case "PreferenceState": {
      const item = value as PreferenceState;
      return item.state === "not-reported" ? item.preferenceRevisionId === null && item.selected === null : item.preferenceRevisionId !== null && item.selected !== null;
    }
    case "VersionPlan": {
      const item = value as VersionPlan;
      if (!reconciliationSorted(item.workIds)) return false;
      if (item.action !== "prefer" && item.previousPreferenceRevisionId !== null) return false;
      return item.action === "register" ? item.definition !== null && item.version === null && item.relation === null
        : item.action === "revise" ? item.definition !== null && item.version !== null && item.relation === null
          : item.action === "relate" ? item.definition === null && item.version === null && item.relation !== null
            : item.workIds.length === 1 && item.definition === null && item.version !== null && item.relation === null;
    }
    case "VersionContext": {
      const item = value as VersionContext;
      const groups = [item.works.map((w) => w.workId), item.versions.map((v) => v.versionId), item.placements.map((p) => p.versionId),
        item.relations.map((r) => r.revisionId), item.preferences.map((p) => p.revisionId), item.sources.map((s) => s.assertionRevisionId)];
      return importDigest(item.contextSha256) && groups.every((ids) => new Set(ids).size === ids.length)
        && item.works.every((w) => w.disposition === "active")
        && reconciliationSameSet(groups[1]!, groups[2]!) && reconciliationSameSet(groups[0]!, item.preferenceStates.map((p) => p.workId))
        && item.versions.every((v) => v.definition.assertionRevisionIds.every((id) => groups[5]!.includes(id)))
        && item.relations.every((r) => groups[1]!.includes(r.assertion.source.versionId) && groups[1]!.includes(r.assertion.target.versionId)
          && r.assertion.evidence.every((e) => groups[5]!.includes(e.assertionRevisionId)))
        && item.sources.every((s) => s.assertion.projectId === item.projectId)
        && item.preferenceStates.every((s) => s.state === "not-reported" || item.preferences.some((p) => p.revisionId === s.preferenceRevisionId
          && p.selected.versionId === s.selected?.versionId && p.selected.revisionId === s.selected?.revisionId));
    }
    case "VersionOutcome": {
      const item = value as VersionOutcome, own = [item.commandId, item.decisionId, item.decisionRevisionId];
      const revisions = [...item.versionRevisions.map((v) => v.revisionId), ...item.workStates.map((w) => w.revisionId),
        ...[item.relationRevisionId, item.preferenceRevisionId].filter((id) => id !== null)];
      return new Set(own).size === own.length && new Set(revisions).size === revisions.length && own.every((id) => !revisions.includes(id))
        && [item.versionRevisions.map((v) => v.versionId), item.workStates.map((w) => w.workId), item.dependencyRunIds].every((ids) => new Set(ids).size === ids.length)
        && item.workStates.length > 0 && item.workStates.every((w) => w.disposition === "active" && w.decisionRevisionId === item.decisionRevisionId);
    }
    case "VersionWorkPage": {
      const item = value as VersionWorkPage, ids = item.items.map((w) => w.workId);
      return reconciliationSorted(ids) && item.items.every((w) => w.disposition === "active")
        && (item.after === null || ids.every((id) => id > item.after!) && (item.nextAfter === null || item.nextAfter > item.after))
        && (item.nextAfter === null || ids.every((id) => id <= item.nextAfter!));
    }
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
    case "versions/works": {
      const request = command as VersionWorksRequest, reply = result as VersionWorkPage;
      return request.after === reply.after && reply.items.length <= request.limit;
    }
    case "versions/inspect": return (command as VersionInspectRequest).revisionId === (result as WorkVersion).revisionId;
    case "versions/context": {
      const request = command as VersionContextRequest, reply = result as VersionContext;
      const {contextSha256, ...context} = reply;
      if (!reconciliationSameSet(request.workIds, reply.works.map((w) => w.workId)) || contextSha256 !== await reconciliationFingerprint(context)) return false;
      for (const work of reply.works) {
        const placed = new Set(reply.placements.filter((p) => p.workIds.includes(work.workId)).map((p) => p.versionId));
        const own = reply.preferences.filter((p) => p.workId === work.workId);
        const candidates = own.length ? own : reply.preferences.filter((p) => placed.has(p.selected.versionId));
        const preference = candidates.at(-1), standing = reply.preferenceStates.find((p) => p.workId === work.workId)!;
        if (!preference) { if (standing.state !== "not-reported") return false; continue; }
        const status = await reconciliationFingerprint([reply.versions.filter((v) => placed.has(v.versionId)),
          reply.placements.filter((p) => placed.has(p.versionId)), reply.relations.filter((r) => placed.has(r.assertion.source.versionId) || placed.has(r.assertion.target.versionId))]);
        const valid = own.length > 0 && reply.placements.some((p) => p.versionId === preference.selected.versionId && p.workIds.length === 1 && p.workIds[0] === work.workId)
          && work.previousRevisionId === preference.workRevisionId && work.decisionRevisionId === preference.commandDecisionRevisionId
          && reply.versions.some((v) => v.versionId === preference.selected.versionId && v.revisionId === preference.selected.revisionId)
          && preference.membershipSha256 === await reconciliationFingerprint(work.assertionRevisionIds) && preference.statusSha256 === status;
        if (standing.state !== (valid ? "current" : "requires-review") || standing.preferenceRevisionId !== preference.revisionId) return false;
      }
      return true;
    }
    case "versions/preview": {
      const request = command as VersionPreviewRequest, reply = result as VersionPreview;
      return request.plan.contextSha256 === reply.contextSha256 && reply.planSha256 === await reconciliationFingerprint(request.plan);
    }
    case "versions/commit": {
      const request = (command as VersionCommitRequest).command, reply = result as VersionOutcome, plan = request.plan;
      if (request.commandId !== reply.commandId || reply.planSha256 !== await reconciliationFingerprint(plan)
        || reply.workStates.some((w) => !plan.workIds.includes(w.workId))
        || (reply.relationRevisionId !== null) !== (plan.action === "relate") || (reply.preferenceRevisionId !== null) !== (plan.action === "prefer")) return false;
      const changed = plan.action === "relate" ? [plan.relation!.source, plan.relation!.target] : plan.action === "revise" ? [plan.version!] : [];
      if (plan.action === "register" ? reply.versionRevisions.length !== 1 || reply.workStates.length !== 1
        : !reconciliationSameSet(changed.map((v) => v.versionId), reply.versionRevisions.map((v) => v.versionId))
          || changed.some((v) => reply.versionRevisions.some((r) => r.revisionId === v.revisionId))) return false;
      return reply.dependencyRunIds.length === reply.workStates.length + changed.length + (plan.previousPreferenceRevisionId !== null ? 1 : 0)
        && (plan.action !== "prefer" || reply.workStates.length === 1);
    }
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
