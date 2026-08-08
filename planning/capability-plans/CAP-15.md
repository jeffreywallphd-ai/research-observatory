---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-15
title: Empirical study design and protocol development
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-15.S01
- CAP-15.S02
- CAP-15.S03
- CAP-15.S04
- CAP-15.S05
- CAP-15.S06
decisions:
- id: CAP-15-D01
  title: Study object
  candidates:
  - Represent StudyDesign as a versioned canonical object linked to intent, opportunity, evidence and decisions
  - Generate a disposable prose protocol from a chat
  recommendation: Represent StudyDesign as a versioned canonical object linked to intent, opportunity, evidence and decisions
  recommendation_basis: Structured, versioned design state supports comparison, staleness and downstream manuscripts.
  selected_option: Represent StudyDesign as a versioned canonical object linked to intent, opportunity, evidence and decisions
  status: accepted
  required_adr: ADR-STUDY-DESIGN-DOMAIN
- id: CAP-15-D02
  title: Method plurality
  candidates:
  - Support quantitative, qualitative, mixed, computational, field and design-science families through extensible method packs
  - Use one universal experimental-study schema
  recommendation: Support quantitative, qualitative, mixed, computational, field and design-science families through extensible method packs
  recommendation_basis: The platform serves multiple scholarly traditions and must not impose one epistemology.
  selected_option: Support quantitative, qualitative, mixed, computational, field and design-science families through extensible method packs
  status: accepted
  required_adr: null
- id: CAP-15-D03
  title: Question logic
  candidates:
  - Separate purposes, questions, propositions/hypotheses where appropriate, mechanisms, estimands/interpretive aims and inference limits
  - Treat every research question as a statistical hypothesis
  recommendation: Separate purposes, questions, propositions/hypotheses where appropriate, mechanisms, estimands/interpretive aims and inference limits
  recommendation_basis: Different research logics require different validation and reporting structures.
  selected_option: Separate purposes, questions, propositions/hypotheses where appropriate, mechanisms, estimands/interpretive aims and inference limits
  status: accepted
  required_adr: null
- id: CAP-15-D04
  title: Alternative generation
  candidates:
  - Generate multiple source-grounded design alternatives with tradeoffs and a recommendation
  - Generate one “best” design with no comparison
  recommendation: Generate multiple source-grounded design alternatives with tradeoffs and a recommendation
  recommendation_basis: Plural alternatives reveal assumptions and preserve researcher authority.
  selected_option: Generate multiple source-grounded design alternatives with tradeoffs and a recommendation
  status: accepted
  required_adr: null
- id: CAP-15-D05
  title: Design selection
  candidates:
  - Researcher adjudicates, combines or rejects alternatives and records rationale
  - Automatically select the highest-scoring design
  recommendation: Researcher adjudicates, combines or rejects alternatives and records rationale
  recommendation_basis: Methods choice is consequential scholarly judgment.
  selected_option: Researcher adjudicates, combines or rejects alternatives and records rationale
  status: accepted
  required_adr: null
- id: CAP-15-D06
  title: Sampling plan
  candidates:
  - Model target population/cases, frame, access, recruitment, inclusion, attrition and power/saturation rationale
  - Store only a target sample-size field
  recommendation: Model target population/cases, frame, access, recruitment, inclusion, attrition and power/saturation rationale
  recommendation_basis: Sampling adequacy and generalizability depend on a complete, design-specific plan.
  selected_option: Model target population/cases, frame, access, recruitment, inclusion, attrition and power/saturation rationale
  status: accepted
  required_adr: null
- id: CAP-15-D07
  title: Power and saturation
  candidates:
  - Use validated calculators/simulation or qualitative saturation rationale with assumptions and human review
  - Let an LLM invent a sample size
  recommendation: Use validated calculators/simulation or qualitative saturation rationale with assumptions and human review
  recommendation_basis: Sample rationale must be reproducible and method-appropriate.
  selected_option: Use validated calculators/simulation or qualitative saturation rationale with assumptions and human review
  status: accepted
  required_adr: null
