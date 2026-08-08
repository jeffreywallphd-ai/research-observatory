---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-17
capability_plan: planning/capability-plans/CAP-17.md
planning_gate: capability-decision-complete
slice_id: CAP-17.S02
title: Technical-report parsing and result extraction
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
- CAP-17.S02.T01
- CAP-17.S02.T02
- CAP-17.S02.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-17.S02 — Technical-report parsing and result extraction

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-17.md` is decision-complete and approved, this plan is approved, required ADRs/design references are accepted or explicitly waived, and the plan validators pass in approval mode. Once the capability campaign starts, execution continues through its slices and pauses only for an allowed infeasibility, external dependency, unavailable required hardware, genuinely new human decision, higher-authority conflict, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-17` — Technical report and study-results integration |
| Capability objective | Ingest private technical reports of empirical work, extract and verify actual methods/results, reconcile them with planned designs, and make source-anchored result evidence available to manuscript drafting. |
| Slice | `CAP-17.S02` — Technical-report parsing and result extraction |
| Slice outcome | Methods and results become structured candidates linked to exact report evidence. |
| Wave / priority | `W8` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `platform-neutral` |
| Backlog tasks | `CAP-17.S02.T01`, `CAP-17.S02.T02`, `CAP-17.S02.T03` |
| Slice dependencies | `CAP-17.S01.T03` |
| Capability decision packet | `planning/capability-plans/CAP-17.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant references: `technical-reports.html`, `document-reader.html`, `parsing-quality.html`, `audit-lineage.html`, `evidence-matrix.html` |
| Approval state | PROPOSED / recommendations resolved; capability approval pending |

## 1. Purpose and contribution to the larger vision

Methods and results become structured candidates linked to exact report evidence.

This slice advances the capability objective: **Ingest private technical reports of empirical work, extract and verify actual methods/results, reconcile them with planned designs, and make source-anchored result evidence available to manuscript drafting.** It is one production vertical inside a long-running capability campaign, not an isolated experiment. Its implementation must preserve evidence before prose, stable scholarly identity, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, rights-aware processing, deployment-neutral contracts, cross-platform portability and the distinction between canonical state and rebuildable analytical derivatives.

**Implementation thesis.** Extract typed study-result candidates from the richest available structure while preserving exact anchors and explicit missingness.

Compatibility with the larger program is mandatory. The slice consumes stable outputs from earlier capabilities and publishes only explicit contracts to later ones. It must not fork project semantics for deployment profile or operating system, bypass the Core API/provenance/workflow/model-policy boundaries, or pre-implement downstream capability behavior beyond narrow ports, fixtures and handoff contracts. Capability completion still requires all exit criteria:

- Unpublished technical reports and supplements remain confidential, rights-aware, immutable, and versioned.
- Methods, results, tables, figures, deviations, null/mixed findings, and uncertainty are source-anchored and human verified.
- The platform never invents or reverse-engineers unreported empirical results and visibly blocks manuscript use of unresolved records.
- Changes to authoritative reports propagate staleness to dependent drafts, reviews, tables, figures, and exports.

## 2. Scope

### 2.1 In scope

- Native report structure and table/figure parsing.
- Quantitative result extraction.
- Qualitative, mixed-method and technical finding extraction.
- Candidate confidence, not-reported states and source anchors.

### 2.2 Explicit non-goals

- Do not implement downstream capability behavior beyond the ports, fixtures and handoffs explicitly named here.
- Do not alter product purpose, accepted scholarly interpretations, rights policy or researcher authority.
- Do not introduce hidden network calls, provider lock-in, OS-specific canonical state or deployment-specific semantics.
- Do not replace evidence-linked states with opaque scores or fluent prose.
- Do not claim production readiness from happy-path tests or task completion alone; slice-wide failure, denial, cancellation, restart, migration, security, accessibility and handoff evidence is required.
- Do not implement an intentional user-experience change before the governed reference is updated and approved.

### 2.3 Slice boundary

- **Consumes:** `CAP-17.S01 accepted artifact revisions and CAP-05 document structure/anchors` and formal dependencies `CAP-17.S01.T03`.
- **Produces:** Methods and results become structured candidates linked to exact report evidence.
- **Owns:** the domain contracts, adapters, workflows, fixtures, policy decisions and evidence listed in this plan.
- **Does not own:** unrelated capabilities, source-provider internals, institutional/cloud operations outside this capability, or user-authoritative scholarly/ethics judgments.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. `docs/product/vision.md` for purpose, users and non-goals.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md` for architecture and deployment boundaries.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved `planning/capability-plans/CAP-17.md` for all material capability decisions.
5. This approved slice plan for implementation detail.
6. Approved style guide, workflow catalog, page contracts and HTML references for user-facing behavior.
7. Repository automation and task-control rules.

