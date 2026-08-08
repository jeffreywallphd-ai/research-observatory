---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-19
title: Reviewer simulation, editorial synthesis, and revision
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-19.S01
- CAP-19.S02
- CAP-19.S03
- CAP-19.S04
- CAP-19.S05
- CAP-19.S06
decisions:
- id: CAP-19-D01
  title: Reviewer profile registry
  candidates:
  - Use governed versioned reviewer-panel profiles by research type, venue and review objective
  - Use one generic reviewer prompt for every article
  recommendation: Use governed versioned reviewer-panel profiles by research type, venue and review objective
  recommendation_basis: Method and contribution criteria differ across empirical, theory and critical work.
  selected_option: Use governed versioned reviewer-panel profiles by research type, venue and review objective
  status: accepted
  required_adr: ADR-REVIEWER-PROTOCOL
- id: CAP-19-D02
  title: Peer-review terminology
  candidates:
  - Map roles and transparency settings to ANSI/NISO peer-review terminology
  - Invent project-specific names for review models
  recommendation: Map roles and transparency settings to ANSI/NISO peer-review terminology
  recommendation_basis: Standard terminology improves clarity and export/interoperability.
  selected_option: Map roles and transparency settings to ANSI/NISO peer-review terminology
  status: accepted
  required_adr: null
- id: CAP-19-D03
  title: Reviewer independence
  candidates:
  - Run each reviewer in an isolated context with an explicit allowed-evidence manifest
  - Let reviewer agents share intermediate opinions and converge
  recommendation: Run each reviewer in an isolated context with an explicit allowed-evidence manifest
  recommendation_basis: Independent first-pass reviews reduce correlated reasoning and premature consensus.
  selected_option: Run each reviewer in an isolated context with an explicit allowed-evidence manifest
  status: accepted
  required_adr: null
- id: CAP-19-D04
  title: Review snapshot
  candidates:
  - Freeze an immutable manuscript, blueprint, evidence and policy snapshot for each review round
  - Review the live manuscript while it changes
  recommendation: Freeze an immutable manuscript, blueprint, evidence and policy snapshot for each review round
  recommendation_basis: Reproducibility and response mapping require a stable reviewed object.
  selected_option: Freeze an immutable manuscript, blueprint, evidence and policy snapshot for each review round
  status: accepted
  required_adr: null
- id: CAP-19-D05
  title: Comment schema
  candidates:
  - Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields
  - Store only free-form review prose
  recommendation: Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields
  recommendation_basis: Structured comments support triage, revision mapping, calibration and export while preserving narrative detail.
  selected_option: Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields
  status: accepted
  required_adr: null
- id: CAP-19-D06
  title: Editorial reviewer
  candidates:
  - Include a scope, contribution, positioning, coherence and venue-fit role
  - Ask every reviewer to judge every criterion
  recommendation: Include a scope, contribution, positioning, coherence and venue-fit role
  recommendation_basis: Role specialization produces more focused and auditable assessments.
  selected_option: Include a scope, contribution, positioning, coherence and venue-fit role
  status: accepted
  required_adr: null
- id: CAP-19-D07
  title: Methods reviewer
  candidates:
  - Use method-family-aware analysis, validity, ethics and reproducibility criteria
  - Use a generic statistical checklist for all papers
  recommendation: Use method-family-aware analysis, validity, ethics and reproducibility criteria
  recommendation_basis: Quantitative, qualitative, mixed, computational and design-science manuscripts require different review logic.
  selected_option: Use method-family-aware analysis, validity, ethics and reproducibility criteria
  status: accepted
  required_adr: null
- id: CAP-19-D08
  title: Theory and critical reviewer
  candidates:
  - Provide separate theory/argument and critical/reflexive reviewer roles
  - Score both with an empirical causal-validity rubric
  recommendation: Provide separate theory/argument and critical/reflexive reviewer roles
  recommendation_basis: These traditions require different standards of contribution and evidence.
  selected_option: Provide separate theory/argument and critical/reflexive reviewer roles
  status: accepted
  required_adr: null
