---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-10
capability_plan: planning/capability-plans/CAP-10.md
planning_gate: capability-decision-complete
slice_id: CAP-10.S01
title: Nearest-prior novelty workspace MVP
status: proposed
wave: W4
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-10.S01.T01
- CAP-10.S01.T02
- CAP-10.S01.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-10.S01 — Nearest-prior novelty workspace MVP

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-10.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and both plan validators pass in approval mode. Once the capability campaign starts, the agent should execute continuously through its slices and pause only for an allowed infeasibility, external dependency, unavailable required hardware, explicit human decision, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-10` — Novelty auditing, research opportunities, and plural research modes |
| Capability objective | Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory. |
| Slice | `CAP-10.S01` — Nearest-prior novelty workspace MVP |
| Slice outcome | A proposed research contribution can be decomposed and compared against the closest literature in a transparent local workflow. |
| Wave / priority | `W4` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-10.S01.T01`, `CAP-10.S01.T02`, `CAP-10.S01.T03` |
| Slice dependencies | `CAP-09.S04.T02`, `CAP-06.S03.T03` |
| Capability decision packet | `planning/capability-plans/CAP-10.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant pages: novelty-audit.html, opportunity-radar.html, critical-lens.html, research-notebook.html, living-monitor.html |
| Approval state | `PROPOSED` / human approval pending |

## 1. Purpose and contribution to the larger vision

A proposed research contribution can be decomposed and compared against the closest literature in a transparent local workflow.

This slice advances the capability objective: **Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory.** It is designed as one production vertical inside a long-running capability campaign, not as an isolated technical experiment. The implementation must preserve the platform’s evidence-before-prose rule, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, cross-platform ports, and the distinction between canonical scholarly state and rebuildable analytical derivatives.

**Implementation thesis.** Evaluate novelty as a bounded, facet-by-facet comparison against the strongest retrieved prior work, using multiple retrieval routes and explicit threat explanations instead of a persuasive originality score.

The containing capability is complete only when all of its slices satisfy these exit conditions:

- The local MVP decomposes an idea, retrieves nearest prior work, compares facets, and produces bounded novelty language with human approval.
- Critical and hermeneutic workflows preserve alternative readings, researcher memos, explicit assumptions, and interpretive authority before theory/critical article production.
- Advanced detectors produce typed candidates with false-positive warnings rather than a universal gap score.
- Accepted opportunities can hand off explicitly to empirical study design or empirical/theory/critical manuscript-development workflows.
- Living-monitor changes can identify affected claims, designs, manuscripts, reviews, and opportunity assessments.

## 2. Scope

### 2.1 In scope

- Research-concept and facet schema.
- Multi-route nearest-prior retrieval and candidate union.
- Facet comparison grid, threat review and human closest-work set.

### 2.2 Explicit non-goals

- Claiming universal novelty.
- Generating opportunities before a researcher defines the proposed concept.
- Using embedding distance as the novelty verdict.
- Do not implement downstream capability behavior beyond narrow ports, fixtures and handoffs explicitly named here.
- Do not introduce university-hosted or managed-cloud infrastructure during the local Windows waves; preserve deployment-neutral contracts only.
- Do not bypass the Core API, canonical repositories, provenance ledger, durable workflow fabric, rights policy, model gateway or approved experience reference.
- Do not declare completion from happy-path task tests alone; slice-wide failure, cancellation, restart, migration, security, accessibility and handoff evidence is required.

### 2.3 Slice boundary

- **Consumes:** `CAP-09.S04.T02`, `CAP-06.S03.T03` and the handoffs in Section 13.
- **Produces:** A proposed research contribution can be decomposed and compared against the closest literature in a transparent local workflow.
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

- All slice dependencies are approved or an explicitly approved integration stub exists: `CAP-09.S04.T02`, `CAP-06.S03.T03`.
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
| **Facet contract** | Version facets for phenomenon/problem, theory/mechanism, constructs, population/unit/level, context, method/data, intervention/system, outcomes and claimed contribution; allow mode/domain extensions. | One free-text idea field or fixed biomedical PICO schema. | Novelty threats often overlap on different dimensions and scholarly traditions need extensibility. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| **Retrieval ensemble** | Union lexical, semantic, citation/bibliographic, graph/entity and review/reference-route candidates; retain route/rank and diversify before facet reranking. | Single vector nearest-neighbor search. | Known terminology and conceptual neighbors are found through different routes; route evidence supports audit. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |
| **Threat review** | Show ranked works with per-facet supported overlap, differences, uncertainty and threat level; humans may add/remove/reclassify but history remains. | One 0-100 novelty score. | A reviewer-defensible novelty claim requires specific comparison, not score authority. | [Literature-Grounded Novelty Assessment of Scientific Ideas](https://aclanthology.org/2025.sdp-1.9/) |

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `services/core/research_observatory/modules/novelty/concepts.py` | Research concept/facet/revision domain. |
| `services/core/research_observatory/modules/novelty/retrieval.py` | Multi-route candidate generation and union. |
| `services/core/research_observatory/modules/novelty/facet_comparison.py` | Evidence-grounded overlap/difference assessment. |
| `packages/ui/novelty-audit/nearest-prior` | Concept editor, candidate list and facet threat grid. |
| `packages/contracts/novelty` | Concept, facet, candidate and comparison schemas. |
| `tests/benchmarks/novelty` | Hidden nearest-prior and facet-overlap cases. |

The paths are recommendations within the approved modular-monolith/package structure. Exact filenames may change without a new decision if module ownership, portable contracts and dependency directions remain intact.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `ResearchConcept` | versioned question/contribution, mode, owner and status |
| `ConceptFacet` | typed value, scope, synonyms, evidence/rationale and uncertainty |
| `PriorWorkCandidate` | work/version, retrieval routes/ranks, eligibility and review state |
| `FacetComparison` | facet, overlap/difference/unknown, supporting passages, assessor and status |
| `NearestPriorSet` | ranked accepted/threatening works, search manifest, cutoff and completeness notes |

**Cross-cutting invariants**

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, graph projections, rankings, generated drafts and detector signals are versioned derivatives.
- Unknown, not reported, not applicable, denied, unavailable, ambiguous, inferred, disputed, stale and failed remain distinct where relevant.
- Every long-running operation has stable identity, status, inputs/manifests, progress, cancellation, checkpoint, restart and evidence records.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `ConceptService.revise/approve` preserves prior facet sets.
- `NearestPriorRetriever.retrieve(concept, corpus, routes, policy)` returns candidate union with route provenance.
- `FacetComparator.assess(concept, candidate, schema, model_policy)` emits evidence-linked candidates.
- `PriorWorkReview.accept/reject/reclassify` records researcher decision and reason.

All contracts use stable canonical IDs, explicit revisions/status, typed errors and version metadata. Provider SDK objects, SQLite rows, model tensors, graph library objects and UI component state may not cross the owning adapter boundary.

### 5.4 Cross-capability and platform compatibility

- Windows x64 is the current implementation target, but paths, process control, credential storage, accelerators and packaging stay behind adapters required by CAP-14 macOS/Linux qualification.
- Local and hosted deployments use the same domain/API/workflow semantics; storage, process, authentication and scaling adapters differ later.
- Downstream CAP-11–19 consume immutable IDs, evidence/provenance, manifests and ports rather than internal tables or framework classes.
- Model, embedding, reranker, parser, graph and vector choices are pinned and replaceable; changing one marks exact dependents stale and requires evaluation rather than silent regeneration.

## 6. User experience and approved reference

- Novelty Audit begins with a structured concept, then search coverage, nearest works and the comparison grid.
- Threat levels are descriptive—high/medium/low/unknown—with explicit overlapping facets and passages.
- Users can launch targeted search from a missing/uncertain facet and return without losing audit state.
- Corpus cutoff, languages, databases and unavailable full text stay visible.

- Workflow navigation must show the project’s selected use case, current numbered stage, completed/upcoming states, expected output and next/previous actions.
- Supporting tools remain accessible, but opening one explains its relationship to the primary path and offers return to the current stage.
- All semantic states use text/icon in addition to color, meet WCAG 2.2 AA targets, support keyboard operation, and have light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed—not left as generic alerts.

**Reference-first rule.** If the planned experience materially differs from `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit approval and a new reference ID; only then implement application code. Restoring a defect to the approved reference does not require a new reference.

