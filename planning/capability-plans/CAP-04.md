---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
planning_policy_version: initiation-assessment-2.0
initiation_assessment:
  policy_version: '2.0'
  assessed_at: '2026-09-19'
  estimation_unit: engineering-hour
  implementation_baseline: W1 Core identity, protected objects, provenance and durable jobs at eaa3f93c; G1 qualification limitations retained.
  vision_architecture_best_practice_fit: Preserve source disagreement and rights; reuse Core authority; ADR-0027 separates private authentication from replay and ADR-0028 supplies real connector isolation. See planning/W2-initiation.md.
  planned_items:
  - {work_id: CAP-04.S01.T01, effort: 18}
  - {work_id: CAP-04.S01.T02, effort: 14}
  - {work_id: CAP-04.S01.T03, effort: 16}
  - {work_id: CAP-04.S02.T01, effort: 12}
  - {work_id: CAP-04.S02.T02, effort: 18}
  - {work_id: CAP-04.S02.T03, effort: 18}
  - {work_id: CAP-04.S03.T01, effort: 16}
  - {work_id: CAP-04.S03.T02, effort: 20}
  - {work_id: CAP-04.S03.T03, effort: 12}
  - {work_id: CAP-04.S04.T01, effort: 12}
  - {work_id: CAP-04.S04.T02, effort: 12}
  - {work_id: CAP-04.S04.T03, effort: 12}
  - {work_id: CAP-04.S05.T01, effort: 16}
  - {work_id: CAP-04.S05.T02, effort: 28}
  - {work_id: CAP-04.S05.T03, effort: 12}
  refactoring_items:
  - id: W2-RUNNER-PROGRESS
    work_id: CAP-04.S01.T01
    effort: 2
    introduced_in_wave: W2
    changes_existing_implementation: true
    major_refactor: false
    disposition: included
    description: Explicit mixed-task support allocation for live output in the existing verifier; included in 18 hours, not additional. Preserve results/fail-stop/diagnostics. At the ceiling, record deferral without partial runner changes; do not delay the product path.
  major_refactor_disposition: No foundational refactor selected. New connectors/LPAC are product scope; broader harness and historical-fixture redesign deferred to future mutable planning.
  wave_refreshes:
  - wave: W2
    assessed_at: '2026-09-19'
    material_changes: W1 boundaries now exist; G1 retains explicit prototype qualification gaps; SDK trust needs a small governed Source Manager reference addition.
    plan_adaptations: One Wave campaign, source identities before reconciliation, four source-specific adapters, broker-only plugin access; preserve inherited workflow catalog 1.5.
    support_improvements: Count W2-RUNNER-PROGRESS once in CAP-04.S01.T01; narrow scanner diagnostics only where new trust-boundary proof depends on them.
    major_refactor_disposition: No major refactor or controller expansion; ordinary product integration only.
capability_id: CAP-04
title: Scholarly ingestion, connectors, canonicalization, and corpus governance
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-04.S01
- CAP-04.S02
- CAP-04.S03
- CAP-04.S04
- CAP-04.S05
decisions:
- id: CAP-04-D01
  title: Open scholarly sources
  candidates:
  - OpenAlex, Crossref, Semantic Scholar and Unpaywall behind capability-described adapters with replay fixtures
  - Local imports with DOI lookup only; defer broad multi-provider discovery
  recommendation: OpenAlex, Crossref, Semantic Scholar and Unpaywall behind capability-described adapters with replay fixtures
  recommendation_basis: Accepted ADR-0027 selects provider-specific private configuration and protected scientific replay without authentication/contact values; W2 execution approval remains pending.
  selected_option: OpenAlex, Crossref, Semantic Scholar and Unpaywall behind capability-described adapters with replay fixtures
  status: accepted
  required_adr: ADR-0027
  binding_waves: [W2]
- id: CAP-04-D02
  title: Canonicalization
  candidates:
  - Canonical work/version/source records with deterministic reconciliation candidates and human ambiguity review
  - Deterministic latest-source canonical projection with immutable assertions, visible conflicts and reversible human overrides
  recommendation: Canonical work/version/source records with deterministic reconciliation candidates and human ambiguity review
  recommendation_basis: Source disagreement and version relationships must remain visible and reversible.
  selected_option: Canonical work/version/source records with deterministic reconciliation candidates and human ambiguity review
  status: accepted
  required_adr: null
  binding_waves: [W2]
- id: CAP-04-D03
  title: Rights/provenance
  candidates:
  - Every import records discovery path, source terms, access status, license/rights and retrieval time
  - Minimal normalized records linked to protected provenance and action-specific rights sidecars
  recommendation: Every import records discovery path, source terms, access status, license/rights and retrieval time
  recommendation_basis: Rights and provenance are required for later text, model and export decisions.
  selected_option: Every import records discovery path, source terms, access status, license/rights and retrieval time
  status: accepted
  required_adr: null
  binding_waves: [W2]
