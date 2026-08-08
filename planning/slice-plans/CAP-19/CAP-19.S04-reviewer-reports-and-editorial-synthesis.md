---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-19
capability_plan: planning/capability-plans/CAP-19.md
planning_gate: capability-decision-complete
slice_id: CAP-19.S04
title: Reviewer reports and editorial synthesis
status: proposed
wave: W8
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- platform-neutral
task_ids:
- CAP-19.S04.T01
- CAP-19.S04.T02
- CAP-19.S04.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-19.S04 — Reviewer reports and editorial synthesis

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-19.md` is decision-complete and approved, this plan is approved, required ADRs/design references are accepted or explicitly waived, and the plan validators pass in approval mode. Once the capability campaign starts, execution continues through its slices and pauses only for an allowed infeasibility, external dependency, unavailable required hardware, genuinely new human decision, higher-authority conflict, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-19` — Reviewer simulation, editorial synthesis, and revision |
| Capability objective | Subject generated or uploaded empirical, theory, and critical drafts to independent multi-role simulated peer review, evidence-aware editorial synthesis, and author-controlled revision and response rounds. |
| Slice | `CAP-19.S04` — Reviewer reports and editorial synthesis |
| Slice outcome | The system produces rigorous, transparent simulated peer review while preserving disagreement and uncertainty. |
| Wave / priority | `W8` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `platform-neutral` |
| Backlog tasks | `CAP-19.S04.T01`, `CAP-19.S04.T02`, `CAP-19.S04.T03` |
| Slice dependencies | `CAP-19.S02.T03`, `CAP-19.S03.T03` |
| Capability decision packet | `planning/capability-plans/CAP-19.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant references: `reviewer-simulation.html`, `revision-response.html`, `manuscript-studio.html`, `audit-lineage.html` |
| Approval state | PROPOSED / recommendations resolved; capability approval pending |

## 1. Purpose and contribution to the larger vision

The system produces rigorous, transparent simulated peer review while preserving disagreement and uncertainty.

This slice advances the capability objective: **Subject generated or uploaded empirical, theory, and critical drafts to independent multi-role simulated peer review, evidence-aware editorial synthesis, and author-controlled revision and response rounds.** It is one production vertical inside a long-running capability campaign, not an isolated experiment. Its implementation must preserve evidence before prose, stable scholarly identity, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, rights-aware processing, deployment-neutral contracts, cross-platform portability and the distinction between canonical state and rebuildable analytical derivatives.

**Implementation thesis.** Produce structured independent reports and a separate editorial synthesis that organizes agreement and disagreement without manufacturing consensus.

Compatibility with the larger program is mandatory. The slice consumes stable outputs from earlier capabilities and publishes only explicit contracts to later ones. It must not fork project semantics for deployment profile or operating system, bypass the Core API/provenance/workflow/model-policy boundaries, or pre-implement downstream capability behavior beyond narrow ports, fixtures and handoff contracts. Capability completion still requires all exit criteria:

- Reviewer roles and criteria match the research type and verified venue expectations, operate independently, and expose evidence, confidence, and possible overreach.
- Generated or uploaded manuscript snapshots are immutable and audited against project evidence, technical reports, article blueprints, and venue criteria.
- Editorial synthesis preserves disagreement and does not present simulated decisions as actual peer review or acceptance probability.
- Every review comment can be triaged, linked to a revision, answered, diffed, and re-reviewed with full lineage.

## 2. Scope

### 2.1 In scope

- Evidence-linked independent reviewer reports.
- Comment severity/confidence/action schema.
- Editorial/meta-review synthesis.
- Reviewer quality, calibration and overreach auditing.

### 2.2 Explicit non-goals

- Do not implement downstream capability behavior beyond the ports, fixtures and handoffs explicitly named here.
- Do not alter product purpose, accepted scholarly interpretations, rights policy or researcher authority.
- Do not introduce hidden network calls, provider lock-in, OS-specific canonical state or deployment-specific semantics.
- Do not replace evidence-linked states with opaque scores or fluent prose.
- Do not claim production readiness from happy-path tests or task completion alone; slice-wide failure, denial, cancellation, restart, migration, security, accessibility and handoff evidence is required.
- Do not implement an intentional user-experience change before the governed reference is updated and approved.

### 2.3 Slice boundary

- **Consumes:** `CAP-19.S02 completed independent runs and CAP-19.S03 frozen snapshot` and formal dependencies `CAP-19.S02.T03`, `CAP-19.S03.T03`.
- **Produces:** The system produces rigorous, transparent simulated peer review while preserving disagreement and uncertainty.
- **Owns:** the domain contracts, adapters, workflows, fixtures, policy decisions and evidence listed in this plan.
- **Does not own:** unrelated capabilities, source-provider internals, institutional/cloud operations outside this capability, or user-authoritative scholarly/ethics judgments.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. `docs/product/vision.md` for purpose, users and non-goals.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md` for architecture and deployment boundaries.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved `planning/capability-plans/CAP-19.md` for all material capability decisions.
5. This approved slice plan for implementation detail.
6. Approved style guide, workflow catalog, page contracts and HTML references for user-facing behavior.
7. Repository automation and task-control rules.

