---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-02
capability_plan: planning/capability-plans/CAP-02.md
planning_gate: capability-decision-complete
slice_id: CAP-02.S03
title: Encrypted local object and cache storage
status: proposed
wave: W1
priority: P0
deployment_profiles:
- LOC
- LAB
platform_targets:
- windows-x64
task_ids:
- CAP-02.S03.T01
- CAP-02.S03.T02
- CAP-02.S03.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-02.S03 - Encrypted local object and cache storage
> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-02.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and `python tools/planctl.py ready CAP-02 --require-approved` passes. After campaign start, execute continuously and pause only for an allowed classified condition.
## 0. Plan control
| Field | Value |
|---|---|
| Capability | `CAP-02` - Local projects, durable storage, security, and recovery |
| Capability objective | Provide safe project lifecycle, local persistence, encrypted content storage, secrets management, and portable recovery for individual and laboratory computers. |
| Slice | `CAP-02.S03` - Encrypted local object and cache storage |
| Slice outcome | Documents, page images, snapshots, models, and exports use content-addressed storage with integrity and rights metadata. |
| Wave / priority | `W1` / `P0` |
| Deployment profiles | `LOC`, `LAB` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-02.S03.T01`, `CAP-02.S03.T02`, `CAP-02.S03.T03` |
| Slice dependencies | `CAP-02.S02.T01` |
| Governing experience | `RO-UI-ACADEMIC-MINIMAL-1.3` for user-facing implementation |
| Approval state | Pending human approval |

## 1. Purpose and contribution to the larger vision
Store permitted documents, derived artifacts, models, reports, and caches locally without exposing content, duplicating bytes, or coupling downstream logic to filesystem layout.

This slice contributes to the capability objective: **Provide safe project lifecycle, local persistence, encrypted content storage, secrets management, and portable recovery for individual and laboratory computers.** It must preserve the capability exit conditions:

- Projects survive crashes, application upgrades, relocations, and verified backup/restore cycles.
- Sensitive documents and credentials are protected with explicit local threat assumptions.
- A lab can configure approved storage and model-cache locations without converting the product into a server deployment.

**Implementation thesis.** Use a content-addressed object service keyed by plaintext SHA-256 identity but store authenticated-encrypted envelopes under opaque keyed paths. Separate durable objects from reconstructible caches and govern reference counts, quotas, integrity, and garbage collection transactionally.

## 2. Scope

### 2.1 In scope
- Streaming put/get/delete, hashes, metadata, reference counting, atomic writes, and corruption detection.
- Authenticated encryption for protected objects, key identifiers, nonce handling, rotation-ready metadata, and unencrypted fixture mode for tests.
- Per-project and shared-cache usage metrics, soft/hard thresholds, orphan detection, preview, and safe cleanup.

### 2.2 Explicit non-goals
- Do not implement downstream capability behavior except for the narrow contracts, fixtures, or extension points explicitly identified in this plan.
- Do not introduce university-hosted or managed-cloud infrastructure during the Windows local waves; preserve deployment-neutral ports only.
- Do not bypass the Core API, project-home authority, repository ports, provenance ledger, workflow fabric, rights policy, or approved experience reference.
- Do not select a new parser, database, cryptographic construction, plugin sandbox, model/provider, or UI pattern where this plan identifies an ADR or human decision gate.
- Do not mark the slice complete when only the happy path or individual tasks pass; slice-wide failure, restart, recovery, security, accessibility, and handoff evidence is required.

### 2.3 Slice boundary
- **Consumes:** `CAP-02.S02.T01`.
- **Produces:** Documents, page images, snapshots, models, and exports use content-addressed storage with integrity and rights metadata.
- **Owns:** The durable contracts, implementation boundary, fixtures, and evidence described below.
- **Does not own:** Product intent, cross-capability policy, or downstream scholarly interpretation beyond the explicit handoffs.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing sources
- `START_HERE.md` and `docs/governance/document-set-and-bootstrap.md`.
- `docs/product/vision.md` for purpose, principles, research modes, and non-goals.
- Accepted ADRs, then `docs/architecture/source/systems-design.md`.
- `planning/backlog.yaml` for `CAP-02.S03` and its task state/dependencies.
- `docs/automation/project-automation-guide.md` and `docs/automation/codex-tracking-guide.md`.
- `design/ui-reference/APPROVAL.yaml`, style guide, workflow catalog, page contracts, and HTML reference for user-facing work.
- Systems Design sections 4, 6, 9, 13, 15, 17-19
- Project-home and security architecture
- Backup/recovery and portability requirements

### 3.2 Required upstream state
- `CAP-02.S02.T01` is complete or explicitly gated.

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

1. **Identify immutable content by SHA-256 of canonical plaintext bytes; verify hash before commit and after decrypt.**
2. **Use per-object random data keys and authenticated streaming encryption for large objects; wrap data keys with a versioned profile master key.**
3. **Derive physical filenames/paths with a keyed transform so plaintext content hashes are not directly exposed in directory listings.**
4. **Write to a temporary file, fsync, verify, atomically rename, then commit metadata/reference linkage.**
5. **Separate durable originals/accepted artifacts from rebuildable cache and temporary work; never evict durable referenced objects.**
6. **Garbage collection is mark-and-sweep from canonical references plus leases/tombstones, with dry-run evidence.**

### 4.1 Replaceability rule
External products and infrastructure remain behind ports. Domain identities, provenance, workflow state, rights decisions, accepted human judgments, source anchors, and portable contracts must survive replacement of any UI framework detail, parser, vector engine, model, API provider, cryptographic envelope version, or deployment adapter.

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations
- `services/core-api/modules/projects/` - project lifecycle and project-home authority.
- `services/core-api/modules/storage/` - SQLite, repositories, object store, snapshots, and recovery.
- `services/core-api/modules/security/` - vault, keys, privacy, and protection profiles.
- `apps/desktop/src/workspaces/projects/` and `settings/` - project and privacy UX.
- `packages/contracts/project/` and `storage/` - portable project/storage contracts.
- `tests/data/`, `tests/security/`, `tests/recovery/`, and `tests/e2e-local/`.

**Slice-specific components**
- Object-store port and local encrypted filesystem adapter.
- Envelope format, key wrapping/versioning, streaming reader/writer, and integrity verifier.
- Object metadata/reference repositories and transactional staging protocol.
- Quota, accounting, cache policy, garbage collection, orphan repair, and diagnostics.

### 5.2 Data model and state ownership
The following durable types are recommended. Final field names belong in versioned schemas and accepted ADRs; persistence classes are adapters, not the portable contract.

- `StoredObject`
- `ObjectEnvelope`
- `WrappedObjectKey`
- `ObjectReference`
- `ObjectLease`
- `CacheEntry`
- `GarbageCollectionRun`

**Required invariants**
- Every durable identity and revision follows CAP-03 canonical identifier/version rules or creates the necessary contract in this slice when CAP-03 is not yet available.
- Consequential state changes are atomic with required provenance/outbox/dependency facts once those foundations exist; earlier slices provide an explicit integration seam and fixtures.
- Accepted human decisions and historical revisions are never silently overwritten.
- Unknown, not-reported, not-applicable, ambiguous, disputed, denied, and unavailable states remain distinct where the domain requires them.
- Persistence, cache, derived index, and UI projections are never treated as interchangeable authority.

### 5.3 Interfaces and contracts
- Put is idempotent by project/object identity and returns immutable object metadata.
- Open returns a controlled stream, never an unrestricted decrypted path.
- Every object records media type, length, plaintext hash, cipher/envelope version, key version, creation source, rights class, and durability class.
- Callers declare purpose and project authority when opening restricted content.

### 5.4 Cross-capability compatibility
- Expose portable schemas/ports rather than Windows paths, SQLite connection objects, framework components, parser-specific nodes, or provider-specific DTOs.
- Keep local/hosted differences at adapter, authentication, process, storage, and deployment boundaries; preserve the same domain/API/workflow semantics.
- All user-facing route/page/workflow IDs remain consistent with the approved reference and machine catalogs.
- All long-running or retryable operations expose durable operation/job identity, cancellation, restart, and evidence semantics.
- Downstream slices consume immutable IDs/revisions and typed policy/provenance instead of reading implementation tables or filesystem layout.

## 6. User experience and approved reference
- Storage settings show durable content, derived artifacts, caches, reclaimable space, and quota separately.
- Cache clearing accurately states what will be recomputed and does not imply scholarly outputs are deleted.
- Integrity failures show affected records and recovery sources.

**Reference-first rule.** If these requirements cannot be implemented within `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow/page contracts, and HTML reference; run the reference validators; obtain explicit human approval and a new reference ID; then implement. A defect that merely restores conformance to the approved reference does not require a new reference version.