### 3.2 Required upstream state

- Every formal dependency is complete or an explicitly approved integration stub exists: `CAP-17.S01.T03`.
- Every slice plan in `CAP-17` exists, matches the backlog and is approved at the same commit as the capability packet.
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
| `CAP-17-D02` | Supported artifact families | **Support native DOCX/HTML/Markdown, PDF fallback, CSV/XLSX/JSON tables, figures and RO-Crate bundles through typed adapters** | Treat every upload as an unstructured PDF | Native structured inputs preserve more semantics and reduce extraction error. | None |
| `CAP-17-D05` | Parsing strategy | **Prefer native structured parsing and existing document pipeline; use pinned PDF parsers only as fallback** | Use one LLM prompt to read all uploaded formats | Deterministic structure extraction improves anchors, reproducibility and cost. | None |
| `CAP-17-D06` | Result domain | **Use typed QuantitativeResult, QualitativeFinding, MixedMethodsIntegration and TechnicalEvaluation records** | Flatten all outcomes into generic claim/value strings | Method-plural result types preserve the meaning and validation requirements of different studies. | ADR-STUDY-RESULT-DOMAIN |
| `CAP-17-D07` | Quantitative fields | **Capture estimate/test/model, uncertainty, sample/analysis set, endpoint, units, comparator, multiplicity, covariates and robustness exactly as reported** | Store only effect direction and p-value | Manuscript claims need sufficient statistical context and missing fields must remain explicit. | None |
| `CAP-17-D08` | Qualitative fields | **Capture finding/theme, analytic method, cases/context, evidence excerpt, negative cases and interpretation status** | Convert qualitative findings into pseudo-effect sizes | Qualitative integrity requires source-linked interpretive records without forced quantification. | None |
| `CAP-17-D09` | Mixed and technical findings | **Represent integration logic, benchmark conditions, configurations, resource use, failures and robustness as typed records** | Store a prose summary only | Mixed-method and technical claims depend on how evidence streams and configurations relate. | None |
| `CAP-17-D10` | Tabular exchange | **Use Frictionless Table Schema for portable result-table descriptors and validation** | Invent a project-specific CSV convention without a schema | Portable field types, constraints, missing values and keys improve reproducibility and export. | None |
| `CAP-17-D11` | Evidence anchoring | **Anchor every extracted result to document/table/figure/cell selectors with revision-aware fallbacks** | Cite only the report filename | Result verification and later correction require exact source location. | None |
| `CAP-17-D18` | No-result-invention policy | **Use not reported/unclear/unverified states and prohibit filling missing results from expectation or literature** | Allow the model to infer plausible missing values | The platform must never manufacture study findings. | None |

No implementation may silently choose a different candidate. If evidence makes an accepted selection infeasible, document the failed assumption, strongest feasible replacements, compatibility/migration cost and recommendation on the capability review page, then obtain focused approval before resuming.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `workers/result-parser` | format-specific structural adapters |
| `workers/result-extractor` | schema-constrained candidate extraction |
| `packages/contracts/results` | typed result schemas |
| `packages/core/results/normalization` | units, tests, endpoints and finding normalization |

Exact filenames may change without reopening planning if ownership, dependency direction, portable contracts and test/evidence boundaries remain intact. New cross-capability dependencies or changed trust/deployment boundaries require the packet/ADR process.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `QuantitativeResultCandidate` | Versioned QuantitativeResultCandidate state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |
| `QualitativeFindingCandidate` | Versioned QualitativeFindingCandidate state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |
| `MixedMethodsIntegrationCandidate` | Versioned MixedMethodsIntegrationCandidate state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |
| `TechnicalEvaluationCandidate` | Versioned TechnicalEvaluationCandidate state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |
| `ResultAnchor` | Versioned ResultAnchor state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |
| `ExtractionRun` | Versioned ExtractionRun state with stable identity, lifecycle/status, provenance and policy metadata appropriate to technical-report parsing and result extraction. |

