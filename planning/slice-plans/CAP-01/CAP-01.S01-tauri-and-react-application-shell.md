---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-01
capability_plan: planning/capability-plans/CAP-01.md
planning_gate: capability-decision-complete
slice_id: CAP-01.S01
title: Tauri and React application shell
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
- CAP-01.S01.T01
- CAP-01.S01.T02
- CAP-01.S01.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-01.S01 - Tauri and React application shell
> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-01.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and `python tools/planctl.py ready CAP-01 --require-approved` passes. After campaign start, execute continuously and pause only for an allowed classified condition.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-01` - Windows-first desktop shell and supervised local runtime |
| Capability objective | Deliver the canonical Windows-first desktop experience and a reliably packaged local analytical service that requires no external server administration. |
| Slice | `CAP-01.S01` - Tauri and React application shell |
| Slice outcome | A production-shaped desktop shell provides navigation, project selection, commands, and application state. |
| Wave / priority | `W1` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-01.S01.T01`, `CAP-01.S01.T02`, `CAP-01.S01.T03` |
| Slice dependencies | `CAP-00.S01.T03`, `CAP-00.S03.T02` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.3` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Establish the stable desktop shell through which every research workflow is experienced, while keeping domain logic and long-running work outside the renderer.

This slice contributes to the capability objective: **Deliver the canonical Windows-first desktop experience and a reliably packaged local analytical service that requires no external server administration.** It must preserve the capability exit conditions:

- The signed-development desktop application installs, launches, navigates, and supervises its compatible sidecar.
- Desktop-to-service communication is authenticated, versioned, observable, and recoverable.
- The same client architecture and project contracts are portable to macOS/Linux in CAP-14 and later connect to university/cloud profiles without forking the UI.

**Implementation thesis.** Use one Tauri 2 shell and one strict React/TypeScript application. Organize workspaces by route and feature boundary, load them lazily, and treat the desktop shell as a replaceable client of versioned Core APIs rather than as the owner of scholarly state.

## 2. Scope

### 2.1 In scope
- Runnable desktop package with strict TypeScript, routing, application state, and development/build commands.
- Title bar, navigation rail, command area, project context, route guards, and placeholder workspaces matching the product information architecture.
- Project-selection experience that can open, create, and recover from unavailable local project locations.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-00.S01.T03`, `CAP-00.S03.T02`.
- **Produces:** A production-shaped desktop shell provides navigation, project selection, commands, and application state.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `START_HERE.md` and `docs/governance/document-set-and-bootstrap.md`.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-01.S01` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 2-6, 12, 16-19
- Approved UI reference and workflow/page contracts
- Automation Guide CAP-01 verification profiles

### 3.2 Required upstream state
- `CAP-00.S01.T03` is complete or explicitly gated.
- `CAP-00.S03.T02` is complete or explicitly gated.

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

1. **Adopt Tauri 2 as the only desktop host for the baseline; do not create an Electron or browser-only fork.**
2. **Use React with TypeScript strict mode, an explicit route object tree, and lazy-loaded workspace bundles.**
3. **Separate server state, local UI state, form state, and durable project state; do not introduce a global store for all four.**
4. **Keep all filesystem, process, keychain, and privileged operations behind narrow Tauri commands or Core API calls.**
5. **Use the approved Academic Minimal UI reference as normative for route presence, shell regions, responsive behavior, light/dark parity, and adaptive workflow navigation.**
6. **Treat the project session as an explicit state machine: no-project, opening, ready, read-only, incompatible, recovery-required, closing.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `apps/desktop/` - Tauri/React shell and user-facing workspaces.
- `apps/desktop/src-tauri/` - privileged commands, process supervision, packaging, and platform adapters.
- `services/core-api/` - packaged FastAPI modular monolith.
- `packages/contracts/` - OpenAPI/schema/generated-client sources.
- `packages/ui-tokens/` and `packages/ui-components/` - approved design system.
- `tests/desktop/`, `tests/contracts/`, `tests/e2e/`, and `tests/packaging/`.

**Slice-specific components**
- `apps/desktop/src/app` application composition root and providers.
- `apps/desktop/src/routes` typed route definitions and lazy workspace modules.
- `apps/desktop/src/shell` top bar, adaptive navigation, workflow context, notifications, and global recovery surfaces.
- `apps/desktop/src/state` narrowly scoped query cache, theme/preferences, and current project session.
- `apps/desktop/src-tauri` command boundary, window policy, deep links, and later sidecar supervision hooks.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `DesktopPreference`
- `RecentProjectReference`
- `ProjectSessionState`
- `RouteContract`
- `WorkflowNavigationContext`

**Required invariants**
- Every durable identity and revision follows CAP-03 canonical identifier/version rules or creates the necessary contract in this slice when CAP-03 is not yet available.
- Consequential state changes are atomic with required provenance/outbox/dependency facts once those foundations exist; earlier slices provide an explicit integration seam and fixtures.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Route IDs are stable, machine-readable, and map to approved page contracts.
- Privileged renderer requests use typed command DTOs; raw path and arbitrary shell invocation are prohibited.
- Project-session changes emit one normalized event consumed by routing, recent-projects, and recovery UI.
- Every route declares its workflow roles, required project state, offline behavior, and loading boundary.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
- Implement Project Home, Projects, New Project, and the complete global shell before feature-specific workspaces.
- Use progressive disclosure: ordered primary workflow stages are prominent; supporting tools remain accessible in a secondary inventory.
- Provide complete keyboard navigation, visible focus, no-project empty states, and recoverable route errors.
- Avoid dashboard-only dead ends: every summary card identifies the relevant workflow stage and next action.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Enable a restrictive Tauri capability/permission configuration and explicit content security policy.
- Disallow arbitrary remote content in the application webview.
- Never expose local absolute paths, launch tokens, or secrets to the DOM or analytics.
- Validate every deep link and external-open request against an allowlist and current project authority.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- A workspace chunk failure is contained by a route-level error boundary and does not terminate the shell.
- If a project fails to open, preserve recent-project metadata and offer inspect, retry, relocate, restore, or remove-reference actions.
- If the Core API is unavailable, show a supervised-runtime recovery surface instead of cascading blank screens.
- Persist only safe UI preferences; incomplete domain actions are owned by durable workflow state, not browser storage.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-01.S01.T01` - Bootstrap the Tauri 2 and React/TypeScript desktop application
**Objective:** Runnable desktop package with strict TypeScript, routing, application state, and development/build commands.