## 7. Security, privacy, rights and research integrity
- Use libsodium secretstream/XChaCha20-Poly1305 or an equivalently reviewed construction; no custom cryptography.
- Keep plaintext only in bounded memory or protected temporary streams; wipe key material where library/runtime permits.
- Set restrictive permissions and prevent path traversal/symlink attacks.
- Object reads enforce rights and egress policy in addition to encryption.

**Baseline controls**
- Apply least privilege, input validation, output encoding, bounded resources, redacted diagnostics, and explicit policy decisions at trusted service boundaries.
- Treat imported metadata, documents, reports, prompts, model output, plugins, URLs, and rich text as untrusted.
- Never invent scholarly evidence, availability, permissions, method details, or completion evidence.
- Keep private projects local by default; remote egress requires the governing project/intent/privacy/rights policy.
- Security or rights review findings are blocking when the backlog review gate requires them.

## 8. Failure, cancellation, restart and recovery
- Recover abandoned staging files, orphan metadata, missing files, tag failures, wrong keys, and partial GC.
- A corrupt object is quarantined and dependents become unavailable/stale; the system never returns unauthenticated partial plaintext.
- GC uses a generation/lease barrier so concurrent readers and writers cannot lose objects.

Each material scenario must have: deterministic trigger fixture, durable state expectation, user-visible state, retry/cancel rule, cleanup/repair rule, provenance/audit expectation, and an automated test where feasible.

