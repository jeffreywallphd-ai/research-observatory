---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-11
title: Windows PC/lab product hardening, validation, packaging, and release
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-11.S01
- CAP-11.S02
- CAP-11.S03
- CAP-11.S04
- CAP-11.S05
- CAP-11.S06
decisions:
- id: CAP-11-D01
  title: Supported hardware profiles
  candidates:
  - Publish benchmark-grounded minimum, recommended and high-capability profiles with explicit workload envelopes
  - Advertise one generic minimum specification without workload limits
  recommendation: Publish benchmark-grounded minimum, recommended and high-capability profiles with explicit workload envelopes
  recommendation_basis: Measured envelopes make unsupported combinations visible and keep release claims evidence-based.
  selected_option: Publish benchmark-grounded minimum, recommended and high-capability profiles with explicit workload envelopes
  status: accepted
  required_adr: null
- id: CAP-11-D02
  title: Resource governance
  candidates:
  - Use one central adaptive resource governor with interactive-job priority, reservations and pause/resume
  - Let each worker independently consume available CPU, RAM and GPU
  recommendation: Use one central adaptive resource governor with interactive-job priority, reservations and pause/resume
  recommendation_basis: Central arbitration prevents parser/model jobs from starving the UI and makes low-resource behavior deterministic.
  selected_option: Use one central adaptive resource governor with interactive-job priority, reservations and pause/resume
  status: accepted
  required_adr: null
- id: CAP-11-D03
  title: Performance acceptance
  candidates:
  - Use versioned representative projects, warm/cold runs, endurance tests and hardware-normalized thresholds
  - Use developer anecdotes and one-time stopwatch measurements
  recommendation: Use versioned representative projects, warm/cold runs, endurance tests and hardware-normalized thresholds
  recommendation_basis: Repeatable workloads are required for supportable scale claims and regression detection.
  selected_option: Use versioned representative projects, warm/cold runs, endurance tests and hardware-normalized thresholds
  status: accepted
  required_adr: null
- id: CAP-11-D04
  title: Failure qualification
  candidates:
  - Use deterministic fault injection across process death, disk pressure, corrupt derivatives and provider failure
  - Test only expected success paths
  recommendation: Use deterministic fault injection across process death, disk pressure, corrupt derivatives and provider failure
  recommendation_basis: Release confidence depends on recoverability under failures users will eventually experience.
  selected_option: Use deterministic fault injection across process death, disk pressure, corrupt derivatives and provider failure
  status: accepted
  required_adr: null
- id: CAP-11-D05
  title: Recovery authority
  candidates:
  - Repair canonical state conservatively; rebuild derivatives; require confirmation for ambiguous destructive repair
  - Attempt automatic repair of every detected inconsistency
  recommendation: Repair canonical state conservatively; rebuild derivatives; require confirmation for ambiguous destructive repair
  recommendation_basis: Accepted scholarly state must not be silently rewritten by recovery logic.
  selected_option: Repair canonical state conservatively; rebuild derivatives; require confirmation for ambiguous destructive repair
  status: accepted
  required_adr: null
- id: CAP-11-D06
  title: Upgrade strategy
  candidates:
  - Signed staged updates with preflight backup, migration rehearsal, compatibility manifest and rollback
  - Replace binaries in place with no migration/rollback contract
  recommendation: Signed staged updates with preflight backup, migration rehearsal, compatibility manifest and rollback
  recommendation_basis: Update failures must be recoverable without project loss.
  selected_option: Signed staged updates with preflight backup, migration rehearsal, compatibility manifest and rollback
  status: accepted
  required_adr: ADR-RELEASE-UPDATE
- id: CAP-11-D07
  title: Offline baseline
  candidates:
  - Treat no-account, network-blocked operation as a release-gated core product path
  - Treat offline operation as best-effort degraded behavior
  recommendation: Treat no-account, network-blocked operation as a release-gated core product path
  recommendation_basis: Local-first privacy and PC/lab use are core product commitments.
  selected_option: Treat no-account, network-blocked operation as a release-gated core product path
  status: accepted
  required_adr: null
- id: CAP-11-D08
  title: Local security acceptance
  candidates:
  - Maintain a threat model and attack-fixture suite for IPC, documents, plugins, models, paths, logs and updates
  - Rely on framework defaults and antivirus
  recommendation: Maintain a threat model and attack-fixture suite for IPC, documents, plugins, models, paths, logs and updates
  recommendation_basis: The desktop processes untrusted scholarly and model artifacts across several native boundaries.
  selected_option: Maintain a threat model and attack-fixture suite for IPC, documents, plugins, models, paths, logs and updates
  status: accepted
  required_adr: null
