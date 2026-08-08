---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-10
title: Novelty auditing, research opportunities, and plural research modes
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-10.S01
- CAP-10.S02
- CAP-10.S03
- CAP-10.S05
- CAP-10.S04
- CAP-10.S06
- CAP-10.S07
decisions:
- id: CAP-10-D01
  title: Novelty representation
  candidates:
  - Facet-based research concept plus bounded, corpus-relative novelty statement
  - Single novelty score or universal “never studied” claim
  recommendation: Facet-based research concept plus bounded, corpus-relative novelty statement
  recommendation_basis: Facet comparison reveals overlap and difference while explicit scope prevents false universal novelty.
  selected_option: Facet-based research concept plus bounded, corpus-relative novelty statement
  status: accepted
  required_adr: null
- id: CAP-10-D02
  title: Generator/challenger separation
  candidates:
  - Seal candidate state; independent challenger uses alternative vocabulary, adjacent fields and threat-ranked evidence
  - Ask the same agent to critique and validate its own idea in one context
  recommendation: Seal candidate state; independent challenger uses alternative vocabulary, adjacent fields and threat-ranked evidence
  recommendation_basis: Independent retrieval and adversarial roles reduce anchoring and produce reviewer-defensible counterevidence.
  selected_option: Seal candidate state; independent challenger uses alternative vocabulary, adjacent fields and threat-ranked evidence
  status: accepted
  required_adr: null
- id: CAP-10-D03
  title: Opportunity ontology
  candidates:
  - Distinct detector families with type-specific evidence, false positives and human interpretation
  - Treat all low-density topic combinations as equivalent gaps
  recommendation: Distinct detector families with type-specific evidence, false positives and human interpretation
  recommendation_basis: Contradictions, boundaries, measurements, bridges, assumptions and silences carry different contribution logics.
  selected_option: Distinct detector families with type-specific evidence, false positives and human interpretation
  status: accepted
  required_adr: null
- id: CAP-10-D04
  title: Critical/hermeneutic authority
  candidates:
  - AI produces evidence-linked provocations and competing readings; researcher memos and adjudications remain authoritative
  - Automate critical interpretation or overwrite evolving memos
  recommendation: AI produces evidence-linked provocations and competing readings; researcher memos and adjudications remain authoritative
  recommendation_basis: Interpretive and normative work requires plurality, iteration and explicit human ownership.
  selected_option: AI produces evidence-linked provocations and competing readings; researcher memos and adjudications remain authoritative
  status: accepted
  required_adr: null
- id: CAP-10-D05
  title: Ranking and monitoring
  candidates:
  - Raw multi-objective vectors, Pareto comparisons and impact-linked living updates
  - Opaque weighted leaderboard and generic keyword alerts
  recommendation: Raw multi-objective vectors, Pareto comparisons and impact-linked living updates
  recommendation_basis: Transparent dimensions preserve tradeoffs; monitors should identify affected claims and dossiers rather than merely announce papers.
  selected_option: Raw multi-objective vectors, Pareto comparisons and impact-linked living updates
  status: accepted
  required_adr: null
- id: CAP-10-D06
  title: Facet contract
  candidates:
  - Version facets for phenomenon/problem, theory/mechanism, constructs, population/unit/level, context, method/data, intervention/system, outcomes and claimed contribution; allow mode/domain extensions.
  - One free-text idea field or fixed biomedical PICO schema.
  recommendation: Version facets for phenomenon/problem, theory/mechanism, constructs, population/unit/level, context, method/data, intervention/system, outcomes and claimed contribution; allow mode/domain extensions.
  recommendation_basis: Novelty threats often overlap on different dimensions and scholarly traditions need extensibility.
  selected_option: Version facets for phenomenon/problem, theory/mechanism, constructs, population/unit/level, context, method/data, intervention/system, outcomes and claimed contribution; allow mode/domain extensions.
  status: accepted
  required_adr: null
- id: CAP-10-D07
  title: Retrieval ensemble
  candidates:
  - Union lexical, semantic, citation/bibliographic, graph/entity and review/reference-route candidates; retain route/rank and diversify before facet reranking.
  - Single vector nearest-neighbor search.
  recommendation: Union lexical, semantic, citation/bibliographic, graph/entity and review/reference-route candidates; retain route/rank and diversify before facet reranking.
  recommendation_basis: Known terminology and conceptual neighbors are found through different routes; route evidence supports audit.
  selected_option: Union lexical, semantic, citation/bibliographic, graph/entity and review/reference-route candidates; retain route/rank and diversify before facet reranking.
  status: accepted
  required_adr: null
