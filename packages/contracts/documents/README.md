# Document contracts

Acquisition location, selection and receipt schemas retain exact original-copy
provenance. The parser schemas below add staged structure under ADR-0028/0029:

| Schema | Value |
|---|---|
| `document-ir.v1.schema.json` | Ordered raw-preserving DocumentIR and quality dimensions |
| `parser-selection.v1.schema.json` | Deterministic recorded source/parser preference |
| `parse-request.v1.schema.json` | Exact protected source, producer and job/attempt binding |
| `parse-result.v1.schema.json` | Staged success, content-free failure or cancellation |
| `native-structure.v1.schema.json` | Native source element/attribute hierarchy, original byte anchors and owned decoded-text runs |
| `retained-parse-result.v1.schema.json` | Encrypted successful output receipt bound to its source and physical attempt |
| `document-structure.v1.schema.json` | Lossless structure with Core-generated revision-scoped element UUIDs |
| `document-revision-acceptance.v1.schema.json` | Exact result confirmation and expected head, with no caller-supplied actor or structure |
| `document-revision.v1.schema.json` | Immutable human-accepted structural revision, decision, source binding and identity map |
| `viewer-source-selector.v1.schema.json` | Opaque exact attachment/original and optional accepted normalized revision |
| `viewer-source-metadata.v1.schema.json` | Current full source identity, with original and normalized revisions kept distinct |
| `viewer-text-chunk.v1.schema.json` | Exact accepted element and bounded Unicode text chunk; separately governed derivation |

Generate with `python packages/contracts/documents/generate_parser_schema.py`;
`--check` rejects drift. JSON Schema proves shape. The additional graph, mapping,
geometry, selection, producer and current authority rules are checked by Core.
The `x-research-observatory-semanticRules` inventory describes that distinction.

All values are protected research data. Worker echoes and selection records are
never grants; callers cannot name paths, repositories or parser loaders. IDs in
the IR are staged local IDs, not canonical element identities. Failed/cancelled
results contain no IR. Inspection-only fallback cannot silently become canonical.
The revision service advances the original document head only through explicit
human structural acceptance. It keeps the source-copy revision distinct from
the retained parse result and accepted normalized revision. Existing IDs and
deep links stay attached to their immutable revision; a reparse never overwrites
an earlier acceptance. Structural acceptance remains scholarly `unverified`.

See [document parsing](../../../docs/architecture/document-parsing.md) for
normalization, offset mapping, selection and protected-source boundaries.

The private native viewer protocol is described in [source viewing](source-viewing.md).
Its schemas describe values; they neither expose a public Core route nor grant
source access. Native/Core current-authority and exact-source checks remain
required at read and delivery.
