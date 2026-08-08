---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-09
capability_plan: planning/capability-plans/CAP-09.md
planning_gate: capability-decision-complete
slice_id: CAP-09.S02
title: Claim, theory, construct, method, and context relations
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
- CAP-09.S02.T01
- CAP-09.S02.T02
- CAP-09.S02.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-09.S02 — Claim, theory, construct, method, and context relations

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-09.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and both plan validators pass in approval mode. Once the capability campaign starts, the agent should execute continuously through its slices and pause only for an allowed infeasibility, external dependency, unavailable required hardware, explicit human decision, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-09` — Scholarly graph, comparison sets, synthesis, and reproducibility |
| Capability objective | Connect bibliographic structure to claims, constructs, methods, contexts, assumptions, evidence, and decisions; then produce source-grounded synthesis and reproducibility artifacts. |
| Slice | `CAP-09.S02` — Claim, theory, construct, method, and context relations |
| Slice outcome | Internal paper semantics become a multi-granular argument representation with preserved wording and evidence. |
| Wave / priority | `W4` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-09.S02.T01`, `CAP-09.S02.T02`, `CAP-09.S02.T03` |
| Slice dependencies | `CAP-09.S01.T03`, `CAP-08.S06.T02` |
| Capability decision packet | `planning/capability-plans/CAP-09.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant pages: claim-graph.html, theory-map.html, synthesis-studio.html, audit-lineage.html |
| Approval state | `PROPOSED` / human approval pending |

## 1. Purpose and contribution to the larger vision

Internal paper semantics become a multi-granular argument representation with preserved wording and evidence.

This slice advances the capability objective: **Connect bibliographic structure to claims, constructs, methods, contexts, assumptions, evidence, and decisions; then produce source-grounded synthesis and reproducibility artifacts.** It is designed as one production vertical inside a long-running capability campaign, not as an isolated technical experiment. The implementation must preserve the platform’s evidence-before-prose rule, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, cross-platform ports, and the distinction between canonical scholarly state and rebuildable analytical derivatives.

**Implementation thesis.** Link author-specific language to reusable scholarly entities while preserving the original wording, and treat extracted claim and argument relations as reviewable candidates rather than automatic facts.

The containing capability is complete only when all of its slices satisfy these exit conditions:

- Typed graph projections are derived from canonical records and every material edge is traceable and contestable.
- Contradiction analysis begins with explicit comparability rather than naive claim similarity.
- Synthesis and exports preserve supporting evidence, disagreement, uncertainty, rights, and exact project state.
- Synthesis and graph outputs can become evidence packets for study design, manuscript blueprints, drafting, and review without losing source lineage.

## 2. Scope

### 2.1 In scope

- Entity linking for theories, constructs, methods, measures, datasets and contexts.
- Claim/argument relation candidate extraction with anchors and uncertainty.
- Relation review, competing interpretations, dispute and adjudication.

### 2.2 Explicit non-goals

- Forcing all disciplines into one fixed ontology.
- Automatically merging similarly named constructs.
- Treating citation presence as support or contradiction.
- Do not implement downstream capability behavior beyond narrow ports, fixtures and handoffs explicitly named here.
- Do not introduce university-hosted or managed-cloud infrastructure during the local Windows waves; preserve deployment-neutral contracts only.
- Do not bypass the Core API, canonical repositories, provenance ledger, durable workflow fabric, rights policy, model gateway or approved experience reference.
- Do not declare completion from happy-path task tests alone; slice-wide failure, cancellation, restart, migration, security, accessibility and handoff evidence is required.

### 2.3 Slice boundary

- **Consumes:** `CAP-09.S01.T03`, `CAP-08.S06.T02` and the handoffs in Section 13.
- **Produces:** Internal paper semantics become a multi-granular argument representation with preserved wording and evidence.
- **Owns:** The portable domain contracts, adapter boundaries, workflows, fixtures, decisions and evidence explicitly listed in this plan.
- **Does not own:** Product purpose, unrelated capabilities, user-authoritative scholarly judgments, source rights, or provider/database/UI framework internals.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. Vision and non-goals in `docs/product/vision.md`.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md`.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved capability decision packet `planning/capability-plans/CAP-09.md`.
5. This approved slice plan.
6. Approved UI reference, workflow/page contracts and style guide for user-facing work.
7. Automation and task-control rules.