- id: CAP-10-D08
  title: Threat review
  candidates:
  - Show ranked works with per-facet supported overlap, differences, uncertainty and threat level; humans may add/remove/reclassify but history remains.
  - One 0-100 novelty score.
  recommendation: Show ranked works with per-facet supported overlap, differences, uncertainty and threat level; humans may add/remove/reclassify but history remains.
  recommendation_basis: A reviewer-defensible novelty claim requires specific comparison, not score authority.
  selected_option: Show ranked works with per-facet supported overlap, differences, uncertainty and threat level; humans may add/remove/reclassify but history remains.
  status: accepted
  required_adr: null
- id: CAP-10-D09
  title: Separation
  candidates:
  - Seal concept/prior-work input at challenge start; challenger has separate role/prompt/evaluation and cannot edit the proposed contribution.
  - One agent alternates advocate and critic inside the same conversation.
  recommendation: Seal concept/prior-work input at challenge start; challenger has separate role/prompt/evaluation and cannot edit the proposed contribution.
  recommendation_basis: Independent state and objective reduce self-confirmation and create an auditable contest.
  selected_option: Seal concept/prior-work input at challenge start; challenger has separate role/prompt/evaluation and cannot edit the proposed contribution.
  status: accepted
  required_adr: null
- id: CAP-10-D10
  title: Expansion strategy
  candidates:
  - Generate synonym, older terminology, theoretical reframing, adjacent-discipline and document-type branches; execute each as a visible SearchRun.
  - Private hidden agent browsing with only a final score.
  recommendation: Generate synonym, older terminology, theoretical reframing, adjacent-discipline and document-type branches; execute each as a visible SearchRun.
  recommendation_basis: The challenge must be reproducible and explain why each branch was searched.
  selected_option: Generate synonym, older terminology, theoretical reframing, adjacent-discipline and document-type branches; execute each as a visible SearchRun.
  status: accepted
  required_adr: null
- id: CAP-10-D11
  title: Output language
  candidates:
  - Produce a bounded statement naming corpus/source scope, cutoff, closest studies, dimensions of difference and residual limits; researcher approval is mandatory.
  - “No prior work exists” or automated novelty certification.
  recommendation: Produce a bounded statement naming corpus/source scope, cutoff, closest studies, dimensions of difference and residual limits; researcher approval is mandatory.
  recommendation_basis: Novelty is relative to documented evidence and remains provisional.
  selected_option: Produce a bounded statement naming corpus/source scope, cutoff, closest studies, dimensions of difference and residual limits; researcher approval is mandatory.
  status: accepted
  required_adr: null
- id: CAP-10-D12
  title: Dossier completeness
  candidates:
  - Require identity, question, why-it-matters, mechanism, opportunity evidence, closest work, disconfirmation, search/corpus diagnostics, novelty statement, study options, outcome-contingent contribution, scoring vector, adjudication and monitoring.
  - Store title, description and scalar novelty score.
  recommendation: Require identity, question, why-it-matters, mechanism, opportunity evidence, closest work, disconfirmation, search/corpus diagnostics, novelty statement, study options, outcome-contingent contribution, scoring vector, adjudication and monitoring.
  recommendation_basis: A reviewer-defensible opportunity requires both supporting and threatening evidence plus feasibility and uncertainty.
  selected_option: Require identity, question, why-it-matters, mechanism, opportunity evidence, closest work, disconfirmation, search/corpus diagnostics, novelty statement, study options, outcome-contingent contribution, scoring vector, adjudication and monitoring.
  status: accepted
  required_adr: null
- id: CAP-10-D13
  title: State model
  candidates:
  - Candidate → assembling → challenge-required → decision-required → accepted/rejected/parked/revise → study-linked/closed, with immutable revisions and explicit missing requirements.
  - Free-form notes with an “active” flag.
  recommendation: Candidate → assembling → challenge-required → decision-required → accepted/rejected/parked/revise → study-linked/closed, with immutable revisions and explicit missing requirements.
  recommendation_basis: Lifecycle/state gates prevent incomplete candidates from becoming accepted gaps.
  selected_option: Candidate → assembling → challenge-required → decision-required → accepted/rejected/parked/revise → study-linked/closed, with immutable revisions and explicit missing requirements.
  status: accepted
  required_adr: null
