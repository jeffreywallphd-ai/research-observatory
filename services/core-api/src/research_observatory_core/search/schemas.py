"""Portable structural schemas; Core additionally verifies query/snapshot semantics."""

from __future__ import annotations

from .contracts import (
    ANALYZER_ID,
    GRAMMAR_VERSION,
    MAX_DEPTH,
    MAX_NODES,
    MAX_OPERANDS,
    MAX_QUERY_LENGTH,
    MAX_WIRE_BYTES,
    TEXT_FIELDS,
)


def analyzer_profile() -> dict:
    return {
        "schemaVersion": "1.0",
        "analyzerId": ANALYZER_ID,
        "engine": "sqlite-fts5",
        "tokenizer": "unicode61",
        "removeDiacritics": 2,
        "stemming": False,
        "sourceNormalization": "unchanged",
    }


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def query_schemas() -> dict[str, dict]:
    """Return new mappings on every call so clients cannot mutate a global contract."""
    node_ref = {"$ref": "#/$defs/node"}
    definitions: dict = {}
    for kind in ("literal", "phrase"):
        value = {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_LENGTH}
        definitions[kind] = _object(
            {
                "kind": {"const": kind},
                "field": {"enum": [None, *TEXT_FIELDS]},
                "value": value,
            }
        )
    definitions["year"] = _object(
        {
            "kind": {"const": "year"},
            "field": {"const": "year"},
            "value": {"type": "integer", "minimum": 1, "maximum": 9999},
            "operator": {"enum": ["=", ">", ">=", "<", "<="]},
        }
    )
    for kind in ("and", "or", "not"):
        definitions[kind] = _object(
            {
                "kind": {"const": kind},
                "operands": {
                    "type": "array",
                    "items": node_ref,
                    "minItems": 1 if kind == "not" else 2,
                    "maxItems": 1 if kind == "not" else MAX_OPERANDS,
                },
            }
        )
    definitions["node"] = {"oneOf": [{"$ref": "#/$defs/" + kind} for kind in definitions]}
    document = _object(
        {
            "schemaVersion": {"const": "1.0"},
            "grammarVersion": {"const": GRAMMAR_VERSION},
            "analyzerId": {"const": ANALYZER_ID},
            "originalQuery": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_LENGTH},
            "normalizedQuery": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_LENGTH},
            "ast": node_ref,
        }
    )
    document["$defs"] = definitions
    document["description"] = (
        "Private local search snapshot. Structural validation alone is insufficient: use Core load_query_document "
        "for strict decoding, original/normalized/AST binding, Unicode policy and expanded-tree budgets."
    )
    document["x-runtimeLimits"] = {
        "queryCodepoints": MAX_QUERY_LENGTH,
        "astDepth": MAX_DEPTH,
        "expandedAstNodes": MAX_NODES,
        "operandsPerJunction": MAX_OPERANDS,
        "wireBytes": MAX_WIRE_BYTES,
    }
    diagnostic = _object(
        {
            "code": {"type": "string", "pattern": "^[a-z]+(?:-[a-z]+)*$"},
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 0},
            "line": {"type": "integer", "minimum": 1},
            "column": {"type": "integer", "minimum": 1},
        }
    )
    profile = _object({name: {"const": value} for name, value in analyzer_profile().items()})
    schemas = {
        "query-document.schema.json": document,
        "query-diagnostic.schema.json": diagnostic,
        "analyzer-profile.schema.json": profile,
    }
    for filename, schema in schemas.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = "https://research-observatory.local/contracts/search/" + filename
    return schemas
