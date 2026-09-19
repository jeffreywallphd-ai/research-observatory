---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-04
capability_plan: planning/capability-plans/CAP-04.md
planning_gate: capability-decision-complete
slice_id: CAP-04.S02
title: Open scholarly source adapters
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
- CAP-04.S02.T01
- CAP-04.S02.T02
- CAP-04.S02.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.7
approval:
  status: approved
  approved_by: human:repository-owner
  approved_at: '2026-09-19T16:55:50.446422+00:00'
  approved_commit: c85a59f3a293f8e3f2eaf6454682c9a14b1efa55
---
# CAP-04.S02 - Open scholarly source adapters
> **Implementation gate — proposed W2 contribution.** Implementation requires the complete W2 packet approved at one immutable commit, its binding ADR/reference decisions resolved, and `python tools/planctl.py --repo . wave ready W2 --require-approved` passing. Then use the same W2 campaign and dependency-eligible taskctl claims; no capability-only approval or lease.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-04` - Scholarly ingestion, connectors, canonicalization, and corpus governance |
| Capability objective | Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths. |
| Slice | `CAP-04.S02` - Open scholarly source adapters |
| Slice outcome | OpenAlex, Crossref, Unpaywall, and Semantic Scholar are available behind stable, observable connector contracts. |
| Wave / priority | `W2` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-04.S02.T01`, `CAP-04.S02.T02`, `CAP-04.S02.T03` |
| Slice dependencies | `CAP-04.S01.T01`, `CAP-07.S01.T01` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.7` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Provide reproducible, respectful, and replaceable access to major open scholarly metadata sources without making any one provider authoritative.

This slice contributes to the capability objective: **Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths.** It must preserve the capability exit conditions:

- Common reference formats and open scholarly sources import through idempotent, rate-aware adapters.
- Works, versions, authors, identifiers, corrections, retractions, and duplicates reconcile without losing source-specific metadata.
- Every corpus item records how it was discovered, what rights apply, and why it is included or excluded.

**Implementation thesis.** Define one connector contract with normalized requests/results, cursor checkpoints, raw response retention, rate-limit state, and provenance. Implement source-specific adapters with polite identification, caching, conditional requests, bounded retries, and recorded query semantics.

## 2. Scope

### 2.1 In scope
- Provider-neutral interfaces for search, lookup, citation traversal, recommendations, OA resolution, retries, cache, and raw-response retention policy.
- Fielded search, identifier lookup, pagination, work/author/source metadata, references where available, rate handling, and response caching.
- Open-access location resolution, academic graph lookup, citations/references, and related-paper recommendations with policy controls.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-04.S01.T01`, `CAP-07.S01.T01`.
- **Produces:** OpenAlex, Crossref, Unpaywall, and Semantic Scholar are available behind stable, observable connector contracts.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `AGENTS.md` and the conditional routes in `planning/README.md`; historical bootstrap documents do not govern current execution.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-04.S02` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 9-10, 15-17, 18-19
- Vision corpus, provenance, rights, and reflexivity requirements
- Connector/source constraints and UI reference

### 3.2 Required upstream state
- `CAP-04.S01.T01` is complete or explicitly gated.
- `CAP-07.S01.T01` is complete or explicitly gated.

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

1. **Adapters return source records plus raw response reference and do not directly create canonical works.**
2. **Retain a protected scientific request/response record, source version, retrieval time and cursor; never retain credential/contact-bearing wire URLs. ADR-0027 separates replay from current broker-injected authentication and covers echoed-value redaction.**
3. **Use source-specific rate-limit controllers, exponential backoff with jitter, Retry-After handling, and circuit breakers.**
4. **Use provider-specific local private configuration. Application use remains account-optional; endpoints that require a key/contact show not-configured explicitly. Only the broker injects those values after policy authorization.**
5. **Use ETag/Last-Modified where available and local response caching consistent with provider terms.**
6. **Record partial-page and resume semantics; never silently restart a large query and merge duplicates without provenance.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `services/core-api/src/research_observatory_core/ingestion/`, `connectors/`, `reconciliation/`, and `corpus/`.
- `packages/contracts/connectors/`, `imports/`, `scholarly-records/`, and `rights/`.
- `apps/desktop/src/workspaces/source-manager/`, `ingestion/`, and `corpus/`.
- `plugins/connectors/` and `tools/connector-conformance/` for the controlled SDK.
- `tests/fixtures/scholarly-metadata/`, `tests/connectors/`, `tests/reconciliation/`, and `tests/rights/`.

**Slice-specific components**
- Connector request/result/cursor/error/rate-limit/provenance contracts.
- Shared HTTP client with destination allowlist, timeout, retry, cache, redaction, and trace instrumentation.
- OpenAlex and Crossref adapters.
- Unpaywall and Semantic Scholar adapters.
- Recorded response fixtures and live qualification tests separated from deterministic PR tests.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `ConnectorRequest`
- `ConnectorResultPage`
- `ConnectorCursor`
- `SourceRecord`
- `RateLimitState`
- `ConnectorError`
- `SourceResponseManifest`

**Required invariants**
- Every durable identity and revision reuses the implemented CAP-03 canonical contracts under ADR-0013/ADR-0024; do not create a parallel identity store.
- Consequential state changes are atomic with existing required provenance/outbox/dependency facts; reuse W1 repository transactions and ADR-0025 durable jobs.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- ConnectorResult includes records, next cursor/checkpoint, warnings, source coverage metadata, rate state, raw-response object reference, and request provenance.
- Errors classify authentication, rate limit, provider unavailable, invalid query, incompatible response, policy denial, and cancellation.
- Source records preserve source IDs and source-specific fields under a namespaced extension area.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
Current visual/page authority is 1.7. Preserve ADR-0026's exact inherited 1.5 workflow-catalog binding; mapping this slice does not relabel existing selections. See [W2 journey and mappings](../../W2-initiation.md#ux-journey-to-refine-in-the-existing-contracts).

- Search/source settings show provider status, coverage, credentials state, rate limits, last successful call, and terms/policy link.
- Degraded providers are visibly excluded from a search run rather than silently treated as zero results.
- Researchers can inspect which source/query discovered each result.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.7`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Allowlist base URLs and redirect destinations; block private/link-local/loopback address resolution for remote adapters.
- Scope provider keys per connector and redact headers/query secrets.
- Limit response size, content type, decompression ratio, and parsing time.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Test 429/Retry-After, 5xx, timeout, connection reset, invalid JSON, missing fields, schema drift, cursor expiry, duplicate page, and cancellation.
- Persist cursor and raw page before advancing the checkpoint.
- Circuit breaker recovery is observable and does not permanently suppress a provider.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-04.S02.T01` - Define connector request, result, cursor, rate-limit, and provenance contracts
**Objective:** Provider-neutral interfaces for search, lookup, citation traversal, recommendations, OA resolution, retries, cache, and raw-response retention policy.

**Dependencies:** `CAP-04.S01.T01`, `CAP-07.S01.T01`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `service`

**Expected deliverables**
- Provider-neutral interfaces for search, lookup, citation traversal, recommendations, OA resolution, retries, cache, and raw-response retention policy.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S02.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Author the versioned schema/interface/state-machine definitions first, including unknown/not-applicable states, compatibility metadata, validation rules, and negative fixtures. Keep framework and persistence types outside the portable contract.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Adapters can be mocked; all results include provider, query, retrieval time, raw identifier, license/terms metadata, and normalized error categories.
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
python tools/verify.py --profile service
```

