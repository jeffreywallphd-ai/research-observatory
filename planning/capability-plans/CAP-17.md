---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-17
title: Technical report and study-results integration
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-17.S01
- CAP-17.S02
- CAP-17.S03
- CAP-17.S04
- CAP-17.S05
- CAP-17.S06
decisions:
- id: CAP-17-D01
  title: Artifact custody
  candidates:
  - Store technical reports and study artifacts in the project private artifact vault by default
  - Upload all reports to a remote model/provider during intake
  recommendation: Store technical reports and study artifacts in the project private artifact vault by default
  recommendation_basis: Unpublished results are highly sensitive and local-first custody preserves the existing trust boundary.
  selected_option: Store technical reports and study artifacts in the project private artifact vault by default
  status: accepted
  required_adr: ADR-RESULT-ARTIFACT-CUSTODY
- id: CAP-17-D02
  title: Supported artifact families
  candidates:
  - Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters
  - Treat every upload as an unstructured PDF
  recommendation: Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters
  recommendation_basis: Native structured inputs preserve more semantics and reduce extraction error.
  selected_option: Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters
  status: accepted
  required_adr: null
- id: CAP-17-D03
  title: Revision lineage
  candidates:
  - Use immutable artifact revisions with correction and supersession relationships
  - Overwrite prior reports when a corrected file is uploaded
  recommendation: Use immutable artifact revisions with correction and supersession relationships
  recommendation_basis: Study-result provenance and manuscript staleness require complete version history.
  selected_option: Use immutable artifact revisions with correction and supersession relationships
  status: accepted
  required_adr: null
- id: CAP-17-D04
  title: Confidentiality and rights
  candidates:
  - Apply artifact classification, project access, egress policy, retention and export controls at intake
  - Rely on folder location and user memory
  recommendation: Apply artifact classification, project access, egress policy, retention and export controls at intake
  recommendation_basis: Policy must travel with every derivative record and external call.
  selected_option: Apply artifact classification, project access, egress policy, retention and export controls at intake
  status: accepted
  required_adr: null
- id: CAP-17-D05
  title: Parsing strategy
  candidates:
  - Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback
  - Use one LLM prompt to read all uploaded formats
  recommendation: Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback
  recommendation_basis: Deterministic structure extraction improves anchors, reproducibility and cost.
  selected_option: Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback
  status: accepted
  required_adr: null
- id: CAP-17-D06
  title: Result domain
  candidates:
  - Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records
  - Flatten all outcomes into generic claim/value strings
  recommendation: Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records
  recommendation_basis: Method-plural result types preserve the meaning and validation requirements of different studies.
  selected_option: Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records
  status: accepted
  required_adr: ADR-STUDY-RESULT-DOMAIN
- id: CAP-17-D07
  title: Quantitative fields
  candidates:
  - Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported
  - Store only effect direction and p-value
  recommendation: Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported
  recommendation_basis: Manuscript claims need sufficient statistical context and missing fields must remain explicit.
  selected_option: Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported
  status: accepted
  required_adr: null
- id: CAP-17-D08
  title: Qualitative fields
  candidates:
  - Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status
  - Convert qualitative findings into pseudo-effect sizes
  recommendation: Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status
  recommendation_basis: Qualitative integrity requires source-linked interpretive records without forced quantification.
  selected_option: Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status
  status: accepted
  required_adr: null
- id: CAP-17-D09
  title: Mixed and technical findings
  candidates:
  - Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records
  - Store a prose summary only
  recommendation: Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records
  recommendation_basis: Mixed-method and technical claims depend on how evidence streams and configurations relate.
  selected_option: Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records
  status: accepted
  required_adr: null
- id: CAP-17-D10
  title: Tabular exchange
  candidates:
  - Use Frictionless Table Schema for portable result-table descriptors and validation
  - Invent a project-specific CSV convention without a schema
  recommendation: Use Frictionless Table Schema for portable result-table descriptors and validation
  recommendation_basis: Portable field types, constraints, missing values and keys improve reproducibility and export.
  selected_option: Use Frictionless Table Schema for portable result-table descriptors and validation
  status: accepted
  required_adr: null
- id: CAP-17-D11
  title: Evidence anchoring
  candidates:
  - Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks
  - Cite only the report filename
  recommendation: Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks
  recommendation_basis: Result verification and later correction require exact source location.
  selected_option: Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks
  status: accepted
  required_adr: null