Cross-cutting invariants:

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, projections, caches, generated recommendations, dashboards and platform artifacts are versioned derivatives.
- Every mutation has stable identity, revision, actor, timestamp, causation/correlation and source or decision provenance.
- Unknown, not reported, unavailable, denied, inferred, disputed, stale and failed remain distinct.
- Long operations persist inputs/manifests, progress, lease, cancellation, retry/checkpoint/restart and terminal evidence.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `No missing value is inferred.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Every candidate has exact artifact revision and selector provenance.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Parser/extractor/model versions are pinned in the extraction manifest.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.

Provider SDK objects, database rows, OS handles, cluster resources, model tensors and UI state may not cross their owning adapter boundary. Contracts include capability/version negotiation and stable error categories so local, institutional, cloud and cross-platform implementations can be tested against the same behavior.

### 5.4 Cross-capability and platform compatibility

- **Upstream:** CAP-17.S01 accepted artifact revisions and CAP-05 document structure/anchors.
- **Downstream:** CAP-17.S03 reconciliation and CAP-17.S04 evidence graph.
- Windows x64 remains the release-authoritative base for CAP-11; CAP-14 adds macOS ARM64 and Linux x86_64/ARM64 without changing canonical semantics.
- Institutional and cloud deployments reuse the same domain/API/workflow meanings; persistence, process, authentication, tenancy and scaling adapters differ.
- Model, parser, vector, graph, workflow, identity, packaging and billing technologies are pinned behind ports and replaceable only through evaluation/ADR where material.
- A changed source, schema, model, policy or decision marks exact dependents stale; it does not silently regenerate accepted outputs.

## 6. User experience and approved reference

- Show source passage/table/figure beside every candidate.
- Separate parsed structure, extracted candidate and verified result states.

- Workflow navigation shows the selected use case, current numbered stage, completed/upcoming/attention states, expected output and previous/next actions.
- Supporting tools remain accessible; opening one explains its relationship to the primary workflow and provides return to the current stage.
- Every semantic state uses text/icon as well as color, targets WCAG 2.2 AA, supports keyboard operation, and maintains light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed explicitly.

**Reference-first rule.** Current reference: `RO-UI-ACADEMIC-MINIMAL-1.3`. Relevant pages: `technical-reports.html`, `document-reader.html`, `parsing-quality.html`, `audit-lineage.html`, `evidence-matrix.html`. If planned behavior materially differs, first update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit human approval and a new reference ID; then implement. For CAP-12 or CAP-13 administration surfaces with no existing approved page, the plan may establish nonvisual contracts, but UI implementation remains blocked on this process.

## 7. Security, privacy, rights and research integrity

- Run document parsing in constrained workers.
- Redact or deny provider-bound content according to artifact policy.

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
| table cell boundaries are ambiguous | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| figure result cannot be machine-read | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| model returns invalid schema | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| qualitative finding lacks supporting passage | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |

Every operation additionally defines cancellation boundaries, idempotency keys, lease expiry, retry classification, cleanup and restart behavior. A restart test uses persisted state rather than an in-memory fake. Partial results stay explicitly partial, and recovery never promotes unverified content or weakens rights/authorization to complete work.

## 9. Task-by-task implementation plan

### CAP-17.S02.T01 — Extract report structure, study metadata, methods, results, tables, and figures

**Objective.** Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.

| Control | Value |
|---|---|
| Dependencies | CAP-17.S01.T03, CAP-05.S04.T03 |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | results, documents, ai |

**Expected deliverables**

- Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.

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

- Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-17.S02.T02 — Extract quantitative result records with exact evidence anchors

**Objective.** Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.

| Control | Value |
|---|---|
| Dependencies | CAP-17.S02.T01 |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | results, evidence, ai |

**Expected deliverables**

- Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.

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

- Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-17.S02.T03 — Extract qualitative, mixed-method, and technical findings

**Objective.** Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.

| Control | Value |
|---|---|
| Dependencies | CAP-17.S02.T01 |
| Estimate / risk | `M` / `high` |
| Review gate | `agent-review` |
| Verification profiles | results, evidence, ai |

**Expected deliverables**

- Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.

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

- Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.


## 10. Slice-wide verification matrix

| Verification area | Method and evidence | Acceptance |
|---|---|---|
| golden quantitative tables including missing/adjusted/robustness fields | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| qualitative negative-case and interpretation fixtures | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| mixed/technical benchmark configuration fixtures | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| anchor relocation and revision tests | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |

The slice reviewer also verifies task-to-slice integration, adjacent contract compatibility, approved-reference conformance, no unrelated scope expansion, and no tests weakened to match the implementation. Reports are machine-readable where possible and linked from the slice evidence manifest.

## 11. Performance and resource budgets

| Budget / objective | Measurement | Gate |
|---|---|---|
| batch extraction honors local resource/cost policy | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| large tables stream and paginate | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| confidence/calibration reports are generated per schema/model version | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |

Before capability approval, any numeric threshold that materially affects support, cost or quality must be selected in the capability packet or a referenced benchmark ADR. Implementation may optimize within the approved boundary but may not quietly relax a threshold. Resource and cost tests include minimum/recommended profiles and sustained workloads where applicable.

## 12. Observability and provenance

The slice emits structured events for operation start/progress/cancel/retry/recover/complete, policy and authorization decisions, dependency/version manifests, user adjudication, stale propagation, performance/cost and verification. Events carry stable project/tenant/operation/task IDs and causation/correlation but exclude raw source text, prompts, unpublished ideas, credentials and participant data by default. Every accepted output can be traced to input revisions, source/evidence records, model/runtime/provider manifests, human decisions and the implementation revision that produced it.

Operational observability and scholarly provenance remain distinct but linkable: operations answer whether the system behaved correctly; provenance answers how a scholarly object came to exist and change. Logs are not a substitute for the append-only provenance ledger, and the ledger is not used as an unrestricted operational log sink.

## 13. Adjacent-slice handoffs

### 13.1 Upstream inputs

CAP-17.S01 accepted artifact revisions and CAP-05 document structure/anchors. The slice validates IDs, revisions, rights/policy state, schema/version compatibility and completeness before accepting the handoff. Missing or stale upstream requirements remain explicit and may block only the affected operation.

### 13.2 Downstream contract

CAP-17.S03 reconciliation and CAP-17.S04 evidence graph. The handoff consists of stable portable IDs, revisioned domain objects, evidence/provenance links, manifests, status/uncertainty, policy decisions and documented invalidation triggers—not internal tables, OS paths, cluster objects or SDK types.

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

The static decision page is `planning/review-site/CAP-17/index.html`; this slice page is `planning/review-site/CAP-17/CAP-17.S02.html`. Automation requesting feedback or approval must provide those links and place resolved recommendations and override controls near the top.

## 20. Research and standards basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `FRICTIONLESS_TABLE` | [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) | Frictionless Data | Portable JSON-declared schemas for CSV/tabular result exchange, validation and missing values. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) | W3C | Revision-aware source, manuscript and review-location selectors. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |

The implementation team must recheck current versions, target support, licenses and institutional/provider contracts immediately before capability approval. Official documentation governs technical integration; research/reporting standards guide methods and evaluation. Neither substitutes for project-specific benchmarks, security review, legal/rights review or domain/methods expertise.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-17 --require-approved`; stop and print the generated review URL if it fails.
2. Claim the current slice/task through `taskctl`; verify branch, worktree, base SHA and lease.
3. Load only the approved packet, this plan, authoritative backlog, mapped architecture/standards and affected code/tests.
4. Reconcile current behavior with contracts; create failing acceptance and material boundary tests before implementation.
5. Implement through portable domain/API/workflow boundaries; record decisions already settled rather than re-asking.
6. Run focused checks continuously and all declared profiles before task submission.
7. Produce machine-linked evidence tied to the reviewed commit; request independent task review.
8. At task completion, execute slice-wide integration, security/accessibility/performance and handoff verification.
9. Request independent slice review. If approved, allow `taskctl` to advance directly to the next ready slice in `CAP-17`.
10. Pause only under the approved taxonomy; preserve state and provide the capability/slice review-site link with the affected decision and recommendation.
