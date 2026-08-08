---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-10
capability_plan: planning/capability-plans/CAP-10.md
planning_gate: capability-decision-complete
slice_id: CAP-10.S06
title: Opportunity radar, ranking, and portfolio governance
status: proposed
wave: W9
priority: P1
deployment_profiles:
- LOC
- LAB
- UNI
- CLD
platform_targets:
- platform-neutral
task_ids:
- CAP-10.S06.T01
- CAP-10.S06.T02
- CAP-10.S06.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-10.S06 — Opportunity radar, ranking, and portfolio governance

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-10.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and both plan validators pass in approval mode. Once the capability campaign starts, the agent should execute continuously through its slices and pause only for an allowed infeasibility, external dependency, unavailable required hardware, explicit human decision, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-10` — Novelty auditing, research opportunities, and plural research modes |
| Capability objective | Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory. |
| Slice | `CAP-10.S06` — Opportunity radar, ranking, and portfolio governance |
| Slice outcome | Researchers can compare candidates on transparent dimensions without collapsing them into an opaque novelty score. |
| Wave / priority | `W9` / `P1` |
| Deployment profiles | `LOC`, `LAB`, `UNI`, `CLD` |
| Platform targets | `platform-neutral` |
| Backlog tasks | `CAP-10.S06.T01`, `CAP-10.S06.T02`, `CAP-10.S06.T03` |
| Slice dependencies | `CAP-10.S04.T03`, `CAP-10.S05.T02` |
| Capability decision packet | `planning/capability-plans/CAP-10.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant pages: novelty-audit.html, opportunity-radar.html, critical-lens.html, research-notebook.html, living-monitor.html |
| Approval state | `PROPOSED` / human approval pending |

## 1. Purpose and contribution to the larger vision

Researchers can compare candidates on transparent dimensions without collapsing them into an opaque novelty score.

This slice advances the capability objective: **Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory.** It is designed as one production vertical inside a long-running capability campaign, not as an isolated technical experiment. The implementation must preserve the platform’s evidence-before-prose rule, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, cross-platform ports, and the distinction between canonical scholarly state and rebuildable analytical derivatives.

**Implementation thesis.** Let researchers compare opportunities across transparent dimensions and Pareto tradeoffs, then govern a private research portfolio for duplication and convergence without collapsing judgment into a hidden composite ranking.

The containing capability is complete only when all of its slices satisfy these exit conditions:

- The local MVP decomposes an idea, retrieves nearest prior work, compares facets, and produces bounded novelty language with human approval.
- Critical and hermeneutic workflows preserve alternative readings, researcher memos, explicit assumptions, and interpretive authority before theory/critical article production.
- Advanced detectors produce typed candidates with false-positive warnings rather than a universal gap score.
- Accepted opportunities can hand off explicitly to empirical study design or empirical/theory/critical manuscript-development workflows.
- Living-monitor changes can identify affected claims, designs, manuscripts, reviews, and opportunity assessments.

## 2. Scope

### 2.1 In scope

- Multi-objective opportunity vectors and uncertainty.
- Pareto radar, comparison and optional explicit weighting.
- Portfolio links, duplication checks and idea-convergence monitoring.

### 2.2 Explicit non-goals

- One platform-owned priority score.
- Sharing unpublished ideas across users without consent.
- Predicting publication acceptance or research success.
- Do not implement downstream capability behavior beyond narrow ports, fixtures and handoffs explicitly named here.
- Do not introduce university-hosted or managed-cloud infrastructure during the local Windows waves; preserve deployment-neutral contracts only.
- Do not bypass the Core API, canonical repositories, provenance ledger, durable workflow fabric, rights policy, model gateway or approved experience reference.
- Do not declare completion from happy-path task tests alone; slice-wide failure, cancellation, restart, migration, security, accessibility and handoff evidence is required.

### 2.3 Slice boundary

