# CAP-05.S05.T01 — extract and reconcile reference-list entries

Claim base: `8071903db413ae3dae1acd1c2232607dbc70e917`; campaign
`codex/w2-implementation`, owner `codex-w2-implementation`.

Authority: the approved W2 packet at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, the canonical backlog task,
[S05 §§5–9.1, 11–14, 19](../../planning/slice-plans/CAP-05/CAP-05.S05-references-citation-contexts-tables-and-figures.md),
accepted ADR-0027/0029 and existing canonical identity/provenance contracts.
CAP-05.S03.T03 is DONE; CP08 is independently approved and integrated.
The current experience reference is RO-UI-ACADEMIC-MINIMAL-1.9, Document Reader
outline, inert source inspection and selected-work/version return context.

This task adds local reference enrichment. It does not create or merge Works,
verify scholarship, enable network destinations, change accepted document v1,
select a parser/model, implement citation contexts/tables/figures, change resource
tier/release criteria, or develop the automation framework. Reader LT01 and the
owner-accepted parser observation remain historical; neither is replayed here.

| Material boundary | Planned proof |
|---|---|
| Ordered raw reference content and author/year/title observations | Authored synthetic JATS/TEI and unstructured fixtures; exact raw contributor ranges, NFC/CRLF/astral offsets, field namespace/format/ancestry attribution. Missing fields and unavailable attributes stay unknown. |
| Identity, matching and uncertainty | Reuse accepted reference/node IDs, exact document/structure hashes and CAP-04 Work revisions. Test unique valid identifiers, competing/disputed/reassigned identifiers, unanchored parser identifiers, and fuzzy component scores with human-review state. No raw reference becomes a fake import SourceAddress or new Work. |
| Complete current match set | Reuse the indexed exact assessment and ranking kernel. Recheck complete matching-key results, current sealed Work heads/members and input freshness before publication/delivery. New duplicate/membership between preparation and writer invalidates publication; no pagination or denied-source omission proves false uniqueness. |
| Protected authority and provenance | Current Native/project/session/human/Intent/privacy and source inspect+derive, plus current target-source authority, throughout publication/read/delivery. Actual SQLCipher/encrypted-object tests exercise denial, project/actor/revision substitution, changed rights and impacted inputs. All material source/Work/decision dependencies survive the common 64-input limit through existing traversable manifests. |
| Atomicity and recovery | New encrypted, versioned enrichment separate from immutable accepted document. Command/actor/payload replay and expected enrichment predecessor. Fault before commit, cancellation, corrupt payload, close/reopen, and retry preserve accepted document and old enrichment; no partial complete coverage. |
| Exact predecessor and migration | Capture a literal populated current v27 fixture before product edits, binding its existing schema/profile fingerprints and retained rows/ciphertexts. Additive backup-first v28 migration; interrupt each material step and prove exact predecessor rollback and retry. Never edit earlier fixture bytes or migration authorities. |
| Resource boundary | Explicit reference/catalog/field/byte/comparison/wall-time limits and current cancellation checks; visible failure leaves original/base document usable. No models or 8/16 GiB hardware runs. |
| Real principal and experience | Fixed opaque Native IPC → bounded Core route → protected source and canonical reconciliation → encrypted durable collection → typed Reader inspection. One actual owned current Native/Core/renderer vertical proof plus keyboard, safe failure, late-response/lock clearing and exact source/return tests. Existing Reader admission accounts retained protected views. |
| Evidence truth | Commit implementation before criterion-linked focused checks and expanded independent task review. Authored/synthetic parsing tests are not signed parser/model or scholarly-quality evidence. Preserve adverse observations. |

Read-only adversarial preflight: incorporated from `reader_rights_task_review`.
It identified complete match-set uniqueness, impacted Work/source/decision
freshness, unavailable TEI attributes, full provenance beyond 64 inputs, and
per-reference ranking rather than irrelevant target–target comparisons. This
advice is not task approval.

Selected coverage: reference extraction/contracts, affected reconciliation,
actual protected persistence/authority, predecessor migration/rollback, strict
Core/Native/client boundary, focused product types/style/schema and Reader
conformance. Full unchanged profiles, citation/table/figure outcomes, broad
performance, installer/platform/resource tiers and release qualification remain
slice/Wave work. No mandatory new human gate was identified for this task.
