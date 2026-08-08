---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-03
capability_plan: planning/capability-plans/CAP-03.md
planning_gate: capability-decision-complete
slice_id: CAP-03.S05
title: Dependency graph, staleness, and controlled recalculation
status: proposed
wave: W1
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-03.S05.T01
- CAP-03.S05.T02
- CAP-03.S05.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-03.S05 - Dependency graph, staleness, and controlled recalculation
> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-03.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and `python tools/planctl.py ready CAP-03 --require-approved` passes. After campaign start, execute continuously and pause only for an allowed classified condition.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-03` - Canonical domain, research intent, provenance, and durable workflows |
| Capability objective | Define canonical research objects, a versioned research-intent and primary-use-case contract, provenance, adaptive objective-specific workflows, durable jobs, human gates, and controlled recalculation. |
| Slice | `CAP-03.S05` - Dependency graph, staleness, and controlled recalculation |
| Slice outcome | Changes to evidence, models, schemas, or decisions identify and safely refresh affected outputs. |
| Wave / priority | `W1` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-03.S05.T01`, `CAP-03.S05.T02`, `CAP-03.S05.T03` |
| Slice dependencies | `CAP-03.S04.T03` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.3` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Ensure that changes to sources, parsers, schemas, decisions, models, or intent invalidate only what truly depends on them and never silently overwrite accepted scholarly judgment.

This slice contributes to the capability objective: **Define canonical research objects, a versioned research-intent and primary-use-case contract, provenance, adaptive objective-specific workflows, durable jobs, human gates, and controlled recalculation.** It must preserve the capability exit conditions:

- Core aggregates and APIs have stable identifiers, explicit versioning, and tested state machines.
- Every consequential transformation records inputs, policy, software/model/schema versions, output, and human disposition.
- Long-running work is resumable, cancellable, resource-governed, and capable of marking downstream outputs stale.
- Each project has a versioned primary use case that produces an ordered, visible workflow and next-step guidance while preserving access to all tools and prior workflow history.
- Study designs, technical reports/results, manuscript sections, reviewer rounds, and revision actions use the same durable workflow, provenance, staleness, and human-gate model.

**Implementation thesis.** Maintain a typed revision-to-revision material dependency graph, compute staleness from changed fingerprints and propagation rules, preview impact before consequential change, and schedule selective recomputation into new immutable revisions.

## 2. Scope

### 2.1 In scope
- Dependency edges from outputs to source revisions, evidence records, ontology versions, prompts/models, parameters, and human decisions.
- Graph traversal that marks affected outputs stale, records cause, deduplicates cascades, and previews impact before destructive changes.
- Workflow generation from stale subgraphs with reuse of valid intermediates, versioned replacement, comparison, and rollback.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-03.S04.T03`.
- **Produces:** Changes to evidence, models, schemas, or decisions identify and safely refresh affected outputs.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `START_HERE.md` and `docs/governance/document-set-and-bootstrap.md`.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-03.S05` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 3, 9, 12-16, 17-19
- Vision design principles DP1-DP12
- Approved workflow catalog and adaptive navigation contracts

### 3.2 Required upstream state
- `CAP-03.S04.T03` is complete or explicitly gated.

### 3.3 Mandatory stop conditions
- A required ADR or human decision listed in Section 19 is unresolved and the affected task cannot be implemented reversibly behind an existing port.
- The implementation would materially change an approved route, workflow, component, interaction, semantic state, or light/dark behavior before the UI reference is updated and approved.
- A dependency contract conflicts with the Systems Design or an accepted ADR.
- Required credentials, signed artifacts, platform hardware, test fixtures, license terms, or security controls are unavailable and cannot be safely stubbed.
- The task would require unrelated work in another capability rather than an explicit backlog task/handoff.
- Evidence suggests the selected technology cannot satisfy security, rights, portability, recovery, or performance requirements; record the evidence and open an ADR instead of forcing implementation.

### 3.3 Decision-complete capability rule

Planning by capability is the default. Before `capability start`, the planning agent inspects all slices and adjacent contracts, researches credible options, and records the strongest best-in-class recommendation as the selected and accepted option for every material decision in the capability packet. Those selections count as completed decisions. The static review site is a confirmation-and-override surface plus the one-time capability approval gate; implementation agents must not repeatedly ask for choices already settled by the packet. After approval, execution proceeds continuously slice by slice through a production-ready end-to-end capability.

### 3.4 Allowed campaign pauses

Only validated infeasibility, an external dependency, unavailable required hardware, a genuinely new consequential human decision, or an approved design-reference gate may pause the capability. Routine debugging, recoverable tests, refactoring and documented fallbacks do not.

## 4. Selected implementation decisions

The capability packet's researched best-in-class recommendations are already selected, accepted, and decision-complete. This section projects the applicable decisions into the slice implementation contract. Capability approval authorizes those defaults; a reviewer may override a selection before approval only with explicit rationale. During execution, no implementation agent may silently choose a different candidate.

The following decisions are the default implementation direction for this slice. They remain subordinate to accepted ADRs and must be revised if benchmark or security evidence disproves them.

1. **Edges connect immutable entity revisions and carry relation type, materiality, governing policy, creation source, and provenance.**
2. **Staleness is a state with reason and source revision, not deletion or automatic recomputation.**
3. **Distinguish direct, transitive, conditional, and non-material dependencies.**
4. **Use deterministic content/configuration fingerprints for parser, model, prompt, schema, template, corpus, intent, and accepted-decision inputs.**
5. **Human-approved/adjudicated outputs require explicit review before replacement; recomputation creates candidates/new revisions.**
6. **Impact preview is required before intent/profile/parser/schema changes and before large batch recalculation.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `packages/contracts/domain/`, `intent/`, `provenance/`, `workflow/`, and `experience/`.
- `services/core-api/domain/` - aggregates and invariants.
- `services/core-api/modules/intent/`, `provenance/`, `workflow/`, and `dependencies/`.
- `apps/desktop/src/workspaces/intent/`, `audit/`, `task-center/`, and shared workflow navigation.
- `design/ui-reference/` for governed workflow/page contracts.
- `tests/contracts/`, `tests/provenance/`, `tests/workflows/`, and `tests/e2e-local/`.

**Slice-specific components**
- Dependency graph repository and registration API.
- Fingerprint/version service and change classifier.
- Stale propagation engine, impact preview/query, and exceptions/waivers.
- Selective recalculation planner integrated with workflows and UI.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `MaterialDependency`
- `DependencyFingerprint`
- `StaleState`
- `ImpactPath`
- `ImpactPreview`
- `RecalculationPlan`
- `StalenessWaiver`

**Required invariants**
- Every durable identity and revision follows CAP-03 canonical identifier/version rules or creates the necessary contract in this slice when CAP-03 is not yet available.
- Consequential state changes are atomic with required provenance/outbox/dependency facts once those foundations exist; earlier slices provide an explicit integration seam and fixtures.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Dependency registration is atomic with artifact/provenance commit.
- Propagation rules are versioned and testable by artifact type.
- Stale state includes reason, originating change, path summary, confidence, detected time, and resolution state.
- Recalculation plans list inputs, expected outputs, resource estimate, human gates, and preserved historical revisions.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
- Every stale badge explains what changed, why the object may be affected, and the safest next action.
- Impact preview groups effects by workflow/output and distinguishes automatic, review-required, blocked, and informational.
- Users can defer recalculation without losing visibility.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Impact views respect source/document/draft access; do not leak names of inaccessible objects.
- Recalculation re-evaluates current rights/egress policy rather than blindly replaying prior external calls.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Propagation is idempotent and resumable; partial traversal records a checkpoint and does not mark unaffected objects.
- Cycles are detected, explained, and handled by strongly connected groups rather than infinite recursion.
- If fingerprint computation fails, affected output enters `unknown impact` review state rather than being considered fresh.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-03.S05.T01` - Implement material dependency registration
**Objective:** Dependency edges from outputs to source revisions, evidence records, ontology versions, prompts/models, parameters, and human decisions.