- **Consumes:** `CAP-10.S04.T03`, `CAP-10.S05.T02` and the handoffs in Section 13.
- **Produces:** Researchers can compare candidates on transparent dimensions without collapsing them into an opaque novelty score.
- **Owns:** The portable domain contracts, adapter boundaries, workflows, fixtures, decisions and evidence explicitly listed in this plan.
- **Does not own:** Product purpose, unrelated capabilities, user-authoritative scholarly judgments, source rights, or provider/database/UI framework internals.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. Vision and non-goals in `docs/product/vision.md`.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md`.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved capability decision packet `planning/capability-plans/CAP-10.md`.
5. This approved slice plan.
6. Approved UI reference, workflow/page contracts and style guide for user-facing work.
7. Automation and task-control rules.

### 3.2 Required upstream state

- All slice dependencies are approved or an explicitly approved integration stub exists: `CAP-10.S04.T03`, `CAP-10.S05.T02`.
- The capability decision packet contains all material cross-slice choices, candidate options, recommendation, accepted selection, migration boundary and approval.
- Every slice plan in the capability exists and is structurally valid before capability approval; all plans are approved before campaign start.
- Required fixtures, benchmark corpora, credentials, model/source licenses, platform resources and human authority are available or represented by approved deterministic stubs.

### 3.3 Decision-complete capability rule

Planning by capability is the default. Before `capability start`, the planning agent inspects all slices and adjacent contracts, researches credible options, and records the strongest best-in-class recommendation as the selected and accepted option for every material decision in the capability packet. Those selections count as completed decisions. The static review site is a confirmation-and-override surface plus the one-time capability approval gate; implementation agents must not repeatedly ask for choices already settled by the packet. After approval, execution proceeds continuously slice by slice through a production-ready end-to-end capability.

### 3.4 Allowed pauses after execution begins

The long-running campaign should continue task-by-task and slice-by-slice. It may pause only when classified as one of the following and recorded by `taskctl`:

- **Infeasible:** validated evidence disproves the selected design and no compatible fallback exists within the approved boundary.
- **External dependency:** a required source/provider/license/credential/approval controlled outside the repository is unavailable.
- **Hardware unavailable:** a required qualification target cannot be simulated and is not accessible.
- **Human decision:** a newly discovered consequential product, architecture, security, rights, ethics or scholarly-authority choice was not reasonably knowable during planning.
- **Approved design gate:** the implementation requires an intentional change to the governed style guide/workflow/page reference.

Ordinary implementation uncertainty, test failure, debugging, refactoring, model fallback, recoverable performance work, or a choice already covered by the packet is not a pause condition.

## 4. Selected implementation decisions

The capability packet's researched best-in-class recommendations are already selected, accepted, and decision-complete. This section projects the applicable decisions into the slice implementation contract. Capability approval authorizes those defaults; a reviewer may override a selection before approval only with explicit rationale. During execution, no implementation agent may silently choose a different candidate.


These selections are recommendations until the capability packet and ADRs are approved. Approval turns them into the execution contract for the campaign.

| Decision | Recommended selection | Alternative not selected | Rationale and replaceability | Basis |
|---|---|---|---|---|
| **Ranking representation** | Store separate dimensions—evidence, leverage, importance, distance, challenge robustness, tractability, data/method access, ethics, timeliness, program fit—with assessor, rubric and uncertainty. | Opaque weighted average as authoritative rank. | Tradeoffs and disagreement are scholarly decisions and should remain inspectable. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| **Pareto default** | Show nondominated fronts and pairwise differences first; optional user weights create a named/versioned view and never overwrite raw dimensions. | Sort all candidates by default formula. | Pareto views avoid pretending dimensions are commensurable while still supporting prioritization. | [ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation](https://doi.org/10.1016/j.procs.2026.01.036) |
| **Convergence governance** | Compare only within authorized local/team portfolio by default; any cross-organization aggregate must be opt-in, privacy-preserving and non-reconstructive. | Centralize all user ideas to detect duplication. | Research ideas are highly sensitive and shared-model convergence is itself a risk. | [ResearchAgent: Iterative Research Idea Generation over Scientific Literature](https://aclanthology.org/2025.naacl-long.342/) |

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `services/core/research_observatory/modules/opportunities/scoring.py` | Rubrics, assessments, uncertainty and vector revisions. |
| `services/core/research_observatory/modules/opportunities/pareto.py` | Front computation, sensitivity and explanation. |
| `services/core/research_observatory/modules/opportunities/portfolio.py` | Links, ownership, lifecycle and duplication candidates. |
| `services/core/research_observatory/modules/opportunities/convergence.py` | Authorized similarity/diversity diagnostics. |
| `packages/ui/opportunity-radar` | Radar, Pareto fronts, comparison and portfolio. |
| `tests/benchmarks/opportunity-ranking` | Known Pareto/sensitivity/privacy cases. |

The paths are recommendations within the approved modular-monolith/package structure. Exact filenames may change without a new decision if module ownership, portable contracts and dependency directions remain intact.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `OpportunityAssessment` | candidate/dimension, value/range, rubric, assessor, evidence and uncertainty |
| `ScoringVector` | immutable dimension set and completeness |
| `RankingView` | Pareto/weights/filters, owner, version and explanation |
| `PortfolioItem` | dossier/research concept, lifecycle, owners, links and confidentiality |
| `DuplicationCandidate` | pair/group, overlap facets, authorization and review state |

**Cross-cutting invariants**

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, graph projections, rankings, generated drafts and detector signals are versioned derivatives.
- Unknown, not reported, not applicable, denied, unavailable, ambiguous, inferred, disputed, stale and failed remain distinct where relevant.
- Every long-running operation has stable identity, status, inputs/manifests, progress, cancellation, checkpoint, restart and evidence records.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `ScoringService.assess/revise` preserves assessor-specific vectors.
- `ParetoService.fronts(vectors, dimensions, direction)` is deterministic and tested.
- `RankingViewService.create` records explicit weights/sensitivity and creator.
- `PortfolioSimilarity.propose(scope, privacy_policy)` returns facet explanations, never raw unauthorized content.

All contracts use stable canonical IDs, explicit revisions/status, typed errors and version metadata. Provider SDK objects, SQLite rows, model tensors, graph library objects and UI component state may not cross the owning adapter boundary.

### 5.4 Cross-capability and platform compatibility

- Windows x64 is the current implementation target, but paths, process control, credential storage, accelerators and packaging stay behind adapters required by CAP-14 macOS/Linux qualification.
- Local and hosted deployments use the same domain/API/workflow semantics; storage, process, authentication and scaling adapters differ later.
- Downstream CAP-11–19 consume immutable IDs, evidence/provenance, manifests and ports rather than internal tables or framework classes.
- Model, embedding, reranker, parser, graph and vector choices are pinned and replaceable; changing one marks exact dependents stale and requires evaluation rather than silent regeneration.

## 6. User experience and approved reference

- Opportunity Radar shows raw dimensions, missing ratings, uncertainty and Pareto front rather than a magic score.
- Users compare selected candidates and see exactly what changes under alternative weights.
- Duplicate/convergence suggestions are reviewable and can be marked related-but-distinct.
- Confidentiality scope is visible on every portfolio item and comparison.

- Workflow navigation must show the project’s selected use case, current numbered stage, completed/upcoming states, expected output and next/previous actions.
- Supporting tools remain accessible, but opening one explains its relationship to the primary path and offers return to the current stage.
- All semantic states use text/icon in addition to color, meet WCAG 2.2 AA targets, support keyboard operation, and have light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed—not left as generic alerts.

**Reference-first rule.** If the planned experience materially differs from `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit approval and a new reference ID; only then implement application code. Restoring a defect to the approved reference does not require a new reference.

