---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-05
capability_plan: planning/capability-plans/CAP-05.md
planning_gate: capability-decision-complete
slice_id: CAP-05.S04
title: Source viewer and evidence inspection experience
status: approved
wave: W2
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-05.S04.T01
- CAP-05.S04.T02
- CAP-05.S04.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.7
approval:
  status: approved
  approved_by: human:repository-owner
  approved_at: '2026-09-19T16:55:50.446422+00:00'
  approved_commit: c85a59f3a293f8e3f2eaf6454682c9a14b1efa55
---
# CAP-05.S04 - Source viewer and evidence inspection experience
> **Implementation gate — proposed W2 contribution.** Implementation requires the complete W2 packet approved at one immutable commit, its binding ADR/reference decisions resolved, and `python tools/planctl.py --repo . wave ready W2 --require-approved` passing. Then use the same W2 campaign and dependency-eligible taskctl claims; no capability-only approval or lease.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-05` - Document acquisition, parsing, source inspection, and page anchors |
| Capability objective | Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context. |
| Slice | `CAP-05.S04` - Source viewer and evidence inspection experience |
| Slice outcome | Researchers can read original pages and structured text side by side, navigate anchors, and inspect provenance without leaving the workflow. |
| Wave / priority | `W2` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-05.S04.T01`, `CAP-05.S04.T02`, `CAP-05.S04.T03` |
| Slice dependencies | `CAP-05.S03.T03`, `CAP-01.S02.T03` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.7` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Let researchers inspect the original source and exact evidence context from any downstream claim without weakening local file, rights, or webview security.

This slice contributes to the capability objective: **Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context.** It must preserve the capability exit conditions:

- Local files, open-access copies, and structured publisher formats enter through rights-aware acquisition workflows.
- Native XML/HTML is preferred; PDF fallback produces sections, passages, references, and page-coordinate anchors with quality scores.
- Users can inspect every evidence anchor in source context and corrections trigger controlled recalculation.

**Implementation thesis.** Embed a hardened local PDF.js viewer and structured-text view that consume controlled decrypted byte/range streams, never direct paths. Use anchor-driven deep links, synchronized highlights/context, accessible navigation, and policy-mediated copy/print/export/external-open actions.

## 2. Scope

### 2.1 In scope
- Desktop viewer with page thumbnails, zoom, text view, section navigation, search, and restricted external-link behavior.
- Navigation from evidence/graph/synthesis objects to highlighted source anchors with surrounding text, metadata, and processing status.
- Policy-driven copy, print, external open, annotation export, and derivative-text limits with clear user messaging.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-05.S03.T03`, `CAP-01.S02.T03`.
- **Produces:** Researchers can read original pages and structured text side by side, navigate anchors, and inspect provenance without leaving the workflow.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `AGENTS.md` and the conditional routes in `planning/README.md`; historical bootstrap documents do not govern current execution.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-05.S04` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 9-10, 13, 16-19
- Vision evidence-before-prose and page-anchor requirements
- Approved Document Reader and Parsing Quality references

### 3.2 Required upstream state
- `CAP-05.S03.T03` is complete or explicitly gated.
- `CAP-01.S02.T03` is complete or explicitly gated.

### 3.3 Mandatory stop conditions
- A required ADR or human decision listed in Section 19 is unresolved and the affected task cannot be implemented reversibly behind an existing port.
- The implementation would materially change an approved route, workflow, component, interaction, semantic state, or light/dark behavior before the UI reference is updated and approved.
- A dependency contract conflicts with the Systems Design or an accepted ADR.
- Required credentials, signed artifacts, platform hardware, test fixtures, license terms, or security controls are unavailable and cannot be safely stubbed.
- The task would require unrelated work in another capability rather than an explicit backlog task/handoff.
- Evidence suggests the selected technology cannot satisfy security, rights, portability, recovery, or performance requirements; record the evidence and open an ADR instead of forcing implementation.

### 3.4 Complete Wave approval

Before execution, resolve and independently review every W2-binding contribution, decision, interface, recovery path and qualification criterion. One explicit owner approval freezes the complete Wave packet. Capability plans remain cross-Wave outcome maps, not execution leases. Ordinary debugging and approved slice transitions do not require new approval.

### 3.5 Allowed campaign pauses

Follow the approval/stop boundaries in AGENTS.md. Pause only affected work for a documented unmet authority, dependency, safety or feasibility gate; ordinary failed checks remain work to resolve. Supplemental refactoring uses the one locked W2 budget and is not permission to change approved scope.

## 4. Selected implementation decisions

These are proposed planning selections, subordinate to accepted ADRs. The shared W2 assessment records remaining gaps; neither a recommendation nor G1 transition approval authorizes implementation. Resolve conflicting forecasts before the single immutable W2 approval, then preserve its selected scope.

The following decisions are the default implementation direction for this slice. They remain subordinate to accepted ADRs and must be revised if benchmark or security evidence disproves them.

1. **Bundle PDF.js locally at a pinned version; no remote viewer assets or generic browser navigation.**
2. **Use authenticated Core byte requests and a local PDF.js range transport, never `file://` paths. ADR-0029 records the sequential-source cost and unresolved pre-approval transport feasibility; do not claim that W1 supplies random access or hold its database transaction for a viewer session.**
3. **Sanitize structured HTML/text and render inert content; no embedded scripts, forms, media fetches, attachments, or PDF actions.**
4. **Use page virtualization, thumbnails, search, section navigation, zoom, and synchronized structured/PDF panes.**
5. **Deep-link state contains opaque project/document revision/anchor IDs and survives restart/relocation.**
6. **Every viewer action (copy, print, open external, annotation export, quotation export) is evaluated by rights policy.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `services/core-api/src/research_observatory_core/documents/`, `acquisition/`, `parsing/`, and `anchors/`.
- `workers/document/` for isolated parser processes and resource controls.
- `packages/contracts/documents/`, `anchors/`, and `rights/`.
- `apps/desktop/src/workspaces/document-reader/` and `parsing-quality/`.
- `tests/fixtures/documents/`, `tests/parsing/`, `tests/anchors/`, `tests/viewer/`, and `tests/security/`.

