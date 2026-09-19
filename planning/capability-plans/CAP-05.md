---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
planning_policy_version: initiation-assessment-2.0
initiation_assessment: null
capability_id: CAP-05
title: Document acquisition, parsing, source inspection, and page anchors
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: reopened
open_blocking_decisions:
- CAP-05-D01
slice_ids:
- CAP-05.S01
- CAP-05.S02
- CAP-05.S03
- CAP-05.S04
- CAP-05.S05
- CAP-05.S06
decisions:
- id: CAP-05-D01
  title: Document preference
  candidates:
  - Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port
  - Native structured intake plus lightweight local PDF text fallback; defer full layout extraction
  recommendation: Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port
  recommendation_basis: ADR-0029 proposes modular Docling 2.126.0 in the ADR-0028 CPU worker; Windows/Python 3.14 wheel resolution succeeded, but exact offline assets/resource profile and viewer feasibility remain pre-approval work.
  selected_option: null
  status: reopened
  required_adr: ADR-0029
  binding_waves: [W2]
- id: CAP-05-D02
  title: Revision/anchor model
  candidates:
  - Immutable document revisions with structural, page-region, text-position and quote selectors
  - Mutable current text with page number only
  recommendation: Immutable document revisions with structural, page-region, text-position and quote selectors
  recommendation_basis: Downstream evidence requires stable, inspectable source context across correction/reparse.
  selected_option: Immutable document revisions with structural, page-region, text-position and quote selectors
  status: accepted
  required_adr: null
  binding_waves: [W2]
- id: CAP-05-D03
  title: Correction
  candidates:
  - Researcher corrections are overlays/new revisions that trigger scoped staleness and reprocessing
  - Edit parsed text in place
  recommendation: Researcher corrections are overlays/new revisions that trigger scoped staleness and reprocessing
  recommendation_basis: Preserves source/parser history and prevents silent mutation of accepted evidence.
  selected_option: Researcher corrections are overlays/new revisions that trigger scoped staleness and reprocessing
  status: accepted
  required_adr: null
  binding_waves: [W2]
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-05 — Capability decision and execution plan

> **W2 planning in progress.** G1's limited transition is approved; this capability
> contribution is not. Resolve local-parser feasibility and complete the initiation
> assessment, estimates and slice refresh before requesting the single W2 approval.
> Retained selected recommendations are planning choices, not execution authority.

