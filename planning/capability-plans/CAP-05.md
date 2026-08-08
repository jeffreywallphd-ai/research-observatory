---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-05
title: Document acquisition, parsing, source inspection, and page anchors
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
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
  - OCR every document; rely only on remote parsing
  recommendation: Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port
  recommendation_basis: Native structure is higher fidelity; local PDF fallback preserves privacy and offline operation.
  selected_option: Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port
  status: accepted
  required_adr: null
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
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-05 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-05` — Document acquisition, parsing, source inspection, and page anchors |
| Objective | Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-05.S01`, `CAP-05.S02`, `CAP-05.S03`, `CAP-05.S04`, `CAP-05.S05`, `CAP-05.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

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
| `CAP-05-D01` | **Document preference** | Prefer native JATS/TEI/XML/HTML; use pinned Docling-style local PDF parsing and retain replaceable parser port | OCR every document; rely only on remote parsing | Native structure is higher fidelity; local PDF fallback preserves privacy and offline operation. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-05-D02` | **Revision/anchor model** | Immutable document revisions with structural, page-region, text-position and quote selectors | Mutable current text with page number only | Downstream evidence requires stable, inspectable source context across correction/reparse. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-05-D03` | **Correction** | Researcher corrections are overlays/new revisions that trigger scoped staleness and reprocessing | Edit parsed text in place | Preserves source/parser history and prevents silent mutation of accepted evidence. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |

### Review and approval

The best-in-class recommendation in every row is already the selected, accepted decision. Reviewers may confirm the complete set without editing individual choices, or replace a recommendation with another documented candidate and record an explicit rationale. The only remaining routine human gate is approval of this capability packet and all slice plans at one immutable commit.


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
- [ ] `python tools/planctl.py ready CAP-05 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) — Multi-selector source anchors and revision-aware annotations.
- [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) — Interoperable provenance entities, activities, agents and derivations.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
