---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-18
capability_plan: planning/capability-plans/CAP-18.md
planning_gate: capability-decision-complete
slice_id: CAP-18.S05
title: Manuscript Studio and publication exports
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
- CAP-18.S05.T01
- CAP-18.S05.T02
- CAP-18.S05.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-18.S05 — Manuscript Studio and publication exports

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-18.md` is decision-complete and approved, this plan is approved, required ADRs/design references are accepted or explicitly waived, and the plan validators pass in approval mode. Once the capability campaign starts, execution continues through its slices and pauses only for an allowed infeasibility, external dependency, unavailable required hardware, genuinely new human decision, higher-authority conflict, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-18` — Source-grounded manuscript drafting and publication artifacts |
| Capability objective | Use approved article blueprints, literature evidence, verified technical reports/results, and researcher-authored content to draft and export empirical, theory, and critical conference/journal articles. |
| Slice | `CAP-18.S05` — Manuscript Studio and publication exports |
| Slice outcome | Researchers can review, edit, approve, and export complete source-grounded manuscripts. |
| Wave / priority | `W8` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `platform-neutral` |
| Backlog tasks | `CAP-18.S05.T01`, `CAP-18.S05.T02`, `CAP-18.S05.T03` |
| Slice dependencies | `CAP-18.S03.T03`, `CAP-18.S04.T03` |
| Capability decision packet | `planning/capability-plans/CAP-18.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant references: `manuscript-studio.html`, `manuscript-blueprint.html`, `technical-reports.html`, `synthesis-studio.html`, `audit-lineage.html` |
| Approval state | PROPOSED / recommendations resolved; capability approval pending |

## 1. Purpose and contribution to the larger vision

Researchers can review, edit, approve, and export complete source-grounded manuscripts.

This slice advances the capability objective: **Use approved article blueprints, literature evidence, verified technical reports/results, and researcher-authored content to draft and export empirical, theory, and critical conference/journal articles.** It is one production vertical inside a long-running capability campaign, not an isolated experiment. Its implementation must preserve evidence before prose, stable scholarly identity, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, rights-aware processing, deployment-neutral contracts, cross-platform portability and the distinction between canonical state and rebuildable analytical derivatives.

**Implementation thesis.** Unify governed authoring, citation, figures/tables, disclosure and multi-format exports in Manuscript Studio without making the editor or converter canonical.

Compatibility with the larger program is mandatory. The slice consumes stable outputs from earlier capabilities and publishes only explicit contracts to later ones. It must not fork project semantics for deployment profile or operating system, bypass the Core API/provenance/workflow/model-policy boundaries, or pre-implement downstream capability behavior beyond narrow ports, fixtures and handoff contracts. Capability completion still requires all exit criteria:

- Paragraphs and claims retain section purpose, evidence/citation support, generation provenance, author decisions, and stale dependencies.
- Empirical methods/results distinguish planned from actual conduct and never invent study details or findings.
- Theory and critical drafts preserve conceptual/interpretive plurality and author voice rather than imposing a single article logic.
- Researchers can edit, compare, approve, audit, disclose, and export complete manuscripts and reproducibility artifacts.

## 2. Scope

### 2.1 In scope

- Manuscript studio ui.
- Citation/reference and bibliography management.
- Figure/table/supplement/disclosure/authorship management.
- Multi-format publication and reproducibility exports.

### 2.2 Explicit non-goals

- Do not implement downstream capability behavior beyond the ports, fixtures and handoffs explicitly named here.
- Do not alter product purpose, accepted scholarly interpretations, rights policy or researcher authority.
- Do not introduce hidden network calls, provider lock-in, OS-specific canonical state or deployment-specific semantics.
- Do not replace evidence-linked states with opaque scores or fluent prose.
- Do not claim production readiness from happy-path tests or task completion alone; slice-wide failure, denial, cancellation, restart, migration, security, accessibility and handoff evidence is required.
- Do not implement an intentional user-experience change before the governed reference is updated and approved.

### 2.3 Slice boundary

- **Consumes:** `CAP-18.S01-S04 accepted sections plus CAP-16 blueprint/publication plan` and formal dependencies `CAP-18.S03.T03`, `CAP-18.S04.T03`.
- **Produces:** Researchers can review, edit, approve, and export complete source-grounded manuscripts.
- **Owns:** the domain contracts, adapters, workflows, fixtures, policy decisions and evidence listed in this plan.
- **Does not own:** unrelated capabilities, source-provider internals, institutional/cloud operations outside this capability, or user-authoritative scholarly/ethics judgments.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. `docs/product/vision.md` for purpose, users and non-goals.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md` for architecture and deployment boundaries.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved `planning/capability-plans/CAP-18.md` for all material capability decisions.
5. This approved slice plan for implementation detail.
6. Approved style guide, workflow catalog, page contracts and HTML references for user-facing behavior.
7. Repository automation and task-control rules.