**Slice-specific components**
- Pinned PDF.js integration and secure content-stream adapter.
- Structured document renderer and synchronized navigation.
- Anchor highlight/context/deep-link controller.
- Evidence/provenance side panel.
- Rights-aware viewer command broker and audit integration.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `ViewerSession`
- `ViewerDeepLink`
- `HighlightSet`
- `ViewerActionRequest`
- `ViewerPolicyDecision`
- `QuotationExport`

**Required invariants**
- Every durable identity and revision reuses the implemented CAP-03 canonical contracts under ADR-0013/ADR-0024; do not create a parallel identity store.
- Consequential state changes are atomic with existing required provenance/outbox/dependency facts; reuse W1 repository transactions and ADR-0025 durable jobs.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Viewer requests identify project, revision, purpose, range/page, and current policy context.
- Deep links use stable app scheme/route and opaque IDs; invalid/inaccessible targets return safe problem state.
- Quotation export carries source work/version/revision, anchor, allowed text, citation metadata, and policy basis.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
Current visual/page authority is 1.7. Preserve ADR-0026's exact inherited 1.5 workflow-catalog binding; mapping this slice does not relabel existing selections. See [W2 journey and mappings](../../W2-initiation.md#ux-journey-to-refine-in-the-existing-contracts).

- Opening evidence lands on the correct highlighted source with surrounding context and a clear back-to-workflow path.
- Multiple anchors use distinguishable, accessible markers and a navigable list.
- Keyboard, screen reader, zoom/reflow, focus, and high-contrast behavior follow the approved design/a11y contracts.
- Denied actions explain the policy and any lawful alternative.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.7`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Disable or intercept external links, embedded JavaScript/actions, attachments, forms, and file launches.
- Set restrictive CSP/sandbox and isolate PDF rendering from privileged commands.
- Validate page/range requests and prevent cross-project object access.
- Clipboard/export controls are enforced in the broker; acknowledge that screen capture cannot be technically prevented.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Test malformed PDF rendering, huge page, missing font, unavailable/corrupt object, expired session, lost Core connection, broken anchor, denied rights, and relocation.
- Viewer crash is route-contained and restartable without corrupting document state.
- Search/highlight failure falls back to page/context view with explicit status.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-05.S04.T01` - Build secure local PDF/page and structured-text viewer
**Objective:** Desktop viewer with page thumbnails, zoom, text view, section navigation, search, and restricted external-link behavior.