## 7. Security, privacy, rights and research integrity

- Unpublished idea facets are private-local by default and treated as highly sensitive.
- Remote egress requires exact preview of concept/passages and approved provider policy.
- Telemetry records hashes/counts, never raw research ideas by default.

Additional mandatory controls:

- Treat source content, metadata, model files, provider responses, reports, URLs, archives and rich text as untrusted.
- Apply least privilege, schema/input validation, destination/path controls, bounded resources, output encoding and redacted diagnostics at trusted boundaries.
- Private projects and unpublished ideas remain local by default; egress requires project policy, rights decision and visible payload/provider preview.
- Never fabricate evidence, citations, availability, permissions, method details, model certainty, benchmark success or completion evidence.
- AI output is candidate state until the domain-specific verifier/human gate promotes it.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior |
|---|---|
| No candidate found | Report coverage limits and routes; do not interpret absence as novelty. |
| Full text unavailable | Compare metadata/abstract only with explicit evidence limitation. |
| Facet schema changes | Version concept/comparisons and mark dependent audit stale. |
| Retriever failure | Preserve partial route results, label missing route and block strong completeness claims. |

Every scenario receives a deterministic fixture where feasible, expected canonical state, expected derivative state, user message/action, retry/cancel rule, cleanup/repair rule, provenance event and automated test. A restart test must execute from persisted state rather than from an in-memory mock alone.

## 9. Task-by-task implementation plan

### CAP-10.S01.T01 — Implement research-concept and facet schema

**Objective.** Versioned concept object for problem, phenomenon, theory, constructs, mechanism, context, unit/level, method, data, expected contribution, and claimed distinctions.