### 3.2 Required upstream state

- Every formal dependency is complete or an explicitly approved integration stub exists: `CAP-18.S03.T03`, `CAP-18.S04.T03`.
- Every slice plan in `CAP-18` exists, matches the backlog and is approved at the same commit as the capability packet.
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
| `CAP-18-D01` | Structured editor | **Use ProseMirror/Tiptap open-source core behind a manuscript-editor port** | Use a plain textarea or contenteditable HTML as canonical editor | Schema-driven transactions and plugins support stable blocks, citations, comments and controlled transformations. | ADR-MANUSCRIPT-EDITOR |
| `CAP-18-D13` | Citation processing | **Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs** | Embed formatted citation strings directly in prose | Separating citation identity from rendering enables style changes and audit. | None |
| `CAP-18-D14` | Publication exports | **Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests** | Treat one DOCX export as the only publication artifact | Multiple venues and reproducibility needs require a tested, replaceable export pipeline. | None |
| `CAP-18-D15` | Tracked change model | **Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional** | Depend on a proprietary alpha tracked-changes API | The core revision model must remain open, inspectable and portable. | None |
| `CAP-18-D16` | Authorship and AI disclosure | **Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly** | List the model as an author or infer authorship automatically | Humans remain accountable and current publication guidance requires transparency. | None |
| `CAP-18-D17` | Textual-overlap audit | **Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict** | Assign an automated plagiarism/misconduct label | Similarity is evidence for review, not proof of intent or misconduct. | None |

No implementation may silently choose a different candidate. If evidence makes an accepted selection infeasible, document the failed assumption, strongest feasible replacements, compatibility/migration cost and recommendation on the capability review page, then obtain focused approval before resuming.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `apps/desktop/manuscript-studio` | approved workspace |
| `packages/ui/manuscript-editor` | editor/review/provenance components |
| `workers/manuscript-export` | Quarto/Pandoc/JATS render service |
| `packages/core/publication` | citation, authorship, disclosure and artifact manifests |

Exact filenames may change without reopening planning if ownership, dependency direction, portable contracts and test/evidence boundaries remain intact. New cross-capability dependencies or changed trust/deployment boundaries require the packet/ADR process.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `CitationOccurrence` | Versioned CitationOccurrence state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `BibliographyEntry` | Versioned BibliographyEntry state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `FigurePlacement` | Versioned FigurePlacement state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `TablePlacement` | Versioned TablePlacement state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `DisclosureStatement` | Versioned DisclosureStatement state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `AuthorshipRecord` | Versioned AuthorshipRecord state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |
| `PublicationExport` | Versioned PublicationExport state with stable identity, lifecycle/status, provenance and policy metadata appropriate to manuscript studio and publication exports. |