- id: CAP-11-D09
  title: Privacy and telemetry
  candidates:
  - Default telemetry off/local; require visible egress preview, rights checks and deletion evidence
  - Enable usage/content telemetry by default
  recommendation: Default telemetry off/local; require visible egress preview, rights checks and deletion evidence
  recommendation_basis: Unpublished research and source content require conservative disclosure controls.
  selected_option: Default telemetry off/local; require visible egress preview, rights checks and deletion evidence
  status: accepted
  required_adr: null
- id: CAP-11-D10
  title: Accessibility target
  candidates:
  - Release against WCAG 2.2 AA-oriented criteria plus desktop assistive-technology testing
  - Rely only on automated accessibility linting
  recommendation: Release against WCAG 2.2 AA-oriented criteria plus desktop assistive-technology testing
  recommendation_basis: Complex tables, graphs and document views require both testable standards and human AT validation.
  selected_option: Release against WCAG 2.2 AA-oriented criteria plus desktop assistive-technology testing
  status: accepted
  required_adr: null
- id: CAP-11-D11
  title: Onboarding model
  candidates:
  - Use objective-specific guided onboarding, sample projects and contextual help
  - Provide a static manual and leave tool order to the user
  recommendation: Use objective-specific guided onboarding, sample projects and contextual help
  recommendation_basis: The approved workflow UX is intended to prevent the product from feeling like disconnected tools.
  selected_option: Use objective-specific guided onboarding, sample projects and contextual help
  status: accepted
  required_adr: null
- id: CAP-11-D12
  title: Lab deployment
  candidates:
  - Provide signed unattended deployment, machine policy layers, cache seeding and redacted support bundles
  - Require manual per-user installation and configuration
  recommendation: Provide signed unattended deployment, machine policy layers, cache seeding and redacted support bundles
  recommendation_basis: Laboratories need repeatable deployment without centralizing project content.
  selected_option: Provide signed unattended deployment, machine policy layers, cache seeding and redacted support bundles
  status: accepted
  required_adr: null
- id: CAP-11-D13
  title: Release evidence
  candidates:
  - Require signed artifacts, SBOM, SLSA-style provenance, checksums and criterion-linked gate evidence
  - Publish an installer after tests pass on the developer machine
  recommendation: Require signed artifacts, SBOM, SLSA-style provenance, checksums and criterion-linked gate evidence
  recommendation_basis: A production release must be independently verifiable and reproducible.
  selected_option: Require signed artifacts, SBOM, SLSA-style provenance, checksums and criterion-linked gate evidence
  status: accepted
  required_adr: null
- id: CAP-11-D14
  title: Support lifecycle
  candidates:
  - Publish supported OS/runtime/model matrix, update rings, known limitations and deprecation policy
  - Support all observed combinations indefinitely
  recommendation: Publish supported OS/runtime/model matrix, update rings, known limitations and deprecation policy
  recommendation_basis: Explicit support boundaries enable reliable maintenance and honest user expectations.
  selected_option: Publish supported OS/runtime/model matrix, update rings, known limitations and deprecation policy
  status: accepted
  required_adr: null
- id: CAP-11-D15
  title: Release gate authority
  candidates:
  - Human approves G5 from immutable evidence; automation assembles but cannot self-certify
  - Allow the release automation to approve itself when checks are green
  recommendation: Human approves G5 from immutable evidence; automation assembles but cannot self-certify
  recommendation_basis: Technical evidence does not replace product, scholarly and operational accountability.
  selected_option: Human approves G5 from immutable evidence; automation assembles but cannot self-certify
  status: accepted
  required_adr: null
- id: CAP-11-D16
  title: Installation formats
  candidates:
  - Use Tauri-supported signed Windows installer artifacts with enterprise deployment examples
  - Distribute unpacked binaries or development commands
  recommendation: Use Tauri-supported signed Windows installer artifacts with enterprise deployment examples
  recommendation_basis: Signed installers support ordinary researchers and institutional software distribution.
  selected_option: Use Tauri-supported signed Windows installer artifacts with enterprise deployment examples
  status: accepted
  required_adr: ADR-WINDOWS-PACKAGING
