---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-03
title: Canonical domain, research intent, provenance, and durable workflows
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-03.S01
- CAP-03.S02
- CAP-03.S03
- CAP-03.S04
- CAP-03.S05
- CAP-03.S06
decisions:
- id: CAP-03-D01
  title: Identifiers
  candidates:
  - UUIDv7-compatible portable IDs with immutable revisions and typed domain contracts
  - Database row IDs exposed across modules
  recommendation: UUIDv7-compatible portable IDs with immutable revisions and typed domain contracts
  recommendation_basis: Stable portable IDs survive project moves and later hosted deployment.
  selected_option: UUIDv7-compatible portable IDs with immutable revisions and typed domain contracts
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-03-D02
  title: Provenance
  candidates:
  - Append-only W3C PROV-aligned ledger plus outbox events and dependency/staleness graph
  - Mutable audit columns only
  recommendation: Append-only W3C PROV-aligned ledger plus outbox events and dependency/staleness graph
  recommendation_basis: The system must reconstruct how evidence, decisions and outputs were produced and invalidated.
  selected_option: Append-only W3C PROV-aligned ledger plus outbox events and dependency/staleness graph
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-03-D03
  title: Workflow
  candidates:
  - Durable local workflow state machine with idempotency, cancellation, checkpoints and human tasks
  - In-memory background promises
  recommendation: Durable local workflow state machine with idempotency, cancellation, checkpoints and human tasks
  recommendation_basis: Long-running scholarly jobs must survive restart and remain inspectable.
  selected_option: Durable local workflow state machine with idempotency, cancellation, checkpoints and human tasks
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-03-D04
  title: Use-case navigation
  candidates:
  - Versioned Research Intent Contract selects one approved workflow profile and adaptive ordered navigation
  - Flat global tool menu only
  recommendation: Versioned Research Intent Contract selects one approved workflow profile and adaptive ordered navigation
  recommendation_basis: Researchers need objective-specific process guidance while retaining access to supporting tools.
  selected_option: Versioned Research Intent Contract selects one approved workflow profile and adaptive ordered navigation
  status: accepted
  required_adr: null
  binding_waves:
  - W1
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-03 — Capability decision and execution plan

> **Wave-scoped decision packet — recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Each decision is classified by the Wave in which it becomes binding. A pre-Wave approval authorizes only the decisions binding in that Wave and that Wave's slice plans at one immutable commit; inherited and future decisions remain nonbinding context.

<div class="visual-flow"><span>Review Wave slices</span><b>→</b><span>Confirm binding decisions</span><b>→</b><span>Approve the Wave</span><b>→</b><span>Run durable Wave campaign</span><b>→</b><span>Wave exit review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-03` — Canonical domain, research intent, provenance, and durable workflows |
| Objective | Define canonical research objects, a versioned research-intent and primary-use-case contract, provenance, adaptive objective-specific workflows, durable jobs, human gates, and controlled recalculation. |
| Execution mode | Capability contribution map; each Wave owns its ordered execution lease |
| Decision status | `COMPLETE` — recommendations selected, accepted, and classified by binding Wave; active-Wave approval remains separate |
| Slice plans | `CAP-03.S01`, `CAP-03.S02`, `CAP-03.S03`, `CAP-03.S04`, `CAP-03.S05`, `CAP-03.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Define canonical research objects, a versioned research-intent and primary-use-case contract, provenance, adaptive objective-specific workflows, durable jobs, human gates, and controlled recalculation.**

Production-ready exit criteria:

- Core aggregates and APIs have stable identifiers, explicit versioning, and tested state machines.
- Every consequential transformation records inputs, policy, software/model/schema versions, output, and human disposition.
- Long-running work is resumable, cancellable, resource-governed, and capable of marking downstream outputs stale.
- Each project has a versioned primary use case that produces an ordered, visible workflow and next-step guidance while preserving access to all tools and prior workflow history.
- Study designs, technical reports/results, manuscript sections, reviewer rounds, and revision actions use the same durable workflow, provenance, staleness, and human-gate model.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-03.S01` | Canonical identifiers and domain contracts | A small stable core model defines records, documents, evidence, decisions, workflows, ontologies, graphs, opportunities, and monitoring events. | `CAP-00.S02.T01`, `CAP-00.S05.T03` |
| `CAP-03.S02` | Research intent contract and mode governance | Every project declares its scholarly purpose, scope, evidence rules, autonomy, and stopping logic before consequential automation. | `CAP-03.S01.T03`, `CAP-01.S01.T02` |
| `CAP-03.S03` | Append-only provenance and audit ledger | The system can reconstruct how every material object and claim was produced and changed. | `CAP-03.S01.T02`, `CAP-02.S02.T01` |
| `CAP-03.S04` | Portable workflow model and local worker fabric | Long-running processes execute as durable, inspectable workflows instead of opaque UI calls. | `CAP-03.S03.T02`, `CAP-02.S02.T03` |
| `CAP-03.S05` | Dependency graph, staleness, and controlled recalculation | Changes to evidence, models, schemas, or decisions identify and safely refresh affected outputs. | `CAP-03.S04.T03` |
| `CAP-03.S06` | Use-case profiles and adaptive guided navigation | A project begins from a scholarly objective and exposes a clear, versioned primary path through the workbench, with visible progress and access to supporting tools. | `CAP-03.S02.T01`, `CAP-00.S06.T04` |

The planning reviewer must test the complete vertical: inputs from previous capabilities, each slice handoff, researcher workflow, durable/provenance behavior, degraded/recovery path and downstream contract. Slice-level optimization may not break the capability-wide path.

## 3. Decision-making protocol

1. Read every slice plan, backlog task, architecture boundary, workflow/page contract and relevant benchmark/source.
2. For each material choice, compare credible candidates using functionality, security, privacy/rights, portability, maintainability, licensing, local resource use, recovery, evaluation quality and downstream compatibility.
3. Present the leading candidates and an explicit recommendation. Avoid asking an open-ended question when evidence supports a best direction.
4. Record the accepted selection, rejected alternatives, evidence and replaceability/migration boundary in this packet and any required ADR.
5. Validate that the selected set is internally compatible and can complete all slices end to end.
6. Resolve all reasonably foreseeable decisions before campaign start. Implementation should not repeatedly interrupt the human for ordinary engineering choices.

## 4. Decision register

| ID | Decision | Recommended selection | Credible alternative | Why recommended / replacement boundary | Basis |
|---|---|---|---|---|---|
| `CAP-03-D01` | **Identifiers** | UUIDv7-compatible portable IDs with immutable revisions and typed domain contracts | Database row IDs exposed across modules | Stable portable IDs survive project moves and later hosted deployment. | [RFC 9562 - Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562.html) |
| `CAP-03-D02` | **Provenance** | Append-only W3C PROV-aligned ledger plus outbox events and dependency/staleness graph | Mutable audit columns only | The system must reconstruct how evidence, decisions and outputs were produced and invalidated. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-03-D03` | **Workflow** | Durable local workflow state machine with idempotency, cancellation, checkpoints and human tasks | In-memory background promises | Long-running scholarly jobs must survive restart and remain inspectable. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-03-D04` | **Use-case navigation** | Versioned Research Intent Contract selects one approved workflow profile and adaptive ordered navigation | Flat global tool menu only | Researchers need objective-specific process guidance while retaining access to supporting tools. | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) |

### Review and approval

The best-in-class recommendation in every row is already selected and accepted. Reviewers may confirm or override it with explicit rationale. The `binding_waves` classification controls authorization: each pre-Wave approval binds only the decisions and slice plans in its exact inventory, while inherited and future decisions remain context.


## 5. Cross-slice architecture contract

- Preserve the authority order: canonical relational/provenance records and human decisions first; indexes, caches, graph projections, model outputs, rankings and generated artifacts remain versioned derivatives unless the Systems Design explicitly states otherwise.
- Stable ports isolate platform, storage, source, parser, model/provider, vector, graph, renderer and deployment adapters.
- Every durable output records source snapshot, schema/policy/model/tool versions, rights/privacy decisions, human decisions and dependency links.
- All long-running jobs are durable, idempotent where appropriate, cancellable, checkpointed, restartable and independently reviewable.
- The campaign remains local/Windows-first for the current waves while producing portable contracts and fixtures needed by CAP-14 macOS/Linux qualification.
- No later capability is implemented early except its documented interface/fixture seam.

## 6. Experience and workflow contract

Relevant approved pages: See the slice plans and capability coverage catalog.

- The project use case determines the primary ordered workflow. Each page shows current stage, prior/next stage, expected output and completion/checkpoint state.
- All tools remain accessible as supporting tools with a clear route back to the primary workflow.
- Intentional changes require the style guide/workflow/page prototype to be updated, validated and human-approved before implementation.
- Accessibility, light/dark parity, offline/partial/error/recovery states and source/provenance inspection are capability exit requirements, not post-release polish.

## 7. Security, privacy, rights and research-integrity decisions

The reviewer must confirm the entire capability’s trust boundaries, data classes, authorization roles, secret/egress rules, rights/license handling, untrusted-content controls, logging/redaction, export behavior, model licenses and human scholarly authority. Where one slice’s output changes another slice’s rights or confidentiality exposure, the stricter policy travels with the object.

## 8. Capability-wide verification strategy

- **Contract:** all portable schemas, negative fixtures and adapter conformance.
- **Integration:** real local components, deterministic provider/source/model fixtures, transaction/outbox/dependency behavior.
- **End to end:** representative workflow across every slice with source inspection and human decision.
- **Recovery:** cancellation, process/application restart, corrupted derivative, migration, rollback/repair and project relocation.
- **Security/rights:** denial, malicious content, prompt injection, path/archive abuse, egress and export filters, redacted diagnostics.
- **Quality/evaluation:** capability-specific gold sets, ablations, calibration/error analysis and independent human samples.
- **Experience:** approved reference, adaptive navigation, keyboard/screen reader/zoom/reflow and light/dark visual checks.
- **Performance:** reference hardware/corpus budgets plus 20% regression threshold.
- **Independent review:** tests must demonstrate semantics, not merely execute code.

## 9. Long-running execution contract

Once approved and started, the agent should execute the whole capability slice by slice. It may make ordinary low-risk implementation choices within the accepted architecture, debug tests, refactor within module boundaries, select documented fallbacks and rerun evaluations without asking for confirmation. Progress is recorded through task/slice evidence and periodic concise updates rather than approval stops.

### Allowed pause classifications

- Implementation evidence demonstrates the approved architecture is infeasible.
- A required external dependency, hardware target or human authority is unavailable.
- A new consequential security, rights, ethics or experience decision was not knowable during planning.
- A governed UI/design change that requires a new approved reference.

Every pause records category, evidence, exact blocked task/slice, attempted alternatives, recommended next action and conditions for resume. Test failures and routine uncertainty are not pause reasons.

## 10. Plan and approval checklist

- [ ] All slice plans exist and pass `slice_plan_check.py` structurally.
- [ ] Every material decision has credible candidates, recommendation and accepted status.
- [ ] Required ADRs and design-reference changes are approved.
- [ ] Capability-wide architecture and end-to-end path are coherent.
- [ ] Fixtures, benchmarks, credentials/licenses, hardware and human authorities are available or approved stubs exist.
- [ ] Security/privacy/rights/research-integrity review is complete.
- [ ] All slice plans are approved at immutable commits.
- [ ] `python tools/planctl.py ready CAP-03 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [RFC 9562 - Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562.html) — Stable sortable UUIDv7 identifiers.
- [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) — Interoperable provenance entities, activities, agents and derivations.
- [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) — AA accessibility target.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