- id: CAP-17-D12
  title: Plan-versus-actual reconciliation
  candidates:
  - Compare approved design/protocol with reported conduct and preserve both states
  - Rewrite the original study design to match the report
  recommendation: Compare approved design/protocol with reported conduct and preserve both states
  recommendation_basis: Transparent deviations are essential for methods/results drafting and review.
  selected_option: Compare approved design/protocol with reported conduct and preserve both states
  status: accepted
  required_adr: null
- id: CAP-17-D13
  title: Deviation handling
  candidates:
  - Create a neutral deviation ledger with materiality, explanation, consequence and human adjudication
  - Automatically label deviations as misconduct or errors
  recommendation: Create a neutral deviation ledger with materiality, explanation, consequence and human adjudication
  recommendation_basis: The system should surface discrepancies without making unsupported normative judgments.
  selected_option: Create a neutral deviation ledger with materiality, explanation, consequence and human adjudication
  status: accepted
  required_adr: null
- id: CAP-17-D14
  title: Verification model
  candidates:
  - Use independent machine checks plus sampled/full human verification based on consequence and confidence
  - Promote extracted results directly to verified
  recommendation: Use independent machine checks plus sampled/full human verification based on consequence and confidence
  recommendation_basis: Study-result evidence is consequential and requires explicit promotion.
  selected_option: Use independent machine checks plus sampled/full human verification based on consequence and confidence
  status: accepted
  required_adr: null
- id: CAP-17-D15
  title: Evidence graph extension
  candidates:
  - Add StudyRun, Result, Finding, AnalysisArtifact, Table, Figure and Deviation entities linked to claims and manuscripts
  - Keep report results outside the scholarly graph
  recommendation: Add StudyRun, Result, Finding, AnalysisArtifact, Table, Figure and Deviation entities linked to claims and manuscripts
  recommendation_basis: A unified graph enables dependency, support and contradiction reasoning across literature and study evidence.
  selected_option: Add StudyRun, Result, Finding, AnalysisArtifact, Table, Figure and Deviation entities linked to claims and manuscripts
  status: accepted
  required_adr: null
- id: CAP-17-D16
  title: Change propagation
  candidates:
  - Mark dependent manuscript claims, sections and reviews stale when verified result/report state changes
  - Leave downstream drafts unchanged after corrections
  recommendation: Mark dependent manuscript claims, sections and reviews stale when verified result/report state changes
  recommendation_basis: Publication outputs must not silently rely on superseded evidence.
  selected_option: Mark dependent manuscript claims, sections and reviews stale when verified result/report state changes
  status: accepted
  required_adr: null
- id: CAP-17-D17
  title: Evidence-package export
  candidates:
  - Export RO-Crate metadata, JSON-LD/JSON records, Frictionless tables, source manifests and checksums
  - Export only a PDF summary
  recommendation: Export RO-Crate metadata, JSON-LD/JSON records, Frictionless tables, source manifests and checksums
  recommendation_basis: A machine- and human-readable package supports audit, reuse and manuscript transfer.
  selected_option: Export RO-Crate metadata, JSON-LD/JSON records, Frictionless tables, source manifests and checksums
  status: accepted
  required_adr: ADR-RESULT-EVIDENCE-PACKAGE