## 9. Task-by-task implementation plan

### 9.1 `CAP-02.S03.T01` - Implement content-addressed object storage abstraction
**Objective:** Streaming put/get/delete, hashes, metadata, reference counting, atomic writes, and corruption detection.

**Dependencies:** `CAP-02.S02.T01`  
**Risk / review gate:** `high` / `agent-review`  
**Verification profiles:** `data`

**Expected deliverables**
- Streaming put/get/delete, hashes, metadata, reference counting, atomic writes, and corruption detection.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-02.S03.T01`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Duplicate content is stored once within a project scope; interrupted writes are not visible; hash mismatch is detected before downstream use.
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
python tools/verify.py --profile data
```

### 9.2 `CAP-02.S03.T02` - Add encryption-at-rest and key-version metadata
**Objective:** Authenticated encryption for protected objects, key identifiers, nonce handling, rotation-ready metadata, and unencrypted fixture mode for tests.

**Dependencies:** `CAP-02.S03.T01`  
**Risk / review gate:** `high` / `security-review`  
**Verification profiles:** `data`, `security-local`

**Expected deliverables**
- Authenticated encryption for protected objects, key identifiers, nonce handling, rotation-ready metadata, and unencrypted fixture mode for tests.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-02.S03.T02`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Implement and test the relevant trust boundary explicitly: validate untrusted input, constrain permissions/resources/destinations, redact diagnostics, deny unsupported access, and verify that failure leaves canonical state unchanged or recoverable.
4. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
5. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Ciphertext tampering is detected; plaintext is not persisted in logs or temporary directories; key loss produces a bounded, explicit failure rather than silent corruption.
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
python tools/verify.py --profile data
python tools/verify.py --profile security-local
```

### 9.3 `CAP-02.S03.T03` - Implement storage accounting, quotas, garbage collection, and cache eviction
**Objective:** Per-project and shared-cache usage metrics, soft/hard thresholds, orphan detection, preview, and safe cleanup.

**Dependencies:** `CAP-02.S03.T02`  
**Risk / review gate:** `medium` / `agent-review`  
**Verification profiles:** `data`, `e2e-local`

**Expected deliverables**
- Per-project and shared-cache usage metrics, soft/hard thresholds, orphan detection, preview, and safe cleanup.

**Ordered implementation sequence**
1. Confirm the governing contracts, task dependencies, approved reference (when user-facing), and the specific fixture set for `CAP-02.S03.T03`. Add failing tests for the required success path and at least one material boundary/failure case before production code.
2. Implement the domain/core path behind the approved port or aggregate boundary. Keep side effects behind adapters, use explicit transaction/idempotency boundaries, and emit provenance/dependency facts atomically where the governing architecture requires them.
3. Integrate persistence, events/provenance, migration/version metadata, and restart behavior. Exercise the path after process/application restart and against prior-compatible fixtures where applicable.
4. Run the task verification commands plus targeted unit/contract/integration tests. Produce criterion-to-evidence records tied to the reviewed commit; update contracts, fixtures, documentation, ADRs, and the slice evidence index without adding unrelated work.