**Dependencies:** `CAP-00.S01.T03`, `CAP-00.S03.T02`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `desktop`

**Expected deliverables**
- Runnable desktop package with strict TypeScript, routing, application state, and development/build commands.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-01.S01.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Author the versioned schema/interface/state-machine definitions first, including unknown/not-applicable states, compatibility metadata, validation rules, and negative fixtures. Keep framework and persistence types outside the portable contract.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- The app launches on supported Windows, opens no unnecessary network ports, and passes desktop lint, type, unit, and build smoke checks.
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
python tools/verify.py --profile desktop
```

### 9.2 `CAP-01.S01.T02` - Implement the primary application frame and workspace routing
**Objective:** Title bar, navigation rail, command area, project context, route guards, and placeholder workspaces matching the product information architecture.

**Dependencies:** `CAP-01.S01.T01`  
**Risk / review gate:** `low` / `agent-review`  
**Verification profiles:** `desktop`

**Expected deliverables**
- Title bar, navigation rail, command area, project context, route guards, and placeholder workspaces matching the product information architecture.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-01.S01.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- All planned local workspaces are reachable by keyboard and deep link; invalid routes recover to a safe project home; no business logic is duplicated in views.
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
python tools/verify.py --profile desktop
```

### 9.3 `CAP-01.S01.T03` - Add project switcher, recent projects, and empty-state flows
**Objective:** Project-selection experience that can open, create, and recover from unavailable local project locations.

**Dependencies:** `CAP-01.S01.T02`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `desktop`

**Expected deliverables**
- Project-selection experience that can open, create, and recover from unavailable local project locations.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-01.S01.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Recent entries are deterministic and removable; missing projects show repair options; the app never silently creates a replacement project.
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
python tools/verify.py --profile desktop
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `desktop` |
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
python tools/verify.py --profile desktop
```

## 11. Performance and resource budgets
- Cold shell paint target: <=2.5 seconds on the minimum supported Windows PC, excluding first-run installation work.
- Route transition target: <=150 ms to visible skeleton and <=1 second to usable cached content for representative local projects.
- Keep initial renderer JavaScript bounded through route-level splitting and dependency budgets.
- Virtualize data-heavy lists and defer graph/canvas engines until their workspaces are opened.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Record shell startup stages, route transitions, renderer errors, Core handshake state, and user-initiated recovery actions with trace IDs.
- Do not record research content, query text, filenames, or draft text in default diagnostics.
- Expose build, UI reference, contract, and Core versions in the local diagnostics surface.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- CAP-01.S02 supplies tokens, components, accessibility, and common states.
- CAP-01.S03/S04 supply supervised runtime and authenticated API connectivity.
- CAP-02 supplies real project lifecycle and durable recent-project resolution.
- CAP-03.S06 replaces static tool ordering with project-specific adaptive workflow navigation.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- No compatibility migration is required for the initial shell; establish versioned preference schema from the first release.
- Route IDs and page-contract IDs become compatibility-sensitive once persisted in deep links or workflow profiles.

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
- The promised outcome is demonstrable end to end: A production-shaped desktop shell provides navigation, project selection, commands, and application state.
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
- ADR: Desktop shell state ownership and routing boundaries.
- ADR: Renderer privilege boundary and Tauri capability policy.

A listed item beginning with `ADR REQUIRED` blocks the relevant implementation choice. Other ADRs may be completed within the first task only when that task explicitly owns the decision and the capability campaign approval permits it.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `TAURI_SIDECAR` | [Tauri 2 - Embedding External Binaries](https://v2.tauri.app/develop/sidecar/) - Tauri | Bundling target-specific external binaries and invoking supervised sidecars. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) - W3C | AA accessibility target. |
| `WAI_APG` | [WAI-ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/) - W3C | Keyboard and assistive-technology patterns. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Continue through dependency-ready tasks and slices without repeatedly requesting decisions already settled by the approved capability packet. Use only classified pause categories and attach exact evidence/next action.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm `CAP-01` is the active capability campaign and `CAP-01.S01` is the next eligible slice.
3. Claim the first READY task in order: `CAP-01.S01.T01`. Do not globally select work outside the capability.
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
