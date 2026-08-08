---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-02
title: Local projects, durable storage, security, and recovery
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-02.S01
- CAP-02.S02
- CAP-02.S03
- CAP-02.S04
- CAP-02.S05
decisions:
- id: CAP-02-D01
  title: Canonical local store
  candidates:
  - SQLite STRICT tables behind repository ports with versioned migrations and SQLCipher or approved equivalent
  - Plain JSON files; external PostgreSQL for desktop
  recommendation: SQLite STRICT tables behind repository ports with versioned migrations and SQLCipher or approved equivalent
  recommendation_basis: SQLite supports local portability and transactions; protected storage satisfies confidential research requirements.
  selected_option: SQLite STRICT tables behind repository ports with versioned migrations and SQLCipher or approved equivalent
  status: accepted
  required_adr: null
- id: CAP-02-D02
  title: Object storage
  candidates:
  - Encrypted content-addressed project object store with atomic writes and manifest verification
  - Store all binaries directly in relational BLOBs
  recommendation: Encrypted content-addressed project object store with atomic writes and manifest verification
  recommendation_basis: Separates large artifacts while supporting dedupe, integrity, backup and relocation.
  selected_option: Encrypted content-addressed project object store with atomic writes and manifest verification
  status: accepted
  required_adr: null
- id: CAP-02-D03
  title: Secrets and recovery
  candidates:
  - OS credential store, project privacy profiles and tested backup/restore/rekey/recovery
  - Secrets in config files
  recommendation: OS credential store, project privacy profiles and tested backup/restore/rekey/recovery
  recommendation_basis: Credential and recovery behavior must be platform-specific at the adapter boundary and production qualified.
  selected_option: OS credential store, project privacy profiles and tested backup/restore/rekey/recovery
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-02 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-02` — Local projects, durable storage, security, and recovery |
| Objective | Provide safe project lifecycle, local persistence, encrypted content storage, secrets management, and portable recovery for individual and laboratory computers. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-02.S01`, `CAP-02.S02`, `CAP-02.S03`, `CAP-02.S04`, `CAP-02.S05` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Provide safe project lifecycle, local persistence, encrypted content storage, secrets management, and portable recovery for individual and laboratory computers.**

Production-ready exit criteria:

- Projects survive crashes, application upgrades, relocations, and verified backup/restore cycles.
- Sensitive documents and credentials are protected with explicit local threat assumptions.
- A lab can configure approved storage and model-cache locations without converting the product into a server deployment.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-02.S01` | Local project lifecycle and directory contract | Projects have explicit identity, version, location, lifecycle state, and safe-open semantics. | `CAP-00.S01.T03`, `CAP-01.S04.T02` |
| `CAP-02.S02` | SQLite schema, migrations, and repository layer | Canonical local state is transactional, versioned, testable, and insulated from UI or model code. | `CAP-02.S01.T01`, `CAP-03.S01.T01` |
| `CAP-02.S03` | Encrypted local object and cache storage | Documents, page images, snapshots, models, and exports use content-addressed storage with integrity and rights metadata. | `CAP-02.S02.T01` |
| `CAP-02.S04` | Local secrets, profiles, and privacy controls | Credentials and policy-sensitive configuration are isolated from ordinary project content. | `CAP-02.S03.T02` |
| `CAP-02.S05` | Backup, restore, relocation, and lab portability | Researchers can protect and move projects without breaking identities, provenance, or evidence links. | `CAP-02.S04.T03`, `CAP-03.S05.T03` |

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
| `CAP-02-D01` | **Canonical local store** | SQLite STRICT tables behind repository ports with versioned migrations and SQLCipher or approved equivalent | Plain JSON files; external PostgreSQL for desktop | SQLite supports local portability and transactions; protected storage satisfies confidential research requirements. | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) |
| `CAP-02-D02` | **Object storage** | Encrypted content-addressed project object store with atomic writes and manifest verification | Store all binaries directly in relational BLOBs | Separates large artifacts while supporting dedupe, integrity, backup and relocation. | [RFC 8493 - The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) |
| `CAP-02-D03` | **Secrets and recovery** | OS credential store, project privacy profiles and tested backup/restore/rekey/recovery | Secrets in config files | Credential and recovery behavior must be platform-specific at the adapter boundary and production qualified. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |

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
- [ ] `python tools/planctl.py ready CAP-02 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) — Local fielded lexical indexing, BM25 ranking, snippets, rebuild and integrity checks.
- [RFC 8493 - The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) — Checksum-validated payload transfer and archival package layout.
- [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) — Interoperable provenance entities, activities, agents and derivations.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
