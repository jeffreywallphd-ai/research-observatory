---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-05
capability_plan: planning/capability-plans/CAP-05.md
planning_gate: capability-decision-complete
slice_id: CAP-05.S05
title: References, citation contexts, tables, and figures
status: proposed
wave: W2
priority: P1
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-05.S05.T01
- CAP-05.S05.T02
- CAP-05.S05.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-05.S05 - References, citation contexts, tables, and figures
> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-05.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and `python tools/planctl.py ready CAP-05 --require-approved` passes. After campaign start, execute continuously and pause only for an allowed classified condition.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-05` - Document acquisition, parsing, source inspection, and page anchors |
| Capability objective | Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context. |
| Slice | `CAP-05.S05` - References, citation contexts, tables, and figures |
| Slice outcome | Document-internal scholarly structures become inspectable records without losing page context. |
| Wave / priority | `W2` / `P1` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-05.S05.T01`, `CAP-05.S05.T02`, `CAP-05.S05.T03` |
| Slice dependencies | `CAP-05.S03.T03` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.3` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Expose references, citation contexts, tables, and figures as source-grounded scholarly structures without confusing parser output with verified evidence.

This slice contributes to the capability objective: **Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context.** It must preserve the capability exit conditions:

- Local files, open-access copies, and structured publisher formats enter through rights-aware acquisition workflows.
- Native XML/HTML is preferred; PDF fallback produces sections, passages, references, and page-coordinate anchors with quality scores.
- Users can inspect every evidence anchor in source context and corrections trigger controlled recalculation.

**Implementation thesis.** Preserve raw reference/citation/table/figure content and exact anchors, normalize into reviewable records, auto-link only exact identifiers, and expose extraction quality separately for each structure.

## 2. Scope

### 2.1 In scope
- Parsed references, identifiers, raw strings, author/year/title fields, and links to canonical works or unresolved candidates.
- Citation markers linked to reference entries with sentence/paragraph context, location, and multi-target handling.
- Table/figure objects, captions, page locations, extracted text/cells where reliable, and image preview references.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-05.S03.T03`.
- **Produces:** Document-internal scholarly structures become inspectable records without losing page context.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `START_HERE.md` and `docs/governance/document-set-and-bootstrap.md`.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-05.S05` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 9-10, 13, 16-19
- Vision evidence-before-prose and page-anchor requirements
- Approved Document Reader and Parsing Quality references

### 3.2 Required upstream state
- `CAP-05.S03.T03` is complete or explicitly gated.

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

1. **Reference entries preserve raw string/order plus parsed fields and identifier candidates.**
2. **Exact validated identifiers may auto-link to canonical works; fuzzy matches remain scored review candidates.**
3. **In-text citation markers link to one or more reference entries and retain sentence/paragraph context anchors.**
4. **Support numeric, author-year, superscript, grouped, ranged, narrative, and footnote citation patterns through parser adapters/fixtures.**
5. **Tables/figures store caption, label, page/region anchors, preview object, and structured extraction only when available.**
6. **Low-confidence cells/figure text never become verified quantitative evidence without downstream verification.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `services/core-api/modules/documents/`, `acquisition/`, `parsing/`, and `anchors/`.
- `workers/document/` for isolated parser processes and resource controls.
- `packages/contracts/documents/`, `anchors/`, and `rights/`.
- `apps/desktop/src/workspaces/document-reader/` and `parsing-quality/`.
- `tests/fixtures/documents/`, `tests/parsing/`, `tests/anchors/`, `tests/viewer/`, and `tests/security/`.

**Slice-specific components**
- Reference/citation/table/figure domain schemas and repositories.
- Reference parser/normalizer and exact/fuzzy reconciliation bridge to CAP-04.S03.
- Citation-marker/context resolver.
- Table/figure preview and structured extraction representation.
- Inspection/review interfaces and quality badges.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `ReferenceEntry`
- `ReferenceFieldAssertion`
- `ReferenceMatchCandidate`
- `CitationMarker`
- `CitationContext`
- `TableObject`
- `TableCell`
- `FigureObject`
- `StructureQuality`

**Required invariants**
- Every durable identity and revision follows CAP-03 canonical identifier/version rules or creates the necessary contract in this slice when CAP-03 is not yet available.
- Consequential state changes are atomic with required provenance/outbox/dependency facts once those foundations exist; earlier slices provide an explicit integration seam and fixtures.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Every derived structure points to document revision and exact anchor(s).
- Reference link status: exact-linked, candidate, ambiguous, unresolved, non-scholarly, or rejected.
- Citation context distinguishes marker text, target reference(s), containing sentence/paragraph, and parser confidence.
- Table cells preserve row/column/span/header coordinates and source region when reliable.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
- Reference and citation views allow jump to source and canonical target, show ambiguity, and support adjudication.
- Tables/figures show original page preview beside extracted representation and explicit quality limitations.
- Users can exclude corrupted structures without altering original parse output.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Sanitize captions/reference text and never render extracted HTML actively.
- Rights policy governs image previews and export.
- External DOI/URL opens require validated/confirmed destinations.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Test missing/truncated references, duplicate labels, multi-target citations, OCR errors, unnumbered figures, split tables, rotated pages, and unresolved canonical targets.
- Enrichment failures leave the base document revision usable.
- Correction creates new derived revisions/provenance and stale propagation.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-05.S05.T01` - Extract and reconcile reference-list entries
**Objective:** Parsed references, identifiers, raw strings, author/year/title fields, and links to canonical works or unresolved candidates.

