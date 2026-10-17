# ruff: noqa: E501
"""Compile only the approved search API's closed DTOs and client semantics."""

import json

OPERATIONS = (
    ("validateLexicalQuery", "validate", "SearchValidationCommand", "SearchQueryValidation"),
    ("executeLexicalSearch", "run", "SearchRunCommand", "SearchJob"),
    ("inspectLexicalSearch", "status", "SearchAddress", "SearchJob"),
    ("pageLexicalSearch", "page", "SearchPageCommand", "SearchPage"),
    ("explainLexicalSearch", "explain", "SearchExplanationCommand", "SearchExplanation"),
    ("cancelLexicalSearch", "cancel", "SearchAddress", "SearchJob"),
)


def _expression(schema, value, references):
    known = {
        "$ref",
        "additionalProperties",
        "anyOf",
        "oneOf",
        "const",
        "default",
        "description",
        "discriminator",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
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
        raise ValueError(f"Unsupported search schema keywords: {sorted(set(schema) - known)}")
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        if not name.isidentifier():
            raise ValueError("Unsupported search schema reference")
        references.add(name)
        return f"searchShape{name}({value})"
    if "const" in schema:
        return f"{value} === {json.dumps(schema['const'])}"
    if "enum" in schema:
        return "(" + " || ".join(f"{value} === {json.dumps(item)}" for item in schema["enum"]) + ")"
    variants = schema.get("anyOf", schema.get("oneOf"))
    if variants is not None:
        return "(" + " || ".join(_expression(item, value, references) for item in variants) + ")"
    kind = schema["type"]
    if kind == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError("Search wire objects must be closed")
        fields, required = schema["properties"], schema.get("required", [])
        optional = [name for name in fields if name not in required]
        predicates = [f"exactKeys(item, {json.dumps(required)}, {json.dumps(optional)})"]
        for key, field in fields.items():
            expression = _expression(field, f"item[{json.dumps(key)}]", references)
            if key not in required:
                expression = f"(!Object.hasOwn(item,{json.dumps(key)}) || ({expression}))"
            predicates.append(expression)
        return f"searchObject({value}, (item) => " + " && ".join(f"({part})" for part in predicates) + ")"
    if kind == "array":
        element = _expression(schema["items"], "element", references)
        return (
            f"(Array.isArray({value}) && {value}.length >= {schema.get('minItems', 0)} "
            f"&& {value}.length <= {schema.get('maxItems', 1000)} && {value}.every((element: unknown) => {element}))"
        )
    if kind == "string":
        result = f"importText({value}, {schema.get('maxLength', 65536)}, {schema.get('minLength', 0)})"
        if "pattern" in schema:
            result += f" && new RegExp({json.dumps(schema['pattern'])}, 'u').test({value} as string)"
        return "(" + result + ")"
    if kind in ("integer", "number"):
        result = (
            f"integer({value}, {schema.get('minimum', -9007199254740991)}, {schema.get('maximum', 9007199254740991)})"
            if kind == "integer"
            else f"(typeof {value} === 'number' && Number.isFinite({value}) "
            f"&& {value} >= {schema.get('minimum', '-Number.MAX_VALUE')} && {value} <= {schema.get('maximum', 'Number.MAX_VALUE')})"
        )
        for key, operator in (("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")):
            if key in schema:
                result += f" && ({value} as number) {operator} {schema[key]}"
        return "(" + result + ")"
    if kind == "boolean":
        return f"typeof {value} === 'boolean'"
    if kind == "null":
        return f"{value} === null"
    raise ValueError("Unsupported search schema type")


def render_search(openapi):
    schemas = openapi["components"]["schemas"]
    pending = {name for _, _, request, response in OPERATIONS for name in (request, response)}
    blocks = {}
    while pending:
        name = min(pending)
        pending.remove(name)
        references: set[str] = set()
        expression = _expression(schemas[name], "value", references)
        blocks[name] = (
            f"function searchShape{name}(value: unknown): value is {name} {{\n"
            f"  return ({expression}) && searchSemantics({json.dumps(name)}, value);\n}}\n"
        )
        pending.update(references - blocks.keys())
    methods = []
    for operation, route, request, response in OPERATIONS:
        path = "/projects/search/" + route
        if openapi["paths"][path]["post"]["operationId"] != operation:
            raise ValueError("Search operation identity differs")
        root_check = "" if route == "validate" else " || !projectRoot(command.root)"
        methods.append(f'''    async {operation}(value: {request}): Promise<{response}> {{
      const command = searchOwned(value);
      if (!searchShape{request}(command){root_check}) throw new Error("RO-CORE-REQUEST-INVALID");
      const body = JSON.stringify(command);
      if (new TextEncoder().encode(body).length > 262144) throw new Error("RO-CORE-REQUEST-INVALID");
      const result = await requestJson(transport, {{ method: "POST", path: "{path}", body, ifMatch: null, idempotencyKey: null }}, decode{response});
      if (!searchReply("{route}", command, result)) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    }},''')
    decoders = [
        f"""export function decode{name}(value: unknown): {name} | null {{
  const owned = searchOwned(value);
  return searchShape{name}(owned) ? owned : null;
}}"""
        for name in sorted({response for _, _, _, response in OPERATIONS})
    ]
    return "\n".join([RUNTIME, *[blocks[name] for name in sorted(blocks)], *decoders]), "\n".join(methods)


RUNTIME = r"""
function searchObject(value: unknown, check: (item: Readonly<Record<string, unknown>>) => boolean): boolean {
  const item = record(value); return item !== null && check(item);
}

function searchOwned(value: unknown): unknown {
  let remaining = 30000;
  function own(item: unknown, depth: number): unknown {
    if (--remaining < 0 || depth > 16) throw new Error("search-value-bound");
    if (typeof item === "string") {
      if (item.length > 524288 || /[\uD800-\uDFFF]/u.test(item)) throw new Error("search-string-bound");
      return item;
    }
    if (item === null || typeof item === "boolean") return item;
    if (typeof item === "number" && Number.isFinite(item)) return item;
    if (typeof item !== "object" || item === null) throw new Error("search-value-type");
    const prototype = Object.getPrototypeOf(item), descriptors = Object.getOwnPropertyDescriptors(item);
    if (Array.isArray(item)) {
      if (prototype !== Array.prototype || item.length > 1000 || Reflect.ownKeys(item).length !== item.length + 1)
        throw new Error("search-array-shape");
      return Object.freeze(Array.from({ length: item.length }, (_, index) => {
        const descriptor = descriptors[String(index)];
        if (!descriptor || !("value" in descriptor)) throw new Error("search-array-accessor");
        return own(descriptor.value, depth + 1);
      }));
    }
    if (prototype !== Object.prototype && prototype !== null) throw new Error("search-object-prototype");
    const owned: Record<string, unknown> = Object.create(null);
    for (const key of Reflect.ownKeys(item)) {
      const descriptor = descriptors[key as string];
      if (typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key)
        || !descriptor || !("value" in descriptor) || !descriptor.enumerable) throw new Error("search-object-shape");
      owned[key] = own(descriptor.value, depth + 1);
    }
    return Object.freeze(owned);
  }
  try {
    const owned = own(value, 0);
    return new TextEncoder().encode(JSON.stringify(owned)).length <= 524288 ? owned : null;
  } catch { return null; }
}

function searchSemantics(name: string, value: unknown): boolean {
  const item = value as any;
  switch (name) {
    case "SearchFilters": return item.yearFrom === null || item.yearTo === null
      || item.yearFrom === undefined || item.yearTo === undefined || item.yearFrom <= item.yearTo;
    case "CodepointRange": return item.start < item.end;
    case "SearchSnippet": {
      const length = [...item.text].length;
      return item.end - item.start === length && item.highlights.every((span: CodepointRange, index: number) =>
        span.start < span.end && span.end <= length && (index === 0 || item.highlights[index - 1].end <= span.start));
    }
    case "SearchDocumentTarget": return item.selection === null ? item.locationState === "unanchored-preview"
      : item.locationState === "contained-text-selection" && item.selection.revisionId === item.revisionId
        && item.selection.normalizedRange !== null;
    case "SearchExecution": return JSON.stringify(item.fieldWeights) === "[8,4,1,2,2,10,1,1]"
      && Number.isFinite(Date.parse(item.validatedAt)) && (item.expiresAt === null ||
        Number.isFinite(Date.parse(item.expiresAt)) && item.validatedAt < item.expiresAt);
    case "SearchHit": return item.source === null || item.source.source.workId === item.workId
      && item.source.source.workRevisionId === item.workRevisionId;
    case "SearchPage": {
      const seen = new Set<string>();
      const stop = item.startPosition + item.hits.length;
      if (stop > item.execution.resultCount || (item.nextCursor === null) !== (stop === item.execution.resultCount)
        || item.hits.length === 0 && stop !== item.execution.resultCount
        || item.afterCursor === null && item.startPosition !== 0) return false;
      return item.hits.every((hit: SearchHit, index: number) => {
        if (seen.has(hit.itemId) || hit.position !== item.startPosition + index + 1 || hit.source !== null
          && hit.source.source.projectId !== item.execution.projectId) return false;
        seen.add(hit.itemId);
        if (index === 0) return true;
        const previous = item.hits[index - 1];
        return hit.position === previous.position + 1 && (hit.score < previous.score
          || hit.score === previous.score && previous.itemId < hit.itemId);
      }) && (item.hits.length > 0 || item.nextCursor === null)
        && (item.nextCursor === null || item.hits.at(-1).position < item.execution.resultCount);
    }
    case "SearchExplanation": {
      const leaves = new Set<string>();
      let sum = 0;
      for (const component of item.components as SearchContribution[]) {
        if (leaves.has(component.leafSha256)) return false;
        leaves.add(component.leafSha256); sum += component.score;
      }
      return Math.abs(sum - item.score) <= Math.max(1e-12, Math.abs(item.score) * 1e-12);
    }
    case "SearchQueryValidation": {
      if (!item.valid) return item.originalQuery === null && item.normalizedQuery === null
        && item.queryDocument === null && item.diagnostic !== null;
      if (item.originalQuery === null || item.normalizedQuery === null || item.queryDocument === null || item.diagnostic !== null)
        return false;
      try {
        const query = JSON.parse(item.queryDocument);
        return query.originalQuery === item.originalQuery && query.normalizedQuery === item.normalizedQuery
          && query.schemaVersion === "1.0" && query.grammarVersion === "ro-search-query-1"
          && query.analyzerId === "ro-unicode61-diacritics2-1";
      } catch { return false; }
    }
    default: return true;
  }
}

function searchReply(route: string, command: unknown, result: unknown): boolean {
  const request = command as any, reply = result as any;
  if (route === "validate") return !reply.valid || reply.originalQuery === request.query;
  if ((reply.execution?.projectId ?? reply.projectId) !== request.projectId) return false;
  if (route === "run") return reply.commandId === request.commandId;
  if ((reply.execution?.jobId ?? reply.jobId) !== request.jobId) return false;
  if (route === "explain") return reply.itemId === request.itemId;
  if (route !== "page") return true;
  if (reply.hits.length > (request.limit ?? 50) || reply.afterCursor !== (request.after ?? null)) return false;
  if (request.after === null || request.after === undefined) return reply.startPosition === 0;
  try {
    const text = request.after.replace(/-/g, "+").replace(/_/g, "/");
    const cursor = JSON.parse(atob(text + "=".repeat((4 - text.length % 4) % 4)));
    return cursor.nextPosition === reply.startPosition && cursor.revisionId === reply.execution.revisionId;
  } catch { return false; }
}
"""