<div class="visual-flow"><span>Refresh W2 contributions</span><b>→</b><span>Resolve binding decisions</span><b>→</b><span>Approve complete W2 packet</span><b>→</b><span>Execute W2 campaign</span><b>→</b><span>Qualify G2 exit</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-05` — Document acquisition, parsing, source inspection, and page anchors |
| Objective | Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context. |
| Execution mode | Contribution to the W2 campaign; slices complete in dependency order |
| Decision status | `REOPENED` — pinned local-parser runtime/assets need feasibility and selection |
| Slice plans | `CAP-05.S01`, `CAP-05.S02`, `CAP-05.S03`, `CAP-05.S04`, `CAP-05.S05`, `CAP-05.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.6`; affected slice/page mappings require refresh; preserve inherited catalog bindings |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 0A. Initiation assessment and planning adaptation

Initial assessment: 2026-09-13, W2. See the shared
[W2 initiation assessment](../W2-initiation.md) for baseline evidence, primary
sources, complete contribution inventory, user journey and retained risks.
Structured estimates remain incomplete; `initiation_assessment: null` deliberately
prevents approval-ready claims.

- **Baseline / fit:** reuse immutable revisions, protected object streams,
  durable jobs and selective recalculation. Traceable source inspection remains
  central to the Vision. A parser's output and quality score are not evidence
  acceptance; the researcher retains correction and interpretation authority.
- **Adaptation:** CAP-05-D01 remains open until the local Docling package/runtime,
  offline assets and resource/isolation design are supported. Resolve secure
  viewer range access in CAP-05.S04.T01 without decrypted paths. These are new
  integration needs, not proof that W1 supplies a hostile-content sandbox.
- **Journey:** corpus/work-version → attachment or permitted copy → parse status
  → exact source anchor → correction/impact preview → return to the originating
  selection. Keep missing full text and ambiguous anchors explicit. A reparse
  cannot silently replace an accepted revision.
- **Support / debt:** use the single shared runner-progress proposal; no second
  allocation or new UX framework. No foundational rewrite is selected. Before
  lock, complete eighteen atomic estimates, inherited-risk dispositions and the
  required document/anchor/viewer ADR and reference mappings.

All six slice procedures now use whole-Wave authority. Three reviewed dependency
edges make parser isolation, viewer navigation and reference-rematching handoffs
explicit. ADR-0029 records the bounded package-resolution result separately from
unproven runtime/security behavior; it preserves the viewer and offline-asset
planning gaps rather than claiming the complete packet is ready.

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context.**

Production-ready exit criteria:

- Local files, open-access copies, and structured publisher formats enter through rights-aware acquisition workflows.
- Native XML/HTML is preferred; PDF fallback produces sections, passages, references, and page-coordinate anchors with quality scores.
- Users can inspect every evidence anchor in source context and corrections trigger controlled recalculation.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-05.S01` | Rights-aware document acquisition | Full-text acquisition is explicit, resumable, checksum-verified, and governed by permitted use. | `CAP-04.S04.T02`, `CAP-02.S03.T03` |
| `CAP-05.S02` | Structured and PDF parsing pipeline | A replaceable local parser pipeline produces normalized document structure with retained originals and quality signals. | `CAP-05.S01.T03`, `CAP-03.S04.T02` |
| `CAP-05.S03` | Immutable document revisions and source anchors | Every extracted passage and downstream assertion points to a specific immutable revision and stable location. | `CAP-05.S02.T03`, `CAP-02.S02.T03` |
| `CAP-05.S04` | Source viewer and evidence inspection experience | Researchers can read original pages and structured text side by side, navigate anchors, and inspect provenance without leaving the workflow. | `CAP-05.S03.T03`, `CAP-01.S02.T03` |
| `CAP-05.S05` | References, citation contexts, tables, and figures | Document-internal scholarly structures become inspectable records without losing page context. | `CAP-05.S03.T03` |
| `CAP-05.S06` | Parsing quality, correction, and reprocessing | Parsing errors can be diagnosed and corrected without obscuring machine output or provenance. | `CAP-05.S04.T02`, `CAP-03.S05.T02` |

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
| `CAP-05-D01` | **Document preference — reopened** | Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port | Native structured intake plus lightweight local PDF text fallback; defer full layout extraction | Retain the planned Docling outcome; prove Windows packaging, offline assets and limits before selection. A reduced-layout alternative changes proposed scope. | [Current parser assessment](../W2-initiation.md#current-primary-source-refresh) |
| `CAP-05-D02` | **Revision/anchor model** | Immutable document revisions with structural, page-region, text-position and quote selectors | Mutable current text with page number only | Downstream evidence requires stable, inspectable source context across correction/reparse. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-05-D03` | **Correction** | Researcher corrections are overlays/new revisions that trigger scoped staleness and reprocessing | Edit parsed text in place | Preserves source/parser history and prevents silent mutation of accepted evidence. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |

### Review and approval

All seven decisions across CAP-04/CAP-05 bind W2. Resolve the reopened parser
decision and keep retained selections reviewable. Approval covers the complete
Wave and every contributing slice at one immutable commit, not this capability
in isolation. The G1 decision is not W2 packet approval.


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
- [ ] Required ADRs and design-reference changes are approved.
- [ ] Capability-wide architecture and end-to-end path are coherent.
- [ ] Fixtures, benchmarks, credentials/licenses, hardware and human authorities are available or approved stubs exist.
- [ ] Security/privacy/rights/research-integrity review is complete.
- [ ] Initiation-assessment 2.0 and all W2 atomic estimates are complete; shared allocations are counted once.
- [ ] All W2 slice plans are approved at the same immutable Wave packet commit.
- [ ] `python tools/planctl.py --repo . wave ready W2 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) — Multi-selector source anchors and revision-aware annotations.
- [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) — Interoperable provenance entities, activities, agents and derivations.

## 12. Approval record

The contribution remains **proposed**, with a W2-binding decision reopened.
Complete its assessment, estimates, selections and required ADR/reference work;
then validate and independently review the entire W2 packet before requesting
the owner's one immutable pre-Wave approval. No capability-only approval or
blanket inheritance of the G1 exception is authorized.
