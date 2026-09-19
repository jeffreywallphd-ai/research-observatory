---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-04
capability_plan: planning/capability-plans/CAP-04.md
planning_gate: capability-decision-complete
slice_id: CAP-04.S05
title: Connector SDK and controlled extensibility
status: proposed
wave: W2
priority: P1
deployment_profiles:
- LOC
- LAB
- UNI
- CLD
platform_targets:
- windows-x64
task_ids:
- CAP-04.S05.T01
- CAP-04.S05.T02
- CAP-04.S05.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.6
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-04.S05 - Connector SDK and controlled extensibility
> **Implementation gate — proposed W2 contribution.** Implementation requires the complete W2 packet approved at one immutable commit, its binding ADR/reference decisions resolved, and `python tools/planctl.py --repo . wave ready W2 --require-approved` passing. Then use the same W2 campaign and dependency-eligible taskctl claims; no capability-only approval or lease.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-04` - Scholarly ingestion, connectors, canonicalization, and corpus governance |
| Capability objective | Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths. |
| Slice | `CAP-04.S05` - Connector SDK and controlled extensibility |
| Slice outcome | New data sources can be added without bypassing provenance, rights, security, or canonicalization. |
| Wave / priority | `W2` / `P1` |
| Deployment profiles | `LOC`, `LAB`, `UNI`, `CLD` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-04.S05.T01`, `CAP-04.S05.T02`, `CAP-04.S05.T03` |
| Slice dependencies | `CAP-04.S04.T03`, `CAP-00.S03.T03` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.6` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Permit laboratories and institutions to extend scholarly sources without weakening the desktop security boundary, provenance, rights controls, or compatibility.

This slice contributes to the capability objective: **Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths.** It must preserve the capability exit conditions:

- Common reference formats and open scholarly sources import through idempotent, rate-aware adapters.
- Works, versions, authors, identifiers, corrections, retractions, and duplicates reconcile without losing source-specific metadata.
- Every corpus item records how it was discovered, what rights apply, and why it is included or excluded.

**Implementation thesis.** Publish a narrow versioned connector manifest/API and run third-party connectors out of process with declared capabilities, allowlisted destinations, scoped secrets, quotas, timeouts, signed packages, and a conformance suite.

## 2. Scope

### 2.1 In scope
- Versioned manifest for source identity, operations, authentication, terms, rate limits, data classes, and required permissions.
- Restricted execution boundary, allowlisted network destinations, scoped credentials, timeouts, quotas, and redacted logging.
- Reference connector for a local/institutional repository plus tests for pagination, errors, provenance, rights, and replay.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-04.S04.T03`, `CAP-00.S03.T03`.
- **Produces:** New data sources can be added without bypassing provenance, rights, security, or canonicalization.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `AGENTS.md` and the conditional routes in `planning/README.md`; historical bootstrap documents do not govern current execution.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-04.S05` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 9-10, 15-17, 18-19
- Vision corpus, provenance, rights, and reflexivity requirements
- Connector/source constraints and UI reference

### 3.2 Required upstream state
- `CAP-04.S04.T03` is complete or explicitly gated.
- `CAP-00.S03.T03` is complete or explicitly gated.

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

1. **Use the proposed ADR-0028 LPAC worker and narrow broker protocol, not a same-user child described as a sandbox. Keep plugins outside Core/renderer and fail closed if required isolation is unavailable.**
2. **Manifest declares plugin ID/version, API compatibility, publisher/signature, operations, destinations, credential scopes, data classes, rights behavior, resource limits, and permissions.**
3. **Default deny filesystem, network, secret, model, export, and project access; grant only declared capabilities.**
4. **Verify exact signed manifests/file hashes against explicit trusted publisher keys, then obtain per-project permission consent. The ADR-0028 proposal uses local Ed25519 trust without a marketplace. Unsigned development fixtures remain disposable test-only inputs, not an ordinary project execution mode.**
5. **Use JSON Schema/OpenAPI-like typed RPC with bounded messages, deadlines, cancellation, and provenance.**
6. **Conformance tests are mandatory for pagination, retries, cancellation, rights, provenance, redaction, schema drift, and malicious behavior.**

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
- Connector SDK schemas, language-neutral protocol, and developer documentation.
- Plugin package/signature/trust-store manager.
- Isolated connector host, capability broker, network allowlist, secret broker, quotas, and redacted logging.
- Sample local/institutional repository connector and conformance runner.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `ConnectorPluginManifest`
- `PluginPackage`
- `PluginTrustRecord`
- `CapabilityGrant`
- `PluginInvocation`
- `PluginQuota`
- `ConformanceResult`

**Required invariants**
- Every durable identity and revision reuses the implemented CAP-03 canonical contracts under ADR-0013/ADR-0024; do not create a parallel identity store.
- Consequential state changes are atomic with existing required provenance/outbox/dependency facts; reuse W1 repository transactions and ADR-0025 durable jobs.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Plugin RPC cannot receive raw project paths or general secret values; use opaque handles and purpose-scoped calls.
- Every result is attributable to plugin/package hash, manifest, operation, request, and raw response reference.
- SDK breaking changes follow explicit major compatibility policy and coexistence window.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
Current visual/page authority is 1.6. Preserve ADR-0026's exact inherited 1.5 workflow-catalog binding; mapping this slice does not relabel existing selections. See [W2 journey and mappings](../../W2-initiation.md#ux-journey-to-refine-in-the-existing-contracts).

The [inert W2 reference proposal](../../W2-reference-proposal.md) supplies the
missing inline Source Manager publisher-trust/project-permission contract.
Its candidate1.7 identity is not active authority. Obtain exact reference approval
with the complete W2 packet before implementing the new interaction; no marketplace
or Application Settings page is selected.

- Source Manager shows publisher, signature/trust, requested permissions, destinations, credentials, status, and conformance result.
- Installing/enabling a plugin requires a permission review; permission increases require reapproval.
- Failures identify plugin versus platform responsibility and offer disable/quarantine.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.6`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Use OS process isolation available to the platform plus application-level capability mediation; do not claim a perfect sandbox where OS guarantees are limited.
- Block network destinations outside resolved allowlist and revalidate DNS/redirects to mitigate SSRF.
- Redact plugin logs and cap CPU/memory/disk/runtime/output.
- Quarantine packages with signature/hash mismatch.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Test crash, hang, fork/child attempt, oversized output, private-network access, secret enumeration, path traversal, malformed RPC, schema incompatibility, and cancellation.
- Connector failure cannot crash Core or corrupt project state.
- Disable/quarantine preserves prior imported records/provenance.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-04.S05.T01` - Publish connector plugin manifest and capability API
**Objective:** Versioned manifest for source identity, operations, authentication, terms, rate limits, data classes, and required permissions.

**Dependencies:** `CAP-04.S04.T03`, `CAP-00.S03.T03`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `foundation`, `service`

**Expected deliverables**
- Versioned manifest for source identity, operations, authentication, terms, rate limits, data classes, and required permissions.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S05.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Author the versioned schema/interface/state-machine definitions first, including unknown/not-applicable states, compatibility metadata, validation rules, and negative fixtures. Keep framework and persistence types outside the portable contract.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- An unsupported capability is rejected before execution; plugin version and permissions appear in provenance; breaking SDK changes follow compatibility policy.
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
python tools/verify.py --profile foundation
python tools/taskctl.py validate
python tools/verify.py --profile service
```