### 3.2 Required upstream state

- All slice dependencies are approved or an explicitly approved integration stub exists: `CAP-09.S01.T03`, `CAP-08.S06.T02`.
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
| **Entity-linking policy** | Use deterministic identifiers/aliases and candidate retrieval first, followed by model-assisted ranking; retain mention text, source context, candidate list and human decision. | Let an LLM emit a canonical entity name without candidates or evidence. | Entity linking is consequential and requires reversible, inspectable resolution rather than fluent normalization. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| **Construct identity** | Allow related, broader/narrower, variant and disputed-equivalence relations; merge only through an adjudicated command. | Case-folded string matching or embedding threshold automatically merges constructs. | Construct drift and operational variation are analytical material, not noise to erase. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| **Argument representation** | Extract claim, evidence, warrant, qualification, rebuttal and relation candidates with exact anchors and candidate status; use schema packs by mode/domain. | One universal support/contradiction classifier over abstracts. | Argument roles and relation meanings vary; source-grounded typed candidates support later comparison and synthesis. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `services/core/research_observatory/modules/scholarly_graph/entity_linking.py` | Mention, candidate, resolution and merge policy. |
| `services/core/research_observatory/modules/scholarly_graph/argument_candidates.py` | Claim/argument extraction orchestration. |
| `packages/contracts/ontology-linking` | Mention, candidate, relation and adjudication schemas. |
| `packages/ui/graph/relation-review` | Source-first candidate comparison and decision UI. |
| `services/core/research_observatory/modules/ontology/merge_service.py` | Versioned merges/splits and dependent staleness. |
| `tests/benchmarks/entity-argument` | Gold mentions, construct variants and relation candidates. |

The paths are recommendations within the approved modular-monolith/package structure. Exact filenames may change without a new decision if module ownership, portable contracts and dependency directions remain intact.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `EntityMention` | document revision, anchor, original text, context and proposed semantic type |
| `EntityLinkCandidate` | canonical entity, lexical/semantic/graph signals, explanation and model manifest |
| `EntityLinkDecision` | selected/new/unresolved/rejected state, actor and rationale |
| `ArgumentUnit` | claim/evidence/warrant/qualification/rebuttal candidate with anchor and status |
| `ArgumentRelationCandidate` | source unit, target unit/entity, type, polarity, scope, confidence and evidence |

**Cross-cutting invariants**

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, graph projections, rankings, generated drafts and detector signals are versioned derivatives.
- Unknown, not reported, not applicable, denied, unavailable, ambiguous, inferred, disputed, stale and failed remain distinct where relevant.
- Every long-running operation has stable identity, status, inputs/manifests, progress, cancellation, checkpoint, restart and evidence records.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `EntityLinker.propose(mention, ontology_pack, snapshot)` returns ranked candidates and signal explanations.
- `EntityResolutionCommand.resolve/create/merge/split` applies role and dependency policy.
- `ArgumentMiner.extract(revision, schema_pack, model_policy)` emits candidates only.
- `RelationReviewCommand.verify/dispute/adjudicate` publishes canonical relation assertions to S01.

All contracts use stable canonical IDs, explicit revisions/status, typed errors and version metadata. Provider SDK objects, SQLite rows, model tensors, graph library objects and UI component state may not cross the owning adapter boundary.

### 5.4 Cross-capability and platform compatibility

- Windows x64 is the current implementation target, but paths, process control, credential storage, accelerators and packaging stay behind adapters required by CAP-14 macOS/Linux qualification.
- Local and hosted deployments use the same domain/API/workflow semantics; storage, process, authentication and scaling adapters differ later.
- Downstream CAP-11–19 consume immutable IDs, evidence/provenance, manifests and ports rather than internal tables or framework classes.
- Model, embedding, reranker, parser, graph and vector choices are pinned and replaceable; changing one marks exact dependents stale and requires evaluation rather than silent regeneration.

## 6. User experience and approved reference

- Review shows mention and passage beside candidates, definitions, prior usage and merge consequences.
- “Create new entity,” “related but distinct,” and “remain unresolved” are first-class decisions.
- Claim/relation candidates are batched by project workflow, consequence and uncertainty.
- Original author wording is visible in maps and exports even after entity linking.