**Dependencies:** `CAP-05.S03.T03`, `CAP-01.S02.T03`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `desktop`, `documents`, `security-local`

**Expected deliverables**
- Desktop viewer with page thumbnails, zoom, text view, section navigation, search, and restricted external-link behavior.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S04.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
5. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
6. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Viewer opens local encrypted content through controlled streams, supports large documents without loading all pages, and never exposes direct file paths to untrusted content.
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
python tools/verify.py --profile documents
python tools/verify.py --profile security-local
```

### 9.2 `CAP-05.S04.T02` - Implement deep links, highlights, and context panels
**Objective:** Navigation from evidence/graph/synthesis objects to highlighted source anchors with surrounding text, metadata, and processing status.

**Dependencies:** `CAP-05.S04.T01`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `desktop`, `documents`, `e2e-local`

**Expected deliverables**
- Navigation from evidence/graph/synthesis objects to highlighted source anchors with surrounding text, metadata, and processing status.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S04.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Deep links survive application restart and project relocation; multiple anchors display distinctly; missing anchors show the relevant revision and repair action.
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
python tools/verify.py --profile documents
python tools/verify.py --profile e2e-local
```

### 9.3 `CAP-05.S04.T03` - Enforce rights-aware viewer actions and export
**Objective:** Policy-driven copy, print, external open, annotation export, and derivative-text limits with clear user messaging.

**Dependencies:** `CAP-05.S04.T02`  
**Risk / review gate:** `high` / `rights-review`  
**Verification profiles:** `desktop`, `security-local`

