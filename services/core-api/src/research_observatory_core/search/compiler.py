"""Bounded AST lowering to parameterized FTS/set operations over lawful rows."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import QueryDocument, QueryNode

_COLUMNS = {
    "title": "title",
    "abstract": "abstract",
    "full-text": "full_text",
    "authors": "authors",
    "venue": "venue",
    "identifiers": "identifiers",
    "tags": "tags",
    "decisions": "decisions",
}


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    sql: str
    parameters: tuple[str | int, ...] = field(repr=False)


def compile_query(document: QueryDocument) -> CompiledQuery:
    """Caller installs current `allowed_items`/`allowed_entries` in memory.

    Each leaf intersects the exact permitted entry set, so a denied full-text
    row cannot contribute to a metadata-only result. NOT complements that same
    current filtered item universe; compound expressions can span lawful rows
    of one item. These temporary tables confer no canonical authority themselves.
    """
    if not isinstance(document, QueryDocument):
        from .contracts import fail

        fail("invalid-query-document")
    document.validate()
    clauses: list[str] = []
    parameters: list[str | int] = []

    def lower(node: QueryNode) -> str:
        if node.kind in ("and", "or", "not"):
            children = tuple(lower(child) for child in node.operands)
            if node.kind == "not":
                body = "SELECT item_id FROM allowed_items EXCEPT SELECT item_id FROM " + children[0]
            else:
                join = " INTERSECT " if node.kind == "and" else " UNION "
                body = join.join("SELECT item_id FROM " + child for child in children)
        elif node.kind == "year":
            # Operator was validated against the closed numeric operator set.
            body = (
                "SELECT r.item_id FROM search_rows r JOIN allowed_entries a ON a.entry_id=r.entry_id "
                "JOIN allowed_items u ON u.item_id=r.item_id "
                "WHERE r.year " + str(node.operator) + " ?"
            )
            parameters.append(node.value)  # type: ignore[arg-type]
        else:
            # All user syntax is inside a single escaped FTS phrase. In
            # particular '-', quotes and operator words cannot become syntax.
            phrase = '"' + str(node.value).replace('"', '""') + '"'
            if node.field is not None:
                phrase = _COLUMNS[node.field] + " : " + phrase
            parameters.append(phrase)
            body = (
                "SELECT r.item_id FROM search_fts JOIN search_rows r ON r.rowid=search_fts.rowid "
                "JOIN allowed_entries a ON a.entry_id=r.entry_id "
                "JOIN allowed_items u ON u.item_id=r.item_id WHERE search_fts MATCH ?"
            )
        name = "q" + str(len(clauses))
        clauses.append(name + " AS (" + body + ")")
        return name

    result = lower(document.ast)
    return CompiledQuery(
        "WITH " + ",".join(clauses) + " SELECT item_id FROM " + result + " ORDER BY item_id", tuple(parameters)
    )


__all__ = ["CompiledQuery", "compile_query"]