## 7. Security, privacy, rights and research integrity

- Local-only default for ideas and similarity embeddings; team comparison follows ACLs.
- No cross-tenant idea similarity in cloud without separate approved privacy design/ADR.
- Exports and screenshots respect confidential-idea policy.

Additional mandatory controls:

- Treat source content, metadata, model files, provider responses, reports, URLs, archives and rich text as untrusted.
- Apply least privilege, schema/input validation, destination/path controls, bounded resources, output encoding and redacted diagnostics at trusted boundaries.
- Private projects and unpublished ideas remain local by default; egress requires project policy, rights decision and visible payload/provider preview.
- Never fabricate evidence, citations, availability, permissions, method details, model certainty, benchmark success or completion evidence.
- AI output is candidate state until the domain-specific verifier/human gate promotes it.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior |
|---|---|
| Missing dimensions | Show incomplete vector; exclude/include from fronts only by explicit policy. |
| Assessors disagree | Preserve vectors and compare; no silent average. |
| Similarity false positive | Human review and facet explanation; no automatic merge. |
| Weights changed | Create new ranking view and sensitivity report, retain decisions based on old view. |

Every scenario receives a deterministic fixture where feasible, expected canonical state, expected derivative state, user message/action, retry/cancel rule, cleanup/repair rule, provenance event and automated test. A restart test must execute from persisted state rather than from an in-memory mock alone.