### 9.2 `CAP-04.S05.T02` - Implement plugin isolation, configuration, and secret access controls
**Objective:** Restricted execution boundary, allowlisted network destinations, scoped credentials, timeouts, quotas, and redacted logging.

**Dependencies:** `CAP-04.S05.T01`  
**Risk / review gate:** `high` / `security-review`  
**Verification profiles:** `service`, `security-local`

**Expected deliverables**
- Restricted execution boundary, allowlisted network destinations, scoped credentials, timeouts, quotas, and redacted logging.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S05.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- A malicious test connector cannot read unrelated secrets or project files; network and export attempts outside manifest permissions are blocked and audited.
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
python tools/verify.py --profile security-local
```

### 9.3 `CAP-04.S05.T03` - Deliver a sample repository connector and conformance suite
**Objective:** Reference connector for a local/institutional repository plus tests for pagination, errors, provenance, rights, and replay.

**Dependencies:** `CAP-04.S05.T02`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `service`, `foundation`

**Expected deliverables**
- Reference connector for a local/institutional repository plus tests for pagination, errors, provenance, rights, and replay.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-04.S05.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the smallest vertical path that satisfies the task objective while preserving the slice architecture and adjacent-capability contracts.
3. Implement the desktop interaction using shared Academic Minimal tokens/components and the approved page/workflow contract. Cover keyboard, focus, screen reader, light/dark, loading, empty, offline, denied, error, and recovery states. If the required experience differs materially, stop and update/approve the governed reference before application code.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Select affected unit/contract/integration checks under the workflow verification-breadth rule; record selected/deferred coverage. Full listed profiles remain slice/Wave coverage, not an automatic replay after every task edit. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- A third-party developer can implement and validate a connector from documentation; conformance failures identify contract violations precisely.
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
python tools/verify.py --profile foundation
python tools/taskctl.py validate
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `foundation`, `security-local`, `service` |
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
python tools/taskctl.py validate
python tools/verify.py --profile foundation
python tools/verify.py --profile security-local
python tools/verify.py --profile service
```

