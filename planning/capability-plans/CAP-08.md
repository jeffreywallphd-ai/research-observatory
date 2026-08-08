---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-08
title: Evidence schemas, extraction, verification, and adjudication
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-08.S01
- CAP-08.S02
- CAP-08.S03
- CAP-08.S04
- CAP-08.S05
- CAP-08.S06
decisions:
- id: CAP-08-D01
  title: Ontology authority
  candidates:
  - Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  - One universal fixed ontology; unconstrained per-project JSON blobs
  recommendation: Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  recommendation_basis: A stable core supports interoperability while packs preserve disciplinary plurality and contestability.
  selected_option: Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  status: accepted
  required_adr: null
- id: CAP-08-D02
  title: Extraction unit
  candidates:
  - Source passage/section candidates with immutable document revision and multi-selector anchors
  - Extract from unconstrained whole-document prompts; store page number only
  recommendation: Source passage/section candidates with immutable document revision and multi-selector anchors
  recommendation_basis: Bounded passages improve provenance and verification while multi-selector anchors survive controlled document revisions.
  selected_option: Source passage/section candidates with immutable document revision and multi-selector anchors
  status: accepted
  required_adr: null
- id: CAP-08-D03
  title: Evidence state model
  candidates:
  - Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions
  - Flatten status to accepted/rejected or overwrite prior machine output
  recommendation: Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions
  recommendation_basis: The richer model preserves epistemic status, disagreement, human authority and recalculation lineage.
  selected_option: Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions
  status: accepted
  required_adr: null
- id: CAP-08-D04
  title: Verification independence
  candidates:
  - Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans
  - Let the extractor self-certify its own output
  recommendation: Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans
  recommendation_basis: Independence reduces correlated confirmation and makes unsupported inference visible.
  selected_option: Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans
  status: accepted
  required_adr: null
- id: CAP-08-D05
  title: Confidence representation
  candidates:
  - Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  - Single uncalibrated “AI confidence” number
  recommendation: Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  recommendation_basis: Users need to know what is uncertain and which action could reduce it.
  selected_option: Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  status: accepted
  required_adr: null
- id: CAP-08-D06
  title: Core scope
  candidates:
  - Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs.
  - Large universal scholarly ontology.
  recommendation: Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs.
  recommendation_basis: A small core protects interoperability while limiting ontology reification.
  selected_option: Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs.
  status: accepted
  required_adr: null
- id: CAP-08-D07
  title: Schema format
  candidates:
  - JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.
  - Free-form JSON or OWL-only authoring.
  recommendation: JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.
  recommendation_basis: JSON Schema is implementable across desktop/server; JSON-LD provides linked-data interchange without making RDF the local runtime.
  selected_option: JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.
  status: accepted
  required_adr: null
- id: CAP-08-D08
  title: Evolution
  candidates:
  - Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview.
  - Edit schema in place and reinterpret old records.
  recommendation: Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview.
  recommendation_basis: Evidence must retain the schema under which it was produced and reviewed.
  selected_option: Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview.
  status: accepted
  required_adr: null
- id: CAP-08-D09
  title: Selection strategy
  candidates:
  - Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale.
  - Send full PDFs by default.
  recommendation: Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale.
  recommendation_basis: Bounded context improves cost, privacy and source attribution while preserving reproducibility.
  selected_option: Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale.
  status: accepted
  required_adr: null
- id: CAP-08-D10
  title: Absence handling
  candidates:
  - Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema.
  - Force a value or use null without meaning.
  recommendation: Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema.
  recommendation_basis: Missingness and inference are epistemically distinct and analytically important.
  selected_option: Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema.
  status: accepted
  required_adr: null
- id: CAP-08-D11
  title: Normalization
  candidates:
  - Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance.
  - Replace source language with closest ontology term automatically.
  recommendation: Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance.
  recommendation_basis: Construct variants and disciplinary terminology must not be collapsed silently.
  selected_option: Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance.
  status: accepted
  required_adr: null
- id: CAP-08-D12
  title: Record identity
  candidates:
  - UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  - Use field/value as primary key.
  recommendation: UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  recommendation_basis: Multiple independent observations, interpretations and disputes can share values without being the same record.
  selected_option: UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  status: accepted
  required_adr: null
- id: CAP-08-D13
  title: Transition authority
  candidates:
  - Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record.
  - Direct status column edits.
  recommendation: Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record.
  recommendation_basis: The audit model must explain who changed epistemic status and why.
  selected_option: Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record.
  status: accepted
  required_adr: null
- id: CAP-08-D14
  title: Confidence
  candidates:
  - Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  - Average model confidence values.
  recommendation: Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  recommendation_basis: Components arise from different processes and should not be collapsed without an explicit analysis.
  selected_option: Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  status: accepted
  required_adr: null