- id: CAP-15-D08
  title: Measurement traceability
  candidates:
  - Link constructs to definitions, instruments/indicators, psychometric/credibility evidence, licensing and alternatives
  - Select measures by semantic similarity alone
  recommendation: Link constructs to definitions, instruments/indicators, psychometric/credibility evidence, licensing and alternatives
  recommendation_basis: Construct validity and rights depend on explicit traceability.
  selected_option: Link constructs to definitions, instruments/indicators, psychometric/credibility evidence, licensing and alternatives
  status: accepted
  required_adr: null
- id: CAP-15-D09
  title: Data collection
  candidates:
  - Version procedures, instruments, interventions, timing, checks, interview/observation protocols and computational run manifests
  - Keep procedural details only in free-form notes
  recommendation: Version procedures, instruments, interventions, timing, checks, interview/observation protocols and computational run manifests
  recommendation_basis: Implementable protocols require structured operational detail.
  selected_option: Version procedures, instruments, interventions, timing, checks, interview/observation protocols and computational run manifests
  status: accepted
  required_adr: null
- id: CAP-15-D10
  title: Analysis plan
  candidates:
  - Separate primary, secondary and exploratory analyses; record preprocessing, assumptions, diagnostics, missingness and robustness
  - Generate a generic list of statistical tests after data collection
  recommendation: Separate primary, secondary and exploratory analyses; record preprocessing, assumptions, diagnostics, missingness and robustness
  recommendation_basis: A priori analysis structure improves transparency and guards against undisclosed flexibility.
  selected_option: Separate primary, secondary and exploratory analyses; record preprocessing, assumptions, diagnostics, missingness and robustness
  status: accepted
  required_adr: null
- id: CAP-15-D11
  title: Qualitative/mixed support
  candidates:
  - Provide coding/interpretive and integration logic without coercing it into quantitative fields
  - Translate all qualitative work into variables and hypotheses
  recommendation: Provide coding/interpretive and integration logic without coercing it into quantitative fields
  recommendation_basis: APA JARS and method practice require distinct qualitative and mixed-method reporting needs.
  selected_option: Provide coding/interpretive and integration logic without coercing it into quantitative fields
  status: accepted
  required_adr: null
- id: CAP-15-D12
  title: Validity analysis
  candidates:
  - Model design-specific validity/quality threats, rival explanations, boundaries and sensitivity strategies
  - Use one generic “limitations” text box
  recommendation: Model design-specific validity/quality threats, rival explanations, boundaries and sensitivity strategies
  recommendation_basis: Threats must connect to design elements and mitigation evidence.
  selected_option: Model design-specific validity/quality threats, rival explanations, boundaries and sensitivity strategies
  status: accepted
  required_adr: null
- id: CAP-15-D13
  title: Outcome-contingent value
  candidates:
  - Specify contribution under supported, null, mixed and context-dependent findings
  - Assume only a positive result is publishable
  recommendation: Specify contribution under supported, null, mixed and context-dependent findings
  recommendation_basis: A rigorous design should create value without outcome fishing.
  selected_option: Specify contribution under supported, null, mixed and context-dependent findings
  status: accepted
  required_adr: null
- id: CAP-15-D14
  title: Ethics authority
  candidates:
  - Generate issues/checklists for human and institutional review; never claim IRB or ethics approval
  - Have the AI classify projects as exempt or approved
  recommendation: Generate issues/checklists for human and institutional review; never claim IRB or ethics approval
  recommendation_basis: Human-subject determinations remain with authorized people and institutions.
  selected_option: Generate issues/checklists for human and institutional review; never claim IRB or ethics approval
  status: accepted
  required_adr: null
- id: CAP-15-D15
  title: Data management
  candidates:
  - Create FAIR-aware data, metadata, access, retention, sharing and deletion plans with local policy overlays
  - Use one generic open-data recommendation
  recommendation: Create FAIR-aware data, metadata, access, retention, sharing and deletion plans with local policy overlays
  recommendation_basis: Data governance must account for confidentiality, rights and field norms.
  selected_option: Create FAIR-aware data, metadata, access, retention, sharing and deletion plans with local policy overlays
  status: accepted
  required_adr: null