**Dependencies:** `CAP-05.S03.T03`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `documents`, `service`

**Expected deliverables**
- Parsed references, identifiers, raw strings, author/year/title fields, and links to canonical works or unresolved candidates.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S05.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the smallest vertical path that satisfies the task objective while preserving the slice architecture and adjacent-capability contracts.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Reference order and raw text are preserved; exact identifiers reconcile automatically; uncertain matches remain candidates with scores and review state.
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
python tools/verify.py --profile documents
python tools/verify.py --profile service
```

### 9.2 `CAP-05.S05.T02` - Extract in-text citation contexts and targets
**Objective:** Citation markers linked to reference entries with sentence/paragraph context, location, and multi-target handling.

**Dependencies:** `CAP-05.S05.T01`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `documents`, `graph`

**Expected deliverables**
- Citation markers linked to reference entries with sentence/paragraph context, location, and multi-target handling.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S05.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the smallest vertical path that satisfies the task objective while preserving the slice architecture and adjacent-capability contracts.
3. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
4. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Fixture citation styles resolve correctly; unresolved and ambiguous targets are explicit; contexts retain exact source anchors.
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
python tools/verify.py --profile documents
python tools/verify.py --profile graph
```

### 9.3 `CAP-05.S05.T03` - Represent tables and figures with captions and page anchors
**Objective:** Table/figure objects, captions, page locations, extracted text/cells where reliable, and image preview references.

**Dependencies:** `CAP-05.S05.T02`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `documents`, `desktop`

**Expected deliverables**
- Table/figure objects, captions, page locations, extracted text/cells where reliable, and image preview references.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-05.S05.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the smallest vertical path that satisfies the task objective while preserving the slice architecture and adjacent-capability contracts.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
5. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
6. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Objects navigate to original pages; extraction quality is displayed; the system does not treat low-confidence cell extraction as verified evidence.
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
python tools/verify.py --profile documents
python tools/verify.py --profile desktop
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `desktop`, `documents`, `graph`, `service` |
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
python tools/verify.py --profile graph
python tools/verify.py --profile service
```

## 11. Performance and resource budgets
- Batch exact identifier lookup and candidate generation; avoid network calls inside parse transaction.
- Lazy-load image previews and large table cells.
- Index reference labels, identifiers, canonical targets, citation locations, and structure type.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Track extraction/link quality by format/parser, unresolved/ambiguous rates, review decisions, table/figure coverage, and later correction rate.
- Record algorithm/config version with every candidate.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- CAP-04.S03 canonicalizes reference targets.
- CAP-08 extraction uses source-grounded contexts/tables/figures.
- CAP-09 claim graph uses citation relations but does not equate citation with support.
- CAP-18 drafting can cite/export only permitted and verified structures.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- Improved reference/citation extraction creates new derived records or document revision enrichment with provenance; raw original remains.
- Quality schema additions preserve prior unknown dimensions.

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
- The promised outcome is demonstrable end to end: Document-internal scholarly structures become inspectable records without losing page context.
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
- ADR: Reference/citation context schema and exact auto-link rules.
- ADR: Table cell representation and quality thresholds.
- ADR: Figure preview/OCR extraction boundaries.

A listed item beginning with `ADR REQUIRED` blocks the relevant implementation choice. Other ADRs may be completed within the first task only when that task explicitly owns the decision and the capability campaign approval permits it.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `CROSSREF` | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) - Crossref | DOI metadata, licenses, updates, ORCID and ROR fields. |
| `DOI_SYNTAX` | [DOI Handbook - DOI Name Syntax](https://www.doi.org/doi-handbook/HTML/doi-name-syntax2.html) - DOI Foundation | Conservative DOI normalization. |
| `WEB_ANNOTATION` | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) - W3C | Multi-selector source anchors and version state. |
| `PDFJS` | [PDF.js API Documentation](https://mozilla.github.io/pdf.js/api/) - Mozilla | Controlled local PDF rendering. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Continue through dependency-ready tasks and slices without repeatedly requesting decisions already settled by the approved capability packet. Use only classified pause categories and attach exact evidence/next action.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm `CAP-05` is the active capability campaign and `CAP-05.S05` is the next eligible slice.
3. Claim the first READY task in order: `CAP-05.S05.T01`. Do not globally select work outside the capability.
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