- id: CAP-10-D14
  title: Outcome memory
  candidates:
  - Retain why ideas were accepted/rejected, subsequent studies/manuscripts/reviewer challenges and later field developments; never rewrite old decision context.
  - Delete rejected candidates or update them in place.
  recommendation: Retain why ideas were accepted/rejected, subsequent studies/manuscripts/reviewer challenges and later field developments; never rewrite old decision context.
  recommendation_basis: Longitudinal learning is a core research-program asset and supports evaluation of the system itself.
  selected_option: Retain why ideas were accepted/rejected, subsequent studies/manuscripts/reviewer challenges and later field developments; never rewrite old decision context.
  status: accepted
  required_adr: null
- id: CAP-10-D15
  title: Critical coding status
  candidates:
  - AI outputs are provocations/candidate readings linked to passages, lens/version and alternatives; only researcher adjudication creates accepted interpretation.
  - Automatic labels such as “stakeholder excluded” or “neoliberal assumption.”
  recommendation: AI outputs are provocations/candidate readings linked to passages, lens/version and alternatives; only researcher adjudication creates accepted interpretation.
  recommendation_basis: Critical claims require contextual interpretation and normative responsibility.
  selected_option: AI outputs are provocations/candidate readings linked to passages, lens/version and alternatives; only researcher adjudication creates accepted interpretation.
  status: accepted
  required_adr: null
- id: CAP-10-D16
  title: Ontology design
  candidates:
  - Small stable core—assumption, stakeholder, authority, dependency, benefit/burden, normative commitment, excluded alternative, system boundary—with versioned tradition/domain packs and competing codes.
  - One exhaustive universal critical ontology.
  recommendation: Small stable core—assumption, stakeholder, authority, dependency, benefit/burden, normative commitment, excluded alternative, system boundary—with versioned tradition/domain packs and competing codes.
  recommendation_basis: Extensibility and plurality reduce ontology lock-in while enabling reusable analysis.
  selected_option: Small stable core—assumption, stakeholder, authority, dependency, benefit/burden, normative commitment, excluded alternative, system boundary—with versioned tradition/domain packs and competing codes.
  status: accepted
  required_adr: null
- id: CAP-10-D17
  title: Hermeneutic process
  candidates:
  - Represent search, reading, memo, question/ontology revision and return-to-search as linked cycles; no mandatory linear stopping rule.
  - Reuse systematic-review queue and completion semantics unchanged.
  recommendation: Represent search, reading, memo, question/ontology revision and return-to-search as linked cycles; no mandatory linear stopping rule.
  recommendation_basis: Understanding changes through iteration between parts and whole and must preserve that lineage.
  selected_option: Represent search, reading, memo, question/ontology revision and return-to-search as linked cycles; no mandatory linear stopping rule.
  status: accepted
  required_adr: null
- id: CAP-10-D18
  title: Detector contract
  candidates:
  - Each detector declares opportunity type, required inputs, comparison universe, algorithm/model, output evidence, uncertainty, known false positives, benchmark and version.
  - One generic prompt asking an LLM to find gaps.
  recommendation: Each detector declares opportunity type, required inputs, comparison universe, algorithm/model, output evidence, uncertainty, known false positives, benchmark and version.
  recommendation_basis: Different opportunity types have different epistemic and technical validity conditions.
  selected_option: Each detector declares opportunity type, required inputs, comparison universe, algorithm/model, output evidence, uncertainty, known false positives, benchmark and version.
  status: accepted
  required_adr: null
- id: CAP-10-D19
  title: Structural signals
  candidates:
  - Use density/bridge/topological methods only to propose regions/relationships; require semantic/evidence interpretation and challenger review.
  - Label empty/low-density graph regions as gaps.
  recommendation: Use density/bridge/topological methods only to propose regions/relationships; require semantic/evidence interpretation and challenger review.
  recommendation_basis: Structural absence can be trivial, infeasible or caused by corpus bias.
  selected_option: Use density/bridge/topological methods only to propose regions/relationships; require semantic/evidence interpretation and challenger review.
  status: accepted
  required_adr: null