### 3.2 Required upstream state

- Every formal dependency is complete or an explicitly approved integration stub exists: `CAP-19.S02.T03`, `CAP-19.S03.T03`.
- Every slice plan in `CAP-19` exists, matches the backlog and is approved at the same commit as the capability packet.
- All material decisions have selected options, rationales and accepted states; required ADRs and design references are accepted.
- Required fixtures, benchmark environments, platform hardware, source/model licenses, provider test accounts and human authority are available or represented by approved deterministic substitutes.
- Relevant prior capability contract tests pass before implementation starts.

### 3.3 Decision-complete capability rule

Planning by capability is the default. Before `capability start`, the planning agent inspects all slices and adjacent contracts, researches credible options, and records the strongest best-in-class recommendation as the selected and accepted option for every material decision in the capability packet. Those selections count as completed decisions. The static review site is a confirmation-and-override surface plus the one-time capability approval gate; implementation agents must not repeatedly ask for choices already settled by the packet. After approval, execution proceeds continuously slice by slice through a production-ready end-to-end capability.

### 3.4 Allowed pauses after execution begins

The campaign may pause only for demonstrated infeasibility of an approved design; an unavailable external credential/service/license/approval; unavailable required physical hardware; a consequential choice that could not reasonably have been identified during planning; a conflict with higher authority; or a required governed design-reference change. Ordinary debugging, refactoring, test failure, model fallback, performance work, task transition or a choice already covered by the packet is not a pause condition. A pause record must link the exact decision and generated review page.

## 4. Selected implementation decisions

The capability packet's researched best-in-class recommendations are already selected, accepted, and decision-complete. This section projects the applicable decisions into the slice implementation contract. Capability approval authorizes those defaults; a reviewer may override a selection before approval only with explicit rationale. During execution, no implementation agent may silently choose a different candidate.


The table below projects the capability packet’s resolved best-in-class defaults into this slice. They are already selected and decision-complete. Capability approval authorizes them as the execution contract; a reviewer may override a default before approval only with an explicit rationale.

| Decision | Recommended selection | Alternative not selected | Rationale | ADR |
|---|---|---|---|---|
| `CAP-19-D05` | Comment schema | **Use structured location, criterion, category, severity, confidence, evidence, rationale and requested-action fields** | Store only free-form review prose | Structured comments support triage, revision mapping, calibration and export while preserving narrative detail. | None |
| `CAP-19-D11` | Panel diversity | **Use role and model diversity with deterministic manifests and compare disagreements** | Use multiple identical prompts to the same model and call it independent | Meaningful diversity requires different criteria/context/model configurations and explicit correlation analysis. | None |
| `CAP-19-D12` | Acceptance prediction | **Prohibit acceptance-probability claims and named-reviewer impersonation** | Predict venue acceptance and simulate named scholars | Reviewer simulation is a developmental critique, not a guarantee or impersonation service. | None |
| `CAP-19-D13` | Editorial synthesis | **Run a separate meta-review stage over completed reports and preserve material disagreement** | Average scores and collapse comments to consensus | Editorial synthesis should organize tradeoffs without erasing dissent. | None |
| `CAP-19-D14` | Calibration and overreach | **Benchmark comments against expert reviews and track false positives, unsupported severity and criterion drift** | Assume fluent reviewer output is reliable | Reviewer quality must be evaluated as a research-support mechanism. | None |

No implementation may silently choose a different candidate. If evidence makes an accepted selection infeasible, document the failed assumption, strongest feasible replacements, compatibility/migration cost and recommendation on the capability review page, then obtain focused approval before resuming.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `packages/core/review/reports` | report/comment domain |
| `workers/reviewer/meta` | editorial synthesis over closed reports |
| `workers/reviewer/audit` | evidence, severity and overreach checks |
| `services/core-api/reviews/reports` | acceptance and publication |