Cross-cutting invariants:

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, projections, caches, generated recommendations, dashboards and platform artifacts are versioned derivatives.
- Every mutation has stable identity, revision, actor, timestamp, causation/correlation and source or decision provenance.
- Unknown, not reported, unavailable, denied, inferred, disputed, stale and failed remain distinct.
- Long operations persist inputs/manifests, progress, lease, cancellation, retry/checkpoint/restart and terminal evidence.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `Citations reference canonical scholarly IDs and render late through CSL.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Figures/tables retain source/result lineage and accessible descriptions.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.
- `Exports are derived artifacts with checksums and validation reports.` — versioned request/response schemas, typed errors, explicit authorization/rights context and idempotent operation identity.

Provider SDK objects, database rows, OS handles, cluster resources, model tensors and UI state may not cross their owning adapter boundary. Contracts include capability/version negotiation and stable error categories so local, institutional, cloud and cross-platform implementations can be tested against the same behavior.

### 5.4 Cross-capability and platform compatibility

- **Upstream:** CAP-18.S01-S04 accepted sections plus CAP-16 blueprint/publication plan.
- **Downstream:** CAP-18.S06 acceptance and CAP-19 review snapshots.
- Windows x64 remains the release-authoritative base for CAP-11; CAP-14 adds macOS ARM64 and Linux x86_64/ARM64 without changing canonical semantics.
- Institutional and cloud deployments reuse the same domain/API/workflow meanings; persistence, process, authentication, tenancy and scaling adapters differ.
- Model, parser, vector, graph, workflow, identity, packaging and billing technologies are pinned behind ports and replaceable only through evaluation/ADR where material.
- A changed source, schema, model, policy or decision marks exact dependents stale; it does not silently regenerate accepted outputs.

## 6. User experience and approved reference

- Conform to `manuscript-studio.html` in light/dark mode.
- Provide section workflow, evidence inspector, tracked suggestions and export readiness.
- Make AI disclosure and human approvals explicit.

- Workflow navigation shows the selected use case, current numbered stage, completed/upcoming/attention states, expected output and previous/next actions.
- Supporting tools remain accessible; opening one explains its relationship to the primary workflow and provides return to the current stage.
- Every semantic state uses text/icon as well as color, targets WCAG 2.2 AA, supports keyboard operation, and maintains light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed explicitly.

**Reference-first rule.** Current reference: `RO-UI-ACADEMIC-MINIMAL-1.3`. Relevant pages: `manuscript-studio.html`, `manuscript-blueprint.html`, `technical-reports.html`, `synthesis-studio.html`, `audit-lineage.html`. If planned behavior materially differs, first update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit human approval and a new reference ID; then implement. For CAP-12 or CAP-13 administration surfaces with no existing approved page, the plan may establish nonvisual contracts, but UI implementation remains blocked on this process.

## 7. Security, privacy, rights and research integrity

- Rights/permissions and confidential-source exclusions are enforced before export.
- Temporary converters run in isolated workspaces.

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
| citation style unavailable | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| figure permission missing | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| export converter fails or hangs | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |
| target format cannot preserve a construct | Persist operation state and exact affected identifiers; preserve canonical truth; mark incomplete derivatives stale or rebuildable; show recovery/alternative. | Deterministic fixture plus restart or denial assertion. |

Every operation additionally defines cancellation boundaries, idempotency keys, lease expiry, retry classification, cleanup and restart behavior. A restart test uses persisted state rather than an in-memory fake. Partial results stay explicitly partial, and recovery never promotes unverified content or weakens rights/authorization to complete work.

## 9. Task-by-task implementation plan

### CAP-18.S05.T01 — Build the Manuscript Studio workspace

**Objective.** Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.

| Control | Value |
|---|---|
| Dependencies | CAP-18.S03.T03, CAP-18.S04.T03, CAP-00.S06.T04 |
| Estimate / risk | `M` / `medium` |
| Review gate | `agent-review` |
| Verification profiles | manuscript, desktop |

**Expected deliverables**

- Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.

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

- Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-18.S05.T02 — Implement citation/reference, figure/table, disclosure, and authorship management

**Objective.** Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.

| Control | Value |
|---|---|
| Dependencies | CAP-18.S05.T01 |
| Estimate / risk | `M` / `medium` |
| Review gate | `agent-review` |
| Verification profiles | manuscript, evidence |

**Expected deliverables**

- Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.

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

- Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

### CAP-18.S05.T03 — Export publication artifacts with reproducibility and lineage

**Objective.** Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.

| Control | Value |
|---|---|
| Dependencies | CAP-18.S05.T02, CAP-09.S06.T03 |
| Estimate / risk | `M` / `medium` |
| Review gate | `agent-review` |
| Verification profiles | manuscript |

**Expected deliverables**

- Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.

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

- Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.


## 10. Slice-wide verification matrix

| Verification area | Method and evidence | Acceptance |
|---|---|---|
| UI/accessibility/reference conformance | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| CSL citation/bibliography golden tests | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| cross-format section/figure/table semantic diff | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |
| export cancellation/restart/cleanup | Automated where deterministic; otherwise reviewed protocol with immutable evidence. | Pass declared threshold with no hidden critical/high exception. |

The slice reviewer also verifies task-to-slice integration, adjacent contract compatibility, approved-reference conformance, no unrelated scope expansion, and no tests weakened to match the implementation. Reports are machine-readable where possible and linked from the slice evidence manifest.

## 11. Performance and resource budgets

| Budget / objective | Measurement | Gate |
|---|---|---|
| editor responsive at target manuscript scale | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| export times reported for all target formats | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |
| no leaked temp files or unrestricted source text | Measure on representative declared profile and store report with manifest. | Threshold accepted in capability packet or benchmark ADR. |

Before capability approval, any numeric threshold that materially affects support, cost or quality must be selected in the capability packet or a referenced benchmark ADR. Implementation may optimize within the approved boundary but may not quietly relax a threshold. Resource and cost tests include minimum/recommended profiles and sustained workloads where applicable.

## 12. Observability and provenance

The slice emits structured events for operation start/progress/cancel/retry/recover/complete, policy and authorization decisions, dependency/version manifests, user adjudication, stale propagation, performance/cost and verification. Events carry stable project/tenant/operation/task IDs and causation/correlation but exclude raw source text, prompts, unpublished ideas, credentials and participant data by default. Every accepted output can be traced to input revisions, source/evidence records, model/runtime/provider manifests, human decisions and the implementation revision that produced it.

Operational observability and scholarly provenance remain distinct but linkable: operations answer whether the system behaved correctly; provenance answers how a scholarly object came to exist and change. Logs are not a substitute for the append-only provenance ledger, and the ledger is not used as an unrestricted operational log sink.

## 13. Adjacent-slice handoffs

### 13.1 Upstream inputs

CAP-18.S01-S04 accepted sections plus CAP-16 blueprint/publication plan. The slice validates IDs, revisions, rights/policy state, schema/version compatibility and completeness before accepting the handoff. Missing or stale upstream requirements remain explicit and may block only the affected operation.

### 13.2 Downstream contract

CAP-18.S06 acceptance and CAP-19 review snapshots. The handoff consists of stable portable IDs, revisioned domain objects, evidence/provenance links, manifests, status/uncertainty, policy decisions and documented invalidation triggers—not internal tables, OS paths, cluster objects or SDK types.

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

The static decision page is `planning/review-site/CAP-18/index.html`; this slice page is `planning/review-site/CAP-18/CAP-18.S05.html`. Automation requesting feedback or approval must provide those links and place resolved recommendations and override controls near the top.

## 20. Research and standards basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `QUARTO_MANUSCRIPTS` | [Quarto Manuscripts](https://quarto.org/docs/manuscripts/) | Quarto | Multi-format scholarly manuscript projects with executable research artifacts. |
| `QUARTO_FORMATS` | [Quarto Formats](https://quarto.org/docs/reference/formats/) | Quarto | Portable HTML, PDF, Word, Markdown, JATS and other publication exports. |
| `QUARTO_CITATIONS` | [Quarto Citations](https://quarto.org/docs/authoring/footnotes-and-citations) | Quarto | Pandoc/CSL citation processing and bibliography inputs. |
| `QUARTO_XREF` | [Quarto Cross References](https://quarto.org/docs/authoring/cross-references) | Quarto | Stable figure, table, equation, section and listing references in generated artifacts. |
| `CSL` | [Citation Style Language 1.0.2 Specification](https://docs.citationstyles.org/en/stable/specification.html) | Citation Style Language | Deterministic citation and bibliography rendering. |
| `CREDIT` | [ANSI/NISO Z39.104-2022 CRediT Contributor Roles Taxonomy](https://www.niso.org/publications/z39104-2022-credit) | NISO | Structured contributor-role capture and transparent authorship metadata. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `PANDOC_JATS` | [Pandoc JATS Support](https://pandoc.org/jats.html) | Pandoc | Replaceable conversion to and from JATS through a tested export adapter. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |

| `MECA201` | [NISO RP-30-2023, Manuscript Exchange Common Approach (MECA) Version 2.0.1](https://www.niso.org/publications/rp-30-2023-meca) | NISO | Portable package interchange for manuscripts, submission metadata, related files and optional peer-review data. |

The implementation team must recheck current versions, target support, licenses and institutional/provider contracts immediately before capability approval. Official documentation governs technical integration; research/reporting standards guide methods and evaluation. Neither substitutes for project-specific benchmarks, security review, legal/rights review or domain/methods expertise.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-18 --require-approved`; stop and print the generated review URL if it fails.
2. Claim the current slice/task through `taskctl`; verify branch, worktree, base SHA and lease.
3. Load only the approved packet, this plan, authoritative backlog, mapped architecture/standards and affected code/tests.
4. Reconcile current behavior with contracts; create failing acceptance and material boundary tests before implementation.
5. Implement through portable domain/API/workflow boundaries; record decisions already settled rather than re-asking.
6. Run focused checks continuously and all declared profiles before task submission.
7. Produce machine-linked evidence tied to the reviewed commit; request independent task review.
8. At task completion, execute slice-wide integration, security/accessibility/performance and handoff verification.
9. Request independent slice review. If approved, allow `taskctl` to advance directly to the next ready slice in `CAP-18`.
10. Pause only under the approved taxonomy; preserve state and provide the capability/slice review-site link with the affected decision and recommendation.