**Expected deliverables**
- Policy-driven copy, print, external open, annotation export, and derivative-text limits with clear user messaging.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S04.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the smallest vertical path that satisfies the task objective while preserving the slice architecture and adjacent-capability contracts.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Restricted documents cannot be exported through alternate UI paths; allowed quotations carry source identifiers; denied actions are audited without storing copied text.
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
python tools/verify.py --profile security-local
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `desktop`, `documents`, `e2e-local`, `security-local` |
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
python tools/verify.py --profile documents
python tools/verify.py --profile e2e-local
python tools/verify.py --profile security-local
```

## 11. Performance and resource budgets
- Accepted ADR-0029 selects bounded verified sequential ranges, maximum sizes/concurrency, cooperative read-loop cancellation, prompt lease release and representative/stress fixtures. Its [storage probe](../../W2-feasibility.md) is not renderer, minimum-hardware or cancellation proof; CAP-05.S04.T01 includes that integration and qualification.
- Render visible pages only, cache bounded thumbnails/pages, and cancel obsolete renders during rapid navigation.
- Open-to-first-page target <=1.5 seconds for a representative local PDF after Core readiness.
- Large documents remain usable without loading all pages or text into renderer memory.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Record viewer open/render/search/anchor resolution/action outcome and safe error codes; no page text or search terms in default logs.
- Visual/a11y tests cover representative PDFs and structured documents.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- Consumes CAP-05.S03 revisions/anchors and CAP-04.S04 rights.
- All evidence/graph/synthesis/manuscript pages use this viewer rather than separate source renderers.
- CAP-14 requalifies PDF.js/custom protocol and accessibility cross-platform.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- PDF.js upgrades require security review, representative visual/anchor regression, and approved reference update only if interaction changes.
- Deep-link route/ID compatibility is preserved or migrated.

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
- The complete W2 campaign is approved and active; the selected task and slice satisfy canonical dependencies and taskctl eligibility.
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
- The selected task is READY under taskctl in the approved W2 campaign, with required predecessor tasks/slices complete.

## 17. Definition of Done
- Deliverables and all task acceptance criteria are satisfied.
- Risk-selected checks pass on the reviewed commit with criterion-to-evidence records and selected/deferred coverage; slice/checkpoint/Wave breadth follows the workflow, not blanket task-profile replay.
- Security, privacy, rights, accessibility, scholarly-method, platform, migration, or release gates are completed when specified.
- Documentation, tests, migrations, fixtures, provenance, and stale-dependency behavior are updated as relevant.
- An independent reviewer sets review.result to approved and status to DONE.
- Newly discovered work is recorded as explicit backlog tasks rather than hidden TODOs.
- The task lease is released and branch/worktree disposition is recorded.
- User-facing implementation conforms to the approved reference ID through token, route/page-contract, workflow-navigation, accessibility, and visual-regression evidence.
- Task completion does not by itself complete the slice or capability; slice and capability end-to-end reviews must also pass.

**Slice-specific completion additions**
- The promised outcome is demonstrable end to end: Researchers can read original pages and structured text side by side, navigate anchors, and inspect provenance without leaving the workflow.
- All task implementations operate together from a clean project/install state, not only in isolated tests.
- The slice evidence bundle passes independent review and the downstream handoff fixtures/contracts are usable.
- W2 campaign state advances through taskctl only after the required independent slice disposition.

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
Shared accepted records: [ADR-0029](../../../docs/adr/ADR-0029-preserve-document-revisions-and-mediate-source-viewing.md).
The following details belong in that shared packet; they do not each require a new ADR or human approval. Any unresolved material detail still prevents W2 packet approval.

- Binding detail: Authenticated range stream versus Tauri custom protocol for local PDF bytes.
- Binding detail: PDF.js sandbox/CSP and external-action policy.
- Binding detail: Quotation/copy/export enforcement boundaries.

Resolve these material topics through the shared W2 ADR set before packet approval; routine implementation details need no separate ADR. New ADRs remain Proposed until accepted. Do not defer a foreseeable binding architecture choice to implementation or treat a safely stubbed test as real-boundary qualification.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `PDFJS` | [PDF.js API Documentation](https://mozilla.github.io/pdf.js/api/) - Mozilla | Controlled local PDF rendering. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) - W3C | Multi-selector source anchors and version state. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) - W3C | AA accessibility target. |
| `WAI_APG` | [WAI-ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/) - W3C | Keyboard and assistive-technology patterns. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Resume the same approved W2 campaign through taskctl. Use full task designators, risk-selected verification, independent dispositions and local integration. Continue through eligible slices/checkpoints to fresh Wave qualification and the separate G2 human exit gate.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm W2 is the approved active campaign and `CAP-05.S04` is dependency-eligible.
3. Claim only the next READY task in `CAP-05.S04` through taskctl; do not bypass Wave dependencies or create a capability lease.
4. Load only the governing documents, accepted ADRs, approved UI reference sections, this plan, task contract, and affected code/tests.
5. Implement one task at a time. Preserve unrelated working changes; do not weaken tests, delete evidence, or make hidden architectural decisions.
6. After each task, run focused verification, attach criterion-linked evidence, obtain the required independent task review, and transition state through `taskctl`.
7. After all tasks are DONE, execute the complete Section 10 slice matrix from a clean state and assemble the Section 15 evidence bundle.
8. Request independent slice review. Preserve findings and prior dispositions; completed-task defects use the linked correction route rather than rewriting history.
9. Record approved slice completion and handoff, then continue the same W2 campaign to its next eligible contribution.

---
**Generated for Research Observatory baseline 1.3, supplemental planning release 1.3.4.**  
**Plan status:** PROPOSED - HUMAN APPROVAL REQUIRED.  
**Authoritative work state remains:** `planning/backlog.yaml`.