## 11. Performance and resource budgets
- Use streaming/paged RPC and bounded buffers.
- Apply per-plugin concurrency/rate quotas and global admission control.
- Conformance includes throughput under limits but prioritizes provider compliance.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Record package hash, permissions, invocation status, resource use, destinations, denied actions, rate state, and conformance version.
- Never include secret values or raw protected content in plugin telemetry.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- CAP-04.S02 establishes baseline connector semantics.
- CAP-04.S04 rights/provenance enforcement applies to plugin results.
- CAP-14 implements equivalent host isolation on macOS/Linux.
- W10 institutional deployment may add administrator-managed trust roots.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- Plugin API uses semantic versions and feature negotiation; incompatible plugins remain disabled with actionable guidance.
- Trust-store/signature policy changes retain audit history.

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
- The promised outcome is demonstrable end to end: New data sources can be added without bypassing provenance, rights, security, or canonicalization.
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
Shared proposed records: [ADR-0027](../../../docs/adr/ADR-0027-keep-scholarly-source-replay-separate-from-private-authentication.md), [ADR-0028](../../../docs/adr/ADR-0028-isolate-windows-connectors-and-parsers-behind-narrow-brokers.md).
The following details belong in that shared packet; they do not each require a new ADR or human approval. Any unresolved material detail still prevents W2 packet approval.

- Binding detail: Connector RPC transport and process-isolation mechanism.
- Binding detail: Plugin signing/trust model (Sigstore/TUF-derived or equivalent).
- Binding detail: Capability vocabulary and network allowlist enforcement.

Resolve these material topics through the shared W2 ADR set before packet approval; routine implementation details need no separate ADR. New ADRs remain Proposed until accepted. Do not defer a foreseeable binding architecture choice to implementation or treat a safely stubbed test as real-boundary qualification.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `SIGSTORE` | [Sigstore Documentation](https://docs.sigstore.dev/) - Sigstore | Plugin and artifact signing/verification. |
| `TUF` | [The Update Framework Specification](https://theupdateframework.github.io/specification/latest/) - The Update Framework | Rollback-resistant update metadata concepts. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core.html) - JSON Schema | Portable contract validation. |
| `OWASP_SSRF` | [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) - OWASP | Safe network acquisition. |
| `CLOUDEVENTS` | [CloudEvents Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md) - CNCF | Portable event envelope. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Resume the same approved W2 campaign through taskctl. Use full task designators, risk-selected verification, independent dispositions and local integration. Continue through eligible slices/checkpoints to fresh Wave qualification and the separate G2 human exit gate.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm W2 is the approved active campaign and `CAP-04.S05` is dependency-eligible.
3. Claim only the next READY task in `CAP-04.S05` through taskctl; do not bypass Wave dependencies or create a capability lease.
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