- id: CAP-19-D09
  title: Evidence-integrity reviewer
  candidates:
  - Audit citations, source entailment, result records, tables/figures and unsupported claims
  - Rely on reviewer impressions of citation quality
  recommendation: Audit citations, source entailment, result records, tables/figures and unsupported claims
  recommendation_basis: Evidence-grounded review is a key differentiator and must be independently checked.
  selected_option: Audit citations, source entailment, result records, tables/figures and unsupported claims
  status: accepted
  required_adr: null
- id: CAP-19-D10
  title: Ethics and reproducibility reviewer
  candidates:
  - Inspect disclosure, data/code/protocol availability, rights, human-subject and reproducibility claims without making institutional determinations
  - Automatically declare ethical compliance
  recommendation: Inspect disclosure, data/code/protocol availability, rights, human-subject and reproducibility claims without making institutional determinations
  recommendation_basis: The system can flag evidence and missingness but cannot replace authorized ethics or editorial judgment.
  selected_option: Inspect disclosure, data/code/protocol availability, rights, human-subject and reproducibility claims without making institutional determinations
  status: accepted
  required_adr: null
- id: CAP-19-D11
  title: Panel diversity
  candidates:
  - Use role and model diversity with deterministic manifests and compare disagreements
  - Use multiple identical prompts to the same model and call it independent
  recommendation: Use role and model diversity with deterministic manifests and compare disagreements
  recommendation_basis: Meaningful diversity requires different criteria/context/model configurations and explicit correlation analysis.
  selected_option: Use role and model diversity with deterministic manifests and compare disagreements
  status: accepted
  required_adr: null
- id: CAP-19-D12
  title: Acceptance prediction
  candidates:
  - Prohibit acceptance-probability claims and named-reviewer impersonation
  - Predict venue acceptance and simulate named scholars
  recommendation: Prohibit acceptance-probability claims and named-reviewer impersonation
  recommendation_basis: Reviewer simulation is a developmental critique, not a guarantee or impersonation service.
  selected_option: Prohibit acceptance-probability claims and named-reviewer impersonation
  status: accepted
  required_adr: null
- id: CAP-19-D13
  title: Editorial synthesis
  candidates:
  - Run a separate meta-review stage over completed reports and preserve material disagreement
  - Average scores and collapse comments to consensus
  recommendation: Run a separate meta-review stage over completed reports and preserve material disagreement
  recommendation_basis: Editorial synthesis should organize tradeoffs without erasing dissent.
  selected_option: Run a separate meta-review stage over completed reports and preserve material disagreement
  status: accepted
  required_adr: null
- id: CAP-19-D14
  title: Calibration and overreach
  candidates:
  - Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift
  - Assume fluent reviewer output is reliable
  recommendation: Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift
  recommendation_basis: Reviewer quality must be evaluated as a research-support mechanism.
  selected_option: Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift
  status: accepted
  required_adr: null
- id: CAP-19-D15
  title: Confidentiality and egress
  candidates:
  - Keep drafts local by default and enforce explicit provider/permission policy with disclosure
  - Upload drafts to any available model automatically
  recommendation: Keep drafts local by default and enforce explicit provider/permission policy with disclosure
  recommendation_basis: Submitted or unpublished manuscripts are confidential scholarly communications.
  selected_option: Keep drafts local by default and enforce explicit provider/permission policy with disclosure
  status: accepted
  required_adr: null
- id: CAP-19-D16
  title: Revision plan
  candidates:
  - Map each accepted comment to stable blocks, actions, owner, status, evidence and change sets
  - Revise prose directly from reviewer text without a plan
  recommendation: Map each accepted comment to stable blocks, actions, owner, status, evidence and change sets
  recommendation_basis: A governed plan preserves author authority and enables selective review.
  selected_option: Map each accepted comment to stable blocks, actions, owner, status, evidence and change sets
  status: accepted
  required_adr: null