- id: CAP-04-D04
  title: Extensibility
  candidates:
  - Allowlisted connector SDK with sandboxed/bounded execution and contract fixtures
  - First-party built-in connectors only; defer third-party execution and SDK delivery
  recommendation: Allowlisted connector SDK with sandboxed/bounded execution and contract fixtures
  recommendation_basis: Accepted ADR-0028 selects LPAC, no direct network or project/vault access, narrow brokers and explicit local publisher/project trust; real packaged isolation remains an implementation qualification obligation.
  selected_option: Allowlisted connector SDK with sandboxed/bounded execution and contract fixtures
  status: accepted
  required_adr: ADR-0028
  binding_waves: [W2]
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-04 — Capability decision and execution plan

> **W2 planning in progress.** G1's limited transition is approved; this capability
> contribution is not. All four recommendations are selected for the proposed packet;
> ADR-0027/0028 and reference 1.7 have explicit owner approval. Final rebound-packet
> review and complete W2 execution approval remain; no task is authorized yet.

<div class="visual-flow"><span>Refresh W2 contributions</span><b>→</b><span>Resolve binding decisions</span><b>→</b><span>Approve complete W2 packet</span><b>→</b><span>Execute W2 campaign</span><b>→</b><span>Qualify G2 exit</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-04` — Scholarly ingestion, connectors, canonicalization, and corpus governance |
| Objective | Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths. |
| Execution mode | Contribution to the W2 campaign; slices complete in dependency order |
| Decision status | `COMPLETE` planning selections; architecture/reference approved, complete W2 approval pending |
| Slice plans | `CAP-04.S01`, `CAP-04.S02`, `CAP-04.S03`, `CAP-04.S04`, `CAP-04.S05` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.7`; W2 slice/page mappings rebound; inherited catalog bindings preserved |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 0A. Initiation assessment and planning adaptation