| Control | Value |
|---|---|
| Dependencies | `CAP-09.S04.T02`, `CAP-06.S03.T03` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `novelty` |

**Expected deliverables**

- Versioned concept object for problem, phenomenon, theory, constructs, mechanism, context, unit/level, method, data, expected contribution, and claimed distinctions.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S01.T01`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
5. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Required facets vary by mode; blank/uncertain facets remain explicit; revisions preserve rationale and link to the governing research intent.
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
```


### CAP-10.S01.T02 — Implement multi-route nearest-prior retrieval

**Objective.** Facet queries across lexical, semantic, citation, bibliographic, and graph routes with candidate union, deduplication, threat-oriented reranking, and manifest.

| Control | Value |
|---|---|
| Dependencies | `CAP-10.S01.T01` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `novelty`, `search`, `graph` |

**Expected deliverables**

- Facet queries across lexical, semantic, citation, bibliographic, and graph routes with candidate union, deduplication, threat-oriented reranking, and manifest.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S01.T02`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
5. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
6. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
7. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
8. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
9. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Gold nearest-prior fixtures are recovered within declared k; each candidate shows retrieval routes and facet overlaps; missing full text is visible.
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
python tools/verify.py --profile search
python tools/verify.py --profile graph
```


### CAP-10.S01.T03 — Build facet comparison grid and threat review

**Objective.** Side-by-side concept versus prior-study comparison, evidence links, similarity/difference judgments, threat level, reviewer decision, and notes.

| Control | Value |
|---|---|
| Dependencies | `CAP-10.S01.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `scholarly-review` |
| Verification profiles | `desktop`, `novelty`, `documents` |

**Expected deliverables**

- Side-by-side concept versus prior-study comparison, evidence links, similarity/difference judgments, threat level, reviewer decision, and notes.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-10.S01.T03`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
3. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
4. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
5. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
6. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Every distinction cites source evidence or is labeled researcher interpretation; nearest records cannot be dismissed without rationale; unresolved threats block positive novelty status.
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
python tools/verify.py --profile documents
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
| Candidate retrieval | Default multi-route audit returns first 100 candidates < 30 s after local indexes; external routes progressive. |
| Facet comparison | Top 25 works resumable; each comparison bounded by selected passages. |
| Interactive review | Open candidate/grid/source p95 < 500 ms cached. |
| Benchmark | Nearest-prior recall@25 and facet agreement reported by domain/mode, not one aggregate only. |

Budgets are evaluated on documented reference hardware and corpus fixtures. A regression exceeding 20% or violating a hard interaction/resource limit blocks approval unless a reviewed explanation and revised target are accepted before implementation proceeds.

## 12. Observability and provenance

Required metrics and diagnostics:

- candidate coverage by route
- nearest-prior recall@k
- facet comparison agreement/correction
- unknown/full-text-missing rates
- human-added threatening works
- audit time/cost

- One trace/correlation ID links desktop action, core command, workflow job, adapter/model call, provenance activity and evidence artifact.
- Operational telemetry is content-redacted by default. Durable scholarly provenance records source IDs/passages/hashes, schema/policy/model versions, decisions and derivation—not secret-bearing logs.
- Support bundles require user preview and classification-aware exclusion of source text, research ideas, prompts and unpublished results.
- Every promoted output records dependencies so CAP-03 can mark it stale precisely.

## 13. Adjacent-slice handoffs

- Consumes CAP-06 search, CAP-08 evidence and CAP-09 graph/comparison sets.
- Provides reviewed concept/facet/prior-work set to S02 challenger and S03 dossier.
- Later study/manuscript capabilities reuse approved concept and bounded comparison, not raw scores.

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
| False novelty from retrieval miss | Route diversity, coverage diagnostics and bounded language. |
| Idea leakage | Local default, explicit egress preview and redacted logs. |
| Facet overformalization | Extensible schemas, free researcher memo and versioned disagreement. |

## 19. Required ADRs and human decisions

- ADR-CAP10-NOVELTY-MVP: facet schema, retrieval routes and threat semantics.

All material choices in Sections 4–5 must appear in the capability packet. Before approval, reviewers may accept the recommendation, select a documented alternative, or require more evidence. After capability start, these choices are not reopened for preference; they are reopened only when implementation evidence demonstrates infeasibility or a newly discovered consequential issue outside the approved decision envelope.

## 20. Research and standards basis

- **Literature-Grounded Novelty Assessment of Scientific Ideas** — Broad retrieval, embedding filtering, facet-based reranking and literature-grounded novelty reasoning.  
  https://aclanthology.org/2025.sdp-1.9/
- **Synthesizing Scientific Literature with Retrieval-Augmented Language Models** — Domain retrieval, reranking, iterative feedback, citation-aware synthesis and evaluation.  
  https://doi.org/10.1038/s41586-025-10072-4
- **PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches** — Search-strategy and information-source reporting.  
  https://doi.org/10.1186/s13643-020-01542-z
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