**Dependencies:** `CAP-03.S04.T03`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `service`, `data`

**Expected deliverables**
- Dependency edges from outputs to source revisions, evidence records, ontology versions, prompts/models, parameters, and human decisions.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-03.S05.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Every recalculable output declares dependencies before completion; missing dependency registration fails a development assertion and appears in audit diagnostics.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Required criterion-linked evidence**
- Reviewed commit SHA, changed-file inventory, and scope-deviation explanation if any.
- Named automated tests and report paths mapped to each acceptance criterion.
- Failure/boundary/restart evidence appropriate to the task risk and verification profiles.
- Security, rights, accessibility, migration, or design-reference review evidence when relevant.
- Updated schema/API/client/migration/fixture/documentation hashes where applicable.
- Independent reviewer result; the implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile service
python tools/verify.py --profile data
```

### 9.2 `CAP-03.S05.T02` - Implement stale-state propagation and impact preview
**Objective:** Graph traversal that marks affected outputs stale, records cause, deduplicates cascades, and previews impact before destructive changes.

**Dependencies:** `CAP-03.S05.T01`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `service`, `data`, `graph`

**Expected deliverables**
- Graph traversal that marks affected outputs stale, records cause, deduplicates cascades, and previews impact before destructive changes.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-03.S05.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Changing a fixture extraction marks the expected matrix, graph, synthesis, and dossier outputs stale without touching unrelated outputs; cycles are handled safely.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Required criterion-linked evidence**
- Reviewed commit SHA, changed-file inventory, and scope-deviation explanation if any.
- Named automated tests and report paths mapped to each acceptance criterion.
- Failure/boundary/restart evidence appropriate to the task risk and verification profiles.
- Security, rights, accessibility, migration, or design-reference review evidence when relevant.
- Updated schema/API/client/migration/fixture/documentation hashes where applicable.
- Independent reviewer result; the implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile service
python tools/verify.py --profile data
python tools/verify.py --profile graph
```