### 9.2 `CAP-04.S02.T02` - Implement OpenAlex and Crossref adapters
**Objective:** Fielded search, identifier lookup, pagination, work/author/source metadata, references where available, rate handling, and response caching.

**Dependencies:** `CAP-04.S02.T01`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `service`, `search`

**Expected deliverables**
- Fielded search, identifier lookup, pagination, work/author/source metadata, references where available, rate handling, and response caching.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S02.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
4. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Known-item fixtures resolve to canonical candidates; pagination resumes after failure; rate limits are obeyed; raw responses can be replayed in tests.
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
python tools/verify.py --profile service
python tools/verify.py --profile search
```

### 9.3 `CAP-04.S02.T03` - Implement Unpaywall and Semantic Scholar adapters
**Objective:** Open-access location resolution, academic graph lookup, citations/references, and related-paper recommendations with policy controls.

**Dependencies:** `CAP-04.S02.T02`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `service`, `search`

**Expected deliverables**
- Open-access location resolution, academic graph lookup, citations/references, and related-paper recommendations with policy controls.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S02.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
4. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- OA URLs retain license and host metadata; recommendation/citation results record direction and source; provider unavailability degrades without corrupting the search run.
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
python tools/verify.py --profile service
python tools/verify.py --profile search
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `search`, `service` |
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
python tools/verify.py --profile search
python tools/verify.py --profile service
```