- id: CAP-17-D18
  title: No-result-invention policy
  candidates:
  - Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature
  - Allow the model to infer plausible missing values
  recommendation: Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature
  recommendation_basis: The platform must never manufacture study findings.
  selected_option: Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-17 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-17` — Technical report and study-results integration |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-17/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Ingest private technical reports of empirical work, extract and verify actual methods/results, reconcile them with planned designs, and make source-anchored result evidence available to manuscript drafting.

Immutable study-artifact packages feed format-native parsing, typed quantitative/qualitative result records, plan-versus-actual reconciliation, independent verification, result graph projection and selective dependency invalidation.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Unpublished technical reports and supplements remain confidential, rights-aware, immutable, and versioned.
- Methods, results, tables, figures, deviations, null/mixed findings, and uncertainty are source-anchored and human verified.
- The platform never invents or reverse-engineers unreported empirical results and visibly blocks manuscript use of unresolved records.
- Changes to authoritative reports propagate staleness to dependent drafts, reviews, tables, figures, and exports.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-17.S01` | Private technical-report and study-artifact intake | Unpublished study results enter through a confidential, rights-aware, versioned channel. | W8 | P0 | CAP-15.S01.T03 |
| `CAP-17.S02` | Technical-report parsing and result extraction | Methods and results become structured candidates linked to exact report evidence. | W8 | P0 | CAP-17.S01.T03 |
| `CAP-17.S03` | Study-plan and result reconciliation | Actual study conduct and results are distinguished from plans and verified before authoring. | W8 | P0 | CAP-17.S02.T03, CAP-15.S05.T03 |
| `CAP-17.S04` | Results evidence graph and dependency propagation | Verified study results become durable evidence with complete downstream impact tracking. | W8 | P0 | CAP-17.S03.T03, CAP-09.S01.T03 |
| `CAP-17.S05` | Technical Reports & Results workspace | Researchers can inspect, verify, and approve result evidence for downstream manuscripts. | W8 | P0 | CAP-17.S04.T03 |
| `CAP-17.S06` | Results integration production acceptance | Technical-report and result evidence is trustworthy enough for controlled manuscript use. | W8 | P0 | CAP-17.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before presenting the packet, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. The strongest recommendation is preselected as the resolved default. Reviewers may confirm it, select another listed option with rationale, or request a revised candidate set. Capability approval accepts all current selections at once. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-17-D01` | Artifact custody | A. Store technical reports and study artifacts in the project private artifact vault by default<br>B. Upload all reports to a remote model/provider during intake | **Store technical reports and study artifacts in the project private artifact vault by default** | Unpublished results are highly sensitive and local-first custody preserves the existing trust boundary. | ADR-RESULT-ARTIFACT-CUSTODY |
| `CAP-17-D02` | Supported artifact families | A. Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters<br>B. Treat every upload as an unstructured PDF | **Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters** | Native structured inputs preserve more semantics and reduce extraction error. | None |
| `CAP-17-D03` | Revision lineage | A. Use immutable artifact revisions with correction and supersession relationships<br>B. Overwrite prior reports when a corrected file is uploaded | **Use immutable artifact revisions with correction and supersession relationships** | Study-result provenance and manuscript staleness require complete version history. | None |
| `CAP-17-D04` | Confidentiality and rights | A. Apply artifact classification, project access, egress policy, retention and export controls at intake<br>B. Rely on folder location and user memory | **Apply artifact classification, project access, egress policy, retention and export controls at intake** | Policy must travel with every derivative record and external call. | None |
| `CAP-17-D05` | Parsing strategy | A. Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback<br>B. Use one LLM prompt to read all uploaded formats | **Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback** | Deterministic structure extraction improves anchors, reproducibility and cost. | None |
| `CAP-17-D06` | Result domain | A. Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records<br>B. Flatten all outcomes into generic claim/value strings | **Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records** | Method-plural result types preserve the meaning and validation requirements of different studies. | ADR-STUDY-RESULT-DOMAIN |
| `CAP-17-D07` | Quantitative fields | A. Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported<br>B. Store only effect direction and p-value | **Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported** | Manuscript claims need sufficient statistical context and missing fields must remain explicit. | None |
| `CAP-17-D08` | Qualitative fields | A. Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status<br>B. Convert qualitative findings into pseudo-effect sizes | **Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status** | Qualitative integrity requires source-linked interpretive records without forced quantification. | None |
| `CAP-17-D09` | Mixed and technical findings | A. Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records<br>B. Store a prose summary only | **Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records** | Mixed-method and technical claims depend on how evidence streams and configurations relate. | None |
| `CAP-17-D10` | Tabular exchange | A. Use Frictionless Table Schema for portable result-table descriptors and validation<br>B. Invent a project-specific CSV convention without a schema | **Use Frictionless Table Schema for portable result-table descriptors and validation** | Portable field types, constraints, missing values and keys improve reproducibility and export. | None |
| `CAP-17-D11` | Evidence anchoring | A. Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks<br>B. Cite only the report filename | **Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks** | Result verification and later correction require exact source location. | None |
| `CAP-17-D12` | Plan-versus-actual reconciliation | A. Compare approved design/protocol with reported conduct and preserve both states<br>B. Rewrite the original study design to match the report | **Compare approved design/protocol with reported conduct and preserve both states** | Transparent deviations are essential for methods/results drafting and review. | None |
| `CAP-17-D13` | Deviation handling | A. Create a neutral deviation ledger with materiality, explanation, consequence and human adjudication<br>B. Automatically label deviations as misconduct or errors | **Create a neutral deviation ledger with materiality, explanation, consequence and human adjudication** | The system should surface discrepancies without making unsupported normative judgments. | None |
| `CAP-17-D14` | Verification model | A. Use independent machine checks plus sampled/full human verification based on consequence and confidence<br>B. Promote extracted results directly to verified | **Use independent machine checks plus sampled/full human verification based on consequence and confidence** | Study-result evidence is consequential and requires explicit promotion. | None |
| `CAP-17-D15` | Evidence graph extension | A. Add StudyRun, Result, Finding, AnalysisArtifact, Table, Figure and Deviation entities linked to claims and manuscripts<br>B. Keep report results outside the scholarly graph | **Add StudyRun, Result, Finding, AnalysisArtifact, Table, Figure and Deviation entities linked to claims and manuscripts** | A unified graph enables dependency, support and contradiction reasoning across literature and study evidence. | None |
| `CAP-17-D16` | Change propagation | A. Mark dependent manuscript claims, sections and reviews stale when verified result/report state changes<br>B. Leave downstream drafts unchanged after corrections | **Mark dependent manuscript claims, sections and reviews stale when verified result/report state changes** | Publication outputs must not silently rely on superseded evidence. | None |
| `CAP-17-D17` | Evidence-package export | A. Export RO-Crate metadata, JSON-LD/JSON records, Frictionless tables, source manifests and checksums<br>B. Export only a PDF summary | **Export RO-Crate metadata, JSON-LD/JSON records, Frictionless tables, source manifests and checksums** | A machine- and human-readable package supports audit, reuse and manuscript transfer. | ADR-RESULT-EVIDENCE-PACKAGE |
| `CAP-17-D18` | No-result-invention policy | A. Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature<br>B. Allow the model to infer plausible missing values | **Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature** | The platform must never manufacture study findings. | None |

Every decision is **resolved by the documented recommendation**: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires an explicit rationale. Approval remains a separate authorization gate for the complete capability and all slice plans.

## 5. Cross-slice architecture contract

Immutable study-artifact packages feed format-native parsing, typed quantitative/qualitative result records, plan-versus-actual reconciliation, independent verification, result graph projection and selective dependency invalidation.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The approved Technical Reports & Results workspace keeps report source, versions, exact anchors, extracted values, deviations, verification and manuscript eligibility in one source-first workflow.

Approved reference exposure: `technical-reports.html`, `document-reader.html`, `parsing-quality.html`, `audit-lineage.html`, `evidence-matrix.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Reports are confidential and local by default; egress is denied unless explicitly permitted; documents and tables are untrusted; manuscript use requires verified result eligibility.