### 9.3 `CAP-03.S05.T03` - Implement selective recomputation and historical retention
**Objective:** Workflow generation from stale subgraphs with reuse of valid intermediates, versioned replacement, comparison, and rollback.

**Dependencies:** `CAP-03.S05.T02`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `service`, `e2e-local`

**Expected deliverables**
- Workflow generation from stale subgraphs with reuse of valid intermediates, versioned replacement, comparison, and rollback.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-03.S05.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Recompute produces a new version rather than overwriting evidence; unchanged inputs reuse verified artifacts; user can compare and restore prior adjudicated output.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Required criterion-linked evidence**
- Reviewed commit SHA, changed-file inventory, and scope-deviation explanation if any.
- Named automated tests and report paths mapped to each acceptance criterion.
- Failure/boundary/restart evidence appropriate to the task risk and verification profiles.
- Security, rights, accessibility, migration, or design-reference review evidence when relevant.
- Updated schema/API/client/migration/fixture/documentation hashes where applicable.
- Independent reviewer result; the implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile service
python tools/verify.py --profile e2e-local
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `data`, `e2e-local`, `graph`, `service` |
| Unit and invariant | Domain/value/state-machine, adapter, normalization, and negative tests for every task-owned rule. |
| Contract and compatibility | Schema/OpenAPI/generated-client or manifest validation, prior-version fixtures, unknown-field behavior, and drift checks. |
| Integration | Real local adapters against the miniature fixture project; no mocked success at the principal slice boundary. |
| End to end | Representative researcher path from the upstream dependency through the slice outcome and downstream handoff fixture. |
| Failure and denial | At least the material cases in Section 8, including canonical state and user-visible recovery assertions. |
| Cancellation and restart | Cancel during a material operation, restart desktop/Core/worker, reconcile authoritative state, and resume or clean up safely. |
| Security/privacy/rights | Required threat-boundary, permission, redaction, egress, restricted-content, and malicious-fixture tests. |
| Accessibility and UI | Keyboard, focus, screen reader semantics, theme parity, approved page/workflow contract, and visual regression when user-facing. |
| Migration/recovery | Prior compatible fixtures, interrupted migration/upgrade where applicable, rollback or repair, and retained historical state. |
| Performance | Representative dataset/hardware benchmark with budgets from Section 11 and regression threshold. |
| Architecture | Dependency/port checks, no direct renderer database/filesystem/secret access, and no hosted infrastructure introduced prematurely. |
| Independent review | Reviewer verifies that tests exercise the stated outcome rather than merely matching implementation details. |