- Workflow navigation must show the project’s selected use case, current numbered stage, completed/upcoming states, expected output and next/previous actions.
- Supporting tools remain accessible, but opening one explains its relationship to the primary path and offers return to the current stage.
- All semantic states use text/icon in addition to color, meet WCAG 2.2 AA targets, support keyboard operation, and have light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed—not left as generic alerts.

**Reference-first rule.** If the planned experience materially differs from `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit approval and a new reference ID; only then implement application code. Restoring a defect to the approved reference does not require a new reference.

## 7. Security, privacy, rights and research integrity

- Remote models receive only policy-approved passages and ontology fields after egress preview.
- Entity labels and source passages inherit project classification.
- Bulk merges require elevated role, impact preview and durable audit.

Additional mandatory controls:

- Treat source content, metadata, model files, provider responses, reports, URLs, archives and rich text as untrusted.
- Apply least privilege, schema/input validation, destination/path controls, bounded resources, output encoding and redacted diagnostics at trusted boundaries.
- Private projects and unpublished ideas remain local by default; egress requires project policy, rights decision and visible payload/provider preview.
- Never fabricate evidence, citations, availability, permissions, method details, model certainty, benchmark success or completion evidence.
- AI output is candidate state until the domain-specific verifier/human gate promotes it.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior |
|---|---|
| No credible entity candidate | Create unresolved/new-entity path; never force nearest vector match. |
| Ontology pack changed | Retain old decision, mark dependent links stale and queue scoped re-resolution. |
| Model returns malformed relation | Reject by schema and retain raw provider diagnostic only under redaction policy. |
| Merge later reversed | Versioned split/remap migration replays affected projections and marks outputs stale. |

Every scenario receives a deterministic fixture where feasible, expected canonical state, expected derivative state, user message/action, retry/cancel rule, cleanup/repair rule, provenance event and automated test. A restart test must execute from persisted state rather than from an in-memory mock alone.

## 9. Task-by-task implementation plan

### CAP-09.S02.T01 — Implement entity linking for theories, constructs, methods, measures, datasets, and contexts

**Objective.** Candidate links using identifiers, dictionaries, embeddings, and project ontology with alternate mappings and author wording.

| Control | Value |
|---|---|
| Dependencies | `CAP-09.S01.T03`, `CAP-08.S06.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `graph`, `evidence`, `search` |

**Expected deliverables**

- Candidate links using identifiers, dictionaries, embeddings, and project ontology with alternate mappings and author wording.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-09.S02.T01`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
4. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
5. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Gold entities meet declared precision/recall; ambiguous mappings remain reviewable; ontology mappings cite evidence or decision provenance.
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
python tools/verify.py --profile graph
python tools/verify.py --profile evidence
python tools/verify.py --profile search
```


### CAP-09.S02.T02 — Implement claim and argument relation candidate extraction

**Objective.** Candidate SUPPORTS, CONTRADICTS, QUALIFIES, EXTENDS, TESTS, DEFINES, OPERATIONALIZES_AS, ASSUMES, and boundary relations with source anchors.

| Control | Value |
|---|---|
| Dependencies | `CAP-09.S02.T01` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `graph`, `ai`, `evidence` |

**Expected deliverables**

- Candidate SUPPORTS, CONTRADICTS, QUALIFIES, EXTENDS, TESTS, DEFINES, OPERATIONALIZES_AS, ASSUMES, and boundary relations with source anchors.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-09.S02.T02`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
5. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Relation candidates include subject/object spans, evidence, direction, status, and uncertainty; direct citation stance is not misrepresented as full claim agreement.
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
python tools/verify.py --profile graph
python tools/verify.py --profile ai
python tools/verify.py --profile evidence
```


### CAP-09.S02.T03 — Implement relation review, dispute, and adjudication

**Objective.** Graph-focused queue and source view for accepting, rejecting, editing, or preserving competing relations and rationales.

