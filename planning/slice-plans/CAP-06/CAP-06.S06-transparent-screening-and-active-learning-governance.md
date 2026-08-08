---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-06
capability_plan: planning/capability-plans/CAP-06.md
planning_gate: capability-decision-complete
slice_id: CAP-06.S06
title: Transparent screening and active-learning governance
status: proposed
wave: W3
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-06.S06.T01
- CAP-06.S06.T02
- CAP-06.S06.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-06.S06 — Transparent screening and active-learning governance

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-06.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and both plan validators pass in approval mode. Once the capability campaign starts, the agent should execute continuously through its slices and pause only for an allowed infeasibility, external dependency, unavailable required hardware, explicit human decision, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-06` — Local search, discovery, corpus diagnostics, and screening |
| Capability objective | Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session. |
| Slice | `CAP-06.S06` — Transparent screening and active-learning governance |
| Slice outcome | Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk. |
| Wave / priority | `W3` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-06.S06.T01`, `CAP-06.S06.T02`, `CAP-06.S06.T03` |
| Slice dependencies | `CAP-06.S05.T02`, `CAP-03.S02.T03` |
| Capability decision packet | `planning/capability-plans/CAP-06.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant pages: search-studio.html, corpus-canvas.html, screening.html |
| Approval state | `PROPOSED` / human approval pending |

## 1. Purpose and contribution to the larger vision

Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk.

This slice advances the capability objective: **Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session.** It is designed as one production vertical inside a long-running capability campaign, not as an isolated technical experiment. The implementation must preserve the platform’s evidence-before-prose rule, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, cross-platform ports, and the distinction between canonical scholarly state and rebuildable analytical derivatives.

**Implementation thesis.** Use active learning to order work—not to decide evidence—while preserving protocol, dual-review conflict handling, random/uncertainty audits and an explicit human-approved stopping record.

The containing capability is complete only when all of its slices satisfy these exit conditions:

- Lexical and semantic indexes are versioned, explainable, rebuildable, and usable offline for project content.
- Search evolution is stored as a visible tree of exact queries, transformations, results, and discovery paths.
- Screening supports human inclusion decisions, uncertainty/random audits, stopping evidence, and reproducible exports.

## 2. Scope

### 2.1 In scope

- Versioned screening protocol, queue, decisions, reasons, assignments and conflicts.
- Transparent active-learning prioritization and model versioning.
- Random audits, uncertainty samples, citation-neighbor checks and stopping diagnostics.

### 2.2 Explicit non-goals

- Automatic include/exclude based solely on model score.
- Claiming statistical recall without a declared estimation method and assumptions.
- Hiding records from human access because they rank low.
- Do not implement downstream capability behavior beyond narrow ports, fixtures and handoffs explicitly named here.
- Do not introduce university-hosted or managed-cloud infrastructure during the local Windows waves; preserve deployment-neutral contracts only.
- Do not bypass the Core API, canonical repositories, provenance ledger, durable workflow fabric, rights policy, model gateway or approved experience reference.
- Do not declare completion from happy-path task tests alone; slice-wide failure, cancellation, restart, migration, security, accessibility and handoff evidence is required.

### 2.3 Slice boundary

- **Consumes:** `CAP-06.S05.T02`, `CAP-03.S02.T03` and the handoffs in Section 13.
- **Produces:** Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk.
- **Owns:** The portable domain contracts, adapter boundaries, workflows, fixtures, decisions and evidence explicitly listed in this plan.
- **Does not own:** Product purpose, unrelated capabilities, user-authoritative scholarly judgments, source rights, or provider/database/UI framework internals.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. Vision and non-goals in `docs/product/vision.md`.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md`.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved capability decision packet `planning/capability-plans/CAP-06.md`.
5. This approved slice plan.
6. Approved UI reference, workflow/page contracts and style guide for user-facing work.
7. Automation and task-control rules.

### 3.2 Required upstream state