**Commands inherited from the backlog**

```text
python tools/verify.py --profile data
python tools/verify.py --profile e2e-local
python tools/verify.py --profile graph
python tools/verify.py --profile service
```

## 11. Performance and resource budgets
- Index both upstream and downstream edges and use bounded, paged graph traversal.
- Batch propagation and coalesce repeated change events.
- Benchmark large fixture graphs and retain path samples rather than every possible path in summary UI.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Record propagation runs, nodes/edges visited, cycle groups, stale counts by reason/type, recalculation outcomes, and false-stale adjudications.
- Track freshness lag from source change to user-visible state.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- All artifact-producing capabilities register dependencies.
- CAP-03.S02 intent revisions and S06 profile changes use impact preview.
- CAP-05 parser upgrades and corrections invoke anchor/dependent impact.
- Living monitoring and later manuscript/reviewer workflows depend on controlled staleness.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- New dependency types are additive; propagation-rule changes are versioned and may require a graph re-evaluation preview.
- Historical dependency edges remain attached to historical artifact revisions.

Every compatibility-sensitive artifact records its format/schema/protocol/parser/component version. Breaking evolution requires an accepted ADR, tested migration or bridge path, and explicit behavior for older projects/clients.

## 15. Required slice evidence bundle
- Approved slice-plan identifier and approval record.
- All task criterion-to-evidence records on the reviewed commit.
- Slice-wide verification report and commands.
- Unit, contract, integration, end-to-end, failure, cancellation, restart, migration/recovery, security/rights/privacy, accessibility/UI, and performance reports as applicable.
- Architecture dependency and approved-reference conformance reports.
- Updated contracts, generated artifacts, migrations, fixtures, threat model, ADRs, operational/recovery documentation, and source acknowledgments.
- Independent slice review confirming production-ready vertical behavior and downstream handoff quality.
- No concealed TODO/FIXME, disabled failing test, manual-only production step, or untracked follow-up required for the slice outcome.

## 16. Definition of Ready
- The containing capability campaign is eligible or explicitly selected, and all predecessor capabilities required by its first active slice are complete or gated.
- Status is READY and all dependency task IDs are DONE.
- The task wave has no activation gate or its activation gate is approved.
- The objective, deliverable, acceptance criteria, verification profiles, platform targets, and review gate are understandable without hidden context.
- Required architecture, experience, template, or scholarly-method decisions exist or the task explicitly creates them.
- Required credentials, fixtures, models, reports, and platforms are available or intentionally stubbed.
- No unresolved blocker or active conflicting lease is recorded.
- For intentional user-facing change, the proposed style-guide/workflow/page-reference revision is validated and approved, and its reference ID is recorded on the task.

**Slice-specific readiness additions**
- This plan is approved and its approval metadata identifies the reviewed commit/reference.
- All blocking ADRs in Section 19 are accepted.
- Required official-source constraints, licenses, fixtures, platform resources, and test credentials are available or safely stubbed.
- The first task is READY under `taskctl` and no prior slice in the active capability remains incomplete.