- id: CAP-10-D20
  title: Promotion
  candidates:
  - Candidates enter unverified state and require evidence packet, significance mechanism and S02 challenge before dossier decision.
  - Auto-add top-scoring candidates as validated gaps.
  recommendation: Candidates enter unverified state and require evidence packet, significance mechanism and S02 challenge before dossier decision.
  recommendation_basis: The platform’s differentiator is disciplined candidate generation plus disconfirmation.
  selected_option: Candidates enter unverified state and require evidence packet, significance mechanism and S02 challenge before dossier decision.
  status: accepted
  required_adr: null
- id: CAP-10-D21
  title: Ranking representation
  candidates:
  - Store separate dimensions—evidence, leverage, importance, distance, challenge robustness, tractability, data/method access, ethics, timeliness, program fit—with assessor, rubric and uncertainty.
  - Opaque weighted average as authoritative rank.
  recommendation: Store separate dimensions—evidence, leverage, importance, distance, challenge robustness, tractability, data/method access, ethics, timeliness, program fit—with assessor, rubric and uncertainty.
  recommendation_basis: Tradeoffs and disagreement are scholarly decisions and should remain inspectable.
  selected_option: Store separate dimensions—evidence, leverage, importance, distance, challenge robustness, tractability, data/method access, ethics, timeliness, program fit—with assessor, rubric and uncertainty.
  status: accepted
  required_adr: null
- id: CAP-10-D22
  title: Pareto default
  candidates:
  - Show nondominated fronts and pairwise differences first; optional user weights create a named/versioned view and never overwrite raw dimensions.
  - Sort all candidates by default formula.
  recommendation: Show nondominated fronts and pairwise differences first; optional user weights create a named/versioned view and never overwrite raw dimensions.
  recommendation_basis: Pareto views avoid pretending dimensions are commensurable while still supporting prioritization.
  selected_option: Show nondominated fronts and pairwise differences first; optional user weights create a named/versioned view and never overwrite raw dimensions.
  status: accepted
  required_adr: null
- id: CAP-10-D23
  title: Convergence governance
  candidates:
  - Compare only within authorized local/team portfolio by default; any cross-organization aggregate must be opt-in, privacy-preserving and non-reconstructive.
  - Centralize all user ideas to detect duplication.
  recommendation: Compare only within authorized local/team portfolio by default; any cross-organization aggregate must be opt-in, privacy-preserving and non-reconstructive.
  recommendation_basis: Research ideas are highly sensitive and shared-model convergence is itself a risk.
  selected_option: Compare only within authorized local/team portfolio by default; any cross-organization aggregate must be opt-in, privacy-preserving and non-reconstructive.
  status: accepted
  required_adr: null
- id: CAP-10-D24
  title: Monitor definition
  candidates:
  - Bind a monitor to versioned queries/search branches, sources, schedule, cursor/window strategy, dedupe policy, budget and target project objects.
  - Keyword alert with no search/version provenance.
  recommendation: Bind a monitor to versioned queries/search branches, sources, schedule, cursor/window strategy, dedupe policy, budget and target project objects.
  recommendation_basis: Living evidence requires knowing exactly what changed relative to a known search state.
  selected_option: Bind a monitor to versioned queries/search branches, sources, schedule, cursor/window strategy, dedupe policy, budget and target project objects.
  status: accepted
  required_adr: null
- id: CAP-10-D25
  title: Membership authority
  candidates:
  - New records enter an inbox/candidate state and follow normal reconciliation/screening; monitor never changes corpus membership directly.
  - Auto-add high-relevance results.
  recommendation: New records enter an inbox/candidate state and follow normal reconciliation/screening; monitor never changes corpus membership directly.
  recommendation_basis: Researchers retain inclusion authority and active-learning errors remain auditable.
  selected_option: New records enter an inbox/candidate state and follow normal reconciliation/screening; monitor never changes corpus membership directly.
  status: accepted
  required_adr: null