- id: CAP-15-D16
  title: Preregistration
  candidates:
  - Export immutable, source-linked preregistration-ready packages; external submission remains an explicit human action
  - Automatically submit or alter registrations
  recommendation: Export immutable, source-linked preregistration-ready packages; external submission remains an explicit human action
  recommendation_basis: OSF registrations are frozen records and may use privacy/embargo controls.
  selected_option: Export immutable, source-linked preregistration-ready packages; external submission remains an explicit human action
  status: accepted
  required_adr: null
- id: CAP-15-D17
  title: Reporting guidance
  candidates:
  - Select method/venue reporting guidance from verified profiles such as JARS/EQUATOR and retain version/source
  - Embed one static checklist for all studies
  recommendation: Select method/venue reporting guidance from verified profiles such as JARS/EQUATOR and retain version/source
  recommendation_basis: Reporting requirements vary by study design and venue.
  selected_option: Select method/venue reporting guidance from verified profiles such as JARS/EQUATOR and retain version/source
  status: accepted
  required_adr: null
- id: CAP-15-D18
  title: Integrity audit
  candidates:
  - Detect missing components, unsupported choices, construct/measure inconsistency, circular logic and undisclosed deviations
  - Assign one opaque design-quality score
  recommendation: Detect missing components, unsupported choices, construct/measure inconsistency, circular logic and undisclosed deviations
  recommendation_basis: Actionable findings and evidence are more useful than a scalar verdict.
  selected_option: Detect missing components, unsupported choices, construct/measure inconsistency, circular logic and undisclosed deviations
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-15 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-15` — Empirical study design and protocol development |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-15/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Use literature evidence, opportunity dossiers, domain knowledge, and researcher constraints to propose, compare, and formalize rigorous empirical study designs without displacing scholarly or ethics authority.

Study designs are first-class versioned domain objects linked to intent, evidence, opportunities, methods, decisions and later manuscript/result capabilities. Extensible method packs preserve quantitative, qualitative, mixed, computational, field and design-science logics.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Multiple plausible study designs are compared through explicit assumptions, evidence, validity, ethics, feasibility, and alternative-outcome value.
- The selected protocol covers research logic, sampling, measurement, data collection, analysis, validity, ethics, data management, and reproducibility.
- Every consequential recommendation is source-linked or clearly labeled as inference, convention, researcher preference, or unresolved decision.
- The platform never implies IRB/ethics approval, preregistration, or methodological validity without human/institutional review.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-15.S01` | Study-design domain and evidence foundation | Study designs are first-class, versioned, source-grounded research objects. | W7 | P0 | CAP-10.S03.T03, CAP-09.S05.T03 |
| `CAP-15.S02` | Research logic and design alternatives | Researchers receive plural, evidence-backed design options and retain final authority. | W7 | P0 | CAP-15.S01.T03 |
| `CAP-15.S03` | Sampling, measurement, and data collection | The selected design contains an implementable and reviewable empirical data plan. | W7 | P0 | CAP-15.S02.T03 |
| `CAP-15.S04` | Analysis, validity, ethics, and reproducibility | The protocol states how evidence will be produced, evaluated, governed, and interpreted under alternative outcomes. | W7 | P0 | CAP-15.S03.T03 |
| `CAP-15.S05` | Study Design Studio and protocol exports | Researchers can produce a source-grounded, reviewable empirical protocol and analysis plan. | W7 | P0 | CAP-15.S04.T03 |
| `CAP-15.S06` | Study-design production acceptance | The study-design capability is production-ready, source-grounded, and expert-reviewed. | W7 | P0 | CAP-15.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before approval, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. Reviewers may accept the recommendation, select another listed option, or request a revised candidate set. Each accepted selection must include rationale and any ADR/reference requirement. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-15-D01` | Study object | A. Represent StudyDesign as a versioned canonical object linked to intent, opportunity, evidence and decisions<br>B. Generate a disposable prose protocol from a chat | **Represent StudyDesign as a versioned canonical object linked to intent, opportunity, evidence and decisions** | Structured, versioned design state supports comparison, staleness and downstream manuscripts. | ADR-STUDY-DESIGN-DOMAIN |
| `CAP-15-D02` | Method plurality | A. Support quantitative, qualitative, mixed, computational, field and design-science families through extensible method packs<br>B. Use one universal experimental-study schema | **Support quantitative, qualitative, mixed, computational, field and design-science families through extensible method packs** | The platform serves multiple scholarly traditions and must not impose one epistemology. | None |
| `CAP-15-D03` | Question logic | A. Separate purposes, questions, propositions/hypotheses where appropriate, mechanisms, estimands/interpretive aims and inference limits<br>B. Treat every research question as a statistical hypothesis | **Separate purposes, questions, propositions/hypotheses where appropriate, mechanisms, estimands/interpretive aims and inference limits** | Different research logics require different validation and reporting structures. | None |
| `CAP-15-D04` | Alternative generation | A. Generate multiple source-grounded design alternatives with tradeoffs and a recommendation<br>B. Generate one “best” design with no comparison | **Generate multiple source-grounded design alternatives with tradeoffs and a recommendation** | Plural alternatives reveal assumptions and preserve researcher authority. | None |
| `CAP-15-D05` | Design selection | A. Researcher adjudicates, combines or rejects alternatives and records rationale<br>B. Automatically select the highest-scoring design | **Researcher adjudicates, combines or rejects alternatives and records rationale** | Methods choice is consequential scholarly judgment. | None |
| `CAP-15-D06` | Sampling plan | A. Model target population/cases, frame, access, recruitment, inclusion, attrition and power/saturation rationale<br>B. Store only a target sample-size field | **Model target population/cases, frame, access, recruitment, inclusion, attrition and power/saturation rationale** | Sampling adequacy and generalizability depend on a complete, design-specific plan. | None |
| `CAP-15-D07` | Power and saturation | A. Use validated calculators/simulation or qualitative saturation rationale with assumptions and human review<br>B. Let an LLM invent a sample size | **Use validated calculators/simulation or qualitative saturation rationale with assumptions and human review** | Sample rationale must be reproducible and method-appropriate. | None |
| `CAP-15-D08` | Measurement traceability | A. Link constructs to definitions, instruments/indicators, psychometric/credibility evidence, licensing and alternatives<br>B. Select measures by semantic similarity alone | **Link constructs to definitions, instruments/indicators, psychometric/credibility evidence, licensing and alternatives** | Construct validity and rights depend on explicit traceability. | None |
| `CAP-15-D09` | Data collection | A. Version procedures, instruments, interventions, timing, checks, interview/observation protocols and computational run manifests<br>B. Keep procedural details only in free-form notes | **Version procedures, instruments, interventions, timing, checks, interview/observation protocols and computational run manifests** | Implementable protocols require structured operational detail. | None |
| `CAP-15-D10` | Analysis plan | A. Separate primary, secondary and exploratory analyses; record preprocessing, assumptions, diagnostics, missingness and robustness<br>B. Generate a generic list of statistical tests after data collection | **Separate primary, secondary and exploratory analyses; record preprocessing, assumptions, diagnostics, missingness and robustness** | A priori analysis structure improves transparency and guards against undisclosed flexibility. | None |
| `CAP-15-D11` | Qualitative/mixed support | A. Provide coding/interpretive and integration logic without coercing it into quantitative fields<br>B. Translate all qualitative work into variables and hypotheses | **Provide coding/interpretive and integration logic without coercing it into quantitative fields** | APA JARS and method practice require distinct qualitative and mixed-method reporting needs. | None |
| `CAP-15-D12` | Validity analysis | A. Model design-specific validity/quality threats, rival explanations, boundaries and sensitivity strategies<br>B. Use one generic “limitations” text box | **Model design-specific validity/quality threats, rival explanations, boundaries and sensitivity strategies** | Threats must connect to design elements and mitigation evidence. | None |
| `CAP-15-D13` | Outcome-contingent value | A. Specify contribution under supported, null, mixed and context-dependent findings<br>B. Assume only a positive result is publishable | **Specify contribution under supported, null, mixed and context-dependent findings** | A rigorous design should create value without outcome fishing. | None |
| `CAP-15-D14` | Ethics authority | A. Generate issues/checklists for human and institutional review; never claim IRB or ethics approval<br>B. Have the AI classify projects as exempt or approved | **Generate issues/checklists for human and institutional review; never claim IRB or ethics approval** | Human-subject determinations remain with authorized people and institutions. | None |
| `CAP-15-D15` | Data management | A. Create FAIR-aware data, metadata, access, retention, sharing and deletion plans with local policy overlays<br>B. Use one generic open-data recommendation | **Create FAIR-aware data, metadata, access, retention, sharing and deletion plans with local policy overlays** | Data governance must account for confidentiality, rights and field norms. | None |
| `CAP-15-D16` | Preregistration | A. Export immutable, source-linked preregistration-ready packages; external submission remains an explicit human action<br>B. Automatically submit or alter registrations | **Export immutable, source-linked preregistration-ready packages; external submission remains an explicit human action** | OSF registrations are frozen records and may use privacy/embargo controls. | None |
| `CAP-15-D17` | Reporting guidance | A. Select method/venue reporting guidance from verified profiles such as JARS/EQUATOR and retain version/source<br>B. Embed one static checklist for all studies | **Select method/venue reporting guidance from verified profiles such as JARS/EQUATOR and retain version/source** | Reporting requirements vary by study design and venue. | None |
| `CAP-15-D18` | Integrity audit | A. Detect missing components, unsupported choices, construct/measure inconsistency, circular logic and undisclosed deviations<br>B. Assign one opaque design-quality score | **Detect missing components, unsupported choices, construct/measure inconsistency, circular logic and undisclosed deviations** | Actionable findings and evidence are more useful than a scalar verdict. | None |

Every decision is resolved by the documented best-in-class recommendation: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires explicit rationale. Approval remains the one authorization gate for the capability and all slice plans.

## 5. Cross-slice architecture contract

Study designs are first-class versioned domain objects linked to intent, evidence, opportunities, methods, decisions and later manuscript/result capabilities. Extensible method packs preserve quantitative, qualitative, mixed, computational, field and design-science logics.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

Study Design Studio presents plural alternatives, evidence, tradeoffs, open decisions and an ordered path from research logic to a reviewable protocol and export.

Approved reference exposure: `study-design.html`, `intent-contract.html`, `evidence-matrix.html`, `audit-lineage.html`, `new-project.html`, `index.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Unpublished plans stay private by default; instrument rights and data-governance constraints are explicit; AI never claims ethics/IRB approval, invents methods or submits registrations without human action.

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

After one-time approval, `taskctl capability start CAP-15` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [ ] All listed decisions have a selected option, rationale and accepted status.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-15 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `EQUATOR` | [EQUATOR Reporting Guidelines Library](https://www.equator-network.org/reporting-guidelines/) | EQUATOR Network | Study-type-specific reporting guidance. |
| `COMMON_RULE` | [Federal Policy for the Protection of Human Subjects](https://www.hhs.gov/ohrp/regulations-and-policy/regulations/common-rule/index.html) | HHS OHRP | Human-subject research review and consent requirements. |
| `FAIR` | [FAIR Guiding Principles](https://www.go-fair.org/fair-principles/) | GO FAIR | Findable, accessible, interoperable and reusable research assets. |
| `OSF_REG` | [OSF Registrations and Preregistrations](https://help.osf.io/article/330-welcome-to-registrations) | Center for Open Science | Time-stamped, read-only registrations and embargoes. |
| `TOP` | [Transparency and Openness Promotion Guidelines](https://www.cos.io/initiatives/top-guidelines) | Center for Open Science | Transparency, preregistration and openness policies. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision feedback | Export from `planning/review-site/CAP-15/index.html` and apply with `planctl`; feedback alone does not approve execution. |