- id: CAP-08-D15
  title: Independence
  candidates:
  - Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably independently evaluated model route.
  - Ask extractor to self-critique in the same context.
  recommendation: Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably independently evaluated model route.
  recommendation_basis: Context separation reduces confirmation and makes inputs auditable.
  selected_option: Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably independently evaluated model route.
  status: accepted
  required_adr: null
- id: CAP-08-D16
  title: Decision dimensions
  candidates:
  - Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments.
  - One pass/fail or confidence score.
  recommendation: Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments.
  recommendation_basis: Different failures require different recovery actions.
  selected_option: Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments.
  status: accepted
  required_adr: null
- id: CAP-08-D17
  title: Human sampling
  candidates:
  - Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals.
  - Review a convenient untracked sample.
  recommendation: Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals.
  recommendation_basis: Calibration and governance require a known sampling frame and reproducible selection.
  selected_option: Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals.
  status: accepted
  required_adr: null
- id: CAP-08-D18
  title: Grid architecture
  candidates:
  - Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance.
  - Client-load all records or embed an uncontrolled spreadsheet engine.
  recommendation: Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance.
  recommendation_basis: The matrix must scale while preserving authorization and domain transitions.
  selected_option: Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance.
  status: accepted
  required_adr: null
- id: CAP-08-D19
  title: Editing
  candidates:
  - All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow.
  - In-place overwrite of accepted evidence.
  recommendation: All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow.
  recommendation_basis: Source-grounded history and staleness require controlled commands.
  selected_option: All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow.
  status: accepted
  required_adr: null
- id: CAP-08-D20
  title: Source interaction
  candidates:
  - Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell.
  - Open unrelated modal/browser window for each source.
  recommendation: Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell.
  recommendation_basis: Source-first review should be fast and accessible without losing table context.
  selected_option: Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell.
  status: accepted
  required_adr: null
- id: CAP-08-D21
  title: Assignment independence
  candidates:
  - Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed.
  - Collaborative live editing as the only mode.
  recommendation: Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed.
  recommendation_basis: Independent coding is required for interpretable agreement and can coexist with later discussion.
  selected_option: Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed.
  status: accepted
  required_adr: null
- id: CAP-08-D22
  title: Agreement metrics
  candidates:
  - 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  - One universal agreement percent.
  recommendation: 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  recommendation_basis: Different data/assignment structures require different statistics and transparent denominators.
  selected_option: 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  status: accepted
  required_adr: null
- id: CAP-08-D23
  title: Adjudication
  candidates:
  - Create a named resolution record referencing all coder records and allow unresolved outcome.
  - Replace coder records with consensus value.
  recommendation: Create a named resolution record referencing all coder records and allow unresolved outcome.
  recommendation_basis: Disagreement may be theoretically meaningful and must remain inspectable.
  selected_option: Create a named resolution record referencing all coder records and allow unresolved outcome.
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-08 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-08` — Evidence schemas, extraction, verification, and adjudication |
| Objective | Transform full text into source-grounded, mode-sensitive evidence records that distinguish observation, machine extraction, inference, verification, dispute, adjudication, and staleness. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-08.S01`, `CAP-08.S02`, `CAP-08.S03`, `CAP-08.S04`, `CAP-08.S05`, `CAP-08.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Transform full text into source-grounded, mode-sensitive evidence records that distinguish observation, machine extraction, inference, verification, dispute, adjudication, and staleness.**

Production-ready exit criteria:

- Researchers can define and version extraction schemas and ontology packs without losing original author wording.
- Every extracted value links to exact source anchors, extractor configuration, verifier outcome, confidence dimensions, and human review state.
- Evidence matrices support comparison, disagreement, adjudication, and export without turning missing information into invented data.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-08.S01` | Core ontology and schema-pack registry | A small stable scholarly core can be extended by domain and method packs under explicit version governance. | `CAP-03.S01.T03`, `CAP-07.S04.T02` |
| `CAP-08.S02` | Source-grounded extraction pipeline | Schema-constrained extraction selects relevant source context and emits candidate evidence without fabricating absent fields. | `CAP-08.S01.T03`, `CAP-05.S03.T03`, `CAP-07.S04.T02` |
| `CAP-08.S03` | Evidence record, status, confidence, and uncertainty model | Extracted content is stored with decomposed certainty and explicit epistemic status. | `CAP-08.S02.T03`, `CAP-03.S03.T02` |
| `CAP-08.S04` | Independent evidence verification | A separate verifier tests passage entailment, schema fit, anchor validity, and unsupported inference. | `CAP-08.S03.T03`, `CAP-07.S05.T03` |
| `CAP-08.S05` | Evidence matrix and source-first analysis UI | Researchers can inspect, filter, compare, pivot, correct, and trace evidence at scale. | `CAP-08.S04.T02`, `CAP-01.S02.T01` |
| `CAP-08.S06` | Coder comparison, adjudication, and evidence export | Human plurality and review outcomes are measurable and preserved. | `CAP-08.S05.T03`, `CAP-04.S04.T02` |