The capability must treat documents, model files, provider responses, archives, URLs, imported data and rich text as untrusted. Least privilege, schema validation, path/destination controls, bounded resources, output encoding, redacted diagnostics and explicit egress policy apply at each trust boundary. The system may recommend and organize evidence but may not fabricate sources, permissions, performance, approval, methodological validity or completion evidence.

## 8. Capability-wide verification strategy

The verification program combines task tests, slice integration, capability end-to-end acceptance and independent review. It must include:

- Contract and schema compatibility across all six slices and affected neighboring capabilities.
- Representative success paths plus material denial, cancellation, restart, migration and recovery paths.
- Security, privacy, rights and research-integrity attack fixtures.
- Accessibility and governed-reference conformance for user-facing work.
- Performance, endurance, resource and cost evidence against declared profiles.
- Clean-environment packaging/deployment tests for each applicable target.
- Criterion-to-evidence manifests tied to the reviewed commit and immutable fixture/model/provider versions.

## 9. Long-running execution contract

After one-time approval, `taskctl capability start CAP-17` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [x] All listed decisions have the researched recommendation preselected and accepted; any override must carry rationale.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-17 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `RO_CRATE` | [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) | RO-Crate Community | Research-object metadata and portability. |
| `DATACITE47` | [DataCite Metadata Schema 4.7](https://schema.datacite.org/meta/kernel-4/) | DataCite | Persistent-identifier-ready metadata for research artifacts and related resources. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `NIST_SSDF` | [Secure Software Development Framework SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | NIST | Secure development and release controls. |
| `FRICTIONLESS_TABLE` | [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) | Frictionless Data | Portable JSON-declared schemas for CSV/tabular result exchange, validation and missing values. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) | W3C | Revision-aware source, manuscript and review-location selectors. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `TOP` | [Transparency and Openness Promotion Guidelines](https://www.cos.io/initiatives/top-guidelines) | Center for Open Science | Transparency, preregistration and openness policies. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |
| `ICMJE_AI` | [ICMJE Use of Artificial Intelligence in Publishing](https://www.icmje.org/recommendations/browse/artificial-intelligence/) | ICMJE | Human accountability, confidentiality and transparent disclosure for AI-assisted publication work. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision review/override | Export from `planning/review-site/CAP-17/index.html` and apply with `planctl`; feedback alone does not approve execution. |