**Acceptance criteria from the authoritative backlog**
- Cleanup never removes referenced canonical objects; users can inspect reclaimed categories before destructive actions; low-disk conditions trigger graceful degradation.
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
python tools/verify.py --profile data
python tools/verify.py --profile e2e-local
```

## 10. Slice-wide verification matrix
| Verification area | Required evidence |
|---|---|
| Backlog profiles | `data`, `e2e-local`, `security-local` |
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
python tools/verify.py --profile data
python tools/verify.py --profile e2e-local
python tools/verify.py --profile security-local
```

## 11. Performance and resource budgets
- Stream objects without loading full files into memory; default chunk sizing is benchmarked across PDF/report/model sizes.
- Deduplication must not reveal cross-project content equality outside project authority.
- Establish throughput, open latency, and GC pause budgets on representative Windows storage.

The implementation must record the hardware/OS, fixture version, warm/cold state, repetitions, percentile or distribution used, and a regression threshold. A budget may be refined by benchmark evidence, but relaxation requires review and must not conceal algorithmic or resource regressions.

## 12. Observability and provenance
- Record byte counts, encryption/decryption duration, integrity failures, cache hit/eviction, quota pressure, and GC decisions.
- Do not log plaintext hashes in support bundles unless explicitly classified safe; prefer opaque object IDs.

Runtime telemetry and support diagnostics are distinct from durable scholarly provenance. Both use trace/correlation identifiers, but default diagnostics must exclude research content, secrets, raw documents, manuscript text, and sensitive query terms.

## 13. Adjacent-slice handoffs
- CAP-02.S04 supplies master-key access and rotation.
- CAP-02.S05 snapshots object manifests and encrypted streams.
- CAP-05 acquisition/parser layers consume streams and immutable object identities.
- All manuscript/report/model artifacts later reuse this store.

**Handoff acceptance rule:** A downstream slice must be able to consume the documented contract and fixture without importing private implementation modules or reconstructing hidden state.

## 14. Migration and backward compatibility
- Envelope/key-version upgrades rewrite objects through verified copy-on-write and retain rollback until new integrity verification passes.
- Object metadata remains portable across local and hosted object-store adapters.

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
- The promised outcome is demonstrable end to end: Documents, page images, snapshots, models, and exports use content-addressed storage with integrity and rights metadata.
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
- ADR: Local object encryption envelope and cryptographic library.
- ADR: Opaque physical path derivation and cross-project deduplication policy.
- ADR: Durable-object versus cache classification.

A listed item beginning with `ADR REQUIRED` blocks the relevant implementation choice. Other ADRs may be completed within the first task only when that task explicitly owns the decision and the capability campaign approval permits it.

## 20. Research and standards basis
| Key | Primary or official source | Applied decision |
|---|---|---|
| `SECRETSTREAM` | [Libsodium Secretstream](https://doc.libsodium.org/secret-key_cryptography/secretstream) - Libsodium | Authenticated streaming encryption of objects and backups. |
| `XCHACHA20` | [Libsodium XChaCha20-Poly1305](https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305/xchacha20-poly1305_construction) - Libsodium | Authenticated encryption envelope construction. |
| `ARGON2` | [RFC 9106 - Argon2](https://www.rfc-editor.org/rfc/rfc9106.html) - IETF | Passphrase-derived recovery/export keys. |

These sources constrain implementation choices but do not replace repository-specific benchmarks, threat analysis, licensing review, accessibility testing, or ADR approval. Source access should be rechecked when implementation begins because APIs, libraries, platform guidance, and license terms can change.

## 21. AI implementation runbook

**Long-running campaign rule.** Continue through dependency-ready tasks and slices without repeatedly requesting decisions already settled by the approved capability packet. Use only classified pause categories and attach exact evidence/next action.
1. Run the repository validators and confirm this plan is approved, matches the current backlog slice/task IDs, and has no unresolved blocking ADR.
2. Confirm `CAP-02` is the active capability campaign and `CAP-02.S03` is the next eligible slice.
3. Claim the first READY task in order: `CAP-02.S03.T01`. Do not globally select work outside the capability.
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