- All slice dependencies are approved or an explicitly approved integration stub exists: `CAP-06.S05.T02`, `CAP-03.S02.T03`.
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
| **Baseline learner** | Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives. | Start with an opaque large neural model. | A simple baseline is fast, inspectable and effective for active prioritization; evaluation can justify replacement. | [ASReview Documentation](https://asreview.readthedocs.io/en/latest/) |
| **Decision model** | Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record. | Overwrite conflicting labels with the last action. | Reviewer independence and disagreement are evidence about the process. | [An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews](https://doi.org/10.1038/s42256-020-00287-7) |
| **Stopping** | Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required. | Stop when model score falls below a fixed threshold. | No single model-derived threshold demonstrates that relevant records are absent. | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) |

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `services/core/research_observatory/modules/screening` | Protocol, assignment, decisions, conflicts, stopping and exports. |
| `services/workers/screening_model` | Feature/model training, prioritization, calibration and versioning. |
| `packages/ui/screening` | Queue, source preview, reasons, conflicts, audits and stopping panel. |
| `packages/contracts/screening` | Protocol, Decision, ModelRun, AuditSample and StoppingRecord schemas. |
| `tests/benchmarks/screening` | Simulation and hidden-relevant-record fixtures. |

The paths are recommendations within the approved modular-monolith/package structure. Exact filenames may change without a new decision if module ownership, portable contracts and dependency directions remain intact.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `ScreeningProtocol` | research intent version, criteria, phases, roles, reasons and stopping policy |
| `ScreeningDecision` | record/reviewer/protocol, include/exclude/uncertain, reason, timestamp and evidence |
| `PrioritizationModelRun` | training labels, feature/model versions, seed, metrics and ranked queue |
| `AuditSample` | random/uncertainty/citation-neighbor sampling frame, seed and outcomes |
| `StoppingRecord` | signals, estimates, residual risk, approver and decision |

**Cross-cutting invariants**

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, graph projections, rankings, generated drafts and detector signals are versioned derivatives.
- Unknown, not reported, not applicable, denied, unavailable, ambiguous, inferred, disputed, stale and failed remain distinct where relevant.
- Every long-running operation has stable identity, status, inputs/manifests, progress, cancellation, checkpoint, restart and evidence records.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `ScreeningQueue.next(assignment, strategy)` returns accessible ranked records and reason signals.
- `ScreeningDecision.record` is append-only and conflict-aware.
- `Prioritizer.train/predict` runs from a frozen label snapshot and deterministic seed.
- `StoppingAssessment.compute` returns recommendation/uncertainty; only human command changes workflow state.

All contracts use stable canonical IDs, explicit revisions/status, typed errors and version metadata. Provider SDK objects, SQLite rows, model tensors, graph library objects and UI component state may not cross the owning adapter boundary.

### 5.4 Cross-capability and platform compatibility

- Windows x64 is the current implementation target, but paths, process control, credential storage, accelerators and packaging stay behind adapters required by CAP-14 macOS/Linux qualification.
- Local and hosted deployments use the same domain/API/workflow semantics; storage, process, authentication and scaling adapters differ later.
- Downstream CAP-11–19 consume immutable IDs, evidence/provenance, manifests and ports rather than internal tables or framework classes.
- Model, embedding, reranker, parser, graph and vector choices are pinned and replaceable; changing one marks exact dependents stale and requires evaluation rather than silent regeneration.

## 6. User experience and approved reference

- Selected use-case workflow places screening after corpus construction and before evidence extraction.
- Record view keeps title/abstract/source/provenance visible; keyboard shortcuts require explicit confirmation for exclusion.
- Users can switch to chronological/random/uncertainty views and inspect why a record was prioritized.
- Stopping panel shows each signal, misses found by audits and a bounded residual-risk statement.

- Workflow navigation must show the project’s selected use case, current numbered stage, completed/upcoming states, expected output and next/previous actions.
- Supporting tools remain accessible, but opening one explains its relationship to the primary path and offers return to the current stage.
- All semantic states use text/icon in addition to color, meet WCAG 2.2 AA targets, support keyboard operation, and have light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed—not left as generic alerts.

**Reference-first rule.** If the planned experience materially differs from `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit approval and a new reference ID; only then implement application code. Restoring a defect to the approved reference does not require a new reference.

## 7. Security, privacy, rights and research integrity

- Reviewer identity and decisions are project-controlled and auditable.
- Model features exclude restricted full text unless project rights permit local processing.
- Remote models are not required; any remote screening model follows CAP-07 egress policy.

Additional mandatory controls:

- Treat source content, metadata, model files, provider responses, reports, URLs, archives and rich text as untrusted.
- Apply least privilege, schema/input validation, destination/path controls, bounded resources, output encoding and redacted diagnostics at trusted boundaries.
- Private projects and unpublished ideas remain local by default; egress requires project policy, rights decision and visible payload/provider preview.
- Never fabricate evidence, citations, availability, permissions, method details, model certainty, benchmark success or completion evidence.
- AI output is candidate state until the domain-specific verifier/human gate promotes it.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior |
|---|---|
| Model training fails | Continue manual/random queue; preserve labels and report diagnostics. |
| Class imbalance | Use class weights/resampling only as versioned model policy; report calibration and yield. |
| Reviewer conflict | Route to adjudication; never silently collapse. |
| Stopping audit finds relevant records | Invalidate stopping recommendation, expand/retrain and record why. |

Every scenario receives a deterministic fixture where feasible, expected canonical state, expected derivative state, user message/action, retry/cancel rule, cleanup/repair rule, provenance event and automated test. A restart test must execute from persisted state rather than from an in-memory mock alone.

## 9. Task-by-task implementation plan

### CAP-06.S06.T01 — Implement screening protocol, queue, decisions, and conflicts

**Objective.** Inclusion/exclusion criteria, title/abstract/full-text stages, reasons, reviewer assignment, blinded option, decisions, and adjudication state.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S05.T02`, `CAP-03.S02.T03` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `service`, `desktop`, `data` |

**Expected deliverables**

- Inclusion/exclusion criteria, title/abstract/full-text stages, reasons, reviewer assignment, blinded option, decisions, and adjudication state.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S06.T01`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
4. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
5. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
6. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
7. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- No final decision lacks actor/reason/stage; criteria version is attached; conflicts remain unresolved until explicit adjudication.
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
python tools/verify.py --profile service
python tools/verify.py --profile desktop
python tools/verify.py --profile data
```


### CAP-06.S06.T02 — Implement active-learning prioritization and model versioning

**Objective.** Pluggable screening ranker trained on project decisions, uncertainty sampling, predictions, model snapshots, and explanation features.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S06.T01` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `search`, `ai`, `service` |

**Expected deliverables**

- Pluggable screening ranker trained on project decisions, uncertainty sampling, predictions, model snapshots, and explanation features.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S06.T02`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
5. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
6. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
7. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
8. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
9. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Prioritization never writes inclusion decisions; retraining is reproducible from labeled data; low-data behavior and class imbalance are tested.
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
python tools/verify.py --profile search
python tools/verify.py --profile ai
python tools/verify.py --profile service
```


### CAP-06.S06.T03 — Implement random audits, citation-neighbor checks, and stopping diagnostics

**Objective.** Audit sampler, rejected-neighbor queue, discovery curves, residual-risk indicators, stopping proposal, and human approval.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S06.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `method-review` |
| Verification profiles | `search`, `desktop`, `evidence` |

**Expected deliverables**

- Audit sampler, rejected-neighbor queue, discovery curves, residual-risk indicators, stopping proposal, and human approval.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S06.T03`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
4. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
5. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Stopping cannot be accepted without recorded audits and corpus diagnostics; deliberately hidden relevant fixtures are recoverable through at least one safety channel; limitations are explicit.
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
python tools/verify.py --profile search
python tools/verify.py --profile desktop
python tools/verify.py --profile evidence
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
| Decision save/next record | p95 < 200 ms local. |
| Model retrain | 100,000 title/abstract records < 60 s for baseline on reference machine. |
| Queue refresh | p95 < 2 s after retrain for 100,000 records. |
| Audit generation | Deterministic sample generation < 5 s with stored seed/frame. |

Budgets are evaluated on documented reference hardware and corpus fixtures. A regression exceeding 20% or violating a hard interaction/resource limit blocks approval unless a reviewed explanation and revised target are accepted before implementation proceeds.

## 12. Observability and provenance

Required metrics and diagnostics:

- screening decisions/hour
- conflict rate
- model WSS/recall simulations
- yield by rank
- audit miss rate
- citation-neighbor recovery
- stopping reversals

- One trace/correlation ID links desktop action, core command, workflow job, adapter/model call, provenance activity and evidence artifact.
- Operational telemetry is content-redacted by default. Durable scholarly provenance records source IDs/passages/hashes, schema/policy/model versions, decisions and derivation—not secret-bearing logs.
- Support bundles require user preview and classification-aware exclusion of source text, research ideas, prompts and unpublished results.
- Every promoted output records dependencies so CAP-03 can mark it stale precisely.

## 13. Adjacent-slice handoffs

- Consumes search/corpus result sets, protocols and document previews.
- Produces included corpus decisions, PRISMA flow counts and stopping records for CAP-08/CAP-09.
- Provides labeled relevance sets to retrieval evaluation without allowing training leakage into held-out tests.

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
| Automation bias | Alternate queues, random audits, explanations and human decision authority. |
| Self-confirming terminology | Citation-neighbor and random audits, cross-source expansion and visible false negatives. |
| Premature stopping | Multi-signal recommendation and explicit approver. |

## 19. Required ADRs and human decisions

- ADR-CAP06-SCREENING: initial active-learning baseline and stopping evidence policy.

All material choices in Sections 4–5 must appear in the capability packet. Before approval, reviewers may accept the recommendation, select a documented alternative, or require more evidence. After capability start, these choices are not reopened for preference; they are reopened only when implementation evidence demonstrates infeasibility or a newly discovered consequential issue outside the approved decision envelope.

## 20. Research and standards basis

- **ASReview Documentation** — Transparent active-learning-assisted screening patterns.  
  https://asreview.readthedocs.io/en/latest/
- **An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews** — Evidence for active-learning screening with human decisions.  
  https://doi.org/10.1038/s42256-020-00287-7
- **PRISMA 2020 Statement** — Systematic-review flow and reporting outputs.  
  https://doi.org/10.1136/bmj.n71
- **PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches** — Search-strategy and information-source reporting.  
  https://doi.org/10.1186/s13643-020-01542-z

These sources support implementation choices, not universal truth claims. Production selection remains conditional on project-specific benchmarks, licenses, privacy/rights constraints and the accepted capability decision packet.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-06 --require-approved` and `python tools/taskctl.py validate`.
2. Confirm the active campaign is `CAP-06`, this is the current slice, and the approved packet/plan commits match the campaign record.
3. Load only the governing context, capability packet, this slice plan, task record, affected code and tests.
4. Execute all tasks in dependency order. Debug, refactor and use approved fallbacks without routine human pauses.
5. After each task, run focused verification, attach criterion-linked evidence and obtain independent task review.
6. After the last task, run the complete Section 10 matrix from a clean/restarted state and assemble the slice evidence bundle.
7. Request independent slice review. On approval, let `taskctl` advance the campaign automatically to the next slice.
8. Pause only with an allowed category from Section 3.4 and exact evidence/next action. Do not self-approve, weaken tests, alter approved UX after implementation, or declare production readiness from narrative evidence.