The planning reviewer must test the complete vertical: inputs from previous capabilities, each slice handoff, researcher workflow, durable/provenance behavior, degraded/recovery path and downstream contract. Slice-level optimization may not break the capability-wide path.

## 3. Decision-making protocol

1. Read every slice plan, backlog task, architecture boundary, workflow/page contract and relevant benchmark/source.
2. For each material choice, compare credible candidates using functionality, security, privacy/rights, portability, maintainability, licensing, local resource use, recovery, evaluation quality and downstream compatibility.
3. Present the leading candidates and an explicit recommendation. Avoid asking an open-ended question when evidence supports a best direction.
4. Record the accepted selection, rejected alternatives, evidence and replaceability/migration boundary in this packet and any required ADR.
5. Validate that the selected set is internally compatible and can complete all slices end to end.
6. Resolve all reasonably foreseeable decisions before campaign start. Implementation should not repeatedly interrupt the human for ordinary engineering choices.

## 4. Decision register

| ID | Decision | Recommended selection | Credible alternative | Why recommended / replacement boundary | Basis |
|---|---|---|---|---|---|
| `CAP-08-D01` | **Ontology authority** | Small stable core plus versioned, forkable schema/ontology packs; original source wording retained | One universal fixed ontology; unconstrained per-project JSON blobs | A stable core supports interoperability while packs preserve disciplinary plurality and contestability. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D02` | **Extraction unit** | Source passage/section candidates with immutable document revision and multi-selector anchors | Extract from unconstrained whole-document prompts; store page number only | Bounded passages improve provenance and verification while multi-selector anchors survive controlled document revisions. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-08-D03` | **Evidence state model** | Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions | Flatten status to accepted/rejected or overwrite prior machine output | The richer model preserves epistemic status, disagreement, human authority and recalculation lineage. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D04` | **Verification independence** | Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans | Let the extractor self-certify its own output | Independence reduces correlated confirmation and makes unsupported inference visible. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D05` | **Confidence representation** | Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty | Single uncalibrated “AI confidence” number | Users need to know what is uncertain and which action could reduce it. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D06` | **Core scope** | Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs. | Large universal scholarly ontology. | A small core protects interoperability while limiting ontology reification. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D07` | **Schema format** | JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export. | Free-form JSON or OWL-only authoring. | JSON Schema is implementable across desktop/server; JSON-LD provides linked-data interchange without making RDF the local runtime. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-08-D08` | **Evolution** | Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview. | Edit schema in place and reinterpret old records. | Evidence must retain the schema under which it was produced and reviewed. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D09` | **Selection strategy** | Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale. | Send full PDFs by default. | Bounded context improves cost, privacy and source attribution while preserving reproducibility. | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) |
| `CAP-08-D10` | **Absence handling** | Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema. | Force a value or use null without meaning. | Missingness and inference are epistemically distinct and analytically important. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-08-D11` | **Normalization** | Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance. | Replace source language with closest ontology term automatically. | Construct variants and disciplinary terminology must not be collapsed silently. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D12` | **Record identity** | UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate. | Use field/value as primary key. | Multiple independent observations, interpretations and disputes can share values without being the same record. | [RFC 9562 - Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562.html) |
| `CAP-08-D13` | **Transition authority** | Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record. | Direct status column edits. | The audit model must explain who changed epistemic status and why. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D14` | **Confidence** | Store component assessments and calibration bands, with “unknown/not assessed” first-class. | Average model confidence values. | Components arise from different processes and should not be collapsed without an explicit analysis. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D15` | **Independence** | Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably independently evaluated model route. | Ask extractor to self-critique in the same context. | Context separation reduces confirmation and makes inputs auditable. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D16` | **Decision dimensions** | Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments. | One pass/fail or confidence score. | Different failures require different recovery actions. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D17` | **Human sampling** | Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals. | Review a convenient untracked sample. | Calibration and governance require a known sampling frame and reproducible selection. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-08-D18` | **Grid architecture** | Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance. | Client-load all records or embed an uncontrolled spreadsheet engine. | The matrix must scale while preserving authorization and domain transitions. | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) |
| `CAP-08-D19` | **Editing** | All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow. | In-place overwrite of accepted evidence. | Source-grounded history and staleness require controlled commands. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D20` | **Source interaction** | Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell. | Open unrelated modal/browser window for each source. | Source-first review should be fast and accessible without losing table context. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-08-D21` | **Assignment independence** | Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed. | Collaborative live editing as the only mode. | Independent coding is required for interpretable agreement and can coexist with later discussion. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-08-D22` | **Agreement metrics** | Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness. | One universal agreement percent. | Different data/assignment structures require different statistics and transparent denominators. | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) |
| `CAP-08-D23` | **Adjudication** | Create a named resolution record referencing all coder records and allow unresolved outcome. | Replace coder records with consensus value. | Disagreement may be theoretically meaningful and must remain inspectable. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |

### Review and approval

The best-in-class recommendation in every row is already the selected, accepted decision. Reviewers may confirm the complete set without editing individual choices, or replace a recommendation with another documented candidate and record an explicit rationale. The only remaining routine human gate is approval of this capability packet and all slice plans at one immutable commit.


## 5. Cross-slice architecture contract

- Preserve the authority order: canonical relational/provenance records and human decisions first; indexes, caches, graph projections, model outputs, rankings and generated artifacts remain versioned derivatives unless the Systems Design explicitly states otherwise.
- Stable ports isolate platform, storage, source, parser, model/provider, vector, graph, renderer and deployment adapters.
- Every durable output records source snapshot, schema/policy/model/tool versions, rights/privacy decisions, human decisions and dependency links.
- All long-running jobs are durable, idempotent where appropriate, cancellable, checkpointed, restartable and independently reviewable.
- The campaign remains local/Windows-first for the current waves while producing portable contracts and fixtures needed by CAP-14 macOS/Linux qualification.
- No later capability is implemented early except its documented interface/fixture seam.

## 6. Experience and workflow contract

Relevant approved pages: `schema-manager.html`, `evidence-matrix.html`, `document-reader.html`, `audit-lineage.html`

- The project use case determines the primary ordered workflow. Each page shows current stage, prior/next stage, expected output and completion/checkpoint state.
- All tools remain accessible as supporting tools with a clear route back to the primary workflow.
- Intentional changes require the style guide/workflow/page prototype to be updated, validated and human-approved before implementation.
- Accessibility, light/dark parity, offline/partial/error/recovery states and source/provenance inspection are capability exit requirements, not post-release polish.

## 7. Security, privacy, rights and research-integrity decisions

The reviewer must confirm the entire capability’s trust boundaries, data classes, authorization roles, secret/egress rules, rights/license handling, untrusted-content controls, logging/redaction, export behavior, model licenses and human scholarly authority. Where one slice’s output changes another slice’s rights or confidentiality exposure, the stricter policy travels with the object.

## 8. Capability-wide verification strategy

- **Contract:** all portable schemas, negative fixtures and adapter conformance.
- **Integration:** real local components, deterministic provider/source/model fixtures, transaction/outbox/dependency behavior.
- **End to end:** representative workflow across every slice with source inspection and human decision.
- **Recovery:** cancellation, process/application restart, corrupted derivative, migration, rollback/repair and project relocation.
- **Security/rights:** denial, malicious content, prompt injection, path/archive abuse, egress and export filters, redacted diagnostics.
- **Quality/evaluation:** capability-specific gold sets, ablations, calibration/error analysis and independent human samples.
- **Experience:** approved reference, adaptive navigation, keyboard/screen reader/zoom/reflow and light/dark visual checks.
- **Performance:** reference hardware/corpus budgets plus 20% regression threshold.
- **Independent review:** tests must demonstrate semantics, not merely execute code.

## 9. Long-running execution contract

Once approved and started, the agent should execute the whole capability slice by slice. It may make ordinary low-risk implementation choices within the accepted architecture, debug tests, refactor within module boundaries, select documented fallbacks and rerun evaluations without asking for confirmation. Progress is recorded through task/slice evidence and periodic concise updates rather than approval stops.

### Allowed pause classifications

- Core ontology changes would break already approved evidence records.
- A project schema encodes a consequential interpretive decision without human approval.
- Source anchors cannot be validated against immutable document revisions.
- Verifier evaluation is below the approved minimum for consequential fields.
- A governed UI/design change that requires a new approved reference.

Every pause records category, evidence, exact blocked task/slice, attempted alternatives, recommended next action and conditions for resume. Test failures and routine uncertainty are not pause reasons.

## 10. Plan and approval checklist

- [ ] All slice plans exist and pass `slice_plan_check.py` structurally.
- [ ] Every material decision has credible candidates, recommendation and accepted status.
- [ ] Required ADRs and design-reference changes are approved.
- [ ] Capability-wide architecture and end-to-end path are coherent.
- [ ] Fixtures, benchmarks, credentials/licenses, hardware and human authorities are available or approved stubs exist.
- [ ] Security/privacy/rights/research-integrity review is complete.
- [ ] All slice plans are approved at immutable commits.
- [ ] `python tools/planctl.py ready CAP-08 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) — Interoperable provenance entities, activities, agents and derivations.
- [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) — Multi-selector source anchors and revision-aware annotations.
- [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) — Scientific claim/evidence verification benchmark and rationale retrieval.
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) — Canonical structured-output and schema-pack validation.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