| Control | Value |
|---|---|
| Dependencies | `CAP-09.S02.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `graph`, `desktop` |

**Expected deliverables**

- Graph-focused queue and source view for accepting, rejecting, editing, or preserving competing relations and rationales.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-09.S02.T03`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
3. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
4. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
5. Preserve canonical evidence and decisions as authority; update only the versioned derivative projection/candidate relation. Test disputed, stale, cyclic, missing and rebuild cases.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Accepted edge is traceable to reviewers and evidence; dispute prevents silent consensus; relation changes mark dependent analyses stale.
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
python tools/verify.py --profile graph
python tools/verify.py --profile desktop
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
| Candidate proposal | p95 < 500 ms local for indexed ontology <= 100,000 entities excluding optional model ranker. |
| Argument extraction | Throughput target >= 20 pages/min CPU baseline with batching and resume. |
| Review load | Source plus candidates visible < 500 ms from local cache. |
| Merge impact | Preview 100,000 dependent links < 10 s with exact counts. |

Budgets are evaluated on documented reference hardware and corpus fixtures. A regression exceeding 20% or violating a hard interaction/resource limit blocks approval unless a reviewed explanation and revised target are accepted before implementation proceeds.

## 12. Observability and provenance

Required metrics and diagnostics:

- entity-link precision/recall/MRR on gold fixtures
- new/unresolved/merge rates
- argument extraction precision/recall by role
- human correction rate
- ontology-change staleness
- review throughput

- One trace/correlation ID links desktop action, core command, workflow job, adapter/model call, provenance activity and evidence artifact.
- Operational telemetry is content-redacted by default. Durable scholarly provenance records source IDs/passages/hashes, schema/policy/model versions, decisions and derivation—not secret-bearing logs.
- Support bundles require user preview and classification-aware exclusion of source text, research ideas, prompts and unpublished results.
- Every promoted output records dependencies so CAP-03 can mark it stale precisely.

## 13. Adjacent-slice handoffs

- Consumes CAP-08 evidence/ontology packs and CAP-05 anchors.
- Publishes verified/disputed relation assertions to S01 and comparison inputs to S03.
- Provides construct-definition and theory-use lineage to S04 and manuscripts.

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
| Ontology reification | Preserve wording, competing links and local/domain packs. |
| Model confirmation bias | Candidate signals, independent review samples and human merge authority. |
| Cross-domain semantic collision | Namespace/context-aware candidates and no automatic global merge. |

## 19. Required ADRs and human decisions

- ADR-CAP09-LINKING: entity identity, merge/split and relation candidate policy.

All material choices in Sections 4–5 must appear in the capability packet. Before approval, reviewers may accept the recommendation, select a documented alternative, or require more evidence. After capability start, these choices are not reopened for preference; they are reopened only when implementation evidence demonstrates infeasibility or a newly discovered consequential issue outside the approved decision envelope.

## 20. Research and standards basis

- **PROV-O: The PROV Ontology** — Interoperable provenance entities, activities, agents and derivations.  
  https://www.w3.org/TR/prov-o/
- **Web Annotation Data Model** — Multi-selector source anchors and revision-aware annotations.  
  https://www.w3.org/TR/annotation-model/
- **Fact or Fiction: Verifying Scientific Claims** — Scientific claim/evidence verification benchmark and rationale retrieval.  
  https://aclanthology.org/2020.emnlp-main.609/
- **JSON Schema Draft 2020-12** — Canonical structured-output and schema-pack validation.  
  https://json-schema.org/draft/2020-12

These sources support implementation choices, not universal truth claims. Production selection remains conditional on project-specific benchmarks, licenses, privacy/rights constraints and the accepted capability decision packet.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-09 --require-approved` and `python tools/taskctl.py validate`.
2. Confirm the active campaign is `CAP-09`, this is the current slice, and the approved packet/plan commits match the campaign record.
3. Load only the governing context, capability packet, this slice plan, task record, affected code and tests.
4. Execute all tasks in dependency order. Debug, refactor and use approved fallbacks without routine human pauses.
5. After each task, run focused verification, attach criterion-linked evidence and obtain independent task review.
6. After the last task, run the complete Section 10 matrix from a clean/restarted state and assemble the slice evidence bundle.
7. Request independent slice review. On approval, let `taskctl` advance the campaign automatically to the next slice.
8. Pause only with an allowed category from Section 3.4 and exact evidence/next action. Do not self-approve, weaken tests, alter approved UX after implementation, or declare production readiness from narrative evidence.
