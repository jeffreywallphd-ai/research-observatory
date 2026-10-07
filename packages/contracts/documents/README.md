# Document contracts

Acquisition location, selection and receipt schemas retain exact original-copy
provenance. The parser schemas below add staged structure under ADR-0028/0029:

| Schema | Value |
|---|---|
| `document-ir.v1.schema.json` | Ordered raw-preserving DocumentIR and quality dimensions |
| `parser-selection.v1.schema.json` | Deterministic recorded source/parser preference |
| `parse-request.v1.schema.json` | Exact protected source, producer and job/attempt binding |
| `parse-result.v1.schema.json` | Staged success, content-free failure or cancellation |

Generate with `python packages/contracts/documents/generate_parser_schema.py`;
`--check` rejects drift. JSON Schema proves shape. The additional graph, mapping,
geometry, selection, producer and current authority rules are checked by Core.
The `x-research-observatory-semanticRules` inventory describes that distinction.

All values are protected research data. Worker echoes and selection records are
never grants; callers cannot name paths, repositories or parser loaders. IDs in
the IR are staged local IDs, not canonical element identities. Failed/cancelled
results contain no IR. Inspection-only fallback cannot silently become canonical.
Only later explicit human acceptance can advance an accepted document head.

See [document parsing](../../../docs/architecture/document-parsing.md) for
normalization, offset mapping, selection and protected-source boundaries.