## 9. Task-by-task implementation plan

### CAP-10.S06.T01 — Implement multi-objective opportunity scoring vectors

**Objective.** Evidence strength, theoretical leverage, substantive importance, prior-work distance, challenge robustness, tractability, data access, ethics, timeliness, and program fit with uncertainty.

| Control | Value |
|---|---|
| Dependencies | `CAP-10.S04.T03`, `CAP-10.S05.T02` |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `novelty`, `evidence` |

**Expected deliverables**

- Evidence strength, theoretical leverage, substantive importance, prior-work distance, challenge robustness, tractability, data access, ethics, timeliness, and program fit with uncertainty.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S06.T01`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
4. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
5. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
6. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Raw dimensions and evidence remain visible; weights are optional, versioned, and user-defined; missing values are not defaulted to favorable scores.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile novelty
python tools/verify.py --profile evidence
```


### CAP-10.S06.T02 — Build Pareto radar and candidate comparison workspace

**Objective.** Filters, Pareto fronts, type-specific warnings, uncertainty, nearest-prior threat, diversity, and side-by-side dossier comparison.

| Control | Value |
|---|---|
| Dependencies | `CAP-10.S06.T01` |
| Estimate / risk | `L` / `medium` |
| Review gate | `agent-review` |
| Verification profiles | `desktop`, `novelty` |

**Expected deliverables**

- Filters, Pareto fronts, type-specific warnings, uncertainty, nearest-prior threat, diversity, and side-by-side dossier comparison.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S06.T02`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
3. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
4. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
5. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
6. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Ranking can be reproduced from saved inputs; changing weights does not mutate underlying evidence; users can explain why one candidate dominates another.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile desktop
python tools/verify.py --profile novelty
```


### CAP-10.S06.T03 — Implement portfolio links, duplication checks, and convergence monitoring

**Objective.** Connections among lab projects, researchers, shared constructs/data, overlapping candidates, prior rejections, and similarity alerts with privacy boundaries.