- id: CAP-19-D17
  title: Response artifact
  candidates:
  - Generate an editable point-by-point response/rebuttal linked to comments and manuscript diffs
  - Produce a generic cover letter summary
  recommendation: Generate an editable point-by-point response/rebuttal linked to comments and manuscript diffs
  recommendation_basis: Traceable responses support real editorial workflows and accountability.
  selected_option: Generate an editable point-by-point response/rebuttal linked to comments and manuscript diffs
  status: accepted
  required_adr: null
- id: CAP-19-D18
  title: Follow-up review
  candidates:
  - Re-run only relevant reviewer roles/criteria against the revised snapshot and prior response
  - Repeat the entire panel blindly after every edit
  recommendation: Re-run only relevant reviewer roles/criteria against the revised snapshot and prior response
  recommendation_basis: Selective re-review reduces cost and focuses verification on resolved issues.
  selected_option: Re-run only relevant reviewer roles/criteria against the revised snapshot and prior response
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-19 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-19` — Reviewer simulation, editorial synthesis, and revision |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-19/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Subject generated or uploaded empirical, theory, and critical drafts to independent multi-role simulated peer review, evidence-aware editorial synthesis, and author-controlled revision and response rounds.

Typed immutable review objects, research-type panel profiles, sealed reviewer contexts, structured reports, explicit meta-review, calibration, revision decisions and round lineage preserve independence and disagreement.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Reviewer roles and criteria match the research type and verified venue expectations, operate independently, and expose evidence, confidence, and possible overreach.
- Generated or uploaded manuscript snapshots are immutable and audited against project evidence, technical reports, article blueprints, and venue criteria.
- Editorial synthesis preserves disagreement and does not present simulated decisions as actual peer review or acceptance probability.
- Every review comment can be triaged, linked to a revision, answered, diffed, and re-reviewed with full lineage.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-19.S01` | Reviewer protocol, roles, and independence | Reviewer simulations are role-bounded, reproducible, and independent before editorial synthesis. | W8 | P0 | CAP-18.S01.T03 |
| `CAP-19.S02` | Extended independent reviewer panel | Generated or uploaded drafts receive complementary substantive, methodological, theoretical, critical, and integrity reviews. | W8 | P0 | CAP-19.S01.T03 |
| `CAP-19.S03` | Generated and uploaded draft intake | Any draft can enter a reproducible, evidence-aware reviewer simulation without losing its original state. | W8 | P0 | CAP-19.S01.T03 |
| `CAP-19.S04` | Reviewer reports and editorial synthesis | The system produces rigorous, transparent simulated peer review while preserving disagreement and uncertainty. | W8 | P0 | CAP-19.S02.T03, CAP-19.S03.T03 |
| `CAP-19.S05` | Revision and response workflow | Reviewer feedback becomes a transparent, author-controlled revision plan and auditable response. | W8 | P0 | CAP-19.S04.T03 |
| `CAP-19.S06` | Reviewer simulation and research-production acceptance | Extended simulated review and revision are production-ready and complete the G8 local research lifecycle. | W8 | P0 | CAP-19.S05.T03, CAP-18.S06.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before presenting the packet, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. The strongest recommendation is preselected as the resolved default. Reviewers may confirm it, select another listed option with rationale, or request a revised candidate set. Capability approval accepts all current selections at once. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-19-D01` | Reviewer profile registry | A. Use governed versioned reviewer-panel profiles by research type, venue and review objective<br>B. Use one generic reviewer prompt for every article | **Use governed versioned reviewer-panel profiles by research type, venue and review objective** | Method and contribution criteria differ across empirical, theory and critical work. | ADR-REVIEWER-PROTOCOL |
| `CAP-19-D02` | Peer-review terminology | A. Map roles and transparency settings to ANSI/NISO peer-review terminology<br>B. Invent project-specific names for review models | **Map roles and transparency settings to ANSI/NISO peer-review terminology** | Standard terminology improves clarity and export/interoperability. | None |
| `CAP-19-D03` | Reviewer independence | A. Run each reviewer in an isolated context with an explicit allowed-evidence manifest<br>B. Let reviewer agents share intermediate opinions and converge | **Run each reviewer in an isolated context with an explicit allowed-evidence manifest** | Independent first-pass reviews reduce correlated reasoning and premature consensus. | None |
| `CAP-19-D04` | Review snapshot | A. Freeze an immutable manuscript, blueprint, evidence and policy snapshot for each review round<br>B. Review the live manuscript while it changes | **Freeze an immutable manuscript, blueprint, evidence and policy snapshot for each review round** | Reproducibility and response mapping require a stable reviewed object. | None |
| `CAP-19-D05` | Comment schema | A. Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields<br>B. Store only free-form review prose | **Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields** | Structured comments support triage, revision mapping, calibration and export while preserving narrative detail. | None |
| `CAP-19-D06` | Editorial reviewer | A. Include a scope, contribution, positioning, coherence and venue-fit role<br>B. Ask every reviewer to judge every criterion | **Include a scope, contribution, positioning, coherence and venue-fit role** | Role specialization produces more focused and auditable assessments. | None |
| `CAP-19-D07` | Methods reviewer | A. Use method-family-aware analysis, validity, ethics and reproducibility criteria<br>B. Use a generic statistical checklist for all papers | **Use method-family-aware analysis, validity, ethics and reproducibility criteria** | Quantitative, qualitative, mixed, computational and design-science manuscripts require different review logic. | None |
| `CAP-19-D08` | Theory and critical reviewer | A. Provide separate theory/argument and critical/reflexive reviewer roles<br>B. Score both with an empirical causal-validity rubric | **Provide separate theory/argument and critical/reflexive reviewer roles** | These traditions require different standards of contribution and evidence. | None |
| `CAP-19-D09` | Evidence-integrity reviewer | A. Audit citations, source entailment, result records, tables/figures and unsupported claims<br>B. Rely on reviewer impressions of citation quality | **Audit citations, source entailment, result records, tables/figures and unsupported claims** | Evidence-grounded review is a key differentiator and must be independently checked. | None |
| `CAP-19-D10` | Ethics and reproducibility reviewer | A. Inspect disclosure, data/code/protocol availability, rights, human-subject and reproducibility claims without making institutional determinations<br>B. Automatically declare ethical compliance | **Inspect disclosure, data/code/protocol availability, rights, human-subject and reproducibility claims without making institutional determinations** | The system can flag evidence and missingness but cannot replace authorized ethics or editorial judgment. | None |
| `CAP-19-D11` | Panel diversity | A. Use role and model diversity with deterministic manifests and compare disagreements<br>B. Use multiple identical prompts to the same model and call it independent | **Use role and model diversity with deterministic manifests and compare disagreements** | Meaningful diversity requires different criteria/context/model configurations and explicit correlation analysis. | None |
| `CAP-19-D12` | Acceptance prediction | A. Prohibit acceptance-probability claims and named-reviewer impersonation<br>B. Predict venue acceptance and simulate named scholars | **Prohibit acceptance-probability claims and named-reviewer impersonation** | Reviewer simulation is a developmental critique, not a guarantee or impersonation service. | None |
| `CAP-19-D13` | Editorial synthesis | A. Run a separate meta-review stage over completed reports and preserve material disagreement<br>B. Average scores and collapse comments to consensus | **Run a separate meta-review stage over completed reports and preserve material disagreement** | Editorial synthesis should organize tradeoffs without erasing dissent. | None |
| `CAP-19-D14` | Calibration and overreach | A. Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift<br>B. Assume fluent reviewer output is reliable | **Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift** | Reviewer quality must be evaluated as a research-support mechanism. | None |
| `CAP-19-D15` | Confidentiality and egress | A. Keep drafts local by default and enforce explicit provider/permission policy with disclosure<br>B. Upload drafts to any available model automatically | **Keep drafts local by default and enforce explicit provider/permission policy with disclosure** | Submitted or unpublished manuscripts are confidential scholarly communications. | None |
| `CAP-19-D16` | Revision plan | A. Map each accepted comment to stable blocks, actions, owner, status, evidence and change sets<br>B. Revise prose directly from reviewer text without a plan | **Map each accepted comment to stable blocks, actions, owner, status, evidence and change sets** | A governed plan preserves author authority and enables selective review. | None |
| `CAP-19-D17` | Response artifact | A. Generate an editable point-by-point response/rebuttal linked to comments and manuscript diffs<br>B. Produce a generic cover letter summary | **Generate an editable point-by-point response/rebuttal linked to comments and manuscript diffs** | Traceable responses support real editorial workflows and accountability. | None |
| `CAP-19-D18` | Follow-up review | A. Re-run only relevant reviewer roles/criteria against the revised snapshot and prior response<br>B. Repeat the entire panel blindly after every edit | **Re-run only relevant reviewer roles/criteria against the revised snapshot and prior response** | Selective re-review reduces cost and focuses verification on resolved issues. | None |

Every decision is **resolved by the documented recommendation**: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires an explicit rationale. Approval remains a separate authorization gate for the complete capability and all slice plans.

## 5. Cross-slice architecture contract

Typed immutable review objects, research-type panel profiles, sealed reviewer contexts, structured reports, explicit meta-review, calibration, revision decisions and round lineage preserve independence and disagreement.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The approved Reviewer Simulation and Revision & Response workspaces make simulated status, reviewer role, criterion, evidence, confidence, overreach, author triage, exact diffs, responses and follow-up rounds visible.

Approved reference exposure: `reviewer-simulation.html`, `revision-response.html`, `manuscript-studio.html`, `audit-lineage.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Unpublished drafts are private by default; reviewer contexts are isolated; provider payloads are explicit; simulation never impersonates named reviewers or predicts acceptance probability.

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

