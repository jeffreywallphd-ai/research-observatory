---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-01
title: Windows-first desktop shell and supervised local runtime
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-01.S01
- CAP-01.S02
- CAP-01.S03
- CAP-01.S04
- CAP-01.S05
decisions:
- id: CAP-01-D01
  title: Desktop shell
  candidates:
  - Tauri 2 with React/TypeScript, Rust command boundary and shared Academic Minimal tokens
  - Electron; browser-only shell
  recommendation: Tauri 2 with React/TypeScript, Rust command boundary and shared Academic Minimal tokens
  recommendation_basis: Meets the Windows-first local desktop design while preserving later macOS/Linux builds.
  selected_option: Tauri 2 with React/TypeScript, Rust command boundary and shared Academic Minimal tokens
  status: accepted
  required_adr: null
- id: CAP-01-D02
  title: Local service
  candidates:
  - Signed/versioned Python FastAPI sidecar supervised by Tauri with authenticated loopback contract
  - Bundle Python logic into UI process; require Docker
  recommendation: Signed/versioned Python FastAPI sidecar supervised by Tauri with authenticated loopback contract
  recommendation_basis: Separates scientific Python workloads while retaining an installable desktop product.
  selected_option: Signed/versioned Python FastAPI sidecar supervised by Tauri with authenticated loopback contract
  status: accepted
  required_adr: null
- id: CAP-01-D03
  title: Installer/update
  candidates:
  - Windows NSIS/MSI qualification with signed artifacts, stable/beta channels and rollback evidence
  - Portable ZIP only
  recommendation: Windows NSIS/MSI qualification with signed artifacts, stable/beta channels and rollback evidence
  recommendation_basis: Production readiness requires install, upgrade, repair and rollback, not only development startup.
  selected_option: Windows NSIS/MSI qualification with signed artifacts, stable/beta channels and rollback evidence
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-01 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-01` — Windows-first desktop shell and supervised local runtime |
| Objective | Deliver the canonical Windows-first desktop experience and a reliably packaged local analytical service that requires no external server administration. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-01.S01`, `CAP-01.S02`, `CAP-01.S03`, `CAP-01.S04`, `CAP-01.S05` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Deliver the canonical Windows-first desktop experience and a reliably packaged local analytical service that requires no external server administration.**

Production-ready exit criteria:

- The signed-development desktop application installs, launches, navigates, and supervises its compatible sidecar.
- Desktop-to-service communication is authenticated, versioned, observable, and recoverable.
- The same client architecture and project contracts are portable to macOS/Linux in CAP-14 and later connect to university/cloud profiles without forking the UI.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-01.S01` | Tauri and React application shell | A production-shaped desktop shell provides navigation, project selection, commands, and application state. | `CAP-00.S01.T03`, `CAP-00.S03.T02` |
| `CAP-01.S02` | Desktop design system and accessibility foundation | Reusable components express status, provenance, evidence, uncertainty, and human decision states consistently. | `CAP-01.S01.T01` |
| `CAP-01.S03` | Packaged Python/FastAPI sidecar | The desktop bundles and supervises a compatible local service with no user-managed Python installation. | `CAP-00.S03.T02`, `CAP-01.S01.T01` |
| `CAP-01.S04` | Authenticated desktop-service contract | Local IPC is private, versioned, cancellable, and observable. | `CAP-01.S03.T03` |
| `CAP-01.S05` | Windows installation and update channels | The PC/lab application can be installed, upgraded, repaired, and removed predictably by individuals or lab administrators. | `CAP-01.S04.T03`, `CAP-00.S05.T03` |

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
| `CAP-01-D01` | **Desktop shell** | Tauri 2 with React/TypeScript, Rust command boundary and shared Academic Minimal tokens | Electron; browser-only shell | Meets the Windows-first local desktop design while preserving later macOS/Linux builds. | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) |
| `CAP-01-D02` | **Local service** | Signed/versioned Python FastAPI sidecar supervised by Tauri with authenticated loopback contract | Bundle Python logic into UI process; require Docker | Separates scientific Python workloads while retaining an installable desktop product. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-01-D03` | **Installer/update** | Windows NSIS/MSI qualification with signed artifacts, stable/beta channels and rollback evidence | Portable ZIP only | Production readiness requires install, upgrade, repair and rollback, not only development startup. | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) |

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
- [ ] `python tools/planctl.py ready CAP-01 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) — AA accessibility target.
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) — Canonical structured-output and schema-pack validation.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