Exact filenames may change without reopening planning if ownership, dependency direction, portable contracts and test/evidence boundaries remain intact. New cross-capability dependencies or changed trust/deployment boundaries require the packet/ADR process.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `ReviewerReport` | Versioned ReviewerReport state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |
| `ReviewComment` | Versioned ReviewComment state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |
| `EditorialSynthesis` | Versioned EditorialSynthesis state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |
| `ReviewerDisagreement` | Versioned ReviewerDisagreement state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |
| `ReviewerCalibrationFinding` | Versioned ReviewerCalibrationFinding state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |
| `ReviewerQualityAudit` | Versioned ReviewerQualityAudit state with stable identity, lifecycle/status, provenance and policy metadata appropriate to reviewer reports and editorial synthesis. |

Cross-cutting invariants:

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, projections, caches, generated recommendations, dashboards and platform artifacts are versioned derivatives.
- Every mutation has stable identity, revision, actor, timestamp, causation/correlation and source or decision provenance.
- Unknown, not reported, unavailable, denied, inferred, disputed, stale and failed remain distinct.
- Long operations persist inputs/manifests, progress, lease, cancellation, retry/checkpoint/restart and terminal evidence.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `Independent reports are immutable after acceptance; corrections create revisions.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Meta-review consumes reports, not hidden reviewer chain-of-thought.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Material disagreement is preserved and mapped to comments/criteria.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.

Provider SDK objects, database rows, OS handles, cluster resources, model tensors and UI state may not cross their owning adapter boundary. Contracts include capability/version negotiation and stable error categories so local, institutional, cloud and cross-platform implementations can be tested against the same behavior.

### 5.4 Cross-capability and platform compatibility

- **Upstream:** CAP-19.S02 completed independent runs and CAP-19.S03 frozen snapshot.
- **Downstream:** CAP-19.S05 revision and response workflow.
- Windows x64 remains the release-authoritative base for CAP-11; CAP-14 adds macOS ARM64 and Linux x86_64/ARM64 without changing canonical semantics.
- Institutional and cloud deployments reuse the same domain/API/workflow meanings; persistence, process, authentication, tenancy and scaling adapters differ.
- Model, parser, vector, graph, workflow, identity, packaging and billing technologies are pinned behind ports and replaceable only through evaluation/ADR where material.
- A changed source, schema, model, policy or decision marks exact dependents stale; it does not silently regenerate accepted outputs.

## 6. User experience and approved reference

- Show report tabs by role and a synthesis view with agreement/disagreement.
- Let researchers reject, reclassify or defer comments with rationale.

- Workflow navigation shows the selected use case, current numbered stage, completed/upcoming/attention states, expected output and previous/next actions.
- Supporting tools remain accessible; opening one explains its relationship to the primary workflow and provides return to the current stage.
- Every semantic state uses text/icon as well as color, targets WCAG 2.2 AA, supports keyboard operation, and maintains light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed explicitly.

**Reference-first rule.** Current reference: `RO-UI-ACADEMIC-MINIMAL-1.3`. Relevant pages: `reviewer-simulation.html`, `revision-response.html`, `manuscript-studio.html`, `audit-lineage.html`. If planned behavior materially differs, first update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit human approval and a new reference ID; then implement. For CAP-12 or CAP-13 administration surfaces with no existing approved page, the plan may establish nonvisual contracts, but UI implementation remains blocked on this process.

## 7. Security, privacy, rights and research integrity

- Do not expose private model reasoning or confidential source text in exports.
- Redact provider identifiers where policy requires while preserving reproducibility manifest internally.

Additional mandatory controls:

- Treat imported documents, archives, URLs, provider/model responses, native packages and rich text as untrusted.
- Apply least privilege, schema/input validation, path/destination controls, bounded resources, output encoding and redacted diagnostics at every trust boundary.
- Private projects and unpublished ideas remain local or tenant-contained by default; egress requires policy, rights decision and visible payload/provider context.
- Never fabricate evidence, citations, availability, permissions, approval, methods, benchmark success or completion evidence.
- AI output is candidate state until the domain verifier and required human authority promote it.
- Security and privacy evidence must test denied paths and verify that canonical state remains unchanged or exactly recoverable.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior | Required test |
|---|---|---|
| meta-review drops minority concern | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| comment lacks location/evidence | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| severity unsupported by criterion | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| reviewer hallucinates venue requirement | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |

Every operation additionally defines cancellation boundaries, idempotency keys, lease expiry, retry classification, cleanup and restart behavior. A restart test uses persisted state rather than an in-memory fake. Partial results stay explicitly partial, and recovery never promotes unverified content or weakens rights/authorization to complete work.

## 9. Task-by-task implementation plan

### CAP-19.S04.T01 — Generate independent reviewer reports with evidence and uncertainty

**Objective.** Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.

| Control | Value |
|---|---|
| Dependencies | CAP-19.S02.T03, CAP-19.S03.T03 |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | reviewer, ai |

**Expected deliverables**

- Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.

**Ordered implementation sequence**

1. Confirm the approved capability packet, approved slice plan, dependencies, affected portable contracts and criterion-to-evidence IDs. Add failing tests for the expected path and at least one material denial, failure, cancellation, restart, migration or boundary condition before production code.
2. Define or revise portable domain schemas and invariants first. Validate positive and negative fixtures; keep provider, OS, database, cluster, model and UI framework objects behind adapters.
3. Implement the smallest end-to-end path through domain service, repository/adapter, durable workflow and approved UI/API surface. Make authorization, rights, transaction/idempotency, cancellation and restart boundaries explicit.
4. Pin dependency/runtime/model/provider versions and record manifests. Treat external and model outputs as untrusted candidate state; validate before canonical persistence or execution.
5. Exercise representative scale, degraded/fallback behavior and relevant platform/deployment profiles. Record latency, resource/cost and quality evidence against declared budgets.
6. Test security, privacy, rights, research-integrity and accessibility boundaries. A failure must leave canonical state unchanged or exactly recoverable, with actionable user-visible status and provenance.
7. Run focused tests plus every declared verification profile. Capture machine-readable reports, artifacts, screenshots/traces where applicable and hashes tied to the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed blockers. Do not self-approve or advance until the review passes.

**Acceptance criteria from the authoritative backlog**

- Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-19.S04.T02 — Implement editorial synthesis preserving reviewer disagreement

**Objective.** An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.

| Control | Value |
|---|---|
| Dependencies | CAP-19.S04.T01 |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | reviewer, ai |

**Expected deliverables**

- An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.

**Ordered implementation sequence**

1. Confirm the approved capability packet, approved slice plan, dependencies, affected portable contracts and criterion-to-evidence IDs. Add failing tests for the expected path and at least one material denial, failure, cancellation, restart, migration or boundary condition before production code.
2. Define or revise portable domain schemas and invariants first. Validate positive and negative fixtures; keep provider, OS, database, cluster, model and UI framework objects behind adapters.
3. Implement the smallest end-to-end path through domain service, repository/adapter, durable workflow and approved UI/API surface. Make authorization, rights, transaction/idempotency, cancellation and restart boundaries explicit.
4. Pin dependency/runtime/model/provider versions and record manifests. Treat external and model outputs as untrusted candidate state; validate before canonical persistence or execution.
5. Exercise representative scale, degraded/fallback behavior and relevant platform/deployment profiles. Record latency, resource/cost and quality evidence against declared budgets.
6. Test security, privacy, rights, research-integrity and accessibility boundaries. A failure must leave canonical state unchanged or exactly recoverable, with actionable user-visible status and provenance.
7. Run focused tests plus every declared verification profile. Capture machine-readable reports, artifacts, screenshots/traces where applicable and hashes tied to the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed blockers. Do not self-approve or advance until the review passes.

**Acceptance criteria from the authoritative backlog**

- An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-19.S04.T03 — Implement reviewer quality, calibration, and overreach audits

**Objective.** Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.

| Control | Value |
|---|---|
| Dependencies | CAP-19.S04.T02 |
| Estimate / risk | `M` / `high` |
| Review gate | `scholarly-method-review` |
| Verification profiles | reviewer, ai, evidence |

**Expected deliverables**

- Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.

**Ordered implementation sequence**

1. Confirm the approved capability packet, approved slice plan, dependencies, affected portable contracts and criterion-to-evidence IDs. Add failing tests for the expected path and at least one material denial, failure, cancellation, restart, migration or boundary condition before production code.
2. Define or revise portable domain schemas and invariants first. Validate positive and negative fixtures; keep provider, OS, database, cluster, model and UI framework objects behind adapters.
3. Implement the smallest end-to-end path through domain service, repository/adapter, durable workflow and approved UI/API surface. Make authorization, rights, transaction/idempotency, cancellation and restart boundaries explicit.
4. Pin dependency/runtime/model/provider versions and record manifests. Treat external and model outputs as untrusted candidate state; validate before canonical persistence or execution.
5. Exercise representative scale, degraded/fallback behavior and relevant platform/deployment profiles. Record latency, resource/cost and quality evidence against declared budgets.
6. Test security, privacy, rights, research-integrity and accessibility boundaries. A failure must leave canonical state unchanged or exactly recoverable, with actionable user-visible status and provenance.
7. Run focused tests plus every declared verification profile. Capture machine-readable reports, artifacts, screenshots/traces where applicable and hashes tied to the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed blockers. Do not self-approve or advance until the review passes.

**Acceptance criteria from the authoritative backlog**

- Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.


## 10. Slice-wide verification matrix

| Verification area | Method and evidence | Acceptance |
|---|---|---|
| structured report schema and location validity | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| disagreement preservation tests | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| expert calibration/false-positive study | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| venue-rule provenance audit | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |

The slice reviewer also verifies task-to-slice integration, adjacent contract compatibility, approved-reference conformance, no unrelated scope expansion, and no tests weakened to match the implementation. Reports are machine-readable where possible and linked from the slice evidence manifest.

## 11. Performance and resource budgets

| Budget / objective | Measurement | Gate |
|---|---|---|
| meta-review bounded to accepted reports | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| quality audit runs before report publication | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| large comment sets virtualized and filterable | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |

Before capability approval, any numeric threshold that materially affects support, cost or quality must be selected in the capability packet or a referenced benchmark ADR. Implementation may optimize within the approved boundary but may not quietly relax a threshold. Resource and cost tests include minimum/recommended profiles and sustained workloads where applicable.

## 12. Observability and provenance

The slice emits structured events for operation start/progress/cancel/retry/recover/complete, policy and authorization decisions, dependency/version manifests, user adjudication, stale propagation, performance/cost and verification. Events carry stable project/tenant/operation/task IDs and causation/correlation but exclude raw source text, prompts, unpublished ideas, credentials and participant data by default. Every accepted output can be traced to input revisions, source/evidence records, model/runtime/provider manifests, human decisions and the implementation revision that produced it.

Operational observability and scholarly provenance remain distinct but linkable: operations answer whether the system behaved correctly; provenance answers how a scholarly object came to exist and change. Logs are not a substitute for the append-only provenance ledger, and the ledger is not used as an unrestricted operational log sink.

## 13. Adjacent-slice handoffs

### 13.1 Upstream inputs

CAP-19.S02 completed independent runs and CAP-19.S03 frozen snapshot. The slice validates IDs, revisions, rights/policy state, schema/version compatibility and completeness before accepting the handoff. Missing or stale upstream requirements remain explicit and may block only the affected operation.

### 13.2 Downstream contract

CAP-19.S05 revision and response workflow. The handoff consists of stable portable IDs, revisioned domain objects, evidence/provenance links, manifests, status/uncertainty, policy decisions and documented invalidation triggers—not internal tables, OS paths, cluster objects or SDK types.

### 13.3 Integration ownership

This slice owns producer-side contract tests and fixtures. The receiving slice owns consumer tests. Capability integration executes both, plus an end-to-end scenario that proves the handoff is usable under success, denial, stale and restart conditions.

## 14. Migration and backward compatibility

- New persisted fields default to explicit unknown/not-applicable states and receive versioned migrations with rehearsal and rollback/forward-open policy.
- API/event/schema changes are additive where feasible and use capability negotiation or supported-version windows.
- Existing accepted evidence and human decisions are never rewritten in place; corrected interpretations create revisions and dependency/staleness events.
- Platform/deployment migrations preserve canonical IDs and semantics. Native indexes, caches and runtime artifacts may be rebuilt from manifests.
- Exports and bundles include schema/revision metadata, checksums and compatibility diagnostics.

## 15. Required slice evidence bundle

- Approved capability packet and slice plan hashes.
- Changed-contract/schema/migration manifests.
- Task evidence manifests and independent review records.
- Unit, contract, integration, end-to-end, denial, cancellation, restart and migration reports.
- Security/privacy/rights/research-integrity test reports.
- Accessibility and approved-reference evidence for user-facing work.
- Performance/resource/cost reports against declared profiles.
- Screenshots, traces or package/deployment artifacts where applicable.
- Open limitations, accepted exceptions, residual risk and downstream handoff verification.

## 16. Definition of Ready

- Capability packet and every slice plan exist, validate and are approved at one immutable commit.
- All decisions affecting this slice have accepted selections and rationale; required ADRs/reference changes are approved.
- Dependencies and producer contract tests pass.
- Fixtures, benchmark environments, credentials, licenses, hardware and human reviewers are available or explicitly substituted.
- Acceptance criteria map to named evidence and verification profiles.
- Security, privacy, rights, ethics and platform impacts are classified.

## 17. Definition of Done

- Every backlog task is complete with criterion-linked evidence and independent review.
- Slice outcome works end to end through canonical domain, adapters/workflow and approved UI/API surface.
- Material success, denial, cancellation, restart, migration, recovery and security paths pass.
- Performance/resources meet approved budgets on relevant targets.
- Documentation, contracts, migrations, fixtures, provenance, stale-dependency behavior and adjacent handoffs are current.
- No concealed TODO, unapproved design drift, unsupported completion claim or unresolved production blocker remains.

## 18. Risks and mitigations

| Risk | Failure mode | Mitigation |
|---|---|---|
| Architecture drift | A local task bypasses portable contracts or introduces deployment/OS-specific canonical state. | Architecture fitness tests, adapter boundaries and independent review. |
| False completion | Task tests pass but slice integration, failure or recovery behavior is absent. | Criterion-linked slice evidence and mandatory independent integration review. |
| Automation bias | Users accept generated recommendation, repair or design without sufficient inspection. | Candidate-state labels, alternatives, source-first UI and human adjudication. |
| Privacy/rights leakage | Sensitive or licensed content enters logs, external providers, caches or exports. | Policy enforcement, egress preview, redaction and denial fixtures. |
| Dependency volatility | OS/provider/library/standard behavior changes during implementation. | Pinned manifests, compatibility tests, replaceable ports and approval-time recheck. |
| Long-running campaign stall | A routine problem is mislabeled as a human decision. | Strict pause taxonomy; agent must debug/fallback within accepted choices before escalating. |

## 19. Required ADRs and human decisions

The capability packet lists required ADRs in its decision register. The researched recommendation is already the resolved selection for every decision; reviewers confirm or override those defaults during the one capability approval. No additional per-task approval is expected during normal execution. A new ADR is required only for a material change to system boundary, trust model, canonical data, deployment topology, platform support, public API, governed UX, external provider/rights policy or support commitment.

The static decision page is `planning/review-site/CAP-19/index.html`; this slice page is `planning/review-site/CAP-19/CAP-19.S04.html`. Automation requesting feedback or approval must provide those links and place resolved recommendations and override controls near the top.

## 20. Research and standards basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `OPENREVIEW_META` | [OpenReview Meta Review Stage](https://docs.openreview.net/reference/stages/meta-review-stage) | OpenReview | Editorial synthesis as a distinct stage from independent reviews. |
| `NISO_PEER_REVIEW` | [ANSI/NISO Z39.106-2023 Standard Terminology for Peer Review](https://www.niso.org/publications/z39106-2023-peerreview) | NISO | Consistent reviewer roles, identity transparency and peer-review process terminology. |
| `ICMJE_AI_REVIEWERS` | [ICMJE Use of AI by Reviewers](https://www.icmje.org/recommendations/browse/artificial-intelligence/ai-use-by-reviewers.html) | ICMJE | Confidentiality, permission, validation and disclosure for AI-assisted review. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |

The implementation team must recheck current versions, target support, licenses and institutional/provider contracts immediately before capability approval. Official documentation governs technical integration; research/reporting standards guide methods and evaluation. Neither substitutes for project-specific benchmarks, security review, legal/rights review or domain/methods expertise.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-19 --require-approved`; stop and print the generated review URL if it fails.
2. Claim the current slice/task through `taskctl`; verify branch, worktree, base SHA and lease.
3. Load only the approved packet, this plan, authoritative backlog, mapped architecture/standards and affected code/tests.
4. Reconcile current behavior with contracts; create failing acceptance and material boundary tests before implementation.
5. Implement through portable domain/API/workflow boundaries; record decisions already settled rather than re-asking.
6. Run focused checks continuously and all declared profiles before task submission.
7. Produce machine-linked evidence tied to the reviewed commit; request independent task review.
8. At task completion, execute slice-wide integration, security/accessibility/performance and handoff verification.
9. Request independent slice review. If approved, allow `taskctl` to advance directly to the next ready slice in `CAP-19`.
10. Pause only under the approved taxonomy; preserve state and provide the capability/slice review-site link with the affected decision and recommendation.