## 17. Definition of Done
- Deliverables and all task acceptance criteria are satisfied.
- Verification commands pass on the reviewed commit and criterion-to-evidence records are attached.
- Security, privacy, rights, accessibility, scholarly-method, platform, migration, or release gates are completed when specified.
- Documentation, tests, migrations, fixtures, provenance, and stale-dependency behavior are updated as relevant.
- An independent reviewer sets review.result to approved and status to DONE.
- Newly discovered work is recorded as explicit backlog tasks rather than hidden TODOs.
- The task lease is released and branch/worktree disposition is recorded.
- User-facing implementation conforms to the approved reference ID through token, route/page-contract, workflow-navigation, accessibility, and visual-regression evidence.
- Task completion does not by itself complete the slice or capability; slice and capability end-to-end reviews must also pass.

**Slice-specific completion additions**
- The promised outcome is demonstrable end to end: Changes to evidence, models, schemas, or decisions identify and safely refresh affected outputs.
- All task implementations operate together from a clean project/install state, not only in isolated tests.
- The slice evidence bundle passes independent review and the downstream handoff fixtures/contracts are usable.
- Capability campaign state advances only after the slice completion record is approved.

## 18. Risks and mitigations
| Risk | Required mitigation |
|---|---|
| Architecture drift | Enforce ports/contracts/dependency checks and compare against this plan and accepted ADRs. |
| Procedural completion without semantic completion | Reviewer maps each acceptance criterion to an actual behavioral test and end-to-end evidence. |
| Vendor or technology lock-in | Keep durable state/contracts independent and require migration/export tests. |
| Hidden security or rights bypass | Test service-level denial through alternate UI/API paths and inspect audit evidence. |
| Recovery only works on the happy path | Fault-inject interruption/restart/corruption at material boundaries and verify canonical state. |
| UX fragmentation | Validate workflow placement, next-step guidance, support-tool return, and approved reference conformance. |
| Performance overfitting | Use representative fixtures and minimum hardware, publish methodology, and retain regression baselines. |
| Scope expansion into later capabilities | Record new work in the backlog and preserve only required extension points here. |

## 19. Required ADRs and human decisions
- ADR: Material dependency taxonomy and fingerprint policy.
- ADR: Staleness propagation/cycle semantics.
- ADR: Human-approved artifact recalculation rules.

A listed item beginning with `ADR REQUIRED` blocks the relevant implementation choice. Other ADRs may be completed within the first task only when that task explicitly owns the decision and the capability campaign approval permits it.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) - W3C | Interoperable provenance concepts. |
| `JCS` | [RFC 8785 - JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html) - IETF | Deterministic hashing/signing of JSON payloads. |
| `JSON_PATCH` | [RFC 6902 - JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html) - IETF | Explicit reviewable corrections. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Continue through dependency-ready tasks and slices without repeatedly requesting decisions already settled by the approved capability packet. Use only classified pause categories and attach exact evidence/next action.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm `CAP-03` is the active capability campaign and `CAP-03.S05` is the next eligible slice.
3. Claim the first READY task in order: `CAP-03.S05.T01`. Do not globally select work outside the capability.
4. Load only the governing documents, accepted ADRs, approved UI reference sections, this plan, task contract, and affected code/tests.
5. Implement one task at a time. Preserve unrelated working changes; do not weaken tests, delete evidence, or make hidden architectural decisions.
6. After each task, run focused verification, attach criterion-linked evidence, obtain the required independent task review, and transition state through `taskctl`.
7. After all tasks are DONE, execute the complete Section 10 slice matrix from a clean state and assemble the Section 15 evidence bundle.
8. Request an independent slice review. Address findings through tracked tasks or reopen the affected task; never self-approve or mark the slice complete based on narrative evidence alone.
9. Record the approved slice completion and handoff artifacts, then allow the capability campaign to select the next dependent slice.

---
**Generated for Research Observatory baseline 1.3, supplemental planning release 1.3.4.**  
**Plan status:** PROPOSED - HUMAN APPROVAL REQUIRED.  
**Authoritative work state remains:** `planning/backlog.yaml`.