- id: CAP-11-D17
  title: Benchmark disclosure
  candidates:
  - Publish limits and methodology with versioned hardware/software manifests
  - Publish only headline throughput numbers
  recommendation: Publish limits and methodology with versioned hardware/software manifests
  recommendation_basis: Users and reviewers must understand the scope of performance claims.
  selected_option: Publish limits and methodology with versioned hardware/software manifests
  status: accepted
  required_adr: null
- id: CAP-11-D18
  title: Support bundle content
  candidates:
  - Generate opt-in, redacted diagnostic bundles with a preview and no source text by default
  - Upload full logs and project files automatically
  recommendation: Generate opt-in, redacted diagnostic bundles with a preview and no source text by default
  recommendation_basis: Support must not become an accidental research-data egress channel.
  selected_option: Generate opt-in, redacted diagnostic bundles with a preview and no source text by default
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-11 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-11` — Windows PC/lab product hardening, validation, packaging, and release |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-11/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Turn the local architecture and research workflows into a dependable Windows product for individual researchers and laboratory computers before server or cloud delivery begins.

The capability closes the Windows local product boundary: one signed Tauri desktop, supervised local services and workers, protected project storage, resource-aware AI and document processing, and criterion-linked release evidence.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Representative end-to-end research projects complete offline on supported PC profiles with no developer intervention.
- Installation, upgrade, backup, restore, crash recovery, security, accessibility, and support procedures pass release gates.
- Lab administrators can deploy, configure, diagnose, and update multiple stations while projects remain locally governed.
- Representative users can select an objective, understand the guided path, move between primary steps and supporting tools, and complete each approved use-case workflow without external instruction.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-11.S01` | Performance profiles, scale targets, and resource governance | The product has measured local limits and remains responsive under realistic corpus, document, model, and workflow loads. | W5 | P0 | CAP-10.S03.T02, CAP-07.S02.T03 |
| `CAP-11.S02` | Reliability, crash recovery, upgrade, and rollback | Expected failures do not lose accepted scholarly work or leave projects in ambiguous states. | W5 | P0 | CAP-11.S01.T03, CAP-02.S02.T02 |
| `CAP-11.S03` | Offline, privacy, and local security acceptance | The local edition has verified no-account/offline behavior and a reviewed threat/control baseline. | W5 | P0 | CAP-11.S02.T03, CAP-07.S03.T03, CAP-09.S06.T03 |
| `CAP-11.S04` | Accessibility, usability, onboarding, and help | Researchers can learn and operate the local product without specialist system administration or inaccessible interaction barriers. | W5 | P0 | CAP-01.S02.T03, CAP-10.S03.T02 |
| `CAP-11.S05` | Lab deployment, policy, maintenance, and support | A laboratory can manage multiple independent PCs while retaining local project operation and predictable support. | W5 | P0 | CAP-01.S05.T03, CAP-02.S05.T03 |
| `CAP-11.S06` | Local release candidate and acceptance gate | The PC/lab edition is released only after technical, scholarly, and operational acceptance on representative workflows. | W5 | P0 | CAP-11.S03.T03, CAP-11.S04.T03, CAP-11.S05.T03, CAP-10.S03.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before approval, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. Reviewers may accept the recommendation, select another listed option, or request a revised candidate set. Each accepted selection must include rationale and any ADR/reference requirement. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-11-D01` | Supported hardware profiles | A. Publish benchmark-grounded minimum, recommended and high-capability profiles with explicit workload envelopes<br>B. Advertise one generic minimum specification without workload limits | **Publish benchmark-grounded minimum, recommended and high-capability profiles with explicit workload envelopes** | Measured envelopes make unsupported combinations visible and keep release claims evidence-based. | None |
| `CAP-11-D02` | Resource governance | A. Use one central adaptive resource governor with interactive-job priority, reservations and pause/resume<br>B. Let each worker independently consume available CPU, RAM and GPU | **Use one central adaptive resource governor with interactive-job priority, reservations and pause/resume** | Central arbitration prevents parser/model jobs from starving the UI and makes low-resource behavior deterministic. | None |
| `CAP-11-D03` | Performance acceptance | A. Use versioned representative projects, warm/cold runs, endurance tests and hardware-normalized thresholds<br>B. Use developer anecdotes and one-time stopwatch measurements | **Use versioned representative projects, warm/cold runs, endurance tests and hardware-normalized thresholds** | Repeatable workloads are required for supportable scale claims and regression detection. | None |
| `CAP-11-D04` | Failure qualification | A. Use deterministic fault injection across process death, disk pressure, corrupt derivatives and provider failure<br>B. Test only expected success paths | **Use deterministic fault injection across process death, disk pressure, corrupt derivatives and provider failure** | Release confidence depends on recoverability under failures users will eventually experience. | None |
| `CAP-11-D05` | Recovery authority | A. Repair canonical state conservatively; rebuild derivatives; require confirmation for ambiguous destructive repair<br>B. Attempt automatic repair of every detected inconsistency | **Repair canonical state conservatively; rebuild derivatives; require confirmation for ambiguous destructive repair** | Accepted scholarly state must not be silently rewritten by recovery logic. | None |
| `CAP-11-D06` | Upgrade strategy | A. Signed staged updates with preflight backup, migration rehearsal, compatibility manifest and rollback<br>B. Replace binaries in place with no migration/rollback contract | **Signed staged updates with preflight backup, migration rehearsal, compatibility manifest and rollback** | Update failures must be recoverable without project loss. | ADR-RELEASE-UPDATE |
| `CAP-11-D07` | Offline baseline | A. Treat no-account, network-blocked operation as a release-gated core product path<br>B. Treat offline operation as best-effort degraded behavior | **Treat no-account, network-blocked operation as a release-gated core product path** | Local-first privacy and PC/lab use are core product commitments. | None |
| `CAP-11-D08` | Local security acceptance | A. Maintain a threat model and attack-fixture suite for IPC, documents, plugins, models, paths, logs and updates<br>B. Rely on framework defaults and antivirus | **Maintain a threat model and attack-fixture suite for IPC, documents, plugins, models, paths, logs and updates** | The desktop processes untrusted scholarly and model artifacts across several native boundaries. | None |
| `CAP-11-D09` | Privacy and telemetry | A. Default telemetry off/local; require visible egress preview, rights checks and deletion evidence<br>B. Enable usage/content telemetry by default | **Default telemetry off/local; require visible egress preview, rights checks and deletion evidence** | Unpublished research and source content require conservative disclosure controls. | None |
| `CAP-11-D10` | Accessibility target | A. Release against WCAG 2.2 AA-oriented criteria plus desktop assistive-technology testing<br>B. Rely only on automated accessibility linting | **Release against WCAG 2.2 AA-oriented criteria plus desktop assistive-technology testing** | Complex tables, graphs and document views require both testable standards and human AT validation. | None |
| `CAP-11-D11` | Onboarding model | A. Use objective-specific guided onboarding, sample projects and contextual help<br>B. Provide a static manual and leave tool order to the user | **Use objective-specific guided onboarding, sample projects and contextual help** | The approved workflow UX is intended to prevent the product from feeling like disconnected tools. | None |
| `CAP-11-D12` | Lab deployment | A. Provide signed unattended deployment, machine policy layers, cache seeding and redacted support bundles<br>B. Require manual per-user installation and configuration | **Provide signed unattended deployment, machine policy layers, cache seeding and redacted support bundles** | Laboratories need repeatable deployment without centralizing project content. | None |
| `CAP-11-D13` | Release evidence | A. Require signed artifacts, SBOM, SLSA-style provenance, checksums and criterion-linked gate evidence<br>B. Publish an installer after tests pass on the developer machine | **Require signed artifacts, SBOM, SLSA-style provenance, checksums and criterion-linked gate evidence** | A production release must be independently verifiable and reproducible. | None |
| `CAP-11-D14` | Support lifecycle | A. Publish supported OS/runtime/model matrix, update rings, known limitations and deprecation policy<br>B. Support all observed combinations indefinitely | **Publish supported OS/runtime/model matrix, update rings, known limitations and deprecation policy** | Explicit support boundaries enable reliable maintenance and honest user expectations. | None |
| `CAP-11-D15` | Release gate authority | A. Human approves G5 from immutable evidence; automation assembles but cannot self-certify<br>B. Allow the release automation to approve itself when checks are green | **Human approves G5 from immutable evidence; automation assembles but cannot self-certify** | Technical evidence does not replace product, scholarly and operational accountability. | None |
| `CAP-11-D16` | Installation formats | A. Use Tauri-supported signed Windows installer artifacts with enterprise deployment examples<br>B. Distribute unpacked binaries or development commands | **Use Tauri-supported signed Windows installer artifacts with enterprise deployment examples** | Signed installers support ordinary researchers and institutional software distribution. | ADR-WINDOWS-PACKAGING |
| `CAP-11-D17` | Benchmark disclosure | A. Publish limits and methodology with versioned hardware/software manifests<br>B. Publish only headline throughput numbers | **Publish limits and methodology with versioned hardware/software manifests** | Users and reviewers must understand the scope of performance claims. | None |
| `CAP-11-D18` | Support bundle content | A. Generate opt-in, redacted diagnostic bundles with a preview and no source text by default<br>B. Upload full logs and project files automatically | **Generate opt-in, redacted diagnostic bundles with a preview and no source text by default** | Support must not become an accidental research-data egress channel. | None |

Every decision is resolved by the documented best-in-class recommendation: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires explicit rationale. Approval remains the one authorization gate for the capability and all slice plans.

## 5. Cross-slice architecture contract

The capability closes the Windows local product boundary: one signed Tauri desktop, supervised local services and workers, protected project storage, resource-aware AI and document processing, and criterion-linked release evidence.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The approved workflow-centered Academic Minimal experience is release-qualified rather than redesigned. Project objective, ordered stages, supporting tools, provenance, recovery and help remain visible across the complete local workflow.

Approved reference exposure: `help-onboarding.html`, `new-project.html`, `project-settings.html`, `projects.html`, `index.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Local-first privacy, untrusted-content isolation, signed updates, protected credentials, support-bundle redaction and verifiable deletion are release conditions.

