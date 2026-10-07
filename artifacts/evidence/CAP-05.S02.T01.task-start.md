# CAP-05.S02.T01 acceptance closure

Claim base: `47a97a44b3da06abdd07a07d8cb410f8bb909b30`.
Authority: approved W2 packet `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
CAP-05.S02 section 9.1, accepted ADR-0028/0029 and the three current backlog criteria.
CAP-05.S01.T03 and CAP-03.S04.T02 are DONE; W2.CP07 is independently approved.

This task defines the portable parser/IR/selection and staged validation boundary.
Native adapters and isolated Docling execution belong to T02/T03; durable revisions,
accepted heads and human acceptance belong to S03. No UI, migration, dependency,
cryptography or automation-framework development is selected.

| Material boundary | Planned proof |
|---|---|
| Raw order, NFC/newline-only normalization and half-open code-point offsets | Unicode 16 text gold and independent origin expectations for CRLF, expansion, reordered/noncontiguous marks, blocking, Hangul/Indic, supplementary characters and empty text; invalid mapping/locator rejection. |
| Versioned portable structure | Strict schema/wire round-trip for ordered nodes, parents, pages/rotation, locations, references/citations, tables/spans, figures and separate unknown quality/confidence; no paths or implementation objects; copied/forged model and nonfinite/surrogate rejection. |
| R01.F01: semantic text and linked-node identity | Reference, citation-marker and table-cell spans must use the node's projection and lie within its decoded text and source location. Reject other-node/projection substitution and missing node text in direct IR and staged handoff; retain legitimate contained spans and reordered/noncontiguous NFC contributors. The first implementation checked each span's mapping independently but omitted this relationship; focused red regressions precede remediation. |
| Deterministic selection | Native-first selection under permutations, stable ties, duplicate conflicts, unavailable/excluded sources, unknown equivalence and separately recorded inspection-only fallback; same Work/version alone is not copy equivalence. |
| Trusted attempt/source/producer | Bind job/attempt, project, attachment/document/candidate/source/Work/version revisions, original digest/length/format and trusted parser/config/assets; reject stale attempts and substituted fields. Local imports may legitimately lack remote receipts. |
| Protected read and delivery | Public-only consumer over an actual protected database and encrypted source; current inspect plus derive in one writer transaction, prompt read closure, current actor/Intent/privacy and trusted session/cancellation delivery fence. Exercise denial before execution and authority change before delivery. |
| Failed/cancelled parsing | Discriminated staged results cannot grant canonical write/acceptance; crash, malformed or partial success, cancellation and stale authority expose no usable IR and leave canonical document facts unchanged. |

The first behavioral tests precede product edits. Existing independent preflight
`artifacts/tmp/CAP-05.S02.T01.advisory-s01-01.json` identifies four finite details
incorporated above; it is advisory, not task approval or qualifying evidence.
No mandatory new gate was discovered. Relevant unit/schema/type/architecture and
protected-read integration checks are selected. Native parsing, packaged/offline
CPU conversion and numeric resource targets remain T02/T03 and slice qualification;
full profiles remain checkpoint/Wave checks. No old runtime result is claimed fresh.