After one-time approval, `taskctl capability start CAP-19` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [x] All listed decisions have the researched recommendation preselected and accepted; any override must carry rationale.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-19 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `NISO_PEER_REVIEW` | [ANSI/NISO Z39.106-2023 Standard Terminology for Peer Review](https://www.niso.org/publications/z39106-2023-peerreview) | NISO | Consistent reviewer roles, identity transparency and peer-review process terminology. |
| `OPENREVIEW_REVIEW` | [OpenReview Review Stage](https://docs.openreview.net/reference/stages/review-stage) | OpenReview | Structured independent review rounds and configurable review forms. |
| `ICMJE_AI_REVIEWERS` | [ICMJE Use of AI by Reviewers](https://www.icmje.org/recommendations/browse/artificial-intelligence/ai-use-by-reviewers.html) | ICMJE | Confidentiality, permission, validation and disclosure for AI-assisted review. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) | W3C | Revision-aware source, manuscript and review-location selectors. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `ICMJE_AI` | [ICMJE Use of Artificial Intelligence in Publishing](https://www.icmje.org/recommendations/browse/artificial-intelligence/) | ICMJE | Human accountability, confidentiality and transparent disclosure for AI-assisted publication work. |
| `OPENREVIEW_META` | [OpenReview Meta Review Stage](https://docs.openreview.net/reference/stages/meta-review-stage) | OpenReview | Editorial synthesis as a distinct stage from independent reviews. |
| `OPENREVIEW_REBUTTAL` | [OpenReview Rebuttal Stage](https://docs.openreview.net/reference/stages/rebuttal-stage) | OpenReview | Explicit response/rebuttal stage linked to prior reviews. |
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
| Decision review/override | Export from `planning/review-site/CAP-19/index.html` and apply with `planctl`; feedback alone does not approve execution. |