- id: CAP-10-D26
  title: Impact analysis
  candidates:
  - Generate evidence-linked “may affect” candidates for claims, comparison sets, syntheses, dossiers and designs; human confirms impact before recalculation/revision.
  - Automatically rewrite affected outputs.
  recommendation: Generate evidence-linked “may affect” candidates for claims, comparison sets, syntheses, dossiers and designs; human confirms impact before recalculation/revision.
  recommendation_basis: New evidence relevance and substantive impact are consequential scholarly judgments.
  selected_option: Generate evidence-linked “may affect” candidates for claims, comparison sets, syntheses, dossiers and designs; human confirms impact before recalculation/revision.
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-10 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-10` — Novelty auditing, research opportunities, and plural research modes |
| Objective | Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-10.S01`, `CAP-10.S02`, `CAP-10.S03`, `CAP-10.S05`, `CAP-10.S04`, `CAP-10.S06`, `CAP-10.S07` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory.**

Production-ready exit criteria:

- The local MVP decomposes an idea, retrieves nearest prior work, compares facets, and produces bounded novelty language with human approval.
- Critical and hermeneutic workflows preserve alternative readings, researcher memos, explicit assumptions, and interpretive authority before theory/critical article production.
- Advanced detectors produce typed candidates with false-positive warnings rather than a universal gap score.
- Accepted opportunities can hand off explicitly to empirical study design or empirical/theory/critical manuscript-development workflows.
- Living-monitor changes can identify affected claims, designs, manuscripts, reviews, and opportunity assessments.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-10.S01` | Nearest-prior novelty workspace MVP | A proposed research contribution can be decomposed and compared against the closest literature in a transparent local workflow. | `CAP-09.S04.T02`, `CAP-06.S03.T03` |
| `CAP-10.S02` | Independent adversarial novelty challenge | A separate workflow attempts to narrow or invalidate the proposed contribution rather than helping sell it. | `CAP-10.S01.T03`, `CAP-09.S06.T01` |
| `CAP-10.S03` | Research opportunity dossier and decision ledger | A candidate moves from algorithmic signal to a reviewer-defensible, monitored scholarly object. | `CAP-10.S02.T03`, `CAP-03.S05.T03` |
| `CAP-10.S05` | Critical and hermeneutic research support | The system surfaces evidence-linked candidate assumptions and alternative framings without replacing interpretive authority. | `CAP-10.S03.T02`, `CAP-08.S01.T03` |
| `CAP-10.S04` | Plural opportunity detector ensemble | Opportunity signals are separated by contribution logic, evidence requirements, and false-positive risks. | `CAP-10.S03.T03`, `CAP-09.S03.T03` |
| `CAP-10.S06` | Opportunity radar, ranking, and portfolio governance | Researchers can compare candidates on transparent dimensions without collapsing them into an opaque novelty score. | `CAP-10.S04.T03`, `CAP-10.S05.T02` |
| `CAP-10.S07` | Living monitor and impact-aware research memory | New literature is evaluated as a change to existing claims, syntheses, and opportunity assessments rather than as a generic alert. | `CAP-10.S03.T03`, `CAP-09.S06.T01` |

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
| `CAP-10-D01` | **Novelty representation** | Facet-based research concept plus bounded, corpus-relative novelty statement | Single novelty score or universal “never studied” claim | Facet comparison reveals overlap and difference while explicit scope prevents false universal novelty. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D02` | **Generator/challenger separation** | Seal candidate state; independent challenger uses alternative vocabulary, adjacent fields and threat-ranked evidence | Ask the same agent to critique and validate its own idea in one context | Independent retrieval and adversarial roles reduce anchoring and produce reviewer-defensible counterevidence. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| `CAP-10-D03` | **Opportunity ontology** | Distinct detector families with type-specific evidence, false positives and human interpretation | Treat all low-density topic combinations as equivalent gaps | Contradictions, boundaries, measurements, bridges, assumptions and silences carry different contribution logics. | [GAPMAP: Mapping Scientific Knowledge Gaps in Biomedical Literature Using Large Language Models](https://arxiv.org/abs/2510.25055) |
| `CAP-10-D04` | **Critical/hermeneutic authority** | AI produces evidence-linked provocations and competing readings; researcher memos and adjudications remain authoritative | Automate critical interpretation or overwrite evolving memos | Interpretive and normative work requires plurality, iteration and explicit human ownership. | [Generating Research Questions Through Problematization](https://doi.org/10.5465/amr.2009.0188) |
| `CAP-10-D05` | **Ranking and monitoring** | Raw multi-objective vectors, Pareto comparisons and impact-linked living updates | Opaque weighted leaderboard and generic keyword alerts | Transparent dimensions preserve tradeoffs; monitors should identify affected claims and dossiers rather than merely announce papers. | [OpenAlex API Documentation](https://docs.openalex.org/) |
| `CAP-10-D06` | **Facet contract** | Version facets for phenomenon/problem, theory/mechanism, constructs, population/unit/level, context, method/data, intervention/system, outcomes and claimed contribution; allow mode/domain extensions. | One free-text idea field or fixed biomedical PICO schema. | Novelty threats often overlap on different dimensions and scholarly traditions need extensibility. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D07` | **Retrieval ensemble** | Union lexical, semantic, citation/bibliographic, graph/entity and review/reference-route candidates; retain route/rank and diversify before facet reranking. | Single vector nearest-neighbor search. | Known terminology and conceptual neighbors are found through different routes; route evidence supports audit. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D08` | **Threat review** | Show ranked works with per-facet supported overlap, differences, uncertainty and threat level; humans may add/remove/reclassify but history remains. | One 0-100 novelty score. | A reviewer-defensible novelty claim requires specific comparison, not score authority. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D09` | **Separation** | Seal concept/prior-work input at challenge start; challenger has separate role/prompt/evaluation and cannot edit the proposed contribution. | One agent alternates advocate and critic inside the same conversation. | Independent state and objective reduce self-confirmation and create an auditable contest. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| `CAP-10-D10` | **Expansion strategy** | Generate synonym, older terminology, theoretical reframing, adjacent-discipline and document-type branches; execute each as a visible SearchRun. | Private hidden agent browsing with only a final score. | The challenge must be reproducible and explain why each branch was searched. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D11` | **Output language** | Produce a bounded statement naming corpus/source scope, cutoff, closest studies, dimensions of difference and residual limits; researcher approval is mandatory. | “No prior work exists” or automated novelty certification. | Novelty is relative to documented evidence and remains provisional. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D12` | **Dossier completeness** | Require identity, question, why-it-matters, mechanism, opportunity evidence, closest work, disconfirmation, search/corpus diagnostics, novelty statement, study options, outcome-contingent contribution, scoring vector, adjudication and monitoring. | Store title, description and scalar novelty score. | A reviewer-defensible opportunity requires both supporting and threatening evidence plus feasibility and uncertainty. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D13` | **State model** | Candidate → assembling → challenge-required → decision-required → accepted/rejected/parked/revise → study-linked/closed, with immutable revisions and explicit missing requirements. | Free-form notes with an “active” flag. | Lifecycle/state gates prevent incomplete candidates from becoming accepted gaps. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-10-D14` | **Outcome memory** | Retain why ideas were accepted/rejected, subsequent studies/manuscripts/reviewer challenges and later field developments; never rewrite old decision context. | Delete rejected candidates or update them in place. | Longitudinal learning is a core research-program asset and supports evaluation of the system itself. | [ResearchAgent: Iterative Research Idea Generation over Scientific Literature](https://aclanthology.org/2025.naacl-long.342/) |
| `CAP-10-D15` | **Critical coding status** | AI outputs are provocations/candidate readings linked to passages, lens/version and alternatives; only researcher adjudication creates accepted interpretation. | Automatic labels such as “stakeholder excluded” or “neoliberal assumption.” | Critical claims require contextual interpretation and normative responsibility. | [Generating Research Questions Through Problematization](https://doi.org/10.5465/amr.2009.0188) |
| `CAP-10-D16` | **Ontology design** | Small stable core—assumption, stakeholder, authority, dependency, benefit/burden, normative commitment, excluded alternative, system boundary—with versioned tradition/domain packs and competing codes. | One exhaustive universal critical ontology. | Extensibility and plurality reduce ontology lock-in while enabling reusable analysis. | [Generating Research Questions Through Problematization](https://doi.org/10.5465/amr.2009.0188) |
| `CAP-10-D17` | **Hermeneutic process** | Represent search, reading, memo, question/ontology revision and return-to-search as linked cycles; no mandatory linear stopping rule. | Reuse systematic-review queue and completion semantics unchanged. | Understanding changes through iteration between parts and whole and must preserve that lineage. | [A Hermeneutic Approach for Conducting Literature Reviews and Literature Searches](https://doi.org/10.17705/1CAIS.03412) |
| `CAP-10-D18` | **Detector contract** | Each detector declares opportunity type, required inputs, comparison universe, algorithm/model, output evidence, uncertainty, known false positives, benchmark and version. | One generic prompt asking an LLM to find gaps. | Different opportunity types have different epistemic and technical validity conditions. | [GAPMAP: Mapping Scientific Knowledge Gaps in Biomedical Literature Using Large Language Models](https://arxiv.org/abs/2510.25055) |
| `CAP-10-D19` | **Structural signals** | Use density/bridge/topological methods only to propose regions/relationships; require semantic/evidence interpretation and challenger review. | Label empty/low-density graph regions as gaps. | Structural absence can be trivial, infeasible or caused by corpus bias. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| `CAP-10-D20` | **Promotion** | Candidates enter unverified state and require evidence packet, significance mechanism and S02 challenge before dossier decision. | Auto-add top-scoring candidates as validated gaps. | The platform’s differentiator is disciplined candidate generation plus disconfirmation. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| `CAP-10-D21` | **Ranking representation** | Store separate dimensions—evidence, leverage, importance, distance, challenge robustness, tractability, data/method access, ethics, timeliness, program fit—with assessor, rubric and uncertainty. | Opaque weighted average as authoritative rank. | Tradeoffs and disagreement are scholarly decisions and should remain inspectable. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| `CAP-10-D22` | **Pareto default** | Show nondominated fronts and pairwise differences first; optional user weights create a named/versioned view and never overwrite raw dimensions. | Sort all candidates by default formula. | Pareto views avoid pretending dimensions are commensurable while still supporting prioritization. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| `CAP-10-D23` | **Convergence governance** | Compare only within authorized local/team portfolio by default; any cross-organization aggregate must be opt-in, privacy-preserving and non-reconstructive. | Centralize all user ideas to detect duplication. | Research ideas are highly sensitive and shared-model convergence is itself a risk. | [ResearchAgent: Iterative Research Idea Generation over Scientific Literature](https://aclanthology.org/2025.naacl-long.342/) |
| `CAP-10-D24` | **Monitor definition** | Bind a monitor to versioned queries/search branches, sources, schedule, cursor/window strategy, dedupe policy, budget and target project objects. | Keyword alert with no search/version provenance. | Living evidence requires knowing exactly what changed relative to a known search state. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-10-D25` | **Membership authority** | New records enter an inbox/candidate state and follow normal reconciliation/screening; monitor never changes corpus membership directly. | Auto-add high-relevance results. | Researchers retain inclusion authority and active-learning errors remain auditable. | [ASReview Documentation](https://asreview.readthedocs.io/en/latest/) |
| `CAP-10-D26` | **Impact analysis** | Generate evidence-linked “may affect” candidates for claims, comparison sets, syntheses, dossiers and designs; human confirms impact before recalculation/revision. | Automatically rewrite affected outputs. | New evidence relevance and substantive impact are consequential scholarly judgments. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |

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

Relevant approved pages: `novelty-audit.html`, `opportunity-radar.html`, `critical-lens.html`, `research-notebook.html`, `living-monitor.html`

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

- Nearest-prior retrieval recall is insufficient for a bounded novelty claim.
- A proposed opportunity depends on unresolved comparability or evidence disputes.
- A critical interpretation requires a normative decision not owned by automation.
- A monitor’s source terms or rights do not permit stable differential retrieval.
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
- [ ] `python tools/planctl.py ready CAP-10 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) — Broad retrieval, embedding filtering, facet-based reranking and literature-grounded novelty reasoning.
- [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) — Structural gap detection, ontology validation and adversarial multi-model evidence checking.
- [GAPMAP: Mapping Scientific Knowledge Gaps in Biomedical Literature Using Large Language Models](https://arxiv.org/abs/2510.25055) — Explicit and implicit gap inference with human validation.
- [Generating Research Questions Through Problematization](https://doi.org/10.5465/amr.2009.0188) — Assumption-challenging research-question methodology.
- [A Hermeneutic Approach for Conducting Literature Reviews and Literature Searches](https://doi.org/10.17705/1CAIS.03412) — Iterative search-reading-interpretation cycles and evolving understanding.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