Initial assessment: 2026-09-13, W2. See the shared
[W2 initiation assessment](../W2-initiation.md) for the complete contribution
inventory, current primary sources, cross-capability journey, carry-forward risks
and one bounded automation proposal. Structured estimates above cover all fifteen
atomic tasks; [estimate basis](../W2-initiation.md#estimate-basis-and-shared-accounting)
distinguishes engineering effort from elapsed agent time. Architecture/reference
review and owner acceptance are recorded; final packet review remains required.

- **Baseline / fit:** reuse W1 Core-owned revisions, protected object streams,
  provenance and durable jobs. The corpus-first outcome still fits the Vision;
  imports/connectors must consume these boundaries, not recreate them.
- **Adaptation:** keep local imports usable without provider credentials. Resolve
  source-specific configuration and redacted request replay in CAP-04-D01;
  resolve actual least-privilege connector execution in CAP-04-D04. An ordinary
  worker process is not a sandbox. The alternative to the SDK would reduce
  proposed W2 scope and is not silently selected.
- **Journey:** project → import picker/preview → review conflicts → commit →
  corpus/manifest → document acquisition. Preserve source, project and selection
  context; failed/cancelled preview must not commit partial canonical records.
- **Support / debt:** one shared runner-progress increment is proposed in the
  linked assessment, counted once, not per capability. No foundational rewrite
  or broad historical-fixture repair is selected. The explicitly mixed first task
  includes 2 support hours within its 18-hour estimate, with focused independent
  control review. No other capability counts that allocation.

The current increment has refreshed all five slice procedures and accepted ADR-0027
and ADR-0028. Source records/manifest IDs precede work/version reconciliation;
the CAP-04.S01 handoff now states that explicitly. The [owner design approval](../../artifacts/evidence/W2.design-architecture-owner-approval-01.md)
binds these decisions and reference 1.7; it grants no task completion or execution.

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths.**

Production-ready exit criteria:

- Common reference formats and open scholarly sources import through idempotent, rate-aware adapters.
- Works, versions, authors, identifiers, corrections, retractions, and duplicates reconcile without losing source-specific metadata.
- Every corpus item records how it was discovered, what rights apply, and why it is included or excluded.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-04.S01` | Reference-library and file imports | Researchers can import existing bibliographies with preview, mapping, validation, and repeatable merge behavior. | `CAP-03.S03.T02`, `CAP-02.S02.T03` |
| `CAP-04.S02` | Open scholarly source adapters | OpenAlex, Crossref, Unpaywall, and Semantic Scholar are available behind stable, observable connector contracts. | `CAP-04.S01.T01`, `CAP-07.S01.T01` |
| `CAP-04.S03` | Canonical work, version, and identity reconciliation | Multiple provider records resolve to inspectable canonical scholarly entities without flattening uncertainty. | `CAP-04.S01.T03`, `CAP-04.S02.T03` |
| `CAP-04.S04` | Corpus membership, discovery path, and rights governance | Corpus state is a deliberate scholarly decision with complete acquisition and inclusion provenance. | `CAP-04.S03.T03`, `CAP-03.S02.T03` |
| `CAP-04.S05` | Connector SDK and controlled extensibility | New data sources can be added without bypassing provenance, rights, security, or canonicalization. | `CAP-04.S04.T03`, `CAP-00.S03.T03` |

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
| `CAP-04-D01` | **Open scholarly sources — selected** | OpenAlex, Crossref, Semantic Scholar and Unpaywall behind capability-described adapters with replay fixtures | Local imports with DOI lookup only; defer broad multi-provider discovery | Retain source coverage; resolve provider configuration, terms, limits and secret-free replay before selection. | [Current source assessment](../W2-initiation.md#current-primary-source-refresh) |
| `CAP-04-D02` | **Canonicalization** | Canonical work/version/source records with deterministic reconciliation candidates and human ambiguity review | Deterministic latest-source canonical projection with immutable assertions, visible conflicts and reversible human overrides | Both preserve evidence; explicit work/version reconciliation makes uncertainty and edition relationships first-class, whereas a latest-source projection is simpler but more sensitive to retrieval order and needs additional conflict inspection. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-04-D03` | **Rights/provenance** | Every import records discovery path, source terms, access status, license/rights and retrieval time | Minimal normalized records linked to protected provenance and action-specific rights sidecars | Both retain rights/provenance; the selected explicit import contract reduces missing-link and stale-sidecar risks for downstream text/model/export actions, at the cost of richer import records. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-04-D04` | **Extensibility — selected** | Allowlisted connector SDK with sandboxed/bounded execution and contract fixtures | First-party built-in connectors only; defer third-party execution and SDK delivery | Retain the SDK outcome; choose and prove the Windows isolation/credential boundary, not merely a child process. | Systems Design section 16.4; CAP-04.S05 |

### Review and approval

All seven decisions across CAP-04/CAP-05 bind W2. Selected recommendations and
their alternatives remain reviewable; the three shared ADRs are accepted. W2 approval
covers the complete Wave and every contributing slice at one immutable commit,
not this capability in isolation. The G1 decision is not W2 packet approval.


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

After complete W2 approval, execute this contribution through the same Wave
campaign and dependency-eligible taskctl claims. Ordinary implementation and
debugging stay within the approved contract. Select risk-appropriate checks;
supplemental refactoring uses W2's single locked budget. Capability completion
does not create a separate lease, approval or release gate.

### Allowed pause classifications

- Implementation evidence demonstrates the approved architecture is infeasible.
- A required external dependency, hardware target or human authority is unavailable.
- A new consequential security, rights, ethics or experience decision was not knowable during planning.
- A governed UI/design change that requires a new approved reference.

Every pause records category, evidence, exact blocked task/slice, attempted alternatives, recommended next action and conditions for resume. Test failures and routine uncertainty are not pause reasons.

## 10. Plan and approval checklist

- [ ] All slice plans exist and pass `slice_plan_check.py` structurally.
- [ ] Every material decision has credible candidates, recommendation and accepted status.
- [x] Required ADRs and design-reference changes are approved.
- [ ] Capability-wide architecture and end-to-end path are coherent.
- [ ] Fixtures, benchmarks, credentials/licenses, hardware and human authorities are available or approved stubs exist.
- [ ] Security/privacy/rights/research-integrity review is complete.
- [ ] Initiation-assessment 2.0 and all W2 atomic estimates are complete; shared allocations are counted once.
- [ ] All W2 slice plans are approved at the same immutable Wave packet commit.
- [ ] `python tools/planctl.py --repo . wave ready W2 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [OpenAlex API Documentation](https://docs.openalex.org/) — Scholarly metadata, citations, cursor paging and source monitoring.
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) — DOI metadata, updates, licenses and cursor-based retrieval.
- [Semantic Scholar Academic Graph API](https://www.semanticscholar.org/product/api) — Citation graph, recommendations and paper metadata.
- [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) — Search-strategy and information-source reporting.

## 12. Approval record

The contribution remains **proposed**, with all W2 planning selections recorded.
Architecture/reference acceptance is recorded separately; validate and
independently review the final rebound W2 packet before requesting
the owner's one immutable pre-Wave approval. No capability-only approval or
blanket inheritance of the G1 exception is authorized.