| Control | Value |
|---|---|
| Dependencies | `CAP-10.S06.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `novelty`, `graph`, `security-local` |

**Expected deliverables**

- Connections among lab projects, researchers, shared constructs/data, overlapping candidates, prior rejections, and similarity alerts with privacy boundaries.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S06.T03`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
4. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
5. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Private projects do not leak content through similarity outputs; duplicate warnings show evidence and can be dismissed with rationale; convergence is a diagnostic, not an automatic block.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile novelty
python tools/verify.py --profile graph
python tools/verify.py --profile security-local
```


## 10. Slice-wide verification matrix

| Verification family | Required slice evidence |
|---|---|
| Domain and schema | Contract examples/negative cases; invariants and state transitions; stable IDs/revisions; property tests where valuable. |
| Adapter and integration | Real local adapters with deterministic fixtures; idempotency; concurrency; transaction/outbox/dependency behavior; replaceability test double. |
| End-to-end | Approved workflow from entry point through durable result, source inspection, user decision and restart. |
| Failure and recovery | At least the Section 8 cases, cancellation acknowledgement, process restart, corrupted/partial derivative repair and no canonical loss. |
| Security, privacy and rights | Authorization denial, prompt/source injection, malformed files/payloads, secret/content redaction, egress and export policy. |
| Accessibility and UI reference | Route/page contract, shared tokens, light/dark, keyboard, focus, screen reader, zoom/reflow and visual-baseline checks. |
| Performance and capacity | Declared fixtures, warm/cold measurements, p50/p95, memory/disk/model footprint, cancellation and regression threshold. |
| Cross-capability | Upstream fixture compatibility, downstream contract fixture, staleness propagation and no forbidden module dependency. |
| Independent review | Reviewer maps every criterion to evidence, challenges tests and confirms no concealed production blocker. |

Task verification commands are authoritative minimums. The slice review must also run a clean-state combined profile and any benchmark/security/reference checks described here.

## 11. Performance and resource budgets

| Measure | Initial production budget / qualification target |
|---|---|
| Pareto computation | 10,000 candidates x 10 dimensions < 2 s using tested algorithm. |
| Radar load | p95 < 500 ms for filtered/project result set. |
| Similarity | Local 10,000-item portfolio incremental comparison < 5 min with blocking/ANN. |
| Privacy | Zero unauthorized raw facet/text exposure in cross-user tests. |

Budgets are evaluated on documented reference hardware and corpus fixtures. A regression exceeding 20% or violating a hard interaction/resource limit blocks approval unless a reviewed explanation and revised target are accepted before implementation proceeds.

## 12. Observability and provenance

Required metrics and diagnostics:

- assessment completeness/disagreement
- front sizes and rank sensitivity
- candidate selection outcomes
- duplicate/related confirmations
- diversity/convergence
- privacy denials

- One trace/correlation ID links desktop action, core command, workflow job, adapter/model call, provenance activity and evidence artifact.
- Operational telemetry is content-redacted by default. Durable scholarly provenance records source IDs/passages/hashes, schema/policy/model versions, decisions and derivation—not secret-bearing logs.
- Support bundles require user preview and classification-aware exclusion of source text, research ideas, prompts and unpublished results.
- Every promoted output records dependencies so CAP-03 can mark it stale precisely.

## 13. Adjacent-slice handoffs

- Consumes S03 dossiers and S04 detector candidates plus S02 challenge results.
- Provides prioritized approved opportunities to CAP-15/16 and living portfolio memory.
- Outcome links feed later design-science evaluation without creating predictive claims.

Handoffs must include portable schemas, accepted/rejected examples, failure fixtures, manifest/version rules, performance baselines and evidence IDs. An informal README-only handoff is insufficient.

## 14. Migration and backward compatibility

- Version every durable schema, policy, model/index/graph manifest and export profile. Use forward migrations with preflight, backup, rollback/repair evidence and test fixtures from the prior supported release.
- Rebuilding a derivative does not mutate canonical evidence/decisions. Old and new derivative versions remain distinguishable until promotion and dependent staleness are resolved.
- Project moves and later Windows/macOS/Linux qualification cannot rely on absolute paths or machine-specific IDs in portable records.
- Deprecations include reader compatibility, warnings, migration telemetry and a declared removal release. Unsupported old projects open read-only with repair/export options rather than silent partial upgrade.

## 15. Required slice evidence bundle

- Approved capability decision packet and this approved slice plan at immutable commits.
- Reviewed commits/diffs for all tasks and criterion-to-evidence records.
- Unit, contract, integration, end-to-end, failure, cancellation, restart, recovery, migration and performance reports.
- Security/privacy/rights/research-integrity review and accessibility/UI conformance evidence where applicable.
- Schemas, migrations, API/client fixtures, model/index/graph manifests, benchmark datasets and hashes.
- Architecture dependency report, staleness/provenance traces and adjacent-slice handoff fixture.
- Independent slice review with approved/changes-requested/blocked outcome.

## 16. Definition of Ready

- Capability packet is decision-complete and approved; each decision lists options, recommendation, accepted selection and migration boundary.
- This plan and all other capability slice plans exist, pass structural checks and are approved.
- Required ADRs/experience changes are approved before the campaign starts.
- Dependencies, fixtures, credentials/licenses, platform resources and human authorities are available or explicitly stubbed.
- The first task is `READY`, no conflicting lease exists, and the campaign can plausibly run to production-ready capability completion without routine stop points.

## 17. Definition of Done

- Every task is `DONE` and independently approved.
- Slice-wide verification passes from a clean state on the required platform/profile.
- Failure, denial, cancellation, restart, migration, recovery, security, accessibility and performance paths satisfy this plan.
- No concealed TODO, placeholder, skipped mandatory test, unreviewed architecture divergence or production blocker remains.
- Handoff contracts/fixtures and dependency/staleness behavior are accepted by the next slice.
- The capability campaign automatically advances to its next dependency-ready slice.

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Hidden normativity in rubric | Editable/versioned dimensions, assessor identity and raw evidence. |
| Idea leakage | Strict scope and no cross-tenant default. |
| Optimization toward odd but trivial ideas | Significance/leverage review and no single novelty objective. |

## 19. Required ADRs and human decisions

- ADR-CAP10-RANKING: dimension contract, Pareto default and portfolio privacy.

All material choices in Sections 4–5 must appear in the capability packet. Before approval, reviewers may accept the recommendation, select a documented alternative, or require more evidence. After capability start, these choices are not reopened for preference; they are reopened only when implementation evidence demonstrates infeasibility or a newly discovered consequential issue outside the approved decision envelope.

## 20. Research and standards basis

- **Literature-Grounded Novelty Assessment of Scientific Ideas** — Broad retrieval, embedding filtering, facet-based reranking and literature-grounded novelty reasoning.  
  https://aclanthology.org/2025.sdp-1.9/
- **ROAD-tv: Research Opportunity Discovery via Topological Data Analysis and Adversarial Multi-LLM Validation** — Structural gap detection, ontology validation and adversarial multi-model evidence checking.  
  https://doi.org/10.1016/j.procs.2026.01.036
- **ResearchAgent: Iterative Research Idea Generation over Scientific Literature** — Graph-grounded idea generation and multi-agent review.  
  https://aclanthology.org/2025.naacl-long.342/
- **PROV-O: The PROV Ontology** — Interoperable provenance entities, activities, agents and derivations.  
  https://www.w3.org/TR/prov-o/

These sources support implementation choices, not universal truth claims. Production selection remains conditional on project-specific benchmarks, licenses, privacy/rights constraints and the accepted capability decision packet.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-10 --require-approved` and `python tools/taskctl.py validate`.
2. Confirm the active campaign is `CAP-10`, this is the current slice, and the approved packet/plan commits match the campaign record.
3. Load only the governing context, capability packet, this slice plan, task record, affected code and tests.
4. Execute all tasks in dependency order. Debug, refactor and use approved fallbacks without routine human pauses.
5. After each task, run focused verification, attach criterion-linked evidence and obtain independent task review.
6. After the last task, run the complete Section 10 matrix from a clean/restarted state and assemble the slice evidence bundle.
7. Request independent slice review. On approval, let `taskctl` advance the campaign automatically to the next slice.
8. Pause only with an allowed category from Section 3.4 and exact evidence/next action. Do not self-approve, weaken tests, alter approved UX after implementation, or declare production readiness from narrative evidence.