## 11. Performance and resource budgets
- Batch identifiers and select only required fields where APIs support it.
- Respect provider limits over raw throughput; expose estimated search duration.
- Cache identical request pages within declared freshness policy.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Per provider: requests, latency, response size, status/error class, retries, rate state, cache hit, schema warning, and cursor progress.
- Keep raw response payloads protected and out of general logs.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- CAP-04.S03 reconciles source records.
- CAP-04.S04 consumes query/discovery provenance and rights fields.
- CAP-05.S01 uses Unpaywall/OA candidates only after rights/acquisition policy.
- CAP-10 search composes providers through these adapters.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- Adapter version and source API version are recorded per result; response mapping changes create new source-record revisions.
- Contract compatibility allows optional new source fields without changing canonicalization semantics.

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
- The promised outcome is demonstrable end to end: OpenAlex, Crossref, Unpaywall, and Semantic Scholar are available behind stable, observable connector contracts.
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
Shared accepted records: [ADR-0027](../../../docs/adr/ADR-0027-keep-scholarly-source-replay-separate-from-private-authentication.md).
The following details belong in that shared packet; they do not each require a new ADR or human approval. Any unresolved material detail still prevents W2 packet approval.

- Binding detail: Shared connector HTTP/cache/rate-control implementation.
- Binding detail: Raw response retention and provider-terms policy.
- Binding detail: Live qualification cadence and fixture recording.

Resolve these material topics through the shared W2 ADR set before packet approval; routine implementation details need no separate ADR. New ADRs remain Proposed until accepted. Do not defer a foreseeable binding architecture choice to implementation or treat a safely stubbed test as real-boundary qualification.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `OPENALEX` | [OpenAlex API Documentation](https://docs.openalex.org/) - OpenAlex | Open scholarly graph metadata. |
| `CROSSREF` | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) - Crossref | DOI metadata, licenses, updates, ORCID and ROR fields. |
| `UNPAYWALL` | [Unpaywall REST API](https://unpaywall.org/products/api) - Unpaywall | Open-access status and lawful locations. |
| `SEMANTIC_SCHOLAR` | [Semantic Scholar Academic Graph API](https://www.semanticscholar.org/product/api) - Allen Institute for AI | Scholarly graph, recommendations, and citations. |
| `OWASP_SSRF` | [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) - OWASP | Safe network acquisition. |
| `OPENTELEMETRY` | [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) - OpenTelemetry | Trace/span correlation. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Resume the same approved W2 campaign through taskctl. Use full task designators, risk-selected verification, independent dispositions and local integration. Continue through eligible slices/checkpoints to fresh Wave qualification and the separate G2 human exit gate.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm W2 is the approved active campaign and `CAP-04.S02` is dependency-eligible.
3. Claim only the next READY task in `CAP-04.S02` through taskctl; do not bypass Wave dependencies or create a capability lease.
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