The capability must treat documents, model files, provider responses, archives, URLs, imported data and rich text as untrusted. Least privilege, schema validation, path/destination controls, bounded resources, output encoding, redacted diagnostics and explicit egress policy apply at each trust boundary. The system may recommend and organize evidence but may not fabricate sources, permissions, performance, approval, methodological validity or completion evidence.

## 8. Capability-wide verification strategy

The verification program combines task tests, slice integration, capability end-to-end acceptance and independent review. It must include:

- Contract and schema compatibility across all six slices and affected neighboring capabilities.
- Representative success paths plus material denial, cancellation, restart, migration and recovery paths.
- Security, privacy, rights and research-integrity attack fixtures.
- Accessibility and governed-reference conformance for user-facing work.
- Performance, endurance, resource and cost evidence against declared profiles.
- Clean-environment packaging/deployment tests for each applicable target.
- Criterion-to-evidence manifests tied to the reviewed commit and immutable fixture/model/provider versions.

## 9. Long-running execution contract

After one-time approval, `taskctl capability start CAP-11` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [ ] All listed decisions have a selected option, rationale and accepted status.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-11 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `TAURI_DISTRIBUTION` | [Tauri 2 Distribution](https://v2.tauri.app/distribute/) | Tauri | Desktop packaging, signing and installer targets. |
| `NIST_SSDF` | [Secure Software Development Framework SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | NIST | Secure development and release controls. |
| `OTEL` | [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) | OpenTelemetry | Portable traces, metrics and logs. |
| `SQLITE_BACKUP` | [SQLite Online Backup API](https://www.sqlite.org/backup.html) | SQLite | Consistent local backups. |
| `SQLITE_INTEGRITY` | [SQLite PRAGMA integrity_check](https://www.sqlite.org/pragma.html#pragma_integrity_check) | SQLite | Project health and corruption detection. |
| `TAURI_UPDATER` | [Tauri Updater Plugin](https://v2.tauri.app/plugin/updater/) | Tauri | Signed update manifests, channels and updater behavior. |
| `NIST_AI_SSDF` | [Secure Software Development Practices for Generative AI and Dual-Use Foundation Models SP 800-218A](https://csrc.nist.gov/pubs/sp/800/218/a/final) | NIST | AI-specific secure development practices. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |
| `SPDX` | [SPDX Specification 3.0](https://spdx.github.io/spdx-spec/v3.0/) | Linux Foundation | Software bill of materials representation. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |
| `ARIA_APG` | [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/) | W3C | Accessible widget and interaction patterns. |
| `INTUNE` | [Add, assign, and monitor a Win32 app in Microsoft Intune](https://learn.microsoft.com/en-us/intune/intune-service/apps/apps-win32-add) | Microsoft | Institutional Windows application deployment. |
| `SIGNTOOL` | [How to sign an app package using SignTool](https://learn.microsoft.com/en-us/windows/win32/appxpkg/how-to-sign-a-package-using-signtool) | Microsoft | Windows package signing. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision feedback | Export from `planning/review-site/CAP-11/index.html` and apply with `planctl`; feedback alone does not approve execution. |
