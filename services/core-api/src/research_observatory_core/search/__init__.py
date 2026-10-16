"""UI-independent lexical query contract for local Core clients."""

from .contracts import (
    ANALYZER_ID,
    GRAMMAR_VERSION,
    MAX_DEPTH,
    MAX_NODES,
    MAX_QUERY_LENGTH,
    MAX_WIRE_BYTES,
    QueryDiagnostic,
    QueryDocument,
    QueryError,
    QueryNode,
    load_query_document,
)
from .grammar import parse_query

__all__ = [
    "ANALYZER_ID",
    "GRAMMAR_VERSION",
    "MAX_DEPTH",
    "MAX_NODES",
    "MAX_QUERY_LENGTH",
    "MAX_WIRE_BYTES",
    "QueryDiagnostic",
    "QueryDocument",
    "QueryError",
    "QueryNode",
    "load_query_document",
    "parse_query",
]
