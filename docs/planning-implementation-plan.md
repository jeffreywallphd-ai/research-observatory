---
document_type: generated-backlog-plan
plan_id: RO-IMPLEMENTATION-PLAN-001
plan_version: 1.3
source: planning/backlog.yaml
source_sha256: 01b697d27151487beae0be64d6835f99af121d29e2b4c08e8d561f51b5084836
generator: tools/backlog_views.py
manual_edit: prohibited
---

# Research Observatory Capability -> Slice -> Task Execution Plan

> **GENERATED FILE - DO NOT EDIT.** `planning/backlog.yaml` is authoritative. Run `python tools/backlog_views.py --repo .` to regenerate this file.

## Authority and scope

This YAML file is the authoritative task, dependency, gate, and progress ledger. Rendered DOCX and Markdown plans are generated explanatory views.

**Delivery priority:** Complete and release the Windows PC/lab edition first; then qualify the same desktop and local project format on macOS and Linux (including Linux ARM64/NVIDIA DGX Spark-class lab systems) before research-production, university-hosted, and managed-cloud delivery.

**Permanent ID policy:** IDs are permanent. Never renumber or reuse an ID after publication.

## Ledger snapshot

| Item | Count |
|---|---:|
| Capabilities | 20 |
| Slices | 117 |
| Tasks | 356 |
| Waves | 12 |
| Release gates | 12 |

See `planning/status-summary.md` for the generated status distributions and capability progress table.

## Waves

| Wave | Track | Goal | Activation |
|---|---|---|---|
| `W0` Engineering foundation | local-baseline | Create the repository, architecture guardrails, verification system, executable backlog, and approved experience reference. | Initial |
| `W1` Windows local runtime and durable core | local-baseline | Establish the Windows desktop, sidecar, local project storage, domain contracts, provenance, and workflows. | `G0` |
| `W2` Windows local evidence foundation | local-baseline | Ingest scholarly records and documents, canonicalize them, parse full text, and preserve inspectable anchors. | `G1` |
| `W3` Windows local research workbench | local-baseline | Deliver search, screening, model execution, structured extraction, verification, and evidence matrices. | `G2` |
| `W4` Windows scholarly reasoning and novelty MVP | local-baseline | Deliver the argument graph, synthesis, reproducibility, nearest-prior comparison, and bounded novelty workflow. | `G3` |
| `W5` Windows PC/lab production release | local-baseline | Harden, package, document, and validate the complete Windows edition for individual and laboratory computers. | `G4` |
| `W6` Cross-platform desktop qualification | cross-platform-desktop | Qualify the same desktop, project format, sidecars, security controls, and local workflows on macOS and Linux x86_64/ARM64 after the Windows release. | `G5` |
| `W7` Study design and manuscript foundations | research-production | Add production-ready critical and hermeneutic research support, evidence-grounded empirical study design, and reusable conference/journal article blueprints for empirical, theory, and critical scholarship. | `G6` |
| `W8` Results integration, manuscript drafting, and reviewer simulation | research-production | Ingest private technical reports, map verified results, draft source-grounded manuscripts, and conduct extended independent reviewer simulations and revision rounds. | `G7` |
| `W9` Advanced research-intelligence preview | research-intelligence | Add advanced plural opportunity detectors, transparent portfolio ranking, convergence monitoring, and living research memory on the cross-platform research-production foundation. | `G8` |
| `W10` University-hosted pilot | institutional | Move the same desktop and contracts to institution-controlled services, identity, collaboration, and operations after the complete local research-production gate. | `G8` |
| `W11` Managed cloud delivery | cloud | Add tenant provisioning, regional isolation, metering, cloud operations, and commercial governance. | `G10` |

## Release gates

### G0 - Executable engineering baseline

**After / unlocks / status:** `W0` / `W1` / `APPROVED`

**Criteria:**

- Fresh clone can run validation and build skeleton artifacts.
- Backlog dependencies, capability campaigns, slice reviews, and task transitions validate automatically.
- Architecture constraints and ADR process are documented.
- Approved UI reference, workflow catalog, page contracts, and design-first automation are installed and validated.

### G1 - Durable Windows local application core

**After / unlocks / status:** `W1` / `W2` / `PENDING`

**Criteria:**

- Signed-development Windows desktop shell starts and supervises the compatible local service.
- Projects persist safely in SQLite and encrypted local storage.
- Provenance, workflows, human gates, and stale-output propagation operate end to end.
- Project creation stores a versioned primary use case and the desktop renders its ordered workflow while preserving access to all tools.

### G2 - Inspectable Windows local corpus

**After / unlocks / status:** `W2` / `W3` / `PENDING`

**Criteria:**

- References and lawful documents can be ingested, reconciled, parsed, and inspected.
- Every document-derived object resolves to an immutable document revision and source anchor.
- Rights and discovery provenance travel with corpus records.

### G3 - Windows local evidence workbench

**After / unlocks / status:** `W3` / `W4` / `PENDING`

**Criteria:**

- Hybrid retrieval, transparent screening, local/approved AI, extraction, verification, and evidence matrices work on benchmark corpora.
- Offline operation does not require an account or container runtime.
- Quality and uncertainty are visible rather than collapsed into one score.

### G4 - Minimum compelling Windows scholarly-reasoning product

**After / unlocks / status:** `W4` / `W5` / `PENDING`

**Criteria:**

- Claims, constructs, methods, contexts, and evidence are traceable through the local graph.
- Synthesis claims pass citation-support checks.
- Nearest-prior comparison produces bounded novelty language and an auditable dossier.

### G5 - Windows PC/lab version 1.0

**After / unlocks / status:** `W5` / `W6` / `PENDING`

**Criteria:**

- Windows installer, upgrade, backup, restore, offline, accessibility, security, and recovery tests pass.
- Representative individual and lab pilot workflows complete without developer intervention.
- All literature-analysis workflows and the Academic Minimal UI reference pass conformance and researcher usability acceptance.
- macOS/Linux, research-production, university, and cloud execution remain gated until this release is approved.

### G6 - Cross-platform desktop version 1.0

**After / unlocks / status:** `W6` / `W7` / `PENDING`

**Criteria:**

- The same desktop and local project format install, upgrade, back up, restore, and run offline on Windows x64, Apple Silicon macOS, Linux x86_64, and Linux ARM64.
- Platform credential stores, signed/notarized or verifiable packages, sidecars, parsers, vector adapters, and local model fallbacks pass security and recovery tests.
- At least one NVIDIA DGX Spark-class ARM64 Linux lab machine completes the representative local workflow and GPU/model qualification where hardware is available.
- Projects and evidence remain portable across qualified desktop operating systems without semantic drift.

### G7 - Study design and manuscript foundation

**After / unlocks / status:** `W7` / `W8` / `PENDING`

**Criteria:**

- Critical and hermeneutic research support exposes evidence-linked assumptions, alternative readings, memo lineage, and human interpretive authority before critical/theory article production.
- Evidence-grounded empirical study designs include alternatives, assumptions, methods, measurement, sampling, analysis, validity, ethics, and reproducibility plans.
- Empirical, theory, and critical conference/journal skeletons are generated from governed generic or verified venue profiles without fabricating requirements.
- Study designs and manuscript blueprints are versioned, source-linked, inspectable, and human approved.
- Cross-platform desktop acceptance covers the new design and blueprint workspaces.

### G8 - End-to-end research-production desktop

**After / unlocks / status:** `W8` / `W9`, `W10` / `PENDING`

**Criteria:**

- Private technical reports can be uploaded, parsed, reconciled with study plans, verified, and linked to exact report passages, tables, and figures.
- Empirical, theory, and critical manuscripts can be drafted from the approved skeleton, literature evidence, verified technical-report evidence, and researcher-authored content without invented results or unsupported citations.
- Generated or uploaded drafts can undergo independent multi-role reviewer simulation, editorial synthesis, revision planning, response-to-reviewers, and auditable redrafting.
- Representative end-to-end research projects complete on qualified desktop platforms with source, disclosure, privacy, and authorship controls.

### G9 - Advanced research-intelligence preview

**After / unlocks / status:** `W9` / - / `PENDING`

**Criteria:**

- Advanced detectors are labeled as candidates and benchmarked separately by opportunity type and false-positive risk.
- Opportunity ranking, portfolio governance, duplication/convergence monitoring, and detector evidence remain transparent and multi-objective.
- Living-monitor changes propagate to affected designs, manuscripts, reviews, claims, syntheses, and dossiers.

### G10 - University pilot

**After / unlocks / status:** `W10` / `W11` / `PENDING`

**Criteria:**

- Institutional deployment meets identity, rights, isolation, backup, observability, and support requirements.
- Desktop remote mode uses the same stable domain contracts as local mode.
- A university pilot completes a full literature-to-study/manuscript/review workflow.

### G11 - Cloud limited availability

**After / unlocks / status:** `W11` / - / `PENDING`

**Criteria:**

- Tenant isolation, residency, metering, security operations, and disaster recovery are independently validated.
- Cloud use does not weaken evidence provenance, technical-report confidentiality, manuscript authorship, or rights controls.
- Cost and reliability targets are met under representative research-production workloads.

## Architecture constraints

- The Tauri desktop application is the canonical user interface for local, university-hosted, and cloud-hosted deployments. Windows is implemented and released first; the same codebase is qualified on Apple Silicon macOS and Linux x86_64/ARM64 in W6.
- The local desktop edition must be complete, account-optional, offline-capable, and installable without Docker, Kubernetes, or a separately administered database on every qualified desktop platform.
- The desktop is Tauri 2 with React and TypeScript; local analytical services are Python/FastAPI sidecars with explicit version handshakes and platform-specific packaging only at the outer boundary.
- Local canonical state uses SQLite in WAL mode and an encrypted, content-addressed local object store; FTS5 is the first lexical index.
- Durable evidence, provenance, ontologies, decisions, study designs, technical-report results, manuscripts, reviewer reports, and workflow state must outlive any model, prompt, vector engine, or commercial provider.
- Model access is provider-neutral. Local inference is supported through hardware-aware adapters; remote providers are explicit, policy-controlled, and never required for basic local use.
- Every consequential analytical or authored object must retain source, transformation, model/schema/template version, confidence, human decision, and stale-dependency lineage.
- Opportunity generation and novelty challenge are separate roles and workflows; neither may silently certify universal novelty.
- Study-design recommendations present alternatives, assumptions, evidence, feasibility, validity, ethics, and residual uncertainty; the platform does not represent generated designs as approved protocols or institutional ethics approval.
- Empirical manuscript text may use only verified literature evidence, verified technical-report/result evidence, explicit researcher-authored statements, or visibly marked unresolved placeholders. The system must never invent methods, sample sizes, analyses, results, tables, figures, or citations.
- Critical and theory drafting preserves competing interpretations, conceptual plurality, author voice, and non-propositional forms where appropriate rather than imposing a positivist article structure.
- Reviewer simulation uses independent role-bounded contexts, records evidence and uncertainty, avoids impersonating named real reviewers, and never represents simulated editorial outcomes as acceptance probabilities or actual peer review.
- Rights, confidentiality, and entitlement metadata are enforced at acquisition, model egress, collaboration, manuscript drafting, report use, export, synchronization, and deletion boundaries.
- University and cloud services implement the same versioned domain contracts rather than creating a separate product architecture.
- During W0-W5, create only the Windows local desktop, core, worker, contracts, tests, documentation, task control, and Windows packaging structure. W6 adds macOS/Linux packaging and platform adapters; hosted infrastructure remains absent until W10.
- The local vector backend remains behind a replaceable port. Select the production adapter through cross-platform reliability, recovery, filtering, portability, and performance benchmarks plus ADR.
- Native scholarly and technical-report formats are preferred. Docling is the baseline local document parser; manuscript and report parsers preserve source locations, tables, figures, revisions, and rights metadata.
- The approved UI reference under design/ui-reference is normative for user-facing routes, workflow profiles, required regions, tokens, semantic states, accessibility behavior, authoring/review interactions, and light/dark parity; mock content and values remain illustrative.
- Every project selects one versioned primary scholarly use case from the approved workflow catalog. That profile orders navigation, defaults, checkpoints, next-step guidance, and expected outputs while the complete tool inventory remains accessible.
- Intentional user-facing changes follow design first: update the style guide, workflow/page contracts, and HTML reference; validate them; obtain human approval; only then implement application code.

## Selection policy

- Treat the YAML backlog as the authoritative execution ledger; DOCX and Markdown are generated views.
- The default automated execution unit is a capability campaign. Select one eligible capability, then complete its slices in declared dependency order until the capability exit criteria are production-ready and independently approved.
- Within the active capability, a slice is the integration and review checkpoint and a task is the atomic implementation/evidence unit. Do not hop to unrelated capabilities merely because another task is READY.
- Start the next slice only after every required task in the current slice is DONE, slice-level end-to-end evidence is attached, and the slice review is approved.
- Close a capability only after all slices are approved, the capability-wide end-to-end profile passes on the reviewed commit, the capability exit criteria are mapped to evidence, and an independent reviewer approves the campaign.
- A capability campaign may pause only for an external dependency, explicit human/ADR/design gate, unavailable required platform, or a blocker that cannot be resolved within the capability boundary. Record the blocker and resume the same campaign when cleared.
- Select only tasks whose dependencies are DONE and whose wave activation gate is approved. The capability campaign keeps priority over other eligible tasks until complete or formally paused.
- Filter by deployment profile and platform target. W0-W5 form the Windows baseline; W6 qualifies macOS/Linux; W7-W8 add research production; W9 and W10 are parallel advanced-intelligence and university tracks after G8; W11 remains cloud-only after G10.
- Claim atomically with taskctl before edits. Capability, slice, and task leases record owner, branch/worktree, base SHA, and expiration.
- Implement the complete selected task and the slice integration needed to satisfy its acceptance criteria. Record newly discovered work as backlog tasks rather than hidden TODOs.
- Remain IN_PROGRESS while running verification. Attach criterion-to-evidence records tied to the exact commit, then submit to REVIEW only when required checks pass.
- A separate reviewer or review agent approves REVIEW to DONE. Changes requested return the task to IN_PROGRESS or BLOCKED with a reason.
- Never renumber existing IDs. New work receives the next task ID in the appropriate slice or a new slice/capability ID.
- For intentional user-facing behavior, an approved UI-reference revision must exist before application implementation. Reference-change tasks precede application-change tasks.

## Definition of ready

- The containing capability campaign is eligible or explicitly selected, and all predecessor capabilities required by its first active slice are complete or gated.
- Status is READY and all dependency task IDs are DONE.
- The task wave has no activation gate or its activation gate is approved.
- The objective, deliverable, acceptance criteria, verification profiles, platform targets, and review gate are understandable without hidden context.
- Required architecture, experience, template, or scholarly-method decisions exist or the task explicitly creates them.
- Required credentials, fixtures, models, reports, and platforms are available or intentionally stubbed.
- No unresolved blocker or active conflicting lease is recorded.
- For intentional user-facing change, the proposed style-guide/workflow/page-reference revision is validated and approved, and its reference ID is recorded on the task.

## Definition of done

- Deliverables and all task acceptance criteria are satisfied.
- Verification commands pass on the reviewed commit and criterion-to-evidence records are attached.
- Security, privacy, rights, accessibility, scholarly-method, platform, migration, or release gates are completed when specified.
- Documentation, tests, migrations, fixtures, provenance, and stale-dependency behavior are updated as relevant.
- An independent reviewer sets review.result to approved and status to DONE.
- Newly discovered work is recorded as explicit backlog tasks rather than hidden TODOs.
- The task lease is released and branch/worktree disposition is recorded.
- User-facing implementation conforms to the approved reference ID through token, route/page-contract, workflow-navigation, accessibility, and visual-regression evidence.
- Task completion does not by itself complete the slice or capability; slice and capability end-to-end reviews must also pass.

# Capability, slice, and task plan

## CAP-00 - Delivery foundation and Codex execution system

**Campaign / completion:** `COMPLETE` / `APPROVED`

**Objective:** Create a reproducible repository, architecture and approved-experience guardrails, validation system, and machine-readable backlog that make small AI-authored changes safe and reviewable.

**Exit criteria:**

- A fresh clone can bootstrap, lint, type-check, test, and build skeleton artifacts through documented commands.
- Codex can identify READY work, claim it, attach evidence, and advance status without corrupting dependencies.
- Architecture changes require an ADR and automated boundary checks prevent accidental coupling.
- The approved style guide, workflow catalog, and HTML reference are stored in-repository and deterministic checks prevent unapproved user-facing implementation or drift.

### CAP-00.S01 - Repository and toolchain bootstrap

**Outcome:** A deterministic monorepo skeleton supports desktop, Python service, shared contracts, tests, packaging, and documentation.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** -

#### - [x] CAP-00.S01.T01 - Create the monorepo directory and package structure

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** -

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Versioned W0-W5 repository structure for desktop, core service, workers, shared contracts, tests, documentation, task control, and Windows packaging.

**Deliverables:**

- Versioned W0-W5 repository structure for desktop, core service, workers, shared contracts, tests, documentation, task control, and Windows packaging.

**Acceptance criteria:**

- A fresh checkout exposes the documented W0-W5 modules, contains no generated binaries, and each module has an owner/readme describing its boundary.
- Deferred university/cloud implementation paths such as admin-console, Helm, Terraform, tenancy, SSO, PostgreSQL, and Temporal are absent; only stable interfaces or documentation may reference them.
- The supplied backlog, schema, and bootstrap taskctl validator are copied without renumbering IDs; full selection/transition hardening remains CAP-00.S04.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S01.T01.json` at `59024eea93130c1d867a46782cb353cff4b88ff4`

#### - [x] CAP-00.S01.T02 - Pin language runtimes and dependency managers

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Committed Node, Rust, Python, and package-manager version declarations plus deterministic lockfiles.

**Deliverables:**

- Committed Node, Rust, Python, and package-manager version declarations plus deterministic lockfiles.

**Acceptance criteria:**

- Bootstrap rejects unsupported runtimes with an actionable message; lockfile-only installs complete without unplanned dependency resolution.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S01.T02.json` at `0f60cf5d3c1d893e178b7a286724f9817a444781`

#### - [x] CAP-00.S01.T03 - Implement one-command developer bootstrap

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T02`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Cross-platform bootstrap command with Windows-first behavior, prerequisite checks, local virtual environments, and generated development configuration.

**Deliverables:**

- Cross-platform bootstrap command with Windows-first behavior, prerequisite checks, local virtual environments, and generated development configuration.

**Acceptance criteria:**

- On a clean Windows test environment the command installs project dependencies, creates only documented local files, and ends with a passing smoke check.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S01.T03.json` at `ed7d2058e0bfe94426975711763036bc0aed1aa4`

### CAP-00.S02 - Architecture and agent operating contract

**Outcome:** Human and AI contributors receive explicit boundaries, conventions, and change-control rules.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T01`

#### - [x] CAP-00.S02.T01 - Write the repository architecture map and dependency rules

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Architecture overview, module dependency diagram, allowed dependency matrix, and stable interface list.

**Deliverables:**

- Architecture overview, module dependency diagram, allowed dependency matrix, and stable interface list.

**Acceptance criteria:**

- Every top-level module has a stated purpose; prohibited dependency directions are explicit; local, university, and cloud boundaries match the architecture baseline.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S02.T01.json` at `b9f5796e136d4c3cd7480ed011527955ed17ed87`

#### - [x] CAP-00.S02.T02 - Create Codex implementation instructions and task protocol

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S02.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Repository-level AGENTS/CODEX guidance covering task selection, scope control, testing, evidence, security, and status transitions.

**Deliverables:**

- Repository-level AGENTS/CODEX guidance covering task selection, scope control, testing, evidence, security, and status transitions.

**Acceptance criteria:**

- An unfamiliar coding agent can select a READY task and state the permitted scope, required checks, and completion protocol without additional oral instruction.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S02.T02.json` at `b8bc0062900d71757f7ece740281f4d7eee1248c`

#### - [x] CAP-00.S02.T03 - Establish architecture decision record workflow

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S02.T02`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** ADR template, index, decision states, and review rule for architecture-affecting changes.

**Deliverables:**

- ADR template, index, decision states, and review rule for architecture-affecting changes.

**Acceptance criteria:**

- A sample ADR can be created and linked from a task; CI detects unindexed ADRs and changes to protected interfaces without an associated decision record.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S02.T03.json` at `34942ab30a6afe0f36da7ddb260bb6b9b213441a`

### CAP-00.S03 - Verification, CI, and supply-chain controls

**Outcome:** Every task can invoke consistent, composable verification profiles locally and in CI.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T03`, `CAP-00.S02.T03`

#### - [x] CAP-00.S03.T01 - Implement the verification profile runner

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T03`, `CAP-00.S02.T03`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** tools/verify.py with named task-facing profiles: foundation, desktop, service, data, documents, search, ai, evidence, graph, novelty, e2e-local, security-local, server, and cloud.

**Deliverables:**

- tools/verify.py with named task-facing profiles: foundation, desktop, service, data, documents, search, ai, evidence, graph, novelty, e2e-local, security-local, server, and cloud.

**Acceptance criteria:**

- Each profile reports commands, duration, and failure cause; profiles can run independently; an unknown profile fails safely; initial foundation profile passes.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.
- The desktop verification profile can invoke UI-reference integrity, token, route/page-contract, workflow, accessibility, and visual-regression subchecks once CAP-00.S06 is installed.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S03.T01.json` at `69657fc7cb993d2f1757e6e6b208bf4f1cefe977`

#### - [x] CAP-00.S03.T02 - Create continuous-integration pipelines and artifact retention

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S03.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** CI jobs for formatting, linting, types, unit tests, contract tests, packaging smoke tests, and retained evidence artifacts.

**Deliverables:**

- CI jobs for formatting, linting, types, unit tests, contract tests, packaging smoke tests, and retained evidence artifacts.

**Acceptance criteria:**

- Pull requests receive deterministic checks; failure artifacts are downloadable; jobs use pinned toolchains and do not require production secrets.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S03.T02.json` at `9877766796b94bfa63faf35c767b095191f203ab`
- `artifacts/evidence/CAP-00.S03.T02.review-fix.json` at `7fe9165caf44aeb59f6e2bb2549dcb23a059afbb`

#### - [x] CAP-00.S03.T03 - Add dependency, license, secret, and vulnerability scanning

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S03.T02`

**Owner / review:** codex / codex-security-review (`approved`)

**Objective:** Automated software-composition analysis, secret detection, license allow/deny policy, and vulnerability reporting.

**Deliverables:**

- Automated software-composition analysis, secret detection, license allow/deny policy, and vulnerability reporting.

**Acceptance criteria:**

- Known test violations are detected; acceptable exceptions require a time-bounded, reviewed record; release-blocking severity thresholds are enforced.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate
- python tools/verify.py --profile security-local

**Evidence:**

- `artifacts/evidence/CAP-00.S03.T03.json` at `7352470d1f9fcd7cacea1bfa604df364a70c1a37`
- `artifacts/evidence/CAP-00.S03.T03.review-fix.json` at `ce2474676425416a77822cea3e47fab804dc33d3`

### CAP-00.S04 - Executable backlog and status governance

**Outcome:** The YAML plan is validated and can be queried or updated safely by Codex and reviewers.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S03.T01`

#### - [x] CAP-00.S04.T01 - Define and validate the backlog schema

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S03.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** JSON Schema or Pydantic model for capabilities, slices, tasks, dependencies, statuses, evidence, owners, and timestamps.

**Deliverables:**

- JSON Schema or Pydantic model for capabilities, slices, tasks, dependencies, statuses, evidence, owners, and timestamps.

**Acceptance criteria:**

- The delivered backlog validates; duplicate IDs, invalid statuses, missing dependencies, and dependency cycles fail with precise diagnostics.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S04.T01.json` at `7d016c5251a6a9385abe8205857ca18b16feb3ca`
- `artifacts/evidence/CAP-00.S04.T01.review-fix.json` at `1493a3cd6198286d6521b4c8cbc6230d68fc7f3c`

#### - [x] CAP-00.S04.T02 - Implement taskctl selection, gate, lease, evidence, and transition commands

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S04.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** CLI commands to validate, select, claim with a lease, block, attach evidence, submit for review, review, reopen, cancel, manage release gates, and report progress.

**Deliverables:**

- CLI commands to validate, select, claim with a lease, block, attach evidence, submit for review, review, reopen, cancel, manage release gates, and report progress.

**Acceptance criteria:**

- Commands enforce dependencies, activation gates, legal transitions, profile filtering, lease ownership, exact-commit evidence, stable IDs, and atomic writes; transition and corruption-recovery tests pass.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S04.T02.json` at `62c8252a79306c9ba4e3fc0798747b87f68be932`
- `artifacts/evidence/CAP-00.S04.T02.review-fix.json` at `438edadfc822f75a246ecbed40577f29b4524558`
- `artifacts/evidence/CAP-00.S04.T02.review-fix-2.json` at `412cce62a2994606d81c4a3dc538205bb3043138`

#### - [x] CAP-00.S04.T03 - Generate human-readable plan views from YAML

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S04.T02`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Deterministic Markdown and summary reports generated from the authoritative backlog.

**Deliverables:**

- Deterministic Markdown and summary reports generated from the authoritative backlog.

**Acceptance criteria:**

- Regeneration produces no diff when YAML is unchanged; counts and statuses match the source ledger; manual edits to generated sections are clearly prohibited.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S04.T03.json` at `e1755e15441e685bdea7354f5fcde0d85a2f6ce5`
- `artifacts/evidence/CAP-00.S04.T03.review-fix.json` at `5d9c1622c93a93b90afb9e2961b058fed983522c`

### CAP-00.S05 - Test corpus, benchmark registry, and release metadata

**Outcome:** Development begins with reusable fixtures and traceable versions rather than ad hoc documents or unverifiable demonstrations.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S04.T03`

#### - [x] CAP-00.S05.T01 - Create a legally redistributable miniature scholarly fixture corpus

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S04.T03`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Small fixture set containing metadata variants, duplicates, PDFs, structured full text, tables, citations, missing fields, and malformed inputs.

**Deliverables:**

- Small fixture set containing metadata variants, duplicates, PDFs, structured full text, tables, citations, missing fields, and malformed inputs.

**Acceptance criteria:**

- Licenses and provenance are recorded; fixtures cover declared edge cases; tests can run offline and deterministically.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S05.T01.json` at `7a4301dbd9de0e05472fe537c92c44e02b7fdee6`
- `artifacts/evidence/CAP-00.S05.T01.review-fix.json` at `5cafdf572fe68575f7a35618b56fda0faabb136e`
- `artifacts/evidence/CAP-00.S05.T01.review-fix-2.json` at `535b1be09a9b3054cc802463dd4b4bac383ec0e2`

#### - [x] CAP-00.S05.T02 - Establish golden-output and benchmark registry conventions

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S05.T01`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Registry format for datasets, expected outputs, tolerances, model versions, prompts, schemas, and evaluation results.

**Deliverables:**

- Registry format for datasets, expected outputs, tolerances, model versions, prompts, schemas, and evaluation results.

**Acceptance criteria:**

- At least one golden parsing and one contract benchmark run end to end; changes require explicit baseline approval rather than silent overwrite.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S05.T02.json` at `e207d56cb90ed4d02858737086ef1b3c6f06b299`
- `artifacts/evidence/CAP-00.S05.T02.review-fix.json` at `c959426487205bc3a883593169f9ca3c5484cc9f`
- `artifacts/evidence/CAP-00.S05.T02.review-fix-2.json` at `dd71a9dcc0c1021140ae101f9c1e73b7bd5bc984`
- `artifacts/evidence/CAP-00.S05.T02.review-fix-3.json` at `369abb4d638a958309240fdfb4aebe8cc0bf99c5`
- `artifacts/evidence/CAP-00.S05.T02.review-fix-4.json` at `4a5fc16ee30575f6f34482ff65d4cd6281f79f82`

#### - [x] CAP-00.S05.T03 - Implement version, changelog, and build-manifest generation

**Status / priority / estimate / risk:** `DONE` / `P0` / `S` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S05.T02`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Single product version source, generated component manifests, changelog convention, and reproducible build metadata.

**Deliverables:**

- Single product version source, generated component manifests, changelog convention, and reproducible build metadata.

**Acceptance criteria:**

- Desktop and sidecar report compatible versions; build artifacts contain commit, dependency, schema, and model-manifest identifiers; dirty builds are labeled.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S05.T03.json` at `23717be17f09ffe614829d7d1e1d44feff2b3d0d`
- `artifacts/evidence/CAP-00.S05.T03.review-fix.json` at `91be762a85bbecbf57f2a4b8d9eb2260a1653eb9`
- `artifacts/evidence/CAP-00.S05.T03.review-fix-2.json` at `4a3196c892db6717d4a78933675a057c486a42a3`
- `artifacts/evidence/CAP-00.S05.T03.review-fix-3.json` at `8534749677355438708f2d3e9e73d167a86e5911`
- `artifacts/evidence/CAP-00.S05.T03.review-fix-4.json` at `d2b2f10f40abf70c65e1c2ed2da85bc49914a4f8`
- `artifacts/evidence/CAP-00.S05.T03.review-fix-5.json` at `8b5bc27f13965fbb949257900abc54a192abf720`

### CAP-00.S06 - Approved experience reference and UI conformance automation

**Outcome:** The Academic Minimal style, page contracts, fourteen use-case workflows, and linked HTML prototypes form an approved in-repository reference that must precede and validate user-facing implementation.

**Wave / priority / status / review:** `W0` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T01`, `CAP-00.S02.T02`

#### - [x] CAP-00.S06.T01 - Install the governed Academic Minimal UI reference

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S01.T01`, `CAP-00.S02.T02`

**Owner / review:** codex / codex-review (`approved`)

**Objective:** Store the approved style guide, workflow catalog, capability/page contracts, linked HTML prototypes, shared assets, approval record, and deterministic generator under design/ui-reference.

**Deliverables:**

- A complete approved UI-reference tree at design/ui-reference with stable entry points and no network dependency.

**Acceptance criteria:**

- The repository contains the approved v1.3 style guide, exactly fourteen workflow profiles, 32 product page contracts, linked light/dark HTML references, approval metadata, and local assets.
- The reference identifies normative versus illustrative content and explicitly defers university/cloud administrator surfaces.
- A fresh clone can open prototype-index.html and traverse every page without broken or escaping links.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S06.T01.json` at `1acd8aa2ad13edc3c8d6938c2e0219010e8135e4`

#### - [x] CAP-00.S06.T02 - Implement UI-reference integrity and approval validation

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S06.T01`, `CAP-00.S03.T01`

**Owner / review:** codex / agent:descartes (`approved`)

**Objective:** Validate approval status, governed-file hashes, generator reproducibility, page inventory, capability coverage, workflow page references, local links, shared assets, and prohibited hosted-scope additions.

**Deliverables:**

- tools/ui_reference_check.py and foundation-profile integration with machine-readable reports.

**Acceptance criteria:**

- Validation fails for a missing or modified governed file, unapproved reference status, broken workflow step, missing page contract, package-escaping link, or unexpected hosted administration route.
- Validation passes on the supplied reference and produces a report containing the exact reference ID and hashes.
- Checks run without browser network access and are deterministic.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S06.T02.json` at `91668d26dc15327929430c6a0da098a2bdc1c4bb`
- `artifacts/evidence/CAP-00.S06.T02.review-fix.json` at `1e5954e60d0405631e56a7a45007a770b01ddb28`
- `artifacts/evidence/CAP-00.S06.T02.review-fix-2.json` at `1ee236ab5ea27a6d84cbf16047f3c858f163bd83`

#### - [x] CAP-00.S06.T03 - Implement design-first change gating

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S06.T02`, `CAP-00.S04.T02`

**Owner / review:** codex / agent:descartes (`approved`)

**Objective:** Require intentional UI/UX changes to update and approve the reference before application implementation; distinguish approved design change from defect restoration and record reference lineage in task and pull-request evidence.

**Deliverables:**

- Repository policy, task contract fields/checks, and pull-request validation for proposed-reference-before-code ordering.

**Acceptance criteria:**

- A pull request that intentionally changes user-facing routes, navigation, tokens, workflows, required regions, or interactions fails when no newer approved reference is present.
- A defect restoration that returns implementation to the current approved reference can proceed with a cited reference ID and focused evidence.
- Reference approval is a human gate; an implementation agent cannot approve its own reference revision.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S06.T03.json` at `5ef232e641d6ad4999a6b7c7c31315ad758820cb`
- `artifacts/evidence/CAP-00.S06.T03.review-fix.json` at `b12a715287bceec8c6f36405409a1db1b119f080`

#### - [x] CAP-00.S06.T04 - Implement UI implementation-conformance verification

**Status / priority / estimate / risk:** `DONE` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-00.S06.T03`

**Owner / review:** codex / agent:descartes (`approved`)

**Objective:** Compare the application against approved tokens, routes/page contracts, use-case workflows, navigation behavior, accessibility rules, responsive states, and visual baselines.

**Deliverables:**

- Desktop verification subchecks for token drift, route/page contracts, workflow conformance, accessibility, and Playwright visual regression in light and dark modes.

**Acceptance criteria:**

- The desktop profile checks all fourteen workflow profiles, primary and supporting-tool navigation, previous/next behavior, light/dark parity, keyboard/focus behavior, required regions, and approved token use.
- Visual regression uses controlled viewport, fonts, data, animation, and platform settings; intentional baseline changes require a new approved reference.
- Reports map each failure to a normative reference artifact and do not treat illustrative mock values as requirements.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/verify.py --profile desktop
- python tools/taskctl.py validate

**Evidence:**

- `artifacts/evidence/CAP-00.S06.T04.json` at `86c386e7c06a9e0b15cdfd5172eea665e120602e`
- `artifacts/evidence/CAP-00.S06.T04.review-fix.json` at `8fd281d2d1ca970394b2cbe23d1a5519f1a77d0f`
- `artifacts/evidence/CAP-00.S06.T04.review-fix-2.json` at `cf4f521e8e362061afb94245986c7bb6203852b2`
- `artifacts/evidence/CAP-00.S06.T04.review-fix-3.json` at `c9e0cec2bc295188353db3b7cf34d609c199805b`

## CAP-01 - Windows-first desktop shell and supervised local runtime

**Campaign / completion:** `ACTIVE` / `IN_PROGRESS`

**Objective:** Deliver the canonical Windows-first desktop experience and a reliably packaged local analytical service that requires no external server administration.

**Exit criteria:**

- The signed-development desktop application installs, launches, navigates, and supervises its compatible sidecar.
- Desktop-to-service communication is authenticated, versioned, observable, and recoverable.
- The same client architecture and project contracts are portable to macOS/Linux in CAP-14 and later connect to university/cloud profiles without forking the UI.

### CAP-01.S01 - Tauri and React application shell

**Outcome:** A production-shaped desktop shell provides navigation, project selection, commands, and application state.

**Wave / priority / status / review:** `W1` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-00.S01.T03`, `CAP-00.S03.T02`

#### - [x] CAP-01.S01.T01 - Bootstrap the Tauri 2 and React/TypeScript desktop application

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-00.S01.T03`, `CAP-00.S03.T02`

**Owner / review:** codex / agent:descartes (`approved`)

**Objective:** Runnable desktop package with strict TypeScript, routing, application state, and development/build commands.

**Deliverables:**

- Runnable desktop package with strict TypeScript, routing, application state, and development/build commands.

**Acceptance criteria:**

- The app launches on supported Windows, opens no unnecessary network ports, and passes desktop lint, type, unit, and build smoke checks.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S01.T01.json` at `79f8603492d5e593c76293dea66885ae6e010223`
- `artifacts/evidence/CAP-01.S01.T01.review-fix.json` at `493ce3b6f60474796b66e214603d0a83b29965b1`
- `artifacts/evidence/CAP-01.S01.T01.review-fix-2.json` at `e989c1393e1f3dfd30206105d7cedcfe7f811bd5`
- `artifacts/evidence/CAP-01.S01.T01.review-fix-3.json` at `4d3380d79ca436557e80e686a43993c9d71ba5e4`

#### - [x] CAP-01.S01.T02 - Implement the primary application frame and workspace routing

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `low`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S01.T01`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Title bar, navigation rail, command area, project context, route guards, and placeholder workspaces matching the product information architecture.

**Deliverables:**

- Title bar, navigation rail, command area, project context, route guards, and placeholder workspaces matching the product information architecture.

**Acceptance criteria:**

- All planned local workspaces are reachable by keyboard and deep link; invalid routes recover to a safe project home; no business logic is duplicated in views.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S01.T02.json` at `8c274496dd272f4079f16eaaef86a2d539876996`
- `artifacts/evidence/CAP-01.S01.T02.review-fix.json` at `5422bd749ba68274faf1f2744ebf8dc439aef6ff`
- `artifacts/evidence/CAP-01.S01.T02.review-fix-2.json` at `e19ecc726ebba7206fb06ce0fa51a228bd830fed`

#### - [x] CAP-01.S01.T03 - Add project switcher, recent projects, and empty-state flows

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S01.T02`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Project-selection experience that can open, create, and recover from unavailable local project locations.

**Deliverables:**

- Project-selection experience that can open, create, and recover from unavailable local project locations.

**Acceptance criteria:**

- Recent entries are deterministic and removable; missing projects show repair options; the app never silently creates a replacement project.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S01.T03.json` at `dae49529e536663d01bdb5cf7e3de40fdfaf24a3`

### CAP-01.S02 - Desktop design system and accessibility foundation

**Outcome:** Reusable components express status, provenance, evidence, uncertainty, and human decision states consistently.

**Wave / priority / status / review:** `W1` / `P0` / `DONE` / `APPROVED`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S01.T01`

#### - [x] CAP-01.S02.T01 - Implement design tokens and core components

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S01.T01`, `CAP-00.S06.T04`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Versioned typography, spacing, color, icon, form, table, dialog, notification, badge, and panel components.

**Deliverables:**

- Versioned typography, spacing, color, icon, form, table, dialog, notification, badge, and panel components.

**Acceptance criteria:**

- Components render consistently at 100-200% scaling, meet contrast requirements, and expose documented variants for status and uncertainty.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.
- Design tokens and reusable components are generated or implemented from the approved design/ui-reference baseline; no alternate visual system is introduced without a newer approved reference.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S02.T01.json` at `5c8dbac196c44bd97d1d21ca92ec848393e438c8`
- `artifacts/evidence/CAP-01.S02.T01.review-fix.json` at `2ad4146b32ec48080cf5189f65d7e30947310a07`
- `artifacts/evidence/CAP-01.S02.T01.review-fix-2.json` at `dc45d304489160acc9f2ab5646698e4d656c9b14`

#### - [x] CAP-01.S02.T02 - Establish keyboard, focus, and screen-reader behavior

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S02.T01`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Global focus management, skip links, shortcut registry, accessible names, live-region policy, and automated accessibility checks.

**Deliverables:**

- Global focus management, skip links, shortcut registry, accessible names, live-region policy, and automated accessibility checks.

**Acceptance criteria:**

- All shell functions operate without a pointer; focus is visible and restored after dialogs; automated checks report no critical violations on core routes.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S02.T02.json` at `b7f82e64764855c5c6cd4ee9b5ce107d3cb44a24`
- `artifacts/evidence/CAP-01.S02.T02.review-fix.json` at `c3306ffc2cfc7bd3988e99b5f43da1a9335c07a0`

#### - [x] CAP-01.S02.T03 - Create consistent loading, error, offline, and recovery states

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S02.T02`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Reusable boundary components for progress, partial results, retry, cancellation, degraded mode, and diagnostic references.

**Deliverables:**

- Reusable boundary components for progress, partial results, retry, cancellation, degraded mode, and diagnostic references.

**Acceptance criteria:**

- Injected service, network, and data failures produce actionable states without blank screens or data loss; error details are copyable without exposing secrets.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S02.T03.json` at `f5386c316ee1e4e559a134d2420dd4bb6a7cec22`
- `artifacts/evidence/CAP-01.S02.T03.review-fix.json` at `10d2bfb3151f3dbe12b3ea311dc33bf1a95bc11b`
- `artifacts/evidence/CAP-01.S02.T03.review-fix-2.json` at `a10563f8bcc9e9bfe892be95be3907ecf3c3a4f3`
- `artifacts/evidence/CAP-01.S02.T03.review-fix-3.json` at `b32e834d6206a9b77d71de5a664d0e5f334450a3`
- `artifacts/evidence/CAP-01.S02.T03.review-fix-4.json` at `cf9c63e4c603eb18e2d9c919f63dff77eb6b000d`
- `artifacts/evidence/CAP-01.S02.T03.review-fix-5.json` at `9f94e9433cb455a2c912ab4e14f3f22e92d7d929`

### CAP-01.S03 - Packaged Python/FastAPI sidecar

**Outcome:** The desktop bundles and supervises a compatible local service with no user-managed Python installation.

**Wave / priority / status / review:** `W1` / `P0` / `IN_PROGRESS` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-00.S03.T02`, `CAP-01.S01.T01`

#### - [x] CAP-01.S03.T01 - Create the modular FastAPI service skeleton

**Status / priority / estimate / risk:** `DONE` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-00.S03.T02`, `CAP-01.S01.T01`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Typed service application with health, readiness, version, configuration, logging, and module registration endpoints.

**Deliverables:**

- Typed service application with health, readiness, version, configuration, logging, and module registration endpoints.

**Acceptance criteria:**

- Service starts in an isolated development environment; OpenAPI is generated; startup validates configuration; unit and contract smoke tests pass.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

**Evidence:**

- `artifacts/evidence/CAP-01.S03.T01.json` at `c7f7395699097e4f963938184449b110ee7d8a25`
- `artifacts/evidence/CAP-01.S03.T01.review-fix.json` at `71f16111874bf006aaae18c5763678a03586c0b4`

#### - [x] CAP-01.S03.T02 - Package the Python service as a Windows sidecar artifact

**Status / priority / estimate / risk:** `DONE` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S03.T01`

**Owner / review:** codex / agent:maxwell (`approved`)

**Objective:** Repeatable sidecar build including pinned Python runtime/dependencies and required local helper binaries.

**Deliverables:**

- Repeatable sidecar build including pinned Python runtime/dependencies and required local helper binaries.

**Acceptance criteria:**

- Artifact runs on a clean supported Windows VM without a system Python; size and contents are inventoried; missing runtime dependencies are detected in CI.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile desktop

**Evidence:**

- `artifacts/evidence/CAP-01.S03.T02.json` at `bb7a1b9875fcc0b42e40460b350d7bf4dda11e0e`
- `artifacts/evidence/CAP-01.S03.T02.review-fix.json` at `1f563fd519e6e284905152440c96fd23d4432e5a`
- `artifacts/evidence/CAP-01.S03.T02.review-fix-2.json` at `b5c30e665e370465cc61d9c14539317121e506ff`

#### - [ ] CAP-01.S03.T03 - Implement sidecar lifecycle supervision in Tauri

**Status / priority / estimate / risk:** `IN_PROGRESS` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S03.T02`

**Owner / review:** codex / agent:curie (`changes-requested`)

**Objective:** Desktop-controlled start, health polling, graceful stop, crash detection, bounded restart, and log collection.

**Deliverables:**

- Desktop-controlled start, health polling, graceful stop, crash detection, bounded restart, and log collection.

**Acceptance criteria:**

- Only one compatible sidecar serves an app instance; crashes produce diagnostic UI and safe retry; app shutdown does not orphan processes or lock projects.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

**Evidence:**

- `artifacts/evidence/CAP-01.S03.T03.json` at `ba98a62eee68f428eb11fdd5064ed142a9d47d22`
- `artifacts/evidence/CAP-01.S03.T03.review-fix.json` at `45a80cc559548e100add72ef0d8bd7f947d335fa`

### CAP-01.S04 - Authenticated desktop-service contract

**Outcome:** Local IPC is private, versioned, cancellable, and observable.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S03.T03`

#### - [ ] CAP-01.S04.T01 - Implement loopback authentication and endpoint binding controls

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Per-launch authentication token, loopback-only binding, strict origin policy, and token rotation/cleanup.

**Deliverables:**

- Per-launch authentication token, loopback-only binding, strict origin policy, and token rotation/cleanup.

**Acceptance criteria:**

- Requests without the current token fail; service is unreachable from non-loopback interfaces; secrets are not written to ordinary logs or crash reports.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile security-local

#### - [ ] CAP-01.S04.T02 - Generate and consume versioned API contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** OpenAPI-derived TypeScript client, error envelope, pagination, job-status, cancellation, and compatibility rules.

**Deliverables:**

- OpenAPI-derived TypeScript client, error envelope, pagination, job-status, cancellation, and compatibility rules.

**Acceptance criteria:**

- Client compilation detects contract drift; desktop blocks incompatible sidecars with a clear remediation path; errors preserve trace IDs and safe details.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service

#### - [ ] CAP-01.S04.T03 - Build desktop diagnostics and support-bundle collection

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-01.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Diagnostics page for component versions, health, storage paths, resource use, recent failures, and redacted support export.

**Deliverables:**

- Diagnostics page for component versions, health, storage paths, resource use, recent failures, and redacted support export.

**Acceptance criteria:**

- A user can generate a bounded support bundle without project documents or secrets; diagnostic data links desktop actions to service trace IDs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile security-local

### CAP-01.S05 - Windows installation and update channels

**Outcome:** The PC/lab application can be installed, upgraded, repaired, and removed predictably by individuals or lab administrators.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S04.T03`, `CAP-00.S05.T03`

#### - [ ] CAP-01.S05.T01 - Create per-user and per-machine Windows installers

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S04.T03`, `CAP-00.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** MSI/MSIX or approved Tauri installer variants with prerequisites, file associations, protocol registration, and uninstall behavior.

**Deliverables:**

- MSI/MSIX or approved Tauri installer variants with prerequisites, file associations, protocol registration, and uninstall behavior.

**Acceptance criteria:**

- Clean install, repair, and uninstall pass on supported Windows versions; user data is preserved by default and removable only through an explicit action.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-01.S05.T02 - Implement signed update manifests and release channels

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Stable, beta, and development update channels with signature verification, compatibility checks, rollback metadata, and staged rollout controls.

**Deliverables:**

- Stable, beta, and development update channels with signature verification, compatibility checks, rollback metadata, and staged rollout controls.

**Acceptance criteria:**

- Tampered or incompatible updates are rejected; interrupted updates recover to the prior working version; automatic download is policy-configurable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

#### - [ ] CAP-01.S05.T03 - Support silent lab deployment and policy configuration

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Documented silent install/uninstall switches, machine policy file, fixed data/model locations, update controls, and log location.

**Deliverables:**

- Documented silent install/uninstall switches, machine policy file, fixed data/model locations, update controls, and log location.

**Acceptance criteria:**

- A lab administrator can deploy and configure the app non-interactively; user-level settings cannot override protected machine policy; diagnostics show effective policy.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile e2e-local

## CAP-02 - Local projects, durable storage, security, and recovery

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Provide safe project lifecycle, local persistence, encrypted content storage, secrets management, and portable recovery for individual and laboratory computers.

**Exit criteria:**

- Projects survive crashes, application upgrades, relocations, and verified backup/restore cycles.
- Sensitive documents and credentials are protected with explicit local threat assumptions.
- A lab can configure approved storage and model-cache locations without converting the product into a server deployment.

### CAP-02.S01 - Local project lifecycle and directory contract

**Outcome:** Projects have explicit identity, version, location, lifecycle state, and safe-open semantics.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-00.S01.T03`, `CAP-01.S04.T02`

#### - [ ] CAP-02.S01.T01 - Define the local project package and directory layout

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-00.S01.T03`, `CAP-01.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Documented layout for database, objects, indexes, caches, models, exports, locks, configuration, and temporary work.

**Deliverables:**

- Documented layout for database, objects, indexes, caches, models, exports, locks, configuration, and temporary work.

**Acceptance criteria:**

- Every file class has retention, backup, and deletion semantics; paths are relocatable; transient data is excluded from portable exports.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data

#### - [ ] CAP-02.S01.T02 - Implement create, open, close, archive, and delete workflows

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Service and desktop flows for project lifecycle with names, IDs, locations, templates, and confirmation gates.

**Deliverables:**

- Service and desktop flows for project lifecycle with names, IDs, locations, templates, and confirmation gates.

**Acceptance criteria:**

- Concurrent open attempts are detected; archive is reversible; deletion distinguishes project records from shared model caches and requires explicit confirmation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile desktop

#### - [ ] CAP-02.S01.T03 - Add project compatibility and safe-open checks

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Project format version, migration requirement, damaged/incomplete indicators, read-only fallback, and repair entry points.

**Deliverables:**

- Project format version, migration requirement, damaged/incomplete indicators, read-only fallback, and repair entry points.

**Acceptance criteria:**

- Newer unsupported projects never open for write; failed validation cannot mutate the project; user receives a clear backup-first remediation path.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

### CAP-02.S02 - SQLite schema, migrations, and repository layer

**Outcome:** Canonical local state is transactional, versioned, testable, and insulated from UI or model code.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S01.T01`, `CAP-03.S01.T01`

#### - [ ] CAP-02.S02.T01 - Create the initial normalized SQLite schema in WAL mode

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S01.T01`, `CAP-03.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Core tables for projects, scholarly records, documents, workflows, evidence, ontologies, decisions, provenance, and settings.

**Deliverables:**

- Core tables for projects, scholarly records, documents, workflows, evidence, ontologies, decisions, provenance, and settings.

**Acceptance criteria:**

- Foreign keys and integrity constraints are enabled; concurrent read/write smoke tests pass; schema includes stable IDs and timestamps without storing derived blobs in arbitrary tables.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data

#### - [ ] CAP-02.S02.T02 - Implement forward migrations and backup-before-migrate policy

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Ordered migration framework, schema history, dry-run/reporting, automatic pre-migration backup, and failure rollback.

**Deliverables:**

- Ordered migration framework, schema history, dry-run/reporting, automatic pre-migration backup, and failure rollback.

**Acceptance criteria:**

- Migrations are idempotently detected, never partially commit, preserve a restorable backup, and are tested from every supported prior schema fixture.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-02.S02.T03 - Build typed repositories and transaction boundaries

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Repository interfaces for canonical aggregates plus unit-of-work patterns and deterministic test helpers.

**Deliverables:**

- Repository interfaces for canonical aggregates plus unit-of-work patterns and deterministic test helpers.

**Acceptance criteria:**

- Business modules do not issue ad hoc SQL outside the data layer; transaction failure leaves no partial aggregate; repository tests cover optimistic conflict and not-found behavior.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data

### CAP-02.S03 - Encrypted local object and cache storage

**Outcome:** Documents, page images, snapshots, models, and exports use content-addressed storage with integrity and rights metadata.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S02.T01`

#### - [ ] CAP-02.S03.T01 - Implement content-addressed object storage abstraction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Streaming put/get/delete, hashes, metadata, reference counting, atomic writes, and corruption detection.

**Deliverables:**

- Streaming put/get/delete, hashes, metadata, reference counting, atomic writes, and corruption detection.

**Acceptance criteria:**

- Duplicate content is stored once within a project scope; interrupted writes are not visible; hash mismatch is detected before downstream use.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data

#### - [ ] CAP-02.S03.T02 - Add encryption-at-rest and key-version metadata

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Authenticated encryption for protected objects, key identifiers, nonce handling, rotation-ready metadata, and unencrypted fixture mode for tests.

**Deliverables:**

- Authenticated encryption for protected objects, key identifiers, nonce handling, rotation-ready metadata, and unencrypted fixture mode for tests.

**Acceptance criteria:**

- Ciphertext tampering is detected; plaintext is not persisted in logs or temporary directories; key loss produces a bounded, explicit failure rather than silent corruption.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile security-local

#### - [ ] CAP-02.S03.T03 - Implement storage accounting, quotas, garbage collection, and cache eviction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Per-project and shared-cache usage metrics, soft/hard thresholds, orphan detection, preview, and safe cleanup.

**Deliverables:**

- Per-project and shared-cache usage metrics, soft/hard thresholds, orphan detection, preview, and safe cleanup.

**Acceptance criteria:**

- Cleanup never removes referenced canonical objects; users can inspect reclaimed categories before destructive actions; low-disk conditions trigger graceful degradation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

### CAP-02.S04 - Local secrets, profiles, and privacy controls

**Outcome:** Credentials and policy-sensitive configuration are isolated from ordinary project content.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S03.T02`

#### - [ ] CAP-02.S04.T01 - Integrate Windows credential storage for secrets

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** OS-protected storage adapter for provider keys, connector tokens, signing trust, and encryption key material.

**Deliverables:**

- OS-protected storage adapter for provider keys, connector tokens, signing trust, and encryption key material.

**Acceptance criteria:**

- Secrets never appear in SQLite, project exports, support bundles, or process arguments; retrieval failures are recoverable and testable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile security-local

#### - [ ] CAP-02.S04.T02 - Implement local user profile and application-lock behavior

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Optional local profile name, inactivity lock, project lock state, and protected reauthentication without requiring a cloud account.

**Deliverables:**

- Optional local profile name, inactivity lock, project lock state, and protected reauthentication without requiring a cloud account.

**Acceptance criteria:**

- Locking removes sensitive content from view, cancels protected actions, and does not claim to provide Windows-account isolation beyond documented assumptions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

#### - [ ] CAP-02.S04.T03 - Create privacy, telemetry, retention, and secure-deletion settings

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-02.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Default-off telemetry, local log retention, provider egress choices, document retention, cache clearing, and best-effort secure deletion disclosures.

**Deliverables:**

- Default-off telemetry, local log retention, provider egress choices, document retention, cache clearing, and best-effort secure deletion disclosures.

**Acceptance criteria:**

- Defaults keep research content local; changing egress requires informed consent; deletion accurately reports guarantees and filesystem limitations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

#### - [ ] CAP-02.S04.T04 - Select and implement the protected local project-database profile

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S04.T01`, `CAP-02.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** ADR-selected production protection for the SQLite project database using SQLCipher or an evaluated equivalent, with Windows credential-backed keys, migration, rekey, recovery, and performance evidence.

**Deliverables:**

- ADR-selected production protection for the SQLite project database using SQLCipher or an evaluated equivalent, with Windows credential-backed keys, migration, rekey, recovery, and performance evidence.

**Acceptance criteria:**

- The production PC/lab profile cannot create or open a writable plaintext project database; an explicitly labeled development/test fixture mode is the only exception.
- Keys never appear in project files, exports, logs, environment dumps, or process arguments; migration, backup/restore, rekey, key-loss, corruption, and crash-recovery tests pass on supported Windows.
- The ADR records threat assumptions, benchmark results, licensing/packaging implications, fallback and rollback behavior, and residual dependence on OS/full-disk protection.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile security-local
- python tools/verify.py --profile e2e-local

### CAP-02.S05 - Backup, restore, relocation, and lab portability

**Outcome:** Researchers can protect and move projects without breaking identities, provenance, or evidence links.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S04.T03`, `CAP-03.S05.T03`

#### - [ ] CAP-02.S05.T01 - Implement consistent project snapshot and backup creation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S04.T03`, `CAP-02.S04.T04`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Quiesced or online-consistent snapshot format with manifest, database backup, object inventory, checksums, version, and optional encryption.

**Deliverables:**

- Quiesced or online-consistent snapshot format with manifest, database backup, object inventory, checksums, version, and optional encryption.

**Acceptance criteria:**

- Backup taken during active reads restores to a consistent state; missing objects fail verification; secrets and excluded caches follow declared policy.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-02.S05.T02 - Implement verified restore, clone, and relocation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Restore wizard and service operations for original restore, clone-as-new, location change, and conflict handling.

**Deliverables:**

- Restore wizard and service operations for original restore, clone-as-new, location change, and conflict handling.

**Acceptance criteria:**

- Restore validates before replacement, preserves stable IDs for true restore, issues new project identity for clone, and never overwrites an existing project silently.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile desktop
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-02.S05.T03 - Create portable lab project and shared-cache conventions

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-02.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Admin-configurable project roots, read/write checks, optional removable-media package, and a separately governed shared model/cache directory.

**Deliverables:**

- Admin-configurable project roots, read/write checks, optional removable-media package, and a separately governed shared model/cache directory.

**Acceptance criteria:**

- A project moved between approved lab PCs opens with intact evidence anchors; machine policy controls shared paths; simultaneous write on unsupported shared filesystems is blocked.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

## CAP-03 - Canonical domain, research intent, provenance, and durable workflows

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Define canonical research objects, a versioned research-intent and primary-use-case contract, provenance, adaptive objective-specific workflows, durable jobs, human gates, and controlled recalculation.

**Exit criteria:**

- Core aggregates and APIs have stable identifiers, explicit versioning, and tested state machines.
- Every consequential transformation records inputs, policy, software/model/schema versions, output, and human disposition.
- Long-running work is resumable, cancellable, resource-governed, and capable of marking downstream outputs stale.
- Each project has a versioned primary use case that produces an ordered, visible workflow and next-step guidance while preserving access to all tools and prior workflow history.
- Study designs, technical reports/results, manuscript sections, reviewer rounds, and revision actions use the same durable workflow, provenance, staleness, and human-gate model.

### CAP-03.S01 - Canonical identifiers and domain contracts

**Outcome:** A small stable core model defines records, documents, evidence, decisions, workflows, ontologies, graphs, opportunities, and monitoring events.

**Wave / priority / status / review:** `W1` / `P0` / `READY` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-00.S02.T01`, `CAP-00.S05.T03`

#### - [ ] CAP-03.S01.T01 - Define core aggregate and value-object contracts

**Status / priority / estimate / risk:** `READY` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-00.S02.T01`, `CAP-00.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Language-neutral schema definitions for IDs, versions, timestamps, source references, status, confidence, rights, and principal aggregates.

**Deliverables:**

- Language-neutral schema definitions for IDs, versions, timestamps, source references, status, confidence, rights, and principal aggregates.

**Acceptance criteria:**

- Contracts preserve observed wording and allow disputed alternatives; generated Python and TypeScript types pass compatibility tests.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate
- python tools/verify.py --profile service

#### - [ ] CAP-03.S01.T02 - Define aggregate state machines and invariants

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Explicit lifecycle diagrams and validators for projects, corpus items, documents, evidence records, decisions, tasks, dossiers, and exports.

**Deliverables:**

- Explicit lifecycle diagrams and validators for projects, corpus items, documents, evidence records, decisions, tasks, dossiers, and exports.

**Acceptance criteria:**

- Illegal transitions fail before persistence; state transitions are deterministic and include actor/reason; terminal states and reopen rules are documented.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

#### - [ ] CAP-03.S01.T03 - Publish versioning and compatibility policy for domain APIs

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Semantic rules for additive/breaking schema change, deprecation, migration, event compatibility, and desktop-sidecar-server negotiation.

**Deliverables:**

- Semantic rules for additive/breaking schema change, deprecation, migration, event compatibility, and desktop-sidecar-server negotiation.

**Acceptance criteria:**

- A compatibility test suite covers current and one prior contract version; breaking changes require ADR and migration path.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate
- python tools/verify.py --profile service

### CAP-03.S02 - Research intent contract and mode governance

**Outcome:** Every project declares its scholarly purpose, scope, evidence rules, autonomy, and stopping logic before consequential automation.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-01.S01.T02`

#### - [ ] CAP-03.S02.T01 - Model the versioned research intent contract

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-01.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Schema for research question, contribution intent, epistemic mode, unit/level, source scope, evidence types, novelty standard, autonomy, and stopping rule.

**Deliverables:**

- Schema for research question, contribution intent, epistemic mode, unit/level, source scope, evidence types, novelty standard, autonomy, and stopping rule.

**Acceptance criteria:**

- All required fields vary appropriately by mode; revisions preserve prior versions and rationale; downstream objects can cite the governing contract version.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

#### - [ ] CAP-03.S02.T02 - Implement guided intent creation and revision UI

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Desktop workflow with mode-specific defaults, examples, warnings, and explicit change-impact preview.

**Deliverables:**

- Desktop workflow with mode-specific defaults, examples, warnings, and explicit change-impact preview.

**Acceptance criteria:**

- A user cannot silently change corpus or novelty scope; revisions show affected workflows/outputs; incomplete contracts can be saved as draft but cannot launch gated analysis.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service

#### - [ ] CAP-03.S02.T03 - Enforce mode and autonomy policy at service boundaries

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Policy checks that constrain tools, required human gates, output labels, and stopping behavior according to the active contract.

**Deliverables:**

- Policy checks that constrain tools, required human gates, output labels, and stopping behavior according to the active contract.

**Acceptance criteria:**

- Attempts to bypass a required gate fail with a policy explanation; policy decisions are logged and covered by tests for systematic, theory, technical, hermeneutic, critical, and novelty modes.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile security-local

### CAP-03.S03 - Append-only provenance and audit ledger

**Outcome:** The system can reconstruct how every material object and claim was produced and changed.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T02`, `CAP-02.S02.T01`

#### - [ ] CAP-03.S03.T01 - Define provenance event, activity, entity, and agent model

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T02`, `CAP-02.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Event schema aligned with practical provenance concepts for source acquisition, parsing, extraction, verification, decisions, synthesis, export, and invalidation.

**Deliverables:**

- Event schema aligned with practical provenance concepts for source acquisition, parsing, extraction, verification, decisions, synthesis, export, and invalidation.

**Acceptance criteria:**

- Events include immutable ID, project, actor, inputs, outputs, versioned configuration, timestamp, and trace; personally sensitive fields are minimized.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data

#### - [ ] CAP-03.S03.T02 - Implement atomic provenance recording and lineage queries

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Append-only ledger persistence integrated with domain transactions plus APIs for ancestors, descendants, production activity, and responsible agent.

**Deliverables:**

- Append-only ledger persistence integrated with domain transactions plus APIs for ancestors, descendants, production activity, and responsible agent.

**Acceptance criteria:**

- No canonical output can commit without its required provenance event; lineage traversal detects missing references; ledger writes are idempotent under retries.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile data
- python tools/verify.py --profile service

#### - [ ] CAP-03.S03.T03 - Create an audit and lineage inspection workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Desktop view from project output to source passages, transformations, models, prompts, decisions, and stale state.

**Deliverables:**

- Desktop view from project output to source passages, transformations, models, prompts, decisions, and stale state.

**Acceptance criteria:**

- A sampled synthesis sentence and evidence field can be traced to exact sources and processing events in two interactions; alternate and superseded records remain visible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

### CAP-03.S04 - Portable workflow model and local worker fabric

**Outcome:** Long-running processes execute as durable, inspectable workflows instead of opaque UI calls.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T02`, `CAP-02.S02.T03`

#### - [ ] CAP-03.S04.T01 - Define workflow, step, job, attempt, artifact, and human-task contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T02`, `CAP-02.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Portable state model with input/output schemas, idempotency keys, retry policy, cancellation, checkpoints, and progress.

**Deliverables:**

- Portable state model with input/output schemas, idempotency keys, retry policy, cancellation, checkpoints, and progress.

**Acceptance criteria:**

- State transitions survive process restart; a workflow definition is independent of local versus server executor; human tasks are first-class and auditable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

#### - [ ] CAP-03.S04.T02 - Implement the local durable queue and worker supervisor

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** SQLite-backed queue, leases, concurrency classes, heartbeat, retry, checkpoint, cancellation, and crash recovery.

**Deliverables:**

- SQLite-backed queue, leases, concurrency classes, heartbeat, retry, checkpoint, cancellation, and crash recovery.

**Acceptance criteria:**

- Killed workers release or recover leases without duplicate committed output; restart resumes resumable work; queue load cannot block interactive reads.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-03.S04.T03 - Build task center, progress, cancellation, and human-gate UI

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Desktop task center showing workflow graph, queued/running/waiting/failed states, resource use, logs, decisions, retry, and cancel.

**Deliverables:**

- Desktop task center showing workflow graph, queued/running/waiting/failed states, resource use, logs, decisions, retry, and cancel.

**Acceptance criteria:**

- User can distinguish active compute from waiting-for-review; cancellation reaches a safe point and reports retained artifacts; human approval resumes the exact workflow version.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

### CAP-03.S05 - Dependency graph, staleness, and controlled recalculation

**Outcome:** Changes to evidence, models, schemas, or decisions identify and safely refresh affected outputs.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S04.T03`

#### - [ ] CAP-03.S05.T01 - Implement material dependency registration

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Dependency edges from outputs to source revisions, evidence records, ontology versions, prompts/models, parameters, and human decisions.

**Deliverables:**

- Dependency edges from outputs to source revisions, evidence records, ontology versions, prompts/models, parameters, and human decisions.

**Acceptance criteria:**

- Every recalculable output declares dependencies before completion; missing dependency registration fails a development assertion and appears in audit diagnostics.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data

#### - [ ] CAP-03.S05.T02 - Implement stale-state propagation and impact preview

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Graph traversal that marks affected outputs stale, records cause, deduplicates cascades, and previews impact before destructive changes.

**Deliverables:**

- Graph traversal that marks affected outputs stale, records cause, deduplicates cascades, and previews impact before destructive changes.

**Acceptance criteria:**

- Changing a fixture extraction marks the expected matrix, graph, synthesis, and dossier outputs stale without touching unrelated outputs; cycles are handled safely.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/verify.py --profile graph

#### - [ ] CAP-03.S05.T03 - Implement selective recomputation and historical retention

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Workflow generation from stale subgraphs with reuse of valid intermediates, versioned replacement, comparison, and rollback.

**Deliverables:**

- Workflow generation from stale subgraphs with reuse of valid intermediates, versioned replacement, comparison, and rollback.

**Acceptance criteria:**

- Recompute produces a new version rather than overwriting evidence; unchanged inputs reuse verified artifacts; user can compare and restore prior adjudicated output.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

### CAP-03.S06 - Use-case profiles and adaptive guided navigation

**Outcome:** A project begins from a scholarly objective and exposes a clear, versioned primary path through the workbench, with visible progress and access to supporting tools.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S02.T01`, `CAP-00.S06.T04`

#### - [ ] CAP-03.S06.T01 - Define the versioned use-case and workflow-profile contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S02.T01`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Represent the fourteen approved use cases, ordered/optional/cyclical steps, rationale, checkpoints, expected outputs, version, migration, and relationship to the Research Intent Contract.

**Deliverables:**

- Typed domain/API contracts and migrations for WorkflowProfile, ProjectWorkflowSelection, WorkflowStageState, and reference/version linkage.

**Acceptance criteria:**

- Exactly eight built-in profiles match the approved workflow catalog and can be extended only through a versioned, reviewed profile pack.
- Ordered, optional, cyclical, supporting-tool, current, completed, attention, and stale states are represented without overloading analytical job state.
- Changing profile preserves prior selection and stage history and produces an impact preview rather than rewriting the record.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/taskctl.py validate

#### - [ ] CAP-03.S06.T02 - Implement primary-use-case selection at project creation and intent revision

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S06.T01`, `CAP-03.S02.T02`, `CAP-01.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Ask the user what scholarly objective they are pursuing, preview the ordered path and output, save it in the versioned intent contract, and permit later revision through explicit impact review.

**Deliverables:**

- New-project and intent-revision application flows backed by the workflow-profile contracts.

**Acceptance criteria:**

- Project creation requires one primary use case before completion and displays purpose, output, process form, and ordered steps.
- Changing use case previews affected schemas, checkpoints, outputs, autonomy defaults, stopping logic, and stale artifacts before confirmation.
- All tools remain available and the selected use case does not change evidence/provenance requirements silently.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/taskctl.py validate

#### - [ ] CAP-03.S06.T03 - Implement adaptive ordered navigation and workflow context

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S06.T02`, `CAP-01.S02.T01`, `CAP-01.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Render the selected workflow as numbered primary navigation, expose current/previous/next steps and rationale on each page, and retain a secondary complete tool inventory.

**Deliverables:**

- Adaptive desktop navigation, workflow context bar, all-tools disclosure, and support-tool return behavior.

**Acceptance criteria:**

- The primary navigation order changes to the selected use case and clearly distinguishes completed, current, upcoming, attention, optional, and cyclical states.
- Opening a tool outside the sequence labels it as supporting and provides a one-action return to the current primary step.
- Navigation is keyboard and screen-reader operable, responsive, and faithful to the approved Academic Minimal reference in both themes.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/taskctl.py validate

#### - [ ] CAP-03.S06.T04 - Implement workflow progress, checkpoints, handoffs, and recalculation impact

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S06.T03`, `CAP-03.S04.T01`, `CAP-03.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Persist stage progress and human checkpoints separately from background jobs, recommend the next meaningful step, and mark affected workflow outputs when intent/evidence changes.

**Deliverables:**

- Workflow progress service, project-home overview, stage completion commands, checkpoint gates, and dependency/staleness integration.

**Acceptance criteria:**

- Progress survives restart and never advances consequential stages solely because a background job completed.
- Project Home shows current use case, position, recommended next action, research-quality gates, stale outputs, and a route back into the workflow.
- Cyclical workflows can revisit stages without erasing prior passes; profile or evidence changes propagate explicit impact/staleness.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/taskctl.py validate

#### - [ ] CAP-03.S06.T05 - Verify all approved use-case workflows end to end

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Test profile selection, navigation order, supporting-tool access, state persistence, profile revision, accessibility, and expected output handoffs across all fourteen use cases.

**Deliverables:**

- Deterministic workflow contract tests and Playwright end-to-end scenarios for all fourteen profiles.

**Acceptance criteria:**

- Each approved profile starts at project creation, renders the exact approved sequence, preserves access to all tools, and resumes correctly after restart.
- Hermeneutic, critical, and living-review cycles can revisit earlier steps without rewriting history; systematic review maintains its reproducible order and audit endpoint.
- Automated evidence identifies the approved UI reference and workflow-catalog version used by every test.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/taskctl.py validate

## CAP-04 - Scholarly ingestion, connectors, canonicalization, and corpus governance

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Build a source-transparent canonical corpus from local libraries, open scholarly APIs, and later licensed adapters while preserving rights, versions, and discovery paths.

**Exit criteria:**

- Common reference formats and open scholarly sources import through idempotent, rate-aware adapters.
- Works, versions, authors, identifiers, corrections, retractions, and duplicates reconcile without losing source-specific metadata.
- Every corpus item records how it was discovered, what rights apply, and why it is included or excluded.

### CAP-04.S01 - Reference-library and file imports

**Outcome:** Researchers can import existing bibliographies with preview, mapping, validation, and repeatable merge behavior.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T02`, `CAP-02.S02.T03`

#### - [ ] CAP-04.S01.T01 - Implement RIS, BibTeX, CSL JSON, DOI-list, and structured CSV parsers

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S03.T02`, `CAP-02.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Streaming parsers that preserve original fields, import source, line/record location, and warnings.

**Deliverables:**

- Streaming parsers that preserve original fields, import source, line/record location, and warnings.

**Acceptance criteria:**

- Fixture files import deterministically; malformed records are isolated rather than aborting the batch; unknown fields remain available for audit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

#### - [ ] CAP-04.S01.T02 - Create import preview, mapping, and conflict UI

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Desktop wizard showing parsed records, field mapping, duplicate candidates, warnings, rights defaults, and import options.

**Deliverables:**

- Desktop wizard showing parsed records, field mapping, duplicate candidates, warnings, rights defaults, and import options.

**Acceptance criteria:**

- User can correct mapping before commit, exclude records, and download an error report; cancellation leaves no partial canonical import.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service

#### - [ ] CAP-04.S01.T03 - Implement idempotent import commits and import manifests

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Batch transaction and manifest linking source file hash, parser version, record decisions, errors, and resulting canonical IDs.

**Deliverables:**

- Batch transaction and manifest linking source file hash, parser version, record decisions, errors, and resulting canonical IDs.

**Acceptance criteria:**

- Re-importing the same file does not duplicate records; changed files create a new manifest and explain additions, updates, and unresolved conflicts.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data

### CAP-04.S02 - Open scholarly source adapters

**Outcome:** OpenAlex, Crossref, Unpaywall, and Semantic Scholar are available behind stable, observable connector contracts.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T01`, `CAP-07.S01.T01`

#### - [ ] CAP-04.S02.T01 - Define connector request, result, cursor, rate-limit, and provenance contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T01`, `CAP-07.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Provider-neutral interfaces for search, lookup, citation traversal, recommendations, OA resolution, retries, cache, and raw-response retention policy.

**Deliverables:**

- Provider-neutral interfaces for search, lookup, citation traversal, recommendations, OA resolution, retries, cache, and raw-response retention policy.

**Acceptance criteria:**

- Adapters can be mocked; all results include provider, query, retrieval time, raw identifier, license/terms metadata, and normalized error categories.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service

#### - [ ] CAP-04.S02.T02 - Implement OpenAlex and Crossref adapters

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Fielded search, identifier lookup, pagination, work/author/source metadata, references where available, rate handling, and response caching.

**Deliverables:**

- Fielded search, identifier lookup, pagination, work/author/source metadata, references where available, rate handling, and response caching.

**Acceptance criteria:**

- Known-item fixtures resolve to canonical candidates; pagination resumes after failure; rate limits are obeyed; raw responses can be replayed in tests.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile search

#### - [ ] CAP-04.S02.T03 - Implement Unpaywall and Semantic Scholar adapters

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Open-access location resolution, academic graph lookup, citations/references, and related-paper recommendations with policy controls.

**Deliverables:**

- Open-access location resolution, academic graph lookup, citations/references, and related-paper recommendations with policy controls.

**Acceptance criteria:**

- OA URLs retain license and host metadata; recommendation/citation results record direction and source; provider unavailability degrades without corrupting the search run.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile search

### CAP-04.S03 - Canonical work, version, and identity reconciliation

**Outcome:** Multiple provider records resolve to inspectable canonical scholarly entities without flattening uncertainty.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T03`, `CAP-04.S02.T03`

#### - [ ] CAP-04.S03.T01 - Implement identifier normalization and exact reconciliation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S01.T03`, `CAP-04.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Normalization for DOI, PMID, arXiv, ISBN, ORCID, provider IDs, URLs, and title fingerprints with source precedence rules.

**Deliverables:**

- Normalization for DOI, PMID, arXiv, ISBN, ORCID, provider IDs, URLs, and title fingerprints with source precedence rules.

**Acceptance criteria:**

- Equivalent identifiers converge; invalid or reassigned identifiers are flagged; source records remain linked and unchanged for audit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data

#### - [ ] CAP-04.S03.T02 - Implement probabilistic duplicate candidate generation and review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Fuzzy candidate scoring using title, authors, year, venue, pages, abstract, and identifiers plus merge/split review UI.

**Deliverables:**

- Fuzzy candidate scoring using title, authors, year, venue, pages, abstract, and identifiers plus merge/split review UI.

**Acceptance criteria:**

- Gold duplicate fixtures meet declared precision/recall thresholds; ambiguous clusters require review; merges are reversible and preserve conflicting fields.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile desktop
- python tools/verify.py --profile data

#### - [ ] CAP-04.S03.T03 - Implement work-version, correction, and retraction relationships

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Version graph for preprint, accepted manuscript, version of record, erratum, correction, expression of concern, and retraction.

**Deliverables:**

- Version graph for preprint, accepted manuscript, version of record, erratum, correction, expression of concern, and retraction.

**Acceptance criteria:**

- Users can identify the preferred citable version and see status warnings; a retraction or correction marks dependent outputs for review rather than deleting history.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/verify.py --profile graph

### CAP-04.S04 - Corpus membership, discovery path, and rights governance

**Outcome:** Corpus state is a deliberate scholarly decision with complete acquisition and inclusion provenance.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S03.T03`, `CAP-03.S02.T03`

#### - [ ] CAP-04.S04.T01 - Model corpus item states, reasons, and discovery paths

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S03.T03`, `CAP-03.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Candidate, included, excluded, pending, duplicate, unavailable, and withdrawn states with query/citation/import lineage and decision history.

**Deliverables:**

- Candidate, included, excluded, pending, duplicate, unavailable, and withdrawn states with query/citation/import lineage and decision history.

**Acceptance criteria:**

- Every item can explain how it entered the project and every state change records actor, reason, governing protocol, and prior state.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data

#### - [ ] CAP-04.S04.T02 - Implement rights, license, entitlement, and permitted-use metadata

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Rights vocabulary and policies for metadata, full text, derived text, embeddings, model egress, collaboration, and export.

**Deliverables:**

- Rights vocabulary and policies for metadata, full text, derived text, embeddings, model egress, collaboration, and export.

**Acceptance criteria:**

- Unknown rights default to restrictive behavior; policy decisions are source-specific and inspectable; changing rights marks affected operations for re-evaluation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile security-local

#### - [ ] CAP-04.S04.T03 - Build corpus provenance and source-overlap reports

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Reports of source contribution, duplicate overlap, missing identifiers, OA/full-text status, years, venues, disciplines, languages, and discovery routes.

**Deliverables:**

- Reports of source contribution, duplicate overlap, missing identifiers, OA/full-text status, years, venues, disciplines, languages, and discovery routes.

**Acceptance criteria:**

- Counts reconcile with canonical corpus state; users can drill from aggregates to records; reports identify unavailable or unknown data rather than imputing it.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile service
- python tools/verify.py --profile search

### CAP-04.S05 - Connector SDK and controlled extensibility

**Outcome:** New data sources can be added without bypassing provenance, rights, security, or canonicalization.

**Wave / priority / status / review:** `W2` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-04.S04.T03`, `CAP-00.S03.T03`

#### - [ ] CAP-04.S05.T01 - Publish connector plugin manifest and capability API

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-04.S04.T03`, `CAP-00.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned manifest for source identity, operations, authentication, terms, rate limits, data classes, and required permissions.

**Deliverables:**

- Versioned manifest for source identity, operations, authentication, terms, rate limits, data classes, and required permissions.

**Acceptance criteria:**

- An unsupported capability is rejected before execution; plugin version and permissions appear in provenance; breaking SDK changes follow compatibility policy.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate
- python tools/verify.py --profile service

#### - [ ] CAP-04.S05.T02 - Implement plugin isolation, configuration, and secret access controls

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-04.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Restricted execution boundary, allowlisted network destinations, scoped credentials, timeouts, quotas, and redacted logging.

**Deliverables:**

- Restricted execution boundary, allowlisted network destinations, scoped credentials, timeouts, quotas, and redacted logging.

**Acceptance criteria:**

- A malicious test connector cannot read unrelated secrets or project files; network and export attempts outside manifest permissions are blocked and audited.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile security-local

#### - [ ] CAP-04.S05.T03 - Deliver a sample repository connector and conformance suite

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-04.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Reference connector for a local/institutional repository plus tests for pagination, errors, provenance, rights, and replay.

**Deliverables:**

- Reference connector for a local/institutional repository plus tests for pagination, errors, provenance, rights, and replay.

**Acceptance criteria:**

- A third-party developer can implement and validate a connector from documentation; conformance failures identify contract violations precisely.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

## CAP-05 - Document acquisition, parsing, source inspection, and page anchors

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Convert lawful full text into immutable, inspectable document revisions while retaining page, layout, reference, table, and figure context.

**Exit criteria:**

- Local files, open-access copies, and structured publisher formats enter through rights-aware acquisition workflows.
- Native XML/HTML is preferred; PDF fallback produces sections, passages, references, and page-coordinate anchors with quality scores.
- Users can inspect every evidence anchor in source context and corrections trigger controlled recalculation.

### CAP-05.S01 - Rights-aware document acquisition

**Outcome:** Full-text acquisition is explicit, resumable, checksum-verified, and governed by permitted use.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T02`, `CAP-02.S03.T03`

#### - [ ] CAP-05.S01.T01 - Implement local document attachment and version association

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T02`, `CAP-02.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Drag/drop and file-picker flows for PDF, JATS, TEI, XML, HTML, DOCX, and plain text with work/version selection.

**Deliverables:**

- Drag/drop and file-picker flows for PDF, JATS, TEI, XML, HTML, DOCX, and plain text with work/version selection.

**Acceptance criteria:**

- Unsupported or password-protected files receive actionable errors; hashes prevent duplicate storage; user confirms uncertain work associations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile desktop

#### - [ ] CAP-05.S01.T02 - Implement open-access location selection and download

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Acquisition from approved OA locations with redirect controls, MIME validation, license capture, checksum, and retry.

**Deliverables:**

- Acquisition from approved OA locations with redirect controls, MIME validation, license capture, checksum, and retry.

**Acceptance criteria:**

- Only policy-permitted locations download; content-type spoofing and oversized responses are rejected; the selected source and license remain attached to the revision.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile security-local

#### - [ ] CAP-05.S01.T03 - Create acquisition queue, conflict, and entitlement placeholders

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Resumable download/import jobs, alternative copies, unavailable state, and manual/institutional entitlement request placeholders.

**Deliverables:**

- Resumable download/import jobs, alternative copies, unavailable state, and manual/institutional entitlement request placeholders.

**Acceptance criteria:**

- Partial acquisitions resume or clean up safely; multiple copies remain distinguishable; lack of full text does not remove the metadata record or fabricate availability.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile service

### CAP-05.S02 - Structured and PDF parsing pipeline

**Outcome:** A replaceable local parser pipeline produces normalized document structure with retained originals and quality signals.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-05.S01.T03`, `CAP-03.S04.T02`

#### - [ ] CAP-05.S02.T01 - Define parser interface, document IR, and parser-selection policy

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-05.S01.T03`, `CAP-03.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Contracts for input formats, structural blocks, coordinates, references, tables, figures, warnings, confidence, and parser provenance.

**Deliverables:**

- Contracts for input formats, structural blocks, coordinates, references, tables, figures, warnings, confidence, and parser provenance.

**Acceptance criteria:**

- The intermediate representation preserves original text order and source offsets; parser selection is deterministic and recorded; failed parsers cannot commit partial canonical output.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents

#### - [ ] CAP-05.S02.T02 - Implement native JATS/TEI/XML/HTML parsing

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-05.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Namespace-aware parsers for titles, abstracts, sections, paragraphs, lists, footnotes, tables, figures, references, and in-text citations.

**Deliverables:**

- Namespace-aware parsers for titles, abstracts, sections, paragraphs, lists, footnotes, tables, figures, references, and in-text citations.

**Acceptance criteria:**

- Golden structured documents reproduce expected hierarchy and text; unsupported elements are retained as typed unknown blocks with source locations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents

#### - [ ] CAP-05.S02.T03 - Integrate the local Docling-based PDF parser with fallback

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-05.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Packaged Docling-based local PDF parser adapter, resource limits, page rendering, OCR-disabled-by-default policy, fallback text extraction, and quality report.

**Deliverables:**

- Packaged Docling-based local PDF parser adapter, resource limits, page rendering, OCR-disabled-by-default policy, fallback text extraction, and quality report.

**Acceptance criteria:**

- Representative scholarly PDFs parse offline through the pinned Docling adapter; scanned/complex files are labeled low quality rather than overclaimed; parser crash is isolated and resumable; a replacement parser requires benchmark evidence and an ADR.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile e2e-local

### CAP-05.S03 - Immutable document revisions and source anchors

**Outcome:** Every extracted passage and downstream assertion points to a specific immutable revision and stable location.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S02.T03`, `CAP-02.S02.T03`

#### - [ ] CAP-05.S03.T01 - Persist normalized sections, blocks, sentences, and references

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S02.T03`, `CAP-02.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Canonical document-revision schema and repositories for structural hierarchy, ordering, labels, text, and reference links.

**Deliverables:**

- Canonical document-revision schema and repositories for structural hierarchy, ordering, labels, text, and reference links.

**Acceptance criteria:**

- Reparse creates a new revision; prior revisions remain queryable; structural IDs are stable within a revision and never reused across different content.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile data

#### - [ ] CAP-05.S03.T02 - Implement page, bounding-box, and text-span anchors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Anchor model supporting page number, normalized rectangle, character span, block/sentence IDs, and anchor-confidence metadata.

**Deliverables:**

- Anchor model supporting page number, normalized rectangle, character span, block/sentence IDs, and anchor-confidence metadata.

**Acceptance criteria:**

- Clicking fixture anchors highlights the intended passage after restart; anchors tolerate display scaling; unavailable coordinates fall back to structural/text anchors visibly.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile desktop

#### - [ ] CAP-05.S03.T03 - Implement anchor resolution and citation-link APIs

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** APIs to resolve evidence to source context, adjacent text, document metadata, and canonical reference targets.

**Deliverables:**

- APIs to resolve evidence to source context, adjacent text, document metadata, and canonical reference targets.

**Acceptance criteria:**

- Every observed evidence fixture resolves to a source revision and readable context; broken anchors are detected and mark dependents stale.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile service

### CAP-05.S04 - Source viewer and evidence inspection experience

**Outcome:** Researchers can read original pages and structured text side by side, navigate anchors, and inspect provenance without leaving the workflow.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T03`, `CAP-01.S02.T03`

#### - [ ] CAP-05.S04.T01 - Build secure local PDF/page and structured-text viewer

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T03`, `CAP-01.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Desktop viewer with page thumbnails, zoom, text view, section navigation, search, and restricted external-link behavior.

**Deliverables:**

- Desktop viewer with page thumbnails, zoom, text view, section navigation, search, and restricted external-link behavior.

**Acceptance criteria:**

- Viewer opens local encrypted content through controlled streams, supports large documents without loading all pages, and never exposes direct file paths to untrusted content.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile documents
- python tools/verify.py --profile security-local

#### - [ ] CAP-05.S04.T02 - Implement deep links, highlights, and context panels

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Navigation from evidence/graph/synthesis objects to highlighted source anchors with surrounding text, metadata, and processing status.

**Deliverables:**

- Navigation from evidence/graph/synthesis objects to highlighted source anchors with surrounding text, metadata, and processing status.

**Acceptance criteria:**

- Deep links survive application restart and project relocation; multiple anchors display distinctly; missing anchors show the relevant revision and repair action.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile documents
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-05.S04.T03 - Enforce rights-aware viewer actions and export

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Policy-driven copy, print, external open, annotation export, and derivative-text limits with clear user messaging.

**Deliverables:**

- Policy-driven copy, print, external open, annotation export, and derivative-text limits with clear user messaging.

**Acceptance criteria:**

- Restricted documents cannot be exported through alternate UI paths; allowed quotations carry source identifiers; denied actions are audited without storing copied text.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

### CAP-05.S05 - References, citation contexts, tables, and figures

**Outcome:** Document-internal scholarly structures become inspectable records without losing page context.

**Wave / priority / status / review:** `W2` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T03`

#### - [ ] CAP-05.S05.T01 - Extract and reconcile reference-list entries

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Parsed references, identifiers, raw strings, author/year/title fields, and links to canonical works or unresolved candidates.

**Deliverables:**

- Parsed references, identifiers, raw strings, author/year/title fields, and links to canonical works or unresolved candidates.

**Acceptance criteria:**

- Reference order and raw text are preserved; exact identifiers reconcile automatically; uncertain matches remain candidates with scores and review state.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile service

#### - [ ] CAP-05.S05.T02 - Extract in-text citation contexts and targets

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Citation markers linked to reference entries with sentence/paragraph context, location, and multi-target handling.

**Deliverables:**

- Citation markers linked to reference entries with sentence/paragraph context, location, and multi-target handling.

**Acceptance criteria:**

- Fixture citation styles resolve correctly; unresolved and ambiguous targets are explicit; contexts retain exact source anchors.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile graph

#### - [ ] CAP-05.S05.T03 - Represent tables and figures with captions and page anchors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Table/figure objects, captions, page locations, extracted text/cells where reliable, and image preview references.

**Deliverables:**

- Table/figure objects, captions, page locations, extracted text/cells where reliable, and image preview references.

**Acceptance criteria:**

- Objects navigate to original pages; extraction quality is displayed; the system does not treat low-confidence cell extraction as verified evidence.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile desktop

### CAP-05.S06 - Parsing quality, correction, and reprocessing

**Outcome:** Parsing errors can be diagnosed and corrected without obscuring machine output or provenance.

**Wave / priority / status / review:** `W2` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S04.T02`, `CAP-03.S05.T02`

#### - [ ] CAP-05.S06.T01 - Implement parsing quality metrics and triage rules

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S04.T02`, `CAP-03.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Metrics for text coverage, reading-order anomalies, missing sections/references, encoding, page-anchor coverage, and parser warnings.

**Deliverables:**

- Metrics for text coverage, reading-order anomalies, missing sections/references, encoding, page-anchor coverage, and parser warnings.

**Acceptance criteria:**

- Known bad fixtures are routed to review; quality dimensions are visible separately; no single score claims correctness.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents

#### - [ ] CAP-05.S06.T02 - Build manual structural correction and annotation tools

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Controlled edits for section labels/order, merged/split blocks, reference matches, page anchors, and exclusion of corrupted regions.

**Deliverables:**

- Controlled edits for section labels/order, merged/split blocks, reference matches, page anchors, and exclusion of corrupted regions.

**Acceptance criteria:**

- Corrections preserve original parser output, actor, rationale, and revision; downstream objects point to the corrected revision only after explicit acceptance.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile documents

#### - [ ] CAP-05.S06.T03 - Implement parser upgrade comparison and stale propagation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-05.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Batch reparse preview, old/new structure diff, anchor migration candidates, acceptance, and dependent-output invalidation.

**Deliverables:**

- Batch reparse preview, old/new structure diff, anchor migration candidates, acceptance, and dependent-output invalidation.

**Acceptance criteria:**

- A parser upgrade cannot silently replace accepted structure; changed anchors are reported; accepted reparse marks only affected evidence and outputs stale.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile documents
- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

## CAP-06 - Local search, discovery, corpus diagnostics, and screening

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session.

**Exit criteria:**

- Lexical and semantic indexes are versioned, explainable, rebuildable, and usable offline for project content.
- Search evolution is stored as a visible tree of exact queries, transformations, results, and discovery paths.
- Screening supports human inclusion decisions, uncertainty/random audits, stopping evidence, and reproducible exports.

### CAP-06.S01 - Fielded lexical search and local indexing

**Outcome:** Exact terminology, Boolean logic, metadata filters, and reproducible ranking are available through SQLite FTS5.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T03`, `CAP-05.S03.T03`

#### - [ ] CAP-06.S01.T01 - Define searchable fields, analyzers, and query grammar

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-04.S04.T03`, `CAP-05.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Search contract covering title, abstract, full text, authors, venue, identifiers, year, tags, decisions, and exact/phrase/Boolean syntax.

**Deliverables:**

- Search contract covering title, abstract, full text, authors, venue, identifiers, year, tags, decisions, and exact/phrase/Boolean syntax.

**Acceptance criteria:**

- Grammar is documented and round-trippable; invalid queries produce location-specific errors; original and normalized query are both retained.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search

#### - [ ] CAP-06.S01.T02 - Implement incremental FTS5 indexing and rebuild

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Index writers for canonical metadata and permitted document text with version markers, checkpoints, and full rebuild command.

**Deliverables:**

- Index writers for canonical metadata and permitted document text with version markers, checkpoints, and full rebuild command.

**Acceptance criteria:**

- Committed corpus changes appear incrementally; interrupted indexing resumes or rebuilds safely; restricted text is excluded according to policy.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile data

#### - [ ] CAP-06.S01.T03 - Implement fielded search, filters, snippets, and ranking explanation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Search API and desktop result view with filters, highlighted snippets, score components, and stable pagination.

**Deliverables:**

- Search API and desktop result view with filters, highlighted snippets, score components, and stable pagination.

**Acceptance criteria:**

- Known-item tests meet declared recall; identical corpus/index/query yields stable ordering; users can distinguish exact, field, and filter contributions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile desktop

### CAP-06.S02 - Semantic representations and vector retrieval

**Outcome:** Conceptually related literature is retrievable through a replaceable, versioned local embedding interface.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T02`, `CAP-07.S01.T03`

#### - [ ] CAP-06.S02.T01 - Define embedding, chunking, vector-index, and compatibility contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T02`, `CAP-07.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Interfaces for document/passage representations, model manifests, dimensions, normalization, chunk provenance, filters, and rebuild state.

**Deliverables:**

- Interfaces for document/passage representations, model manifests, dimensions, normalization, chunk provenance, filters, and rebuild state.

**Acceptance criteria:**

- Indexes reject incompatible vectors; every vector resolves to source text and model version; contract supports embedded and server engines.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile ai

#### - [ ] CAP-06.S02.T02 - Integrate a local scientific embedding baseline

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Packaged or user-installed local embedding option with model-license metadata, resource profile, batching, cancellation, and deterministic fixture behavior.

**Deliverables:**

- Packaged or user-installed local embedding option with model-license metadata, resource profile, batching, cancellation, and deterministic fixture behavior.

**Acceptance criteria:**

- A supported CPU-only machine can index the fixture corpus offline; unavailable model produces guided setup rather than failing the project; output provenance is complete.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile ai
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-06.S02.T03 - Implement local vector indexing, filtered similarity search, and rebuild

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Benchmark, select through ADR, and implement a replaceable local vector adapter with incremental updates, metadata filtering, nearest-neighbor query, health checks, exact-search fallback, and model-change migration.

**Deliverables:**

- Benchmark, select through ADR, and implement a replaceable local vector adapter with incremental updates, metadata filtering, nearest-neighbor query, health checks, exact-search fallback, and model-change migration.

**Acceptance criteria:**

- Windows install, recovery, filtering, portability, corpus-size, latency, and rebuild benchmarks support the selected adapter and ADR; semantic known-neighbor tests meet baseline; deletion and rights changes remove or quarantine vectors; model upgrade marks the index stale and requires explicit rebuild.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile data

### CAP-06.S03 - Hybrid retrieval and reranking

**Outcome:** Search ensembles combine exact, semantic, graph, and project-specific relevance while preserving component evidence.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T03`, `CAP-06.S02.T03`

#### - [ ] CAP-06.S03.T01 - Implement lexical-semantic result fusion

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S01.T03`, `CAP-06.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Configurable reciprocal-rank or calibrated fusion with deduplication, filters, component scores, and deterministic tie handling.

**Deliverables:**

- Configurable reciprocal-rank or calibrated fusion with deduplication, filters, component scores, and deterministic tie handling.

**Acceptance criteria:**

- Gold queries show no regression in known-item coverage versus individual retrievers; component ranks remain inspectable and logged.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search

#### - [ ] CAP-06.S03.T02 - Implement optional local or approved reranking

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Reranker adapter for query-record/passage pairs with batching, resource limits, policy checks, and score provenance.

**Deliverables:**

- Reranker adapter for query-record/passage pairs with batching, resource limits, policy checks, and score provenance.

**Acceptance criteria:**

- Reranking can be disabled without changing corpus state; timeout falls back to fused order; model and candidate set are recorded.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile ai

#### - [ ] CAP-06.S03.T03 - Persist complete search-run manifests and replay

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** SearchRun record containing exact query, expansion, sources, indexes/models, weights, filters, timestamps, result set, and errors.

**Deliverables:**

- SearchRun record containing exact query, expansion, sources, indexes/models, weights, filters, timestamps, result set, and errors.

**Acceptance criteria:**

- A local run can be replayed against the same snapshot to reproduce results within documented tolerances; changed corpus/index is reported rather than hidden.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile service
- python tools/verify.py --profile data

### CAP-06.S04 - Search Studio and transparent expansion

**Outcome:** Researchers can iteratively broaden, narrow, branch, and compare searches without losing their reasoning history.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S03.T03`, `CAP-04.S02.T03`

#### - [ ] CAP-06.S04.T01 - Build query editor, source selection, preview, and saved-run UI

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S03.T03`, `CAP-04.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Search Studio with fielded editor, source/index selectors, filters, counts, warnings, save/run/cancel, and result comparison.

**Deliverables:**

- Search Studio with fielded editor, source/index selectors, filters, counts, warnings, save/run/cancel, and result comparison.

**Acceptance criteria:**

- Exact executed queries remain visible; unsaved edits are distinguishable from executed runs; source failures are shown per adapter.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile search

#### - [ ] CAP-06.S04.T02 - Implement versioned search-tree branches and query translation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Parent/child SearchRun relationships, annotations, database-specific translations, and side-by-side result-set differences.

**Deliverables:**

- Parent/child SearchRun relationships, annotations, database-specific translations, and side-by-side result-set differences.

**Acceptance criteria:**

- Users can fork without overwriting history; translations show unsupported clauses and semantic change warnings; additions/removals trace to a branch.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile desktop

#### - [ ] CAP-06.S04.T03 - Implement citation, bibliographic-coupling, and semantic expansion actions

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Explicit expansion operations from selected seeds or clusters, with depth/limits, expected rationale, preview, and provenance.

**Deliverables:**

- Explicit expansion operations from selected seeds or clusters, with depth/limits, expected rationale, preview, and provenance.

**Acceptance criteria:**

- Each discovered record identifies the seed and path; duplicate expansion is idempotent; depth limits and cancellation prevent runaway traversal.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile graph
- python tools/verify.py --profile service

### CAP-06.S05 - Corpus canvas, coverage, and reflexivity diagnostics

**Outcome:** Field structure and collection bias are visible before analytical claims are made.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S04.T03`, `CAP-04.S04.T03`

#### - [ ] CAP-06.S05.T01 - Build corpus table/canvas with clusters and discovery overlays

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S04.T03`, `CAP-04.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Scalable corpus view with inclusion state, clusters, citation/semantic neighborhoods, source, full-text, and discovery-path overlays.

**Deliverables:**

- Scalable corpus view with inclusion state, clusters, citation/semantic neighborhoods, source, full-text, and discovery-path overlays.

**Acceptance criteria:**

- Views remain responsive on target local corpus sizes; visual grouping never changes canonical decisions; every aggregate supports record drill-down.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile search
- python tools/verify.py --profile graph

#### - [ ] CAP-06.S05.T02 - Implement coverage, overlap, missingness, and concentration metrics

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Dashboards by source, date, venue, discipline, language, geography, method where known, OA/full text, citation concentration, and missing fields.

**Deliverables:**

- Dashboards by source, date, venue, discipline, language, geography, method where known, OA/full text, citation concentration, and missing fields.

**Acceptance criteria:**

- Metrics state denominator and unknowns; source overlap reconciles to canonical records; no absent metadata is silently classified.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile data
- python tools/verify.py --profile desktop

#### - [ ] CAP-06.S05.T03 - Implement corpus-boundary sensitivity comparisons

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Compare saved corpus snapshots or filters and show affected records, evidence availability, clusters, and downstream conclusions.

**Deliverables:**

- Compare saved corpus snapshots or filters and show affected records, evidence availability, clusters, and downstream conclusions.

**Acceptance criteria:**

- Changing a boundary produces an auditable candidate snapshot; dependent analyses are previewed before recalculation; comparisons are exportable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile service
- python tools/verify.py --profile graph

### CAP-06.S06 - Transparent screening and active-learning governance

**Outcome:** Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S05.T02`, `CAP-03.S02.T03`

#### - [ ] CAP-06.S06.T01 - Implement screening protocol, queue, decisions, and conflicts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S05.T02`, `CAP-03.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Inclusion/exclusion criteria, title/abstract/full-text stages, reasons, reviewer assignment, blinded option, decisions, and adjudication state.

**Deliverables:**

- Inclusion/exclusion criteria, title/abstract/full-text stages, reasons, reviewer assignment, blinded option, decisions, and adjudication state.

**Acceptance criteria:**

- No final decision lacks actor/reason/stage; criteria version is attached; conflicts remain unresolved until explicit adjudication.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile desktop
- python tools/verify.py --profile data

#### - [ ] CAP-06.S06.T02 - Implement active-learning prioritization and model versioning

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Pluggable screening ranker trained on project decisions, uncertainty sampling, predictions, model snapshots, and explanation features.

**Deliverables:**

- Pluggable screening ranker trained on project decisions, uncertainty sampling, predictions, model snapshots, and explanation features.

**Acceptance criteria:**

- Prioritization never writes inclusion decisions; retraining is reproducible from labeled data; low-data behavior and class imbalance are tested.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-06.S06.T03 - Implement random audits, citation-neighbor checks, and stopping diagnostics

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-06.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Audit sampler, rejected-neighbor queue, discovery curves, residual-risk indicators, stopping proposal, and human approval.

**Deliverables:**

- Audit sampler, rejected-neighbor queue, discovery curves, residual-risk indicators, stopping proposal, and human approval.

**Acceptance criteria:**

- Stopping cannot be accepted without recorded audits and corpus diagnostics; deliberately hidden relevant fixtures are recoverable through at least one safety channel; limitations are explicit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence

## CAP-07 - Provider-neutral model gateway and governed AI execution

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Make embeddings, rerankers, NLI models, extractors, and LLMs replaceable, policy-controlled, reproducible, and usable locally or through approved providers.

**Exit criteria:**

- All model calls pass through typed task contracts and produce versioned, observable result envelopes.
- Local inference supports the complete basic PC/lab workflow; remote egress is optional and explicitly authorized.
- Prompts, schemas, repair, evaluation, costs, and model upgrades are controlled as durable system assets.

### CAP-07.S01 - Model task, provider, and routing contracts

**Outcome:** AI capabilities are invoked by scholarly task type rather than hard-coded vendor API.

**Wave / priority / status / review:** `W1` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-00.S03.T03`

#### - [ ] CAP-07.S01.T01 - Define model task interfaces and result envelopes

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-00.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Contracts for embedding, reranking, classification, NLI, structured extraction, generation, tool use, token accounting, confidence, and citations.

**Deliverables:**

- Contracts for embedding, reranking, classification, NLI, structured extraction, generation, tool use, token accounting, confidence, and citations.

**Acceptance criteria:**

- Each result records provider/model/version/configuration, request hash, policy decision, latency, usage, and validation outcome; unsupported features fail explicitly.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai

#### - [ ] CAP-07.S01.T02 - Implement model registry and capability discovery

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Registry of installed/available models, licenses, context limits, modalities, hardware requirements, quality tiers, and allowed data classes.

**Deliverables:**

- Registry of installed/available models, licenses, context limits, modalities, hardware requirements, quality tiers, and allowed data classes.

**Acceptance criteria:**

- Routing never selects a model lacking required capability or permission; registry changes are versioned and visible to users/admins.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-07.S01.T03 - Implement routing, fallback, timeout, and circuit-breaker policy

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Policy engine using task, privacy, rights, reproducibility, hardware, cost, and project preferences to select provider and fallback.

**Deliverables:**

- Policy engine using task, privacy, rights, reproducibility, hardware, cost, and project preferences to select provider and fallback.

**Acceptance criteria:**

- Fallback cannot cross a prohibited egress boundary; failures preserve the original request state; route decisions and alternatives are auditable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local

### CAP-07.S02 - Local model runtime and model management

**Outcome:** PC/lab users can run supported models through llama.cpp-class runtimes without manually administering a model server.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-07.S01.T03`, `CAP-01.S03.T03`

#### - [ ] CAP-07.S02.T01 - Integrate a supervised local inference runtime

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-07.S01.T03`, `CAP-01.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Sidecar-managed llama.cpp-compatible runtime with health, cancellation, streaming, batching limits, hardware detection, and safe shutdown.

**Deliverables:**

- Sidecar-managed llama.cpp-compatible runtime with health, cancellation, streaming, batching limits, hardware detection, and safe shutdown.

**Acceptance criteria:**

- A supported quantized model completes fixture prompts on CPU; cancellation releases resources; runtime crash does not corrupt workflow or project data.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile service
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-07.S02.T02 - Implement model catalog, download/import, integrity, and license consent

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-07.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Model manifest catalog, resumable download or local import, checksums/signatures, disk estimates, license display, and removal.

**Deliverables:**

- Model manifest catalog, resumable download or local import, checksums/signatures, disk estimates, license display, and removal.

**Acceptance criteria:**

- Models cannot execute before integrity and license state are recorded; failed download resumes safely; removal is blocked while a job depends on the model.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

#### - [ ] CAP-07.S02.T03 - Implement hardware profiles and adaptive resource limits

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-07.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** CPU/GPU/RAM/VRAM detection, recommended models, context/batch caps, concurrency, thermal-friendly modes, and user overrides.

**Deliverables:**

- CPU/GPU/RAM/VRAM detection, recommended models, context/batch caps, concurrency, thermal-friendly modes, and user overrides.

**Acceptance criteria:**

- Low-resource test profiles remain responsive; unsafe allocations are refused or confirmed; effective limits appear in task provenance.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile e2e-local

### CAP-07.S03 - Approved remote model providers

**Outcome:** Remote inference is available through explicit opt-in adapters with redaction, data-class, and reproducibility controls.

**Wave / priority / status / review:** `W3` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-07.S01.T03`, `CAP-02.S04.T01`

#### - [ ] CAP-07.S03.T01 - Implement the first two external provider adapters behind the gateway

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-07.S01.T03`, `CAP-02.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Typed adapters for approved commercial/open endpoints with streaming, structured output, retries, rate handling, and normalized errors.

**Deliverables:**

- Typed adapters for approved commercial/open endpoints with streaming, structured output, retries, rate handling, and normalized errors.

**Acceptance criteria:**

- Provider-specific code does not leak into scholarly modules; contract tests replay recorded safe fixtures; missing credentials produce guided setup.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai

#### - [ ] CAP-07.S03.T02 - Implement egress preview, minimization, and consent

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-07.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Preflight showing provider, data class, text amount, rights status, redactions, retention policy link, and local alternative.

**Deliverables:**

- Preflight showing provider, data class, text amount, rights status, redactions, retention policy link, and local alternative.

**Acceptance criteria:**

- Protected or rights-restricted text is blocked by policy; user consent is scoped and revocable; the exact transmitted payload hash is logged without storing unnecessary plaintext.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local

#### - [ ] CAP-07.S03.T03 - Implement offline/network-disabled enforcement and remote fallback behavior

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `windows-x64`

**Dependencies:** `CAP-07.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Application and service controls that disable remote providers, fail closed, and continue with supported local paths.

**Deliverables:**

- Application and service controls that disable remote providers, fail closed, and continue with supported local paths.

**Acceptance criteria:**

- Network-disabled tests prove no external DNS/HTTP attempts from AI modules; queued remote jobs become blocked with clear remediation rather than silently rerouted.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local
- python tools/verify.py --profile e2e-local

### CAP-07.S04 - Prompt, schema, and structured-output registry

**Outcome:** AI behavior is reproducible and testable as versioned configuration rather than hidden prompt strings.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S01.T01`, `CAP-00.S05.T02`

#### - [ ] CAP-07.S04.T01 - Create versioned prompt and tool-template registry

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S01.T01`, `CAP-00.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Named templates with purpose, mode, variables, provider constraints, authorship, evaluation state, and change history.

**Deliverables:**

- Named templates with purpose, mode, variables, provider constraints, authorship, evaluation state, and change history.

**Acceptance criteria:**

- Every production model call references an immutable prompt version; unregistered ad hoc prompts are rejected outside development mode.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai

#### - [ ] CAP-07.S04.T02 - Implement schema-constrained generation and deterministic validation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** JSON-schema/Pydantic output requests, parsing, validation, bounded repair, missing/unclear states, and raw-response retention policy.

**Deliverables:**

- JSON-schema/Pydantic output requests, parsing, validation, bounded repair, missing/unclear states, and raw-response retention policy.

**Acceptance criteria:**

- Invalid output never enters canonical records; repair attempts are limited and logged; fixture malformed responses produce typed failure or validated recovery.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-07.S04.T03 - Implement prompt/schema regression tests and approval states

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Golden cases, semantic checks, safety/rights tests, model matrix, draft/validated/deprecated states, and upgrade comparison.

**Deliverables:**

- Golden cases, semantic checks, safety/rights tests, model matrix, draft/validated/deprecated states, and upgrade comparison.

**Acceptance criteria:**

- A model or prompt upgrade cannot become default if declared regressions exceed thresholds; approvals name benchmark, reviewer, and residual limitations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

### CAP-07.S05 - AI observability, budgets, and evaluation operations

**Outcome:** Model use is measurable by scholarly task, project, provider, quality, latency, and cost without exposing research content.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S04.T03`, `CAP-03.S03.T03`

#### - [ ] CAP-07.S05.T01 - Instrument model calls with redacted traces and usage accounting

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S04.T03`, `CAP-03.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Trace IDs, task type, model/config, token counts, duration, retries, validation, cache, failure, and optional cost.

**Deliverables:**

- Trace IDs, task type, model/config, token counts, duration, retries, validation, cache, failure, and optional cost.

**Acceptance criteria:**

- Metrics aggregate without raw sensitive prompts; a generated output links to its exact call records; local calls report resource use rather than fabricated monetary cost.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-07.S05.T02 - Implement project budgets, quotas, cache policy, and cancellation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Configurable limits for remote spend, tokens, concurrent local jobs, storage, repeated calls, and cache reuse.

**Deliverables:**

- Configurable limits for remote spend, tokens, concurrent local jobs, storage, repeated calls, and cache reuse.

**Acceptance criteria:**

- Budget exhaustion stops before provider charge where possible; cache reuse honors model/prompt/schema/data-right versions; user can cancel queued and active work.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile service
- python tools/verify.py --profile desktop

#### - [ ] CAP-07.S05.T03 - Create model evaluation dashboard and upgrade workflow

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-07.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Benchmark results by task/domain/model, calibration/error summaries, cost/latency, approval status, and controlled default switch.

**Deliverables:**

- Benchmark results by task/domain/model, calibration/error summaries, cost/latency, approval status, and controlled default switch.

**Acceptance criteria:**

- Users/admins can compare current and candidate models on the same registry cases; default change records rationale and marks dependent results according to reproducibility policy.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile desktop

## CAP-08 - Evidence schemas, extraction, verification, and adjudication

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Transform full text into source-grounded, mode-sensitive evidence records that distinguish observation, machine extraction, inference, verification, dispute, adjudication, and staleness.

**Exit criteria:**

- Researchers can define and version extraction schemas and ontology packs without losing original author wording.
- Every extracted value links to exact source anchors, extractor configuration, verifier outcome, confidence dimensions, and human review state.
- Evidence matrices support comparison, disagreement, adjudication, and export without turning missing information into invented data.

### CAP-08.S01 - Core ontology and schema-pack registry

**Outcome:** A small stable scholarly core can be extended by domain and method packs under explicit version governance.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-07.S04.T02`

#### - [ ] CAP-08.S01.T01 - Implement the stable core ontology and relation vocabulary

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S01.T03`, `CAP-07.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Versioned entities and relations for works, passages, theories, constructs, definitions, methods, measures, contexts, claims, findings, assumptions, stakeholders, and opportunities.

**Deliverables:**

- Versioned entities and relations for works, passages, theories, constructs, definitions, methods, measures, contexts, claims, findings, assumptions, stakeholders, and opportunities.

**Acceptance criteria:**

- Terms have stable IDs, labels, definitions, provenance, allowed relations, and deprecation rules; competing definitions are representable rather than overwritten.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile graph

#### - [ ] CAP-08.S01.T02 - Implement extraction-schema authoring and validation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Schema editor and API for fields, types, cardinality, controlled vocabularies, evidence requirements, prompts, verification, and mode applicability.

**Deliverables:**

- Schema editor and API for fields, types, cardinality, controlled vocabularies, evidence requirements, prompts, verification, and mode applicability.

**Acceptance criteria:**

- Invalid or cyclic schema dependencies fail before use; required evidence rules are explicit; schema drafts cannot silently change completed extractions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence

#### - [ ] CAP-08.S01.T03 - Implement ontology/schema import, export, fork, and version comparison

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Portable pack format with manifest, dependencies, mappings, license, signatures/checksums, and structured diff.

**Deliverables:**

- Portable pack format with manifest, dependencies, mappings, license, signatures/checksums, and structured diff.

**Acceptance criteria:**

- Imported packs are validated in isolation; project forks receive new identity; upgrades preview affected evidence and require explicit adoption.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile service

### CAP-08.S02 - Source-grounded extraction pipeline

**Outcome:** Schema-constrained extraction selects relevant source context and emits candidate evidence without fabricating absent fields.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S01.T03`, `CAP-05.S03.T03`, `CAP-07.S04.T02`

#### - [ ] CAP-08.S02.T01 - Implement section/passages selection for extraction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S01.T03`, `CAP-05.S03.T03`, `CAP-07.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Rule, search, embedding, and citation-aware selectors that produce bounded context packets with exact anchors and coverage metadata.

**Deliverables:**

- Rule, search, embedding, and citation-aware selectors that produce bounded context packets with exact anchors and coverage metadata.

**Acceptance criteria:**

- Selectors are reproducible; excluded sections remain queryable; context packets never exceed configured rights/model limits; selection provenance is retained.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile search
- python tools/verify.py --profile documents

#### - [ ] CAP-08.S02.T02 - Implement field and relation extraction workflows

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Batch and on-demand extractors using registered schemas, typed outputs, explicit not-reported/unclear/inferred states, and checkpoints.

**Deliverables:**

- Batch and on-demand extractors using registered schemas, typed outputs, explicit not-reported/unclear/inferred states, and checkpoints.

**Acceptance criteria:**

- Every nonempty value includes supporting anchors; absent values remain absent states; failed records retry independently; cancellation preserves completed candidates.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-08.S02.T03 - Implement normalization and entity-link candidate generation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Normalization for dates, samples, methods, measures, model/dataset names, construct synonyms, and links to ontology entities while retaining raw text.

**Deliverables:**

- Normalization for dates, samples, methods, measures, model/dataset names, construct synonyms, and links to ontology entities while retaining raw text.

**Acceptance criteria:**

- Normalized values never replace source wording; ambiguous links remain ranked candidates; unit conversions record formula and source unit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile service

### CAP-08.S03 - Evidence record, status, confidence, and uncertainty model

**Outcome:** Extracted content is stored with decomposed certainty and explicit epistemic status.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S02.T03`, `CAP-03.S03.T02`

#### - [ ] CAP-08.S03.T01 - Implement evidence-record persistence and lineage

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S02.T03`, `CAP-03.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Canonical record for field/relation, raw and normalized value, source anchors, extraction activity, schema, model, confidence dimensions, and dependencies.

**Deliverables:**

- Canonical record for field/relation, raw and normalized value, source anchors, extraction activity, schema, model, confidence dimensions, and dependencies.

**Acceptance criteria:**

- Evidence cannot commit without valid source revision and schema version; duplicate retries are idempotent; record history is immutable and queryable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile data

#### - [ ] CAP-08.S03.T02 - Implement observed, extracted, inferred, verified, disputed, adjudicated, and stale states

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** State machine, transition rules, labels, downstream-use policy, and UI badges for evidence status.

**Deliverables:**

- State machine, transition rules, labels, downstream-use policy, and UI badges for evidence status.

**Acceptance criteria:**

- Inferred content cannot be presented as direct source evidence; disputed alternatives coexist; only approved states are eligible for configured synthesis outputs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile service
- python tools/verify.py --profile desktop

#### - [ ] CAP-08.S03.T03 - Implement decomposed confidence and missingness

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Separate extraction, entailment, entity-link, comparability, source-quality, and corpus-coverage fields plus not-reported/unclear/not-applicable states.

**Deliverables:**

- Separate extraction, entailment, entity-link, comparability, source-quality, and corpus-coverage fields plus not-reported/unclear/not-applicable states.

**Acceptance criteria:**

- UI and exports do not collapse dimensions into one probability; missingness is filterable; each dimension states how it was generated and calibrated.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile desktop

### CAP-08.S04 - Independent evidence verification

**Outcome:** A separate verifier tests passage entailment, schema fit, anchor validity, and unsupported inference.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T03`, `CAP-07.S05.T03`

#### - [ ] CAP-08.S04.T01 - Implement verifier workflow and decision contract

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T03`, `CAP-07.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Independent model/rule/human verifier inputs, verdicts, reasons, confidence, corrected candidates, and escalation rules.

**Deliverables:**

- Independent model/rule/human verifier inputs, verdicts, reasons, confidence, corrected candidates, and escalation rules.

**Acceptance criteria:**

- Verifier cannot inherit hidden extractor output beyond the candidate and evidence packet; verdict references exact anchors; unavailable verification is explicit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

#### - [ ] CAP-08.S04.T02 - Implement entailment, anchor, and schema-fit checks

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** NLI/LLM/rule ensemble checks for support, contradiction, insufficient evidence, location validity, type/cardinality, and unsupported extrapolation.

**Deliverables:**

- NLI/LLM/rule ensemble checks for support, contradiction, insufficient evidence, location validity, type/cardinality, and unsupported extrapolation.

**Acceptance criteria:**

- Curated positive/negative fixtures meet declared thresholds; invalid anchors always fail; a fluent but unsupported candidate is rejected.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai
- python tools/verify.py --profile documents

#### - [ ] CAP-08.S04.T03 - Implement calibrated sampling and human-verification queues

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Risk-based and random audit samples, reviewer assignments, agreement tracking, escalation, and threshold reporting.

**Deliverables:**

- Risk-based and random audit samples, reviewer assignments, agreement tracking, escalation, and threshold reporting.

**Acceptance criteria:**

- High-consequence/low-confidence fields route to humans; audit sample is reproducible; project cannot claim validated extraction without recorded sample results.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile desktop

### CAP-08.S05 - Evidence matrix and source-first analysis UI

**Outcome:** Researchers can inspect, filter, compare, pivot, correct, and trace evidence at scale.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S04.T02`, `CAP-01.S02.T01`

#### - [ ] CAP-08.S05.T01 - Build scalable evidence matrix with saved views

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S04.T02`, `CAP-01.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Virtualized rows/columns, filters, sorting, grouping, frozen identifiers, saved views, and schema-specific layouts.

**Deliverables:**

- Virtualized rows/columns, filters, sorting, grouping, frozen identifiers, saved views, and schema-specific layouts.

**Acceptance criteria:**

- Target local matrix sizes remain interactive; every cell shows status/missingness; saved views reference stable schema fields and survive compatible upgrades.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence

#### - [ ] CAP-08.S05.T02 - Implement source inspection and alternative-candidate interaction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Cell detail with exact passages/pages, extraction/verifier provenance, raw/normalized values, alternative candidates, comments, and related records.

**Deliverables:**

- Cell detail with exact passages/pages, extraction/verifier provenance, raw/normalized values, alternative candidates, comments, and related records.

**Acceptance criteria:**

- User can inspect evidence without losing matrix position; selecting an alternative creates an adjudication rather than overwriting machine history.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence
- python tools/verify.py --profile documents

#### - [ ] CAP-08.S05.T03 - Implement bulk review, correction, and recomputation actions

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Selection-based verify, reject, normalize, tag, assign, re-extract, and stale-impact preview with permission and confirmation rules.

**Deliverables:**

- Selection-based verify, reject, normalize, tag, assign, re-extract, and stale-impact preview with permission and confirmation rules.

**Acceptance criteria:**

- Bulk actions report affected records before commit, operate atomically or provide itemized failures, and create per-record audit events.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence
- python tools/verify.py --profile service

### CAP-08.S06 - Coder comparison, adjudication, and evidence export

**Outcome:** Human plurality and review outcomes are measurable and preserved.

**Wave / priority / status / review:** `W3` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S05.T03`, `CAP-04.S04.T02`

#### - [ ] CAP-08.S06.T01 - Implement independent coder assignments and agreement metrics

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S05.T03`, `CAP-04.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Coder-specific views, blinded option, overlap samples, field/relation agreement, missingness agreement, and uncertainty intervals.

**Deliverables:**

- Coder-specific views, blinded option, overlap samples, field/relation agreement, missingness agreement, and uncertainty intervals.

**Acceptance criteria:**

- Metrics use appropriate denominators, distinguish exact from semantic agreement, and do not treat unresolved differences as error by default.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile desktop

#### - [ ] CAP-08.S06.T02 - Implement adjudication workspace and rationale records

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Side-by-side machine/coder alternatives, source context, discussion, decision, rationale, reviewer, and downstream impact.

**Deliverables:**

- Side-by-side machine/coder alternatives, source context, discussion, decision, rationale, reviewer, and downstream impact.

**Acceptance criteria:**

- Adjudication never deletes alternatives; unresolved plurality is a valid state; accepted decision records the exact evidence and schema version.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence

#### - [ ] CAP-08.S06.T03 - Implement evidence table and audit exports

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** CSV/XLSX-compatible CSV, JSON, JSON-LD, codebook, decision log, source-anchor manifest, and rights-aware package export.

**Deliverables:**

- CSV/XLSX-compatible CSV, JSON, JSON-LD, codebook, decision log, source-anchor manifest, and rights-aware package export.

**Acceptance criteria:**

- Exports reproduce current filters and status rules, include data dictionary and provenance IDs, and omit restricted text unless explicitly permitted.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile security-local

## CAP-09 - Scholarly graph, comparison sets, synthesis, and reproducibility

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Connect bibliographic structure to claims, constructs, methods, contexts, assumptions, evidence, and decisions; then produce source-grounded synthesis and reproducibility artifacts.

**Exit criteria:**

- Typed graph projections are derived from canonical records and every material edge is traceable and contestable.
- Contradiction analysis begins with explicit comparability rather than naive claim similarity.
- Synthesis and exports preserve supporting evidence, disagreement, uncertainty, rights, and exact project state.
- Synthesis and graph outputs can become evidence packets for study design, manuscript blueprints, drafting, and review without losing source lineage.

### CAP-09.S01 - Local graph domain and replaceable graph storage

**Outcome:** The system can query scholarly relations locally without binding the domain to a particular graph database.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T02`, `CAP-03.S05.T02`

#### - [ ] CAP-09.S01.T01 - Define graph node, edge, assertion, evidence, and dispute contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-08.S03.T02`, `CAP-03.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Typed graph projection schema, directionality, cardinality, provenance, confidence, status, temporal validity, and competing-edge representation.

**Deliverables:**

- Typed graph projection schema, directionality, cardinality, provenance, confidence, status, temporal validity, and competing-edge representation.

**Acceptance criteria:**

- Every analytical edge is either directly sourced or labeled inferred; edges can be disputed and superseded; canonical domain objects remain authoritative.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph

#### - [ ] CAP-09.S01.T02 - Implement the local graph projection and query adapter

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** SQLite-backed adjacency/index projection or embedded graph adapter with neighborhood, path, filter, aggregation, and pagination operations.

**Deliverables:**

- SQLite-backed adjacency/index projection or embedded graph adapter with neighborhood, path, filter, aggregation, and pagination operations.

**Acceptance criteria:**

- Fixture graph queries return deterministic results; rebuild from canonical records is possible; graph corruption cannot mutate canonical evidence.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile data

#### - [ ] CAP-09.S01.T03 - Implement projection updates, versioning, and consistency checks

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Incremental event-driven projection updates, full rebuild, projection version, lag metrics, and canonical-vs-projection validation.

**Deliverables:**

- Incremental event-driven projection updates, full rebuild, projection version, lag metrics, and canonical-vs-projection validation.

**Acceptance criteria:**

- Projection catches up after restart; duplicate events are idempotent; consistency checker identifies missing and extra nodes/edges precisely.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile service

### CAP-09.S02 - Claim, theory, construct, method, and context relations

**Outcome:** Internal paper semantics become a multi-granular argument representation with preserved wording and evidence.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T03`, `CAP-08.S06.T02`

#### - [ ] CAP-09.S02.T01 - Implement entity linking for theories, constructs, methods, measures, datasets, and contexts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T03`, `CAP-08.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Candidate links using identifiers, dictionaries, embeddings, and project ontology with alternate mappings and author wording.

**Deliverables:**

- Candidate links using identifiers, dictionaries, embeddings, and project ontology with alternate mappings and author wording.

**Acceptance criteria:**

- Gold entities meet declared precision/recall; ambiguous mappings remain reviewable; ontology mappings cite evidence or decision provenance.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence
- python tools/verify.py --profile search

#### - [ ] CAP-09.S02.T02 - Implement claim and argument relation candidate extraction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Candidate SUPPORTS, CONTRADICTS, QUALIFIES, EXTENDS, TESTS, DEFINES, OPERATIONALIZES_AS, ASSUMES, and boundary relations with source anchors.

**Deliverables:**

- Candidate SUPPORTS, CONTRADICTS, QUALIFIES, EXTENDS, TESTS, DEFINES, OPERATIONALIZES_AS, ASSUMES, and boundary relations with source anchors.

**Acceptance criteria:**

- Relation candidates include subject/object spans, evidence, direction, status, and uncertainty; direct citation stance is not misrepresented as full claim agreement.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence

#### - [ ] CAP-09.S02.T03 - Implement relation review, dispute, and adjudication

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Graph-focused queue and source view for accepting, rejecting, editing, or preserving competing relations and rationales.

**Deliverables:**

- Graph-focused queue and source view for accepting, rejecting, editing, or preserving competing relations and rationales.

**Acceptance criteria:**

- Accepted edge is traceable to reviewers and evidence; dispute prevents silent consensus; relation changes mark dependent analyses stale.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile desktop

### CAP-09.S03 - Comparability sets and contradiction candidates

**Outcome:** Studies are normalized into defensible comparison sets before support, contradiction, or boundary inference.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S02.T03`, `CAP-08.S05.T03`

#### - [ ] CAP-09.S03.T01 - Define mode-specific comparability dimensions and rules

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S02.T03`, `CAP-08.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned schemas for construct meaning, unit/level, population, context, time, measure, method, intervention, outcome, model/dataset, and evidence type.

**Deliverables:**

- Versioned schemas for construct meaning, unit/level, population, context, time, measure, method, intervention, outcome, model/dataset, and evidence type.

**Acceptance criteria:**

- Rules can be field/domain specific; unknown dimensions reduce comparability visibly; researchers can override with rationale.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence

#### - [ ] CAP-09.S03.T02 - Implement comparability clustering and pair explanation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Rule/embedding-assisted grouping, pairwise similarity/difference vector, hard exclusions, and cluster confidence.

**Deliverables:**

- Rule/embedding-assisted grouping, pairwise similarity/difference vector, hard exclusions, and cluster confidence.

**Acceptance criteria:**

- Known noncomparable fixtures remain separated; each grouping explains matching and differing dimensions; cluster membership is contestable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile search
- python tools/verify.py --profile ai

#### - [ ] CAP-09.S03.T03 - Implement support, contradiction, qualification, and boundary candidate detection

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Candidate analysis over comparable claims/findings with evidence packet, alternative explanation, and review state.

**Deliverables:**

- Candidate analysis over comparable claims/findings with evidence packet, alternative explanation, and review state.

**Acceptance criteria:**

- Candidates identify whether disagreement may arise from measure/context/time/method; no candidate is promoted as a finding without human confirmation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence
- python tools/verify.py --profile novelty

### CAP-09.S04 - Graph, theory, construct, and lineage workspaces

**Outcome:** Complex field structures are navigable through task-specific views rather than one undifferentiated network.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T03`, `CAP-06.S05.T01`

#### - [ ] CAP-09.S04.T01 - Build scalable claim and argument graph explorer

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S01.T03`, `CAP-06.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Filtered graph view, neighborhood expansion, clustering, edge/status legend, search, selection, and source/evidence side panel.

**Deliverables:**

- Filtered graph view, neighborhood expansion, clustering, edge/status legend, search, selection, and source/evidence side panel.

**Acceptance criteria:**

- View remains usable on target graph sizes through progressive loading; every visible edge opens its evidence and audit trail; layouts never change canonical state.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile graph

#### - [ ] CAP-09.S04.T02 - Build theory, construct-definition, and operationalization maps

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Views for definitions, synonyms, theory use, construct drift, measures, mechanisms, levels, contexts, and temporal lineage.

**Deliverables:**

- Views for definitions, synonyms, theory use, construct drift, measures, mechanisms, levels, contexts, and temporal lineage.

**Acceptance criteria:**

- Researchers can compare author wording and normalized mappings; definition changes over time are not collapsed; all nodes link to source anchors.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence

#### - [ ] CAP-09.S04.T03 - Build citation, semantic, method, and temporal map presets

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Reusable graph/canvas presets with visible inclusion criteria, weighting, layout parameters, and exportable snapshots.

**Deliverables:**

- Reusable graph/canvas presets with visible inclusion criteria, weighting, layout parameters, and exportable snapshots.

**Acceptance criteria:**

- Preset generation is deterministic for a snapshot; users can inspect why items cluster; exported image/data include filter and version manifest.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile graph
- python tools/verify.py --profile search

### CAP-09.S05 - Evidence-grounded synthesis and citation audit

**Outcome:** Narrative and tabular synthesis is downstream of accepted evidence and preserves disagreement and uncertainty.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S03.T03`, `CAP-08.S06.T02`

#### - [ ] CAP-09.S05.T01 - Implement synthesis plan and evidence-packet assembly

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S03.T03`, `CAP-08.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Outline/section plan linked to research intent, accepted evidence queries, inclusion rules, contradiction packets, and source limits.

**Deliverables:**

- Outline/section plan linked to research intent, accepted evidence queries, inclusion rules, contradiction packets, and source limits.

**Acceptance criteria:**

- Every planned claim has candidate supporting evidence or is labeled interpretive; excluded/disputed evidence rules are explicit; packet can be inspected before generation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

#### - [ ] CAP-09.S05.T02 - Implement source-grounded synthesis with claim-level citations

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Draft generation from evidence packets, sentence/claim segmentation, citation objects, uncertainty language, and preserved alternative findings.

**Deliverables:**

- Draft generation from evidence packets, sentence/claim segmentation, citation objects, uncertainty language, and preserved alternative findings.

**Acceptance criteria:**

- No factual sentence is accepted without supporting evidence links; generated prose cannot cite records outside the project; conflicting evidence is not silently averaged.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence
- python tools/verify.py --profile graph

#### - [ ] CAP-09.S05.T03 - Implement citation support, completeness, and mismatch audit

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Entailment and coverage checks between synthesis claims, cited passages, citation placement, and excluded evidence with review queue.

**Deliverables:**

- Entailment and coverage checks between synthesis claims, cited passages, citation placement, and excluded evidence with review queue.

**Acceptance criteria:**

- Unsupported or incomplete claims block final status; known mismatch fixtures are caught; auditor records model/rule versions and human disposition.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence
- python tools/verify.py --profile novelty

### CAP-09.S06 - Reproducibility packages and scholarly exports

**Outcome:** A project can produce a rights-aware record of corpus, searches, schemas, models, decisions, analysis, and outputs.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S05.T03`, `CAP-04.S04.T02`

#### - [ ] CAP-09.S06.T01 - Define reproducibility manifest and snapshot boundary

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S05.T03`, `CAP-04.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Manifest for project/intent versions, sources, query runs, corpus IDs/hashes, documents/access, schemas, models/prompts, decisions, workflows, environment, and limitations.

**Deliverables:**

- Manifest for project/intent versions, sources, query runs, corpus IDs/hashes, documents/access, schemas, models/prompts, decisions, workflows, environment, and limitations.

**Acceptance criteria:**

- Manifest distinguishes redistributable data from references to restricted sources; snapshot can be verified without requiring the original workstation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile service
- python tools/verify.py --profile data
- python tools/verify.py --profile graph

#### - [ ] CAP-09.S06.T02 - Implement PRISMA-compatible flow and review appendices

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Flow counts, exclusion reasons, search histories, screening/audit methods, extraction/verification summaries, and editable disclosure text.

**Deliverables:**

- Flow counts, exclusion reasons, search histories, screening/audit methods, extraction/verification summaries, and editable disclosure text.

**Acceptance criteria:**

- Counts reconcile with event ledger; method text names models/versions and human validation; user can inspect every aggregate before export.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile search
- python tools/verify.py --profile graph

#### - [ ] CAP-09.S06.T03 - Implement DOCX/Markdown/CSV/JSON-LD/graph export bundle

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Rights-filtered reports, evidence tables, graph data, dossier objects, manifests, checksums, and stable internal identifiers.

**Deliverables:**

- Rights-filtered reports, evidence tables, graph data, dossier objects, manifests, checksums, and stable internal identifiers.

**Acceptance criteria:**

- Exports open in target tools, contain no unresolved internal paths, pass citation/source link checks, and include a machine-readable inventory and rights report.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence
- python tools/verify.py --profile security-local

## CAP-10 - Novelty auditing, research opportunities, and plural research modes

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Move from evidence mapping to defensible opportunity dossiers through nearest-prior comparison, independent challenge, plural gap logic, critical problematization, and living research memory.

**Exit criteria:**

- The local MVP decomposes an idea, retrieves nearest prior work, compares facets, and produces bounded novelty language with human approval.
- Critical and hermeneutic workflows preserve alternative readings, researcher memos, explicit assumptions, and interpretive authority before theory/critical article production.
- Advanced detectors produce typed candidates with false-positive warnings rather than a universal gap score.
- Accepted opportunities can hand off explicitly to empirical study design or empirical/theory/critical manuscript-development workflows.
- Living-monitor changes can identify affected claims, designs, manuscripts, reviews, and opportunity assessments.

### CAP-10.S01 - Nearest-prior novelty workspace MVP

**Outcome:** A proposed research contribution can be decomposed and compared against the closest literature in a transparent local workflow.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S04.T02`, `CAP-06.S03.T03`

#### - [ ] CAP-10.S01.T01 - Implement research-concept and facet schema

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-09.S04.T02`, `CAP-06.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned concept object for problem, phenomenon, theory, constructs, mechanism, context, unit/level, method, data, expected contribution, and claimed distinctions.

**Deliverables:**

- Versioned concept object for problem, phenomenon, theory, constructs, mechanism, context, unit/level, method, data, expected contribution, and claimed distinctions.

**Acceptance criteria:**

- Required facets vary by mode; blank/uncertain facets remain explicit; revisions preserve rationale and link to the governing research intent.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty

#### - [ ] CAP-10.S01.T02 - Implement multi-route nearest-prior retrieval

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Facet queries across lexical, semantic, citation, bibliographic, and graph routes with candidate union, deduplication, threat-oriented reranking, and manifest.

**Deliverables:**

- Facet queries across lexical, semantic, citation, bibliographic, and graph routes with candidate union, deduplication, threat-oriented reranking, and manifest.

**Acceptance criteria:**

- Gold nearest-prior fixtures are recovered within declared k; each candidate shows retrieval routes and facet overlaps; missing full text is visible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile search
- python tools/verify.py --profile graph

#### - [ ] CAP-10.S01.T03 - Build facet comparison grid and threat review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Side-by-side concept versus prior-study comparison, evidence links, similarity/difference judgments, threat level, reviewer decision, and notes.

**Deliverables:**

- Side-by-side concept versus prior-study comparison, evidence links, similarity/difference judgments, threat level, reviewer decision, and notes.

**Acceptance criteria:**

- Every distinction cites source evidence or is labeled researcher interpretation; nearest records cannot be dismissed without rationale; unresolved threats block positive novelty status.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile novelty
- python tools/verify.py --profile documents

### CAP-10.S02 - Independent adversarial novelty challenge

**Outcome:** A separate workflow attempts to narrow or invalidate the proposed contribution rather than helping sell it.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S01.T03`, `CAP-09.S06.T01`

#### - [ ] CAP-10.S02.T01 - Implement terminology, historical-vocabulary, and adjacent-field expansion

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S01.T03`, `CAP-09.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Challenger generation of synonyms, construct variants, older labels, disciplinary framings, document types, and negative/alternative formulations.

**Deliverables:**

- Challenger generation of synonyms, construct variants, older labels, disciplinary framings, document types, and negative/alternative formulations.

**Acceptance criteria:**

- Every expansion has rationale and source/mode scope; researcher can accept/reject branches; expansions are executed as ordinary auditable search runs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile ai
- python tools/verify.py --profile search

#### - [ ] CAP-10.S02.T02 - Implement challenger orchestration and threat ranking

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Separate agent/workflow identity, retrieval budget, tool permissions, semantic nearest-neighbor search, citation traversal, and overlap/threat explanations.

**Deliverables:**

- Separate agent/workflow identity, retrieval budget, tool permissions, semantic nearest-neighbor search, citation traversal, and overlap/threat explanations.

**Acceptance criteria:**

- Generator state is not used as unexamined ground truth; challenger seeks disconfirming work; each threat explanation cites exact literature evidence and uncertainty.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile ai
- python tools/verify.py --profile service

#### - [ ] CAP-10.S02.T03 - Implement bounded novelty statement and approval gate

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Structured statement of corpus, databases, dates, terminology, closest studies, distinctions, residual uncertainty, and prohibited overclaims.

**Deliverables:**

- Structured statement of corpus, databases, dates, terminology, closest studies, distinctions, residual uncertainty, and prohibited overclaims.

**Acceptance criteria:**

- System cannot produce “never studied” as an approved claim; statement remains draft until threats and coverage are adjudicated; exported wording matches recorded scope.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence

### CAP-10.S03 - Research opportunity dossier and decision ledger

**Outcome:** A candidate moves from algorithmic signal to a reviewer-defensible, monitored scholarly object.

**Wave / priority / status / review:** `W4` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S02.T03`, `CAP-03.S05.T03`

#### - [ ] CAP-10.S03.T01 - Implement the complete opportunity dossier schema

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S02.T03`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Identity, question, importance, mechanism, evidence, closest work, disconfirmation, search manifest, diagnostics, novelty, study options, outcomes, scoring vector, adjudication, and monitoring.

**Deliverables:**

- Identity, question, importance, mechanism, evidence, closest work, disconfirmation, search manifest, diagnostics, novelty, study options, outcomes, scoring vector, adjudication, and monitoring.

**Acceptance criteria:**

- Schema represents unsupported and rejected candidates as well as accepted ones; all evidence-bearing sections link to canonical objects and versions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile service

#### - [ ] CAP-10.S03.T02 - Build dossier assembly, review, and export workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Guided desktop workspace that assembles evidence packets, nearest-prior comparisons, contribution under alternative outcomes, decisions, and publication-ready export.

**Deliverables:**

- Guided desktop workspace that assembles evidence packets, nearest-prior comparisons, contribution under alternative outcomes, decisions, and publication-ready export.

**Acceptance criteria:**

- Missing required sections and unresolved high threats block provisional acceptance; exported dossier includes bounded status and unresolved uncertainty.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence

#### - [ ] CAP-10.S03.T03 - Implement opportunity decision and outcome memory

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-10.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Accept/reject/defer/reopen decisions, rationales, related projects/manuscripts, later reviewer challenges, outcomes, and version history.

**Deliverables:**

- Accept/reject/defer/reopen decisions, rationales, related projects/manuscripts, later reviewer challenges, outcomes, and version history.

**Acceptance criteria:**

- Decisions never delete candidate history; a later paper or reviewer challenge can narrow/invalidate a prior assessment; changes propagate to linked outputs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile data
- python tools/verify.py --profile graph

### CAP-10.S05 - Critical and hermeneutic research support

**Outcome:** The system surfaces evidence-linked candidate assumptions and alternative framings without replacing interpretive authority.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T02`, `CAP-08.S01.T03`

#### - [ ] CAP-10.S05.T01 - Implement critical research ontology pack and candidate extraction

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T02`, `CAP-08.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned pack for authority, ownership, participation, contestability, exit, dependency, benefits, burdens, stakeholders, knowledge legitimacy, norms, and ecological boundaries.

**Deliverables:**

- Versioned pack for authority, ownership, participation, contestability, exit, dependency, benefits, burdens, stakeholders, knowledge legitimacy, norms, and ecological boundaries.

**Acceptance criteria:**

- Candidates always link to passages and include “why this reading may be wrong”; pack is editable/forkable; machine output remains a provocation, not an adjudicated fact.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile evidence
- python tools/verify.py --profile novelty

#### - [ ] CAP-10.S05.T02 - Build competing-reading and problematization workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Side-by-side assumptions, absences, stakeholder positions, alternative system boundaries, counter-readings, researcher memos, and adjudication.

**Deliverables:**

- Side-by-side assumptions, absences, stakeholder positions, alternative system boundaries, counter-readings, researcher memos, and adjudication.

**Acceptance criteria:**

- Multiple readings coexist; user can reject ontology framing; final interpretation requires named human approval and preserves dissent.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence

#### - [ ] CAP-10.S05.T03 - Implement hermeneutic search-read-interpret cycles and memo lineage

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Versioned questions, search branches, reading sets, memos, concept changes, and rationale links that show how understanding evolved.

**Deliverables:**

- Versioned questions, search branches, reading sets, memos, concept changes, and rationale links that show how understanding evolved.

**Acceptance criteria:**

- Changing interpretation can launch a new search branch without rewriting history; memos remain researcher-owned and are never silently replaced by summaries.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile search
- python tools/verify.py --profile graph

### CAP-10.S04 - Plural opportunity detector ensemble

**Outcome:** Opportunity signals are separated by contribution logic, evidence requirements, and false-positive risks.

**Wave / priority / status / review:** `W9` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T03`, `CAP-09.S03.T03`

#### - [ ] CAP-10.S04.T01 - Implement explicit, coverage, and future-work detectors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T03`, `CAP-09.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Author-stated gaps/limitations extraction, schema-cell sparsity with denominator, recency checks, and later-work challenge search.

**Deliverables:**

- Author-stated gaps/limitations extraction, schema-cell sparsity with denominator, recency checks, and later-work challenge search.

**Acceptance criteria:**

- Boilerplate is labeled; low density is not equated with importance; candidates include coverage scope and whether later work may address the statement.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence
- python tools/verify.py --profile search

#### - [ ] CAP-10.S04.T02 - Implement contradiction, boundary, measurement, and robustness detectors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Signals derived from comparability sets, claim relations, scope-vs-sample, definition/measure variation, controls, replications, and external validity.

**Deliverables:**

- Signals derived from comparability sets, claim relations, scope-vs-sample, definition/measure variation, controls, replications, and external validity.

**Acceptance criteria:**

- Candidates state alternative explanations and required human confirmations; incomparable studies are excluded or labeled; each detector has a benchmark set.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence

#### - [ ] CAP-10.S04.T03 - Implement bridge, structural, temporal, method, data, and theory-integration detectors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Graph bridges, semantic/citation separation, temporal shocks/drift, missing controls/data/benchmarks, and shared-mechanism candidates.

**Deliverables:**

- Graph bridges, semantic/citation separation, temporal shocks/drift, missing controls/data/benchmarks, and shared-mechanism candidates.

**Acceptance criteria:**

- Structural absence is presented as a signal rather than proof; every candidate identifies why the relation could matter and the principal false-positive explanation.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile graph
- python tools/verify.py --profile search

### CAP-10.S06 - Opportunity radar, ranking, and portfolio governance

**Outcome:** Researchers can compare candidates on transparent dimensions without collapsing them into an opaque novelty score.

**Wave / priority / status / review:** `W9` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `platform-neutral`

**Dependencies:** `CAP-10.S04.T03`, `CAP-10.S05.T02`

#### - [ ] CAP-10.S06.T01 - Implement multi-objective opportunity scoring vectors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `platform-neutral`

**Dependencies:** `CAP-10.S04.T03`, `CAP-10.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Evidence strength, theoretical leverage, substantive importance, prior-work distance, challenge robustness, tractability, data access, ethics, timeliness, and program fit with uncertainty.

**Deliverables:**

- Evidence strength, theoretical leverage, substantive importance, prior-work distance, challenge robustness, tractability, data access, ethics, timeliness, and program fit with uncertainty.

**Acceptance criteria:**

- Raw dimensions and evidence remain visible; weights are optional, versioned, and user-defined; missing values are not defaulted to favorable scores.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence

#### - [ ] CAP-10.S06.T02 - Build Pareto radar and candidate comparison workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `platform-neutral`

**Dependencies:** `CAP-10.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Filters, Pareto fronts, type-specific warnings, uncertainty, nearest-prior threat, diversity, and side-by-side dossier comparison.

**Deliverables:**

- Filters, Pareto fronts, type-specific warnings, uncertainty, nearest-prior threat, diversity, and side-by-side dossier comparison.

**Acceptance criteria:**

- Ranking can be reproduced from saved inputs; changing weights does not mutate underlying evidence; users can explain why one candidate dominates another.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile novelty

#### - [ ] CAP-10.S06.T03 - Implement portfolio links, duplication checks, and convergence monitoring

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `UNI`, `CLD` / `platform-neutral`

**Dependencies:** `CAP-10.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Connections among lab projects, researchers, shared constructs/data, overlapping candidates, prior rejections, and similarity alerts with privacy boundaries.

**Deliverables:**

- Connections among lab projects, researchers, shared constructs/data, overlapping candidates, prior rejections, and similarity alerts with privacy boundaries.

**Acceptance criteria:**

- Private projects do not leak content through similarity outputs; duplicate warnings show evidence and can be dismissed with rationale; convergence is a diagnostic, not an automatic block.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile novelty
- python tools/verify.py --profile graph
- python tools/verify.py --profile security-local

### CAP-10.S07 - Living monitor and impact-aware research memory

**Outcome:** New literature is evaluated as a change to existing claims, syntheses, and opportunity assessments rather than as a generic alert.

**Wave / priority / status / review:** `W9` / `P1` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T03`, `CAP-09.S06.T01`

#### - [ ] CAP-10.S07.T01 - Implement saved monitors and differential source retrieval

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T03`, `CAP-09.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Scheduled/manual monitor definitions using exact queries, semantic/citation conditions, source cursors, cutoff, rights, and project policies.

**Deliverables:**

- Scheduled/manual monitor definitions using exact queries, semantic/citation conditions, source cursors, cutoff, rights, and project policies.

**Acceptance criteria:**

- Monitor runs retrieve only new/changed candidates where supported, preserve source errors, and never alter corpus membership without screening rules.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile search
- python tools/verify.py --profile service

#### - [ ] CAP-10.S07.T02 - Implement new-paper triage and impact analysis

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S07.T01`

**Owner / review:** - / - (`-`)

**Objective:** Compare new records/evidence with existing claims, clusters, syntheses, nearest-prior sets, and dossiers; generate affected-object candidates.

**Deliverables:**

- Compare new records/evidence with existing claims, clusters, syntheses, nearest-prior sets, and dossiers; generate affected-object candidates.

**Acceptance criteria:**

- Impact is evidence-linked and labeled candidate; irrelevant new work can be dismissed with rationale; accepted changes mark exact dependencies stale.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile graph
- python tools/verify.py --profile novelty
- python tools/verify.py --profile evidence

#### - [ ] CAP-10.S07.T03 - Build living-review change report and reassessment workflow

**Status / priority / estimate / risk:** `NOT_STARTED` / `P1` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S07.T02`

**Owner / review:** - / - (`-`)

**Objective:** Version comparison, strengthened/narrowed/invalidated claim candidates, changed coverage, required decisions, and updated exports.

**Deliverables:**

- Version comparison, strengthened/narrowed/invalidated claim candidates, changed coverage, required decisions, and updated exports.

**Acceptance criteria:**

- A change report reconciles additions and decisions; prior outputs remain accessible; accepted update creates new versions and records why conclusions changed.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile graph
- python tools/verify.py --profile e2e-local

## CAP-11 - Windows PC/lab product hardening, validation, packaging, and release

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Turn the local architecture and research workflows into a dependable Windows product for individual researchers and laboratory computers before server or cloud delivery begins.

**Exit criteria:**

- Representative end-to-end research projects complete offline on supported PC profiles with no developer intervention.
- Installation, upgrade, backup, restore, crash recovery, security, accessibility, and support procedures pass release gates.
- Lab administrators can deploy, configure, diagnose, and update multiple stations while projects remain locally governed.
- Representative users can select an objective, understand the guided path, move between primary steps and supporting tools, and complete each approved use-case workflow without external instruction.

### CAP-11.S01 - Performance profiles, scale targets, and resource governance

**Outcome:** The product has measured local limits and remains responsive under realistic corpus, document, model, and workflow loads.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-10.S03.T02`, `CAP-07.S02.T03`

#### - [ ] CAP-11.S01.T01 - Define supported PC and lab hardware profiles and target workloads

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-10.S03.T02`, `CAP-07.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Minimum, recommended, and high-capability profiles with corpus size, document pages, embeddings, concurrent jobs, model classes, latency, and disk targets.

**Deliverables:**

- Minimum, recommended, and high-capability profiles with corpus size, document pages, embeddings, concurrent jobs, model classes, latency, and disk targets.

**Acceptance criteria:**

- Profiles are grounded in repeatable benchmarks; unsupported combinations produce warnings; no marketing claim exceeds tested configurations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local

#### - [ ] CAP-11.S01.T02 - Build representative local performance and endurance benchmarks

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Automated ingest, parse, index, search, extraction, graph, backup, and long-run workflow scenarios with resource telemetry.

**Deliverables:**

- Automated ingest, parse, index, search, extraction, graph, backup, and long-run workflow scenarios with resource telemetry.

**Acceptance criteria:**

- Benchmarks run from a known snapshot, detect regression thresholds, and include low-memory/disk-pressure cases; results are versioned in the registry.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

#### - [ ] CAP-11.S01.T03 - Implement adaptive concurrency, throttling, and low-resource modes

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Central resource governor for CPU, RAM, GPU/VRAM, disk, model jobs, parser jobs, interactive priority, and pause/resume.

**Deliverables:**

- Central resource governor for CPU, RAM, GPU/VRAM, disk, model jobs, parser jobs, interactive priority, and pause/resume.

**Acceptance criteria:**

- Desktop remains responsive during heavy work; low-resource mode completes fixture workflow within declared limits; users can see and override safe defaults.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile service

### CAP-11.S02 - Reliability, crash recovery, upgrade, and rollback

**Outcome:** Expected failures do not lose accepted scholarly work or leave projects in ambiguous states.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S01.T03`, `CAP-02.S02.T02`

#### - [ ] CAP-11.S02.T01 - Implement fault-injection test suite for local workflows

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S01.T03`, `CAP-02.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Tests for app/service/worker termination, power-like interruption, disk full, corrupted cache, unavailable model, parser crash, and provider failure.

**Deliverables:**

- Tests for app/service/worker termination, power-like interruption, disk full, corrupted cache, unavailable model, parser crash, and provider failure.

**Acceptance criteria:**

- Each scenario has documented expected recovery; canonical transactions remain consistent; failures produce traceable, actionable diagnostics.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile data

#### - [ ] CAP-11.S02.T02 - Implement startup recovery and project health repair

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Recovery scan for locks, queue leases, incomplete objects, migration state, projection lag, stale outputs, and damaged optional caches.

**Deliverables:**

- Recovery scan for locks, queue leases, incomplete objects, migration state, projection lag, stale outputs, and damaged optional caches.

**Acceptance criteria:**

- Startup never performs destructive repair silently; safe repairs are idempotent; risky repairs require verified backup and user approval.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile desktop
- python tools/verify.py --profile data

#### - [ ] CAP-11.S02.T03 - Validate application/project upgrade and application rollback matrix

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Automated supported-version upgrade paths, project migrations, sidecar compatibility, update rollback, and forward-open restrictions.

**Deliverables:**

- Automated supported-version upgrade paths, project migrations, sidecar compatibility, update rollback, and forward-open restrictions.

**Acceptance criteria:**

- Every supported prior version upgrades through a clean backup; rollback does not open a migrated project unsafely; failures leave a documented recovery artifact.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile data
- python tools/verify.py --profile e2e-local

### CAP-11.S03 - Offline, privacy, and local security acceptance

**Outcome:** The local edition has verified no-account/offline behavior and a reviewed threat/control baseline.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S02.T03`, `CAP-07.S03.T03`, `CAP-09.S06.T03`

#### - [ ] CAP-11.S03.T01 - Execute offline and air-gapped workflow acceptance

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S02.T03`, `CAP-07.S03.T03`, `CAP-09.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Network-blocked tests covering project creation, import, local documents, search, screening, local models, evidence, graph, novelty, export, backup, and restore.

**Deliverables:**

- Network-blocked tests covering project creation, import, local documents, search, screening, local models, evidence, graph, novelty, export, backup, and restore.

**Acceptance criteria:**

- Complete benchmark workflow succeeds without network or account; unavailable online features are clearly labeled and do not block basic use.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

#### - [ ] CAP-11.S03.T02 - Complete local threat model and security test plan

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Threats and controls for loopback IPC, untrusted documents, plugins, model files, secrets, update chain, path traversal, logs, exports, and lab policy.

**Deliverables:**

- Threats and controls for loopback IPC, untrusted documents, plugins, model files, secrets, update chain, path traversal, logs, exports, and lab policy.

**Acceptance criteria:**

- Security review resolves critical/high findings or documents approved exceptions with owners and expiry; penetration-oriented tests are automated where feasible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile security-local

#### - [ ] CAP-11.S03.T03 - Complete privacy, rights, deletion, and disclosure review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Data-flow inventory, egress matrix, telemetry defaults, retention, deletion claims, rights enforcement tests, AI-use disclosure, and user-facing notices.

**Deliverables:**

- Data-flow inventory, egress matrix, telemetry defaults, retention, deletion claims, rights enforcement tests, AI-use disclosure, and user-facing notices.

**Acceptance criteria:**

- No hidden content egress is found; restricted fixtures are blocked at every tested boundary; disclosures accurately distinguish local, remote, and derived processing.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile security-local
- python tools/verify.py --profile e2e-local

### CAP-11.S04 - Accessibility, usability, onboarding, and help

**Outcome:** Researchers can learn and operate the local product without specialist system administration or inaccessible interaction barriers.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S02.T03`, `CAP-10.S03.T02`

#### - [ ] CAP-11.S04.T01 - Complete WCAG-oriented desktop accessibility audit and remediation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S02.T03`, `CAP-10.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Keyboard, focus, semantics, contrast, scaling, screen reader, reduced motion, tables, graphs, dialogs, notifications, and document viewer audit.

**Deliverables:**

- Keyboard, focus, semantics, contrast, scaling, screen reader, reduced motion, tables, graphs, dialogs, notifications, and document viewer audit.

**Acceptance criteria:**

- No critical accessibility defects remain in release workflows; exceptions have tested alternative access; results and test environment are documented.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop

#### - [ ] CAP-11.S04.T02 - Conduct task-based usability studies on core local workflows

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Study protocol and findings for setup, corpus import, document inspection, search, screening, extraction, graph, novelty, export, and recovery.

**Deliverables:**

- Study protocol and findings for setup, corpus import, document inspection, search, screening, extraction, graph, novelty, export, and recovery.

**Acceptance criteria:**

- Representative researchers complete core tasks; critical failures are remediated; findings distinguish learnability, efficiency, trust calibration, and control.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.
- Study tasks are organized by scholarly objective and evaluate continuity across the ordered workflow rather than isolated page usability alone.

**Verification:**

- python tools/verify.py --profile e2e-local

#### - [ ] CAP-11.S04.T03 - Implement onboarding, contextual help, tutorials, and sample project

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** First-run checks, guided project, glossary, mode explanations, evidence/provenance guidance, shortcuts, troubleshooting, and searchable help.

**Deliverables:**

- First-run checks, guided project, glossary, mode explanations, evidence/provenance guidance, shortcuts, troubleshooting, and searchable help.

**Acceptance criteria:**

- A new user completes a sample evidence-to-novelty workflow without external instructions; help is available offline and matches the released UI.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-11.S04.T04 - Validate objective-specific guided workflows with researchers

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `windows-x64`

**Dependencies:** `CAP-03.S06.T05`, `CAP-11.S04.T02`, `CAP-11.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Evaluate whether researchers can choose the correct use case, understand the ordered path, move between primary and supporting tools, recover context, and complete representative work without perceiving disconnected utilities.

**Deliverables:**

- Usability protocol and findings across the eight workflow profiles, prioritized remediations, and approval evidence for the released UI reference.

**Acceptance criteria:**

- Participants can explain their current stage, prior/next step, expected output, and why supporting tools are available.
- Testing covers at least rapid orientation, systematic/scoping review, theory synthesis, critical problematization, and novelty audit, with the remaining profiles evaluated through expert walkthrough or task test.
- Material workflow or navigation changes update and obtain approval for the UI reference before application remediation begins.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile desktop
- python tools/taskctl.py validate

### CAP-11.S05 - Lab deployment, policy, maintenance, and support

**Outcome:** A laboratory can manage multiple independent PCs while retaining local project operation and predictable support.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S05.T03`, `CAP-02.S05.T03`

#### - [ ] CAP-11.S05.T01 - Create laboratory deployment and machine-policy package

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LAB` / `windows-x64`

**Dependencies:** `CAP-01.S05.T03`, `CAP-02.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Silent installer examples, policy schema, approved data/model/cache paths, provider restrictions, update channel, log retention, and uninstall procedures.

**Deliverables:**

- Silent installer examples, policy schema, approved data/model/cache paths, provider restrictions, update channel, log retention, and uninstall procedures.

**Acceptance criteria:**

- Deployment succeeds through a standard lab software-distribution workflow; protected settings cannot be overridden accidentally; policy validation is visible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-11.S05.T02 - Implement lab-safe model and parser cache seeding

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Offline/semi-offline cache bundle, manifest, checksum verification, approved-model list, shared read-only cache option, and update procedure.

**Deliverables:**

- Offline/semi-offline cache bundle, manifest, checksum verification, approved-model list, shared read-only cache option, and update procedure.

**Acceptance criteria:**

- A lab can seed approved models without each station downloading them; tampered or unapproved artifacts are rejected; cache sharing never enables concurrent project writes.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-11.S05.T03 - Create redacted support, diagnostics, and maintenance runbooks

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Admin/user runbooks for install, update, backup, restore, storage pressure, model/runtime issues, logs, support bundle, and escalation.

**Deliverables:**

- Admin/user runbooks for install, update, backup, restore, storage pressure, model/runtime issues, logs, support bundle, and escalation.

**Acceptance criteria:**

- Runbooks resolve seeded incidents without developer access to research content; support bundles honor redaction and rights rules; escalation captures reproducible facts.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

### CAP-11.S06 - Local release candidate and acceptance gate

**Outcome:** The PC/lab edition is released only after technical, scholarly, and operational acceptance on representative workflows.

**Wave / priority / status / review:** `W5` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S03.T03`, `CAP-11.S04.T03`, `CAP-11.S05.T03`, `CAP-10.S03.T03`

#### - [ ] CAP-11.S06.T01 - Assemble the release-candidate build and signed manifest

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S03.T03`, `CAP-11.S04.T03`, `CAP-11.S05.T03`, `CAP-10.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned installer, sidecar, model/parser compatibility list, notices, SBOM, signatures, checksums, release notes, and known limitations.

**Deliverables:**

- Versioned installer, sidecar, model/parser compatibility list, notices, SBOM, signatures, checksums, release notes, and known limitations.

**Acceptance criteria:**

- Artifacts reproduce from tagged source; signatures/checksums verify; notices cover bundled dependencies/models; version handshake and upgrade policy match the manifest.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate
- python tools/verify.py --profile desktop
- python tools/verify.py --profile security-local

#### - [ ] CAP-11.S06.T02 - Run complete local end-to-end acceptance and regression suite

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `L` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Automated and manual workflow from intent through corpus, documents, search, screening, evidence, graph, novelty, export, backup, restore, and update.

**Deliverables:**

- Automated and manual workflow from intent through corpus, documents, search, screening, evidence, graph, novelty, export, backup, restore, and update.

**Acceptance criteria:**

- All P0 tasks are DONE; release-blocking thresholds pass; failures have evidence and disposition; final results identify hardware and dataset profiles.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.
- Acceptance exercises the fourteen approved use-case profiles, adaptive navigation, supporting-tool access, reference conformance, and recovery of workflow context after restart.

**Verification:**

- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

#### - [ ] CAP-11.S06.T03 - Approve G5 and publish PC/lab version 1.0 documentation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`

**Dependencies:** `CAP-11.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Signed gate record, user/admin manuals, architecture/AI disclosure, support policy, benchmark limits, known issues, and university/cloud unlock decision.

**Deliverables:**

- Signed gate record, user/admin manuals, architecture/AI disclosure, support policy, benchmark limits, known issues, and university/cloud unlock decision.

**Acceptance criteria:**

- Gate approval names reviewers and evidence; no P0 critical issue is open; W7 tasks remain DEFERRED unless the approval explicitly unlocks them.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile foundation
- python tools/taskctl.py validate

## CAP-12 - University-hosted deployment, institutional identity, collaboration, and operations

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Run the same scholarly application against institution-controlled services and storage while preserving the desktop client, domain contracts, evidence lineage, and rights-aware governance.

**Exit criteria:**

- The desktop can switch between local and university connection profiles without a forked interface or incompatible project semantics.
- University services provide SSO, project isolation, collaboration, licensed-source enforcement, durable workflows, observability, backup, and recovery.
- A pilot research group completes a full workflow under institution-approved security and operations controls.

### CAP-12.S01 - Desktop remote connection mode and API abstraction

**Outcome:** The canonical client can connect securely to a university project home while retaining local caches and clear deployment context.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-11.S06.T03`

#### - [ ] CAP-12.S01.T01 - Extract local/remote service interfaces behind a client gateway

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-11.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Versioned desktop data/service gateway with local sidecar and remote HTTP/WebSocket implementations, capability negotiation, and common errors.

**Deliverables:**

- Versioned desktop data/service gateway with local sidecar and remote HTTP/WebSocket implementations, capability negotiation, and common errors.

**Acceptance criteria:**

- Existing local tests remain green; UI modules do not branch on vendor/deployment internals; unsupported remote capabilities are visible before use.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile server

#### - [ ] CAP-12.S01.T02 - Implement university connection profiles and secure onboarding

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Server URL discovery/validation, OIDC sign-in launch, certificate/policy display, capability/version check, and profile management.

**Deliverables:**

- Server URL discovery/validation, OIDC sign-in launch, certificate/policy display, capability/version check, and profile management.

**Acceptance criteria:**

- Profiles never store passwords; invalid/untrusted endpoints are rejected; users can clearly distinguish local from institutional project context.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile server
- python tools/verify.py --profile security-local

#### - [ ] CAP-12.S01.T03 - Implement bounded local cache and disconnected-read behavior

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Encrypted metadata/preview cache, cache rights/retention policy, invalidation, user clearing, and explicit offline limitations.

**Deliverables:**

- Encrypted metadata/preview cache, cache rights/retention policy, invalidation, user clearing, and explicit offline limitations.

**Acceptance criteria:**

- Restricted content follows institutional policy; stale cache is labeled; disconnected edits are either safely queued for supported objects or blocked explicitly.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile server
- python tools/verify.py --profile security-local

### CAP-12.S02 - Institutional service and data-plane foundation

**Outcome:** A deployable server stack implements the shared domain services with production-grade relational, object, vector, and workflow infrastructure.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S01.T01`, `CAP-03.S04.T03`

#### - [ ] CAP-12.S02.T01 - Containerize service and worker roles and define institutional deployment profiles

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S01.T01`, `CAP-03.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Hardened OCI images, nonroot execution, health/readiness, configuration and secret injection, SBOM, resource limits, and a single-server Compose/Podman reference profile; Helm/Kubernetes is added only when an institutional topology ADR selects it.

**Deliverables:**

- Hardened OCI images, nonroot execution, health/readiness, configuration and secret injection, SBOM, resource limits, and a single-server Compose/Podman reference profile; Helm/Kubernetes is added only when an institutional topology ADR selects it.

**Acceptance criteria:**

- Images build reproducibly, contain no embedded secrets, pass vulnerability policy, and separate API, parser, model, and general worker responsibilities; the pilot runs on the documented single-server profile without assuming Kubernetes.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S02.T02 - Implement PostgreSQL, S3-compatible object, and Qdrant adapters

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Server persistence adapters preserving repository/object/vector contracts, migrations, encryption configuration, and consistency checks.

**Deliverables:**

- Server persistence adapters preserving repository/object/vector contracts, migrations, encryption configuration, and consistency checks.

**Acceptance criteria:**

- Contract suites pass against local and server adapters; tenant/project scope is mandatory; object/vector references reconcile to canonical records.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile data

#### - [ ] CAP-12.S02.T03 - Implement Temporal-based durable workflow executor

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Mapping from portable workflow contracts to Temporal workflows/activities, human tasks, retries, cancellation, versioning, and visibility.

**Deliverables:**

- Mapping from portable workflow contracts to Temporal workflows/activities, human tasks, retries, cancellation, versioning, and visibility.

**Acceptance criteria:**

- Representative local workflow runs equivalently on Temporal; retries are idempotent; workflow code upgrades follow safe versioning rules.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile service

### CAP-12.S03 - Institutional identity, authorization, and project isolation

**Outcome:** University users authenticate through OIDC and access only permitted projects, sources, models, and administrative functions.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S02.T03`

#### - [ ] CAP-12.S03.T01 - Implement OIDC authorization-code with PKCE and session management

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Desktop browser sign-in, short-lived access, refresh/reauthentication, logout, group claims, and server token validation.

**Deliverables:**

- Desktop browser sign-in, short-lived access, refresh/reauthentication, logout, group claims, and server token validation.

**Acceptance criteria:**

- Token replay and expired sessions fail; desktop stores refresh material in OS protection; sign-out revokes/clears sessions according to provider capability.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S03.T02 - Implement RBAC/ABAC and policy enforcement points

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Roles for researcher, reviewer, project admin, librarian/rights admin, model admin, platform admin plus project/data-class attributes.

**Deliverables:**

- Roles for researcher, reviewer, project admin, librarian/rights admin, model admin, platform admin plus project/data-class attributes.

**Acceptance criteria:**

- Every service operation has an authorization test; default is deny; policy decisions include principal, resource, action, rule, and trace without leaking content.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S03.T03 - Implement project and tenant isolation tests

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Repository, object, vector, workflow, cache, export, log, and admin isolation test suite including malicious identifiers and bulk operations.

**Deliverables:**

- Repository, object, vector, workflow, cache, export, log, and admin isolation test suite including malicious identifiers and bulk operations.

**Acceptance criteria:**

- Cross-project/tenant fixture attacks fail across every boundary; support/admin access is explicit and audited; no aggregate dashboard exposes unauthorized metadata.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

### CAP-12.S04 - Team collaboration and scholarly adjudication

**Outcome:** Research groups can share projects, assign work, compare decisions, discuss disputes, and retain scholarly plurality.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T03`, `CAP-08.S06.T02`

#### - [ ] CAP-12.S04.T01 - Implement team membership, roles, invitations, and project sharing

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T03`, `CAP-08.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Membership lifecycle, group mapping, invitation/approval policy, role changes, removal, and access review.

**Deliverables:**

- Membership lifecycle, group mapping, invitation/approval policy, role changes, removal, and access review.

**Acceptance criteria:**

- Removed members lose access promptly; role changes are audited; project owner cannot accidentally make restricted sources globally visible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile desktop

#### - [ ] CAP-12.S04.T02 - Implement collaborative screening, coding, verification, and task assignment

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Assignments, reviewer queues, blinded stages, comments, mentions, due dates, notifications, and conflict states.

**Deliverables:**

- Assignments, reviewer queues, blinded stages, comments, mentions, due dates, notifications, and conflict states.

**Acceptance criteria:**

- Concurrent edits use explicit version/conflict handling; notifications do not leak protected content; offline caches respect updated access.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile desktop
- python tools/verify.py --profile evidence

#### - [ ] CAP-12.S04.T03 - Implement team adjudication, memos, and unresolved-plurality support

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Decision meetings/workspace, alternatives, votes where configured, named adjudicator, rationale, memos, and preserved dissent.

**Deliverables:**

- Decision meetings/workspace, alternatives, votes where configured, named adjudicator, rationale, memos, and preserved dissent.

**Acceptance criteria:**

- Consensus is not inferred from silence; all final decisions identify authority and evidence; unresolved disagreement remains exportable and analyzable.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile desktop
- python tools/verify.py --profile graph

### CAP-12.S05 - Licensed sources, institutional rights, retention, and compute policy

**Outcome:** Institutional entitlements and unpublished materials are governed consistently across search, storage, model egress, collaboration, and export.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T02`, `CAP-04.S05.T03`, `CAP-07.S01.T03`

#### - [ ] CAP-12.S05.T01 - Implement licensed-source adapter and entitlement framework

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S03.T02`, `CAP-04.S05.T03`, `CAP-07.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Adapter hooks for proxy/link resolver/database exports, user/group entitlement claims, terms metadata, access checks, and audit.

**Deliverables:**

- Adapter hooks for proxy/link resolver/database exports, user/group entitlement claims, terms metadata, access checks, and audit.

**Acceptance criteria:**

- A source record is accessible only to entitled principals; adapter cannot redistribute full text through exports; terms and retrieval context remain attached.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S05.T02 - Implement institutional data classification, retention, and legal-hold policies

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Policy sets for public, licensed, sensitive, unpublished, regulated, and restricted data with storage, model, sharing, export, retention, deletion, and hold rules.

**Deliverables:**

- Policy sets for public, licensed, sensitive, unpublished, regulated, and restricted data with storage, model, sharing, export, retention, deletion, and hold rules.

**Acceptance criteria:**

- Conflicting policies resolve predictably and visibly; legal hold blocks deletion; policy changes identify affected content and operations.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S05.T03 - Implement institutional model/provider and research-compute routing

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Approved model catalog, on-prem vLLM/compute endpoints, external-provider restrictions, quotas, scheduling classes, and provenance.

**Deliverables:**

- Approved model catalog, on-prem vLLM/compute endpoints, external-provider restrictions, quotas, scheduling classes, and provenance.

**Acceptance criteria:**

- Restricted data routes only to approved compute; provider changes are centrally governed; local/remote model results use the same evidence and evaluation contracts.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server
- python tools/verify.py --profile ai

### CAP-12.S06 - Institutional operations, disaster recovery, and pilot acceptance

**Outcome:** The university edition is observable, supportable, recoverable, and validated with a real research group.

**Wave / priority / status / review:** `W10` / `P2` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S04.T03`, `CAP-12.S05.T03`

#### - [ ] CAP-12.S06.T01 - Implement centralized observability, audit, and administration

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S04.T03`, `CAP-12.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Metrics, traces, logs, queue/workflow health, storage, model usage, rights events, audit search, redaction, dashboards, and alerts.

**Deliverables:**

- Metrics, traces, logs, queue/workflow health, storage, model usage, rights events, audit search, redaction, dashboards, and alerts.

**Acceptance criteria:**

- An operator can trace a user-visible failure without reading project content; alert thresholds and runbooks exist; privileged actions are separately audited.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S06.T02 - Implement backup, restore, disaster recovery, and upgrade procedures

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** PostgreSQL/object/vector/workflow backups, consistency points, encryption keys, restore validation, RPO/RTO tests, schema/workflow upgrade, and rollback plan.

**Deliverables:**

- PostgreSQL/object/vector/workflow backups, consistency points, encryption keys, restore validation, RPO/RTO tests, schema/workflow upgrade, and rollback plan.

**Acceptance criteria:**

- A staged disaster recovery exercise restores a representative project with intact evidence/provenance; RPO/RTO results are recorded and within approved targets.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

#### - [ ] CAP-12.S06.T03 - Deploy and evaluate a university pilot; approve G7

**Status / priority / estimate / risk:** `DEFERRED` / `P2` / `L` / `high`

**Profiles / platforms:** `UNI` / `platform-neutral`

**Dependencies:** `CAP-12.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Production-like pilot, onboarding, security/rights approval, support process, end-to-end research workflow, user evaluation, issue disposition, and gate record.

**Deliverables:**

- Production-like pilot, onboarding, security/rights approval, support process, end-to-end research workflow, user evaluation, issue disposition, and gate record.

**Acceptance criteria:**

- Pilot completes without local/server semantic divergence; critical issues are closed; gate approval explicitly decides whether managed-cloud work may leave DEFERRED.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile server

## CAP-13 - Managed cloud control plane, tenant data planes, governance, and SaaS operations

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Deliver the same desktop-led product as a secure managed service with regional tenant isolation, elastic workers, metering, residency, support, and commercial operations.

**Exit criteria:**

- Organizations and tenant data planes provision through a governed control plane with tested isolation and residency.
- Cloud compute, model use, storage, quotas, billing, audit, incident response, backup, and disaster recovery meet declared service objectives.
- Cloud delivery preserves the local/university evidence, provenance, rights, and bounded-novelty semantics rather than weakening them for convenience.

### CAP-13.S01 - SaaS organization and tenant control plane

**Outcome:** Organizations, regions, plans, policies, and tenant resources are provisioned through auditable lifecycle workflows.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-12.S06.T03`

#### - [ ] CAP-13.S01.T01 - Define organization, tenant, region, plan, and environment contracts

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-12.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Control-plane schema for lifecycle, ownership, residency, isolation tier, feature policy, quotas, billing account, support tier, and status.

**Deliverables:**

- Control-plane schema for lifecycle, ownership, residency, isolation tier, feature policy, quotas, billing account, support tier, and status.

**Acceptance criteria:**

- Tenant identity is globally unique and immutable; lifecycle transitions are explicit; deleted/suspended states have documented data and access semantics.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S01.T02 - Implement tenant provisioning and deprovisioning workflows

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Idempotent orchestration for databases/schemas, object namespaces, vector collections, queues, keys, policies, DNS/routing, monitoring, and validation.

**Deliverables:**

- Idempotent orchestration for databases/schemas, object namespaces, vector collections, queues, keys, policies, DNS/routing, monitoring, and validation.

**Acceptance criteria:**

- Partial provisioning is resumable/compensated; resources are tagged and inventoried; deprovision honors retention, legal hold, backup, and deletion verification.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S01.T03 - Build cloud administration and support control surface

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** Restricted admin UI/API for tenant status, plan/policy, usage, incidents, maintenance, support access, and audit with just-in-time elevation.

**Deliverables:**

- Restricted admin UI/API for tenant status, plan/policy, usage, incidents, maintenance, support access, and audit with just-in-time elevation.

**Acceptance criteria:**

- Admin cannot browse research content by default; elevated support requires reason, scope, duration, approval where configured, and immutable audit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

### CAP-13.S02 - Regional tenant data planes and isolation tiers

**Outcome:** Tenant data is hosted in declared regions using pooled, dedicated-schema, dedicated-database, or dedicated-deployment isolation as policy requires.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T03`, `CAP-12.S02.T03`

#### - [ ] CAP-13.S02.T01 - Implement multi-tenant service routing and mandatory tenant context

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T03`, `CAP-12.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Authenticated tenant resolution, request/job/event context propagation, repository guards, object/vector namespace enforcement, and trace tagging.

**Deliverables:**

- Authenticated tenant resolution, request/job/event context propagation, repository guards, object/vector namespace enforcement, and trace tagging.

**Acceptance criteria:**

- No operation executes without validated tenant context; cross-tenant attack suite fails; background workers and exports preserve context end to end.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S02.T02 - Implement regional data-plane templates and dedicated options

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Infrastructure definitions for pooled and dedicated tiers, regional endpoints, encryption keys, databases, object/vector stores, workflow namespaces, and workers.

**Deliverables:**

- Infrastructure definitions for pooled and dedicated tiers, regional endpoints, encryption keys, databases, object/vector stores, workflow namespaces, and workers.

**Acceptance criteria:**

- Infrastructure is reproducible and policy-selected; dedicated tier has no pooled data services; residency test verifies storage, processing, backup, and logs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S02.T03 - Implement tenant-aware migration, backup, restore, and relocation controls

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Per-tenant consistent backup/restore, schema migration, export/import, region relocation workflow, and cryptographic deletion evidence.

**Deliverables:**

- Per-tenant consistent backup/restore, schema migration, export/import, region relocation workflow, and cryptographic deletion evidence.

**Acceptance criteria:**

- Restore cannot cross residency/policy without approval; migration is resumable; relocation records data path and downtime; deletion reports remaining backups and expiry.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

### CAP-13.S03 - Cloud identity, entitlement, metering, and billing

**Outcome:** Organizations can govern membership and plans while usage is measured transparently by value-driving resource.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T02`

#### - [ ] CAP-13.S03.T01 - Implement cloud identity, organization membership, and federation

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** OIDC/social or enterprise federation, MFA policy, invitations, roles, groups, session/device controls, and SCIM-ready interfaces.

**Deliverables:**

- OIDC/social or enterprise federation, MFA policy, invitations, roles, groups, session/device controls, and SCIM-ready interfaces.

**Acceptance criteria:**

- High-risk roles require stronger authentication; membership removal revokes access; federation claims are mapped and audited safely.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S03.T02 - Implement feature entitlements, quotas, and usage metering

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Plan/override policy, meters for storage, documents, model tokens/cost, compute time, embeddings, workers, exports, and monitor runs with idempotent events.

**Deliverables:**

- Plan/override policy, meters for storage, documents, model tokens/cost, compute time, embeddings, workers, exports, and monitor runs with idempotent events.

**Acceptance criteria:**

- Meter totals reconcile to service traces within tolerance; retries do not double count; users/admins can inspect current usage and impending limits.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S03.T03 - Implement billing-provider integration and account lifecycle

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Customer/subscription mapping, invoices, trials, plan changes, credits, failed payment, grace/suspension, tax-ready records, and webhook verification.

**Deliverables:**

- Customer/subscription mapping, invoices, trials, plan changes, credits, failed payment, grace/suspension, tax-ready records, and webhook verification.

**Acceptance criteria:**

- Signed webhooks are idempotent; billing failure never destroys data; entitlements change predictably; no payment data is stored outside provider-approved scope.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

### CAP-13.S04 - Elastic workers, models, search, and cost governance

**Outcome:** Cloud analytical workloads scale by class without sacrificing reproducibility, rights, or budget controls.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T02`, `CAP-07.S05.T02`

#### - [ ] CAP-13.S04.T01 - Implement autoscaled worker pools and scheduling classes

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T02`, `CAP-07.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** General, parser, embedding, model, export, and monitor queues with autoscaling, fairness, priority, limits, cancellation, and tenant quotas.

**Deliverables:**

- General, parser, embedding, model, export, and monitor queues with autoscaling, fairness, priority, limits, cancellation, and tenant quotas.

**Acceptance criteria:**

- Interactive work is protected from batch starvation; scaledown does not lose checkpoints; tenant limits and global safeguards are enforced.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S04.T02 - Implement cloud model-provider and private-endpoint routing

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Routing across managed inference, private vLLM/GPU pools, and approved external APIs using tenant policy, region, rights, cost, and quality.

**Deliverables:**

- Routing across managed inference, private vLLM/GPU pools, and approved external APIs using tenant policy, region, rights, cost, and quality.

**Acceptance criteria:**

- Restricted data never crosses prohibited provider/region; model versions are pinned for reproducible workflows; fallback policy is tenant-visible.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S04.T03 - Implement cost allocation, anomaly detection, and protective controls

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Per-tenant/project/task cost attribution, budgets, forecasts, anomalous usage alerts, circuit breakers, and administrative/user controls.

**Deliverables:**

- Per-tenant/project/task cost attribution, budgets, forecasts, anomalous usage alerts, circuit breakers, and administrative/user controls.

**Acceptance criteria:**

- Runaway fixture workloads are stopped within threshold; allocation reconciles to provider invoices/compute metrics; controls do not corrupt accepted work.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

### CAP-13.S05 - Cloud security, privacy, residency, and compliance operations

**Outcome:** Security and privacy controls operate continuously across tenant, regional, administrative, and software-supply-chain boundaries.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T03`, `CAP-13.S03.T01`

#### - [ ] CAP-13.S05.T01 - Implement managed key hierarchy, rotation, and tenant-key options

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S02.T03`, `CAP-13.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Cloud KMS envelope encryption for databases, objects, backups, secrets, optional customer-managed/dedicated keys, rotation, revocation, and audit.

**Deliverables:**

- Cloud KMS envelope encryption for databases, objects, backups, secrets, optional customer-managed/dedicated keys, rotation, revocation, and audit.

**Acceptance criteria:**

- Keys are region/policy scoped; rotation is tested without downtime or data loss; revoked keys fail closed; operators cannot retrieve plaintext keys.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S05.T02 - Implement residency, retention, data-subject, and deletion workflows

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Policy engine and evidence for storage/processing locations, retention schedules, export, correction, deletion, legal hold, and backup expiry.

**Deliverables:**

- Policy engine and evidence for storage/processing locations, retention schedules, export, correction, deletion, legal hold, and backup expiry.

**Acceptance criteria:**

- Requests enumerate affected data classes and complete within policy; deletion is verifiable and honest about delayed backups; no hidden cross-region processing occurs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S05.T03 - Implement incident detection, response, audit evidence, and security testing

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** SIEM integration, alert triage, incident roles, tenant notification workflow, forensic retention, vulnerability management, penetration tests, and compliance evidence packs.

**Deliverables:**

- SIEM integration, alert triage, incident roles, tenant notification workflow, forensic retention, vulnerability management, penetration tests, and compliance evidence packs.

**Acceptance criteria:**

- Tabletop and technical exercises meet response targets; critical findings have tracked remediation; audit evidence traces controls to operating data rather than screenshots alone.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

### CAP-13.S06 - Desktop-cloud experience, service reliability, and launch gate

**Outcome:** Cloud customers use the canonical desktop with clear synchronization, reliability, support, and service-status behavior.

**Wave / priority / status / review:** `W11` / `P3` / `DEFERRED` / `PENDING`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S04.T03`, `CAP-13.S05.T03`

#### - [ ] CAP-13.S06.T01 - Complete cloud connection, project, cache, and conflict experience

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S04.T03`, `CAP-13.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Cloud profile onboarding, organization/project selection, capability display, local cache policy, session expiry, upload/download progress, and supported conflict resolution.

**Deliverables:**

- Cloud profile onboarding, organization/project selection, capability display, local cache policy, session expiry, upload/download progress, and supported conflict resolution.

**Acceptance criteria:**

- Users never confuse local and cloud storage; interrupted transfers resume safely; access/rights changes invalidate cached content; errors link to trace/support IDs.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop
- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S06.T02 - Establish SLOs, monitoring, support, maintenance, and disaster recovery

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Availability/latency/durability objectives, error budgets, dashboards, alerting, on-call, status communication, runbooks, backups, regional recovery, and drills.

**Deliverables:**

- Availability/latency/durability objectives, error budgets, dashboards, alerting, on-call, status communication, runbooks, backups, regional recovery, and drills.

**Acceptance criteria:**

- SLO measurements exclude no material user paths; disaster exercise meets approved RPO/RTO; support escalation protects tenant confidentiality.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

#### - [ ] CAP-13.S06.T03 - Run limited-availability validation and approve G8

**Status / priority / estimate / risk:** `DEFERRED` / `P3` / `L` / `high`

**Profiles / platforms:** `CLD` / `platform-neutral`

**Dependencies:** `CAP-13.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Security/isolation tests, performance/load, billing reconciliation, cost limits, pilot organizations, user evaluation, incident drill, documentation, and gate decision.

**Deliverables:**

- Security/isolation tests, performance/load, billing reconciliation, cost limits, pilot organizations, user evaluation, incident drill, documentation, and gate decision.

**Acceptance criteria:**

- All P3 launch criteria are evidenced; critical issues are closed; cloud release preserves provenance/rights/novelty semantics; gate names residual limitations and expansion conditions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile cloud

## CAP-14 - Cross-platform desktop qualification and release

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Extend the production Windows local edition to Apple Silicon macOS and Ubuntu-compatible Linux x86_64/ARM64 while preserving one codebase, one project format, and equivalent security and scholarly behavior.

**Exit criteria:**

- Supported macOS and Linux packages install, upgrade, recover, back up, and run offline without Docker or a server.
- The same project opens across Windows, macOS, and Linux with identical evidence, provenance, workflows, and outputs.
- Platform secrets, signing/update trust, paths, sidecars, parsers, vector adapters, and model backends pass platform-specific security and reliability tests.
- Linux ARM64, including an NVIDIA DGX Spark-class lab profile where available, completes representative GPU/model and end-to-end qualification.

### CAP-14.S01 - Platform abstraction and build matrix

**Outcome:** One codebase builds and reports its capabilities consistently across qualified desktop operating systems.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`, `macos-arm64`, `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-11.S06.T03`

#### - [ ] CAP-14.S01.T01 - Define desktop platform ports and eliminate hidden Windows assumptions

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-11.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Document and implement platform interfaces for paths, process supervision, secret storage, notifications, updates, GPU discovery, and packaging without forking the domain/UI.

**Deliverables:**

- Document and implement platform interfaces for paths, process supervision, secret storage, notifications, updates, GPU discovery, and packaging without forking the domain/UI.

**Acceptance criteria:**

- Document and implement platform interfaces for paths, process supervision, secret storage, notifications, updates, GPU discovery, and packaging without forking the domain/UI.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile architecture

#### - [ ] CAP-14.S01.T02 - Establish macOS/Linux build and continuous-integration matrix

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Reproducible Tauri, Rust, Node, Python-sidecar, parser, and installer builds run for macOS ARM64, Linux x86_64, and Linux ARM64 with cached but verifiable dependencies.

**Deliverables:**

- Reproducible Tauri, Rust, Node, Python-sidecar, parser, and installer builds run for macOS ARM64, Linux x86_64, and Linux ARM64 with cached but verifiable dependencies.

**Acceptance criteria:**

- Reproducible Tauri, Rust, Node, Python-sidecar, parser, and installer builds run for macOS ARM64, Linux x86_64, and Linux ARM64 with cached but verifiable dependencies.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile foundation

#### - [ ] CAP-14.S01.T03 - Implement platform capability detection and diagnostics

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S01.T02`

**Owner / review:** - / - (`-`)

**Objective:** The desktop reports OS/architecture, credential backend, filesystem policy, acceleration backends, parser/vector/model compatibility, and unsupported conditions without exposing sensitive system data.

**Deliverables:**

- The desktop reports OS/architecture, credential backend, filesystem policy, acceleration backends, parser/vector/model compatibility, and unsupported conditions without exposing sensitive system data.

**Acceptance criteria:**

- The desktop reports OS/architecture, credential backend, filesystem policy, acceleration backends, parser/vector/model compatibility, and unsupported conditions without exposing sensitive system data.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform

### CAP-14.S02 - Apple Silicon macOS product qualification

**Outcome:** The local product is production-ready on supported Apple Silicon macOS versions.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `macos-arm64`

**Dependencies:** `CAP-14.S01.T03`

#### - [ ] CAP-14.S02.T01 - Package and supervise the Apple Silicon macOS desktop and sidecars

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `macos-arm64`

**Dependencies:** `CAP-14.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Tauri and all required Python/native sidecars launch, handshake, cancel, and recover on Apple Silicon macOS with platform-correct paths and permissions.

**Deliverables:**

- Tauri and all required Python/native sidecars launch, handshake, cancel, and recover on Apple Silicon macOS with platform-correct paths and permissions.

**Acceptance criteria:**

- Tauri and all required Python/native sidecars launch, handshake, cancel, and recover on Apple Silicon macOS with platform-correct paths and permissions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform

#### - [ ] CAP-14.S02.T02 - Integrate macOS Keychain, signing, notarization, and updates

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `macos-arm64`

**Dependencies:** `CAP-14.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Secrets and project keys use Keychain-backed protection; application, sidecars, update manifests, and installers pass signing/notarization and tamper rejection.

**Deliverables:**

- Secrets and project keys use Keychain-backed protection; application, sidecars, update manifests, and installers pass signing/notarization and tamper rejection.

**Acceptance criteria:**

- Secrets and project keys use Keychain-backed protection; application, sidecars, update manifests, and installers pass signing/notarization and tamper rejection.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile security-local

#### - [ ] CAP-14.S02.T03 - Qualify macOS install, upgrade, offline, backup, accessibility, and recovery

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `macos-arm64`

**Dependencies:** `CAP-14.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** A clean Apple Silicon machine completes installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, uninstall, and update rollback.

**Deliverables:**

- A clean Apple Silicon machine completes installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, uninstall, and update rollback.

**Acceptance criteria:**

- A clean Apple Silicon machine completes installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, uninstall, and update rollback.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

### CAP-14.S03 - Linux x86_64 and ARM64 product qualification

**Outcome:** The local product is production-ready on approved Ubuntu-compatible Linux workstation profiles.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S01.T03`

#### - [ ] CAP-14.S03.T01 - Package and supervise Linux x86_64 and ARM64 desktop sidecars

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Tauri and required Python/native sidecars launch, handshake, cancel, and recover on Ubuntu-compatible Linux x86_64 and ARM64 profiles.

**Deliverables:**

- Tauri and required Python/native sidecars launch, handshake, cancel, and recover on Ubuntu-compatible Linux x86_64 and ARM64 profiles.

**Acceptance criteria:**

- Tauri and required Python/native sidecars launch, handshake, cancel, and recover on Ubuntu-compatible Linux x86_64 and ARM64 profiles.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform

#### - [ ] CAP-14.S03.T02 - Integrate Linux Secret Service, XDG paths, package formats, and updates

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Secrets use an approved Secret Service/keyring backend with documented headless fallback; XDG paths, AppImage/deb or selected packages, signatures, and update behavior are correct.

**Deliverables:**

- Secrets use an approved Secret Service/keyring backend with documented headless fallback; XDG paths, AppImage/deb or selected packages, signatures, and update behavior are correct.

**Acceptance criteria:**

- Secrets use an approved Secret Service/keyring backend with documented headless fallback; XDG paths, AppImage/deb or selected packages, signatures, and update behavior are correct.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile security-local

#### - [ ] CAP-14.S03.T03 - Qualify Linux install, upgrade, offline, backup, accessibility, and recovery

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Clean x86_64 and ARM64 systems complete installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, and update rollback.

**Deliverables:**

- Clean x86_64 and ARM64 systems complete installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, and update rollback.

**Acceptance criteria:**

- Clean x86_64 and ARM64 systems complete installation, representative workflows, migration, backup/restore, offline use, accessibility, crash recovery, and update rollback.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

### CAP-14.S04 - Cross-platform scientific and AI runtime

**Outcome:** Hardware acceleration is optional, governed, observable, and portable across supported desktop platforms.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`, `macos-arm64`, `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S01.T03`, `CAP-07.S02.T03`

#### - [ ] CAP-14.S04.T01 - Implement hardware-aware local acceleration ports

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S01.T03`, `CAP-07.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Model, embedding, reranking, parsing, and analytical jobs discover and select CPU, CUDA, Metal, or other approved backends through policy-controlled adapters and deterministic fallbacks.

**Deliverables:**

- Model, embedding, reranking, parsing, and analytical jobs discover and select CPU, CUDA, Metal, or other approved backends through policy-controlled adapters and deterministic fallbacks.

**Acceptance criteria:**

- Model, embedding, reranking, parsing, and analytical jobs discover and select CPU, CUDA, Metal, or other approved backends through policy-controlled adapters and deterministic fallbacks.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile ai

#### - [ ] CAP-14.S04.T02 - Qualify NVIDIA CUDA execution on Linux including DGX Spark-class ARM64

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S04.T01`, `CAP-14.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Approved local models and GPU-eligible jobs run on Linux NVIDIA systems, including an ARM64 DGX Spark-class profile where available, with memory limits, cancellation, telemetry, and CPU fallback.

**Deliverables:**

- Approved local models and GPU-eligible jobs run on Linux NVIDIA systems, including an ARM64 DGX Spark-class profile where available, with memory limits, cancellation, telemetry, and CPU fallback.

**Acceptance criteria:**

- Approved local models and GPU-eligible jobs run on Linux NVIDIA systems, including an ARM64 DGX Spark-class profile where available, with memory limits, cancellation, telemetry, and CPU fallback.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile ai
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-14.S04.T03 - Qualify parser, vector, and local-model portability and fallback

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S04.T01`, `CAP-14.S02.T01`, `CAP-14.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Pinned parser, vector, embedding, reranking, and inference packages pass functional/recovery benchmarks on all desktop targets or provide an explicit supported fallback without changing project semantics.

**Deliverables:**

- Pinned parser, vector, embedding, reranking, and inference packages pass functional/recovery benchmarks on all desktop targets or provide an explicit supported fallback without changing project semantics.

**Acceptance criteria:**

- Pinned parser, vector, embedding, reranking, and inference packages pass functional/recovery benchmarks on all desktop targets or provide an explicit supported fallback without changing project semantics.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile documents
- python tools/verify.py --profile search
- python tools/verify.py --profile ai

### CAP-14.S05 - Cross-platform project compatibility and recovery

**Outcome:** Projects and analytical results remain portable and semantically identical across qualified desktop operating systems.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`, `macos-arm64`, `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S02.T03`, `CAP-14.S03.T03`

#### - [ ] CAP-14.S05.T01 - Guarantee cross-platform project and bundle compatibility

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S02.T03`, `CAP-14.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Canonical SQLite/object/provenance structures, identifiers, paths, timestamps, and bundle manifests open identically on Windows, macOS, and Linux without lossy conversion.

**Deliverables:**

- Canonical SQLite/object/provenance structures, identifiers, paths, timestamps, and bundle manifests open identically on Windows, macOS, and Linux without lossy conversion.

**Acceptance criteria:**

- Canonical SQLite/object/provenance structures, identifiers, paths, timestamps, and bundle manifests open identically on Windows, macOS, and Linux without lossy conversion.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile data

#### - [ ] CAP-14.S05.T02 - Implement platform-safe path, filename, permission, and migration handling

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Projects reject or safely normalize incompatible filenames, case collisions, symlinks, permissions, and path lengths; migrations and rollback are platform-independent.

**Deliverables:**

- Projects reject or safely normalize incompatible filenames, case collisions, symlinks, permissions, and path lengths; migrations and rollback are platform-independent.

**Acceptance criteria:**

- Projects reject or safely normalize incompatible filenames, case collisions, symlinks, permissions, and path lengths; migrations and rollback are platform-independent.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile data
- python tools/verify.py --profile security-local

#### - [ ] CAP-14.S05.T03 - Run cross-platform transfer, recovery, and semantic-equivalence tests

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S05.T02`, `CAP-14.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** The same fixture projects move among all qualified OS targets and preserve records, evidence anchors, graph relations, workflows, outputs, hashes, and review decisions.

**Deliverables:**

- The same fixture projects move among all qualified OS targets and preserve records, evidence anchors, graph relations, workflows, outputs, hashes, and review decisions.

**Acceptance criteria:**

- The same fixture projects move among all qualified OS targets and preserve records, evidence anchors, graph relations, workflows, outputs, hashes, and review decisions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile e2e-local

### CAP-14.S06 - Cross-platform desktop release gate

**Outcome:** The complete local edition is release-qualified on Windows, macOS, and Linux.

**Wave / priority / status / review:** `W6` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB` / `windows-x64`, `macos-arm64`, `linux-x64`, `linux-arm64`

**Dependencies:** `CAP-14.S05.T03`

#### - [ ] CAP-14.S06.T01 - Assemble cross-platform release artifacts and provenance

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Generate platform installers/packages, sidecars, hashes, SBOMs, signatures/notarization evidence, build manifests, and supported-platform metadata from immutable revisions.

**Deliverables:**

- Generate platform installers/packages, sidecars, hashes, SBOMs, signatures/notarization evidence, build manifests, and supported-platform metadata from immutable revisions.

**Acceptance criteria:**

- Generate platform installers/packages, sidecars, hashes, SBOMs, signatures/notarization evidence, build manifests, and supported-platform metadata from immutable revisions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile security-local

#### - [ ] CAP-14.S06.T02 - Run complete cross-platform end-to-end acceptance

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Each qualified OS completes representative literature workflows, backup/restore, offline work, model/parser fallbacks, accessibility, and project transfer under release conditions.

**Deliverables:**

- Each qualified OS completes representative literature workflows, backup/restore, offline work, model/parser fallbacks, accessibility, and project transfer under release conditions.

**Acceptance criteria:**

- Each qualified OS completes representative literature workflows, backup/restore, offline work, model/parser fallbacks, accessibility, and project transfer under release conditions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform
- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

#### - [ ] CAP-14.S06.T03 - Approve G6 and publish cross-platform desktop documentation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB` / `platform-neutral`

**Dependencies:** `CAP-14.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Record reviewed evidence, supported versions/architectures, known limitations, installation/upgrade guidance, and G6 approval without weakening the Windows release.

**Deliverables:**

- Record reviewed evidence, supported versions/architectures, known limitations, installation/upgrade guidance, and G6 approval without weakening the Windows release.

**Acceptance criteria:**

- Record reviewed evidence, supported versions/architectures, known limitations, installation/upgrade guidance, and G6 approval without weakening the Windows release.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile desktop-cross-platform

## CAP-15 - Empirical study design and protocol development

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Use literature evidence, opportunity dossiers, domain knowledge, and researcher constraints to propose, compare, and formalize rigorous empirical study designs without displacing scholarly or ethics authority.

**Exit criteria:**

- Multiple plausible study designs are compared through explicit assumptions, evidence, validity, ethics, feasibility, and alternative-outcome value.
- The selected protocol covers research logic, sampling, measurement, data collection, analysis, validity, ethics, data management, and reproducibility.
- Every consequential recommendation is source-linked or clearly labeled as inference, convention, researcher preference, or unresolved decision.
- The platform never implies IRB/ethics approval, preregistration, or methodological validity without human/institutional review.

### CAP-15.S01 - Study-design domain and evidence foundation

**Outcome:** Study designs are first-class, versioned, source-grounded research objects.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-10.S03.T03`, `CAP-09.S05.T03`

#### - [ ] CAP-15.S01.T01 - Define empirical study-design domain contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-03.S01.T03`, `CAP-10.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Model research purposes, questions, hypotheses where appropriate, design alternatives, units/levels, constructs, samples, measures, procedures, analyses, validity threats, ethics, preregistration, and protocol versions.

**Deliverables:**

- Model research purposes, questions, hypotheses where appropriate, design alternatives, units/levels, constructs, samples, measures, procedures, analyses, validity threats, ethics, preregistration, and protocol versions.

**Acceptance criteria:**

- Model research purposes, questions, hypotheses where appropriate, design alternatives, units/levels, constructs, samples, measures, procedures, analyses, validity threats, ethics, preregistration, and protocol versions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile data

#### - [ ] CAP-15.S01.T02 - Link study-design elements to literature and opportunity evidence

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S01.T01`, `CAP-09.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Every recommended design element can cite supporting or cautionary literature, opportunity dossiers, prior measures, datasets, methods, and researcher memos with explicit evidence status.

**Deliverables:**

- Every recommended design element can cite supporting or cautionary literature, opportunity dossiers, prior measures, datasets, methods, and researcher memos with explicit evidence status.

**Acceptance criteria:**

- Every recommended design element can cite supporting or cautionary literature, opportunity dossiers, prior measures, datasets, methods, and researcher memos with explicit evidence status.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile evidence
- python tools/verify.py --profile graph

#### - [ ] CAP-15.S01.T03 - Implement study-design versioning, comparison, and staleness

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S01.T02`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Design alternatives and approved protocols preserve history; changed evidence or assumptions identify affected design elements without silently rewriting the protocol.

**Deliverables:**

- Design alternatives and approved protocols preserve history; changed evidence or assumptions identify affected design elements without silently rewriting the protocol.

**Acceptance criteria:**

- Design alternatives and approved protocols preserve history; changed evidence or assumptions identify affected design elements without silently rewriting the protocol.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile data

### CAP-15.S02 - Research logic and design alternatives

**Outcome:** Researchers receive plural, evidence-backed design options and retain final authority.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S01.T03`

#### - [ ] CAP-15.S02.T01 - Generate and compare empirical research questions and design logics

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Produce multiple source-grounded research-question, hypothesis/proposition where appropriate, mechanism, and causal/interpretive logic alternatives without forcing one epistemology.

**Deliverables:**

- Produce multiple source-grounded research-question, hypothesis/proposition where appropriate, mechanism, and causal/interpretive logic alternatives without forcing one epistemology.

**Acceptance criteria:**

- Produce multiple source-grounded research-question, hypothesis/proposition where appropriate, mechanism, and causal/interpretive logic alternatives without forcing one epistemology.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile ai

#### - [ ] CAP-15.S02.T02 - Compare quantitative, qualitative, mixed, computational, and field design families

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Present fit, assumptions, inference limits, feasibility, data requirements, ethics, and likely contribution under experiments, quasi-experiments, surveys, cases, field studies, qualitative, mixed, and computational designs.

**Deliverables:**

- Present fit, assumptions, inference limits, feasibility, data requirements, ethics, and likely contribution under experiments, quasi-experiments, surveys, cases, field studies, qualitative, mixed, and computational designs.

**Acceptance criteria:**

- Present fit, assumptions, inference limits, feasibility, data requirements, ethics, and likely contribution under experiments, quasi-experiments, surveys, cases, field studies, qualitative, mixed, and computational designs.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile ai

#### - [ ] CAP-15.S02.T03 - Implement human design selection and rationale adjudication

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Researchers select, combine, reject, or modify alternatives and record the scholarly rationale, unresolved tradeoffs, and required consultations.

**Deliverables:**

- Researchers select, combine, reject, or modify alternatives and record the scholarly rationale, unresolved tradeoffs, and required consultations.

**Acceptance criteria:**

- Researchers select, combine, reject, or modify alternatives and record the scholarly rationale, unresolved tradeoffs, and required consultations.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

### CAP-15.S03 - Sampling, measurement, and data collection

**Outcome:** The selected design contains an implementable and reviewable empirical data plan.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S02.T03`

#### - [ ] CAP-15.S03.T01 - Design population, sampling, recruitment, and case-selection plans

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Specify target population/cases, sampling frame, inclusion/exclusion, recruitment, power or saturation rationale, attrition, representativeness, and access constraints.

**Deliverables:**

- Specify target population/cases, sampling frame, inclusion/exclusion, recruitment, power or saturation rationale, attrition, representativeness, and access constraints.

**Acceptance criteria:**

- Specify target population/cases, sampling frame, inclusion/exclusion, recruitment, power or saturation rationale, attrition, representativeness, and access constraints.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

#### - [ ] CAP-15.S03.T02 - Design construct operationalization and measurement plans

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S03.T01`, `CAP-09.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Map constructs to definitions, instruments, indicators, coding schemes, reliability/validity evidence, measurement alternatives, and licensing or adaptation constraints.

**Deliverables:**

- Map constructs to definitions, instruments, indicators, coding schemes, reliability/validity evidence, measurement alternatives, and licensing or adaptation constraints.

**Acceptance criteria:**

- Map constructs to definitions, instruments, indicators, coding schemes, reliability/validity evidence, measurement alternatives, and licensing or adaptation constraints.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile evidence

#### - [ ] CAP-15.S03.T03 - Design data collection, intervention, procedure, and artifact plans

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Specify procedures, interventions/exposures, timing, instruments, manipulation checks, observations, interview protocols, computational runs, datasets, code, and audit artifacts.

**Deliverables:**

- Specify procedures, interventions/exposures, timing, instruments, manipulation checks, observations, interview protocols, computational runs, datasets, code, and audit artifacts.

**Acceptance criteria:**

- Specify procedures, interventions/exposures, timing, instruments, manipulation checks, observations, interview protocols, computational runs, datasets, code, and audit artifacts.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

### CAP-15.S04 - Analysis, validity, ethics, and reproducibility

**Outcome:** The protocol states how evidence will be produced, evaluated, governed, and interpreted under alternative outcomes.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S03.T03`

#### - [ ] CAP-15.S04.T01 - Design quantitative, qualitative, mixed, or computational analysis plans

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Specify preprocessing, models/tests, qualitative coding/interpretation, integration logic, missing-data handling, robustness, diagnostics, assumptions, decision rules, and software/artifact expectations.

**Deliverables:**

- Specify preprocessing, models/tests, qualitative coding/interpretation, integration logic, missing-data handling, robustness, diagnostics, assumptions, decision rules, and software/artifact expectations.

**Acceptance criteria:**

- Specify preprocessing, models/tests, qualitative coding/interpretation, integration logic, missing-data handling, robustness, diagnostics, assumptions, decision rules, and software/artifact expectations.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

#### - [ ] CAP-15.S04.T02 - Model validity threats, boundary conditions, sensitivity, and null-result value

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Create design-specific internal/external/construct/statistical or interpretive quality analyses and identify how supported, null, mixed, or context-dependent findings would contribute.

**Deliverables:**

- Create design-specific internal/external/construct/statistical or interpretive quality analyses and identify how supported, null, mixed, or context-dependent findings would contribute.

**Acceptance criteria:**

- Create design-specific internal/external/construct/statistical or interpretive quality analyses and identify how supported, null, mixed, or context-dependent findings would contribute.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile evidence

#### - [ ] CAP-15.S04.T03 - Create ethics, data-management, preregistration, and reproducibility plans

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Draft issues for human review covering consent, privacy, risk, data governance, retention, access, preregistration, materials/code, deviations, disclosure, and institutional review requirements without claiming approval.

**Deliverables:**

- Draft issues for human review covering consent, privacy, risk, data governance, retention, access, preregistration, materials/code, deviations, disclosure, and institutional review requirements without claiming approval.

**Acceptance criteria:**

- Draft issues for human review covering consent, privacy, risk, data governance, retention, access, preregistration, materials/code, deviations, disclosure, and institutional review requirements without claiming approval.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile security-local

### CAP-15.S05 - Study Design Studio and protocol exports

**Outcome:** Researchers can produce a source-grounded, reviewable empirical protocol and analysis plan.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S04.T03`

#### - [ ] CAP-15.S05.T01 - Build the Study Design Studio workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S04.T03`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Deliver an inspect-contest-adjudicate interface for design alternatives, literature rationale, protocol components, open decisions, completeness, and workflow handoffs.

**Deliverables:**

- Deliver an inspect-contest-adjudicate interface for design alternatives, literature rationale, protocol components, open decisions, completeness, and workflow handoffs.

**Acceptance criteria:**

- Deliver an inspect-contest-adjudicate interface for design alternatives, literature rationale, protocol components, open decisions, completeness, and workflow handoffs.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile desktop

#### - [ ] CAP-15.S05.T02 - Implement protocol, analysis-plan, and preregistration-ready exports

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S05.T01`, `CAP-09.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Export source-linked DOCX, Markdown, and structured manifests for protocol review; templates remain generic unless verified venue/registry guidance is supplied.

**Deliverables:**

- Export source-linked DOCX, Markdown, and structured manifests for protocol review; templates remain generic unless verified venue/registry guidance is supplied.

**Acceptance criteria:**

- Export source-linked DOCX, Markdown, and structured manifests for protocol review; templates remain generic unless verified venue/registry guidance is supplied.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile manuscript

#### - [ ] CAP-15.S05.T03 - Implement study-design completeness, contradiction, and integrity audit

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Detect missing components, unsupported choices, inconsistent constructs/measures, circular design logic, undisclosed deviations, and claims exceeding the design.

**Deliverables:**

- Detect missing components, unsupported choices, inconsistent constructs/measures, circular design logic, undisclosed deviations, and claims exceeding the design.

**Acceptance criteria:**

- Detect missing components, unsupported choices, inconsistent constructs/measures, circular design logic, undisclosed deviations, and claims exceeding the design.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence

### CAP-15.S06 - Study-design production acceptance

**Outcome:** The study-design capability is production-ready, source-grounded, and expert-reviewed.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S05.T03`

#### - [ ] CAP-15.S06.T01 - Run opportunity-to-protocol end-to-end acceptance

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Representative quantitative, qualitative, mixed, and technical studies move from literature/opportunity evidence through design alternatives to an approved protocol with no invented requirements.

**Deliverables:**

- Representative quantitative, qualitative, mixed, and technical studies move from literature/opportunity evidence through design alternatives to an approved protocol with no invented requirements.

**Acceptance criteria:**

- Representative quantitative, qualitative, mixed, and technical studies move from literature/opportunity evidence through design alternatives to an approved protocol with no invented requirements.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-15.S06.T02 - Evaluate study-design quality with domain and methods experts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Blinded experts assess appropriateness, evidence grounding, alternative coverage, validity/ethics visibility, tractability, and researcher authority across domains.

**Deliverables:**

- Blinded experts assess appropriateness, evidence grounding, alternative coverage, validity/ethics visibility, tractability, and researcher authority across domains.

**Acceptance criteria:**

- Blinded experts assess appropriateness, evidence grounding, alternative coverage, validity/ethics visibility, tractability, and researcher authority across domains.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

#### - [ ] CAP-15.S06.T03 - Approve study-design portion of G7

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Map capability exit criteria to evidence, record residual limitations, and approve the empirical study-design foundation for manuscript integration.

**Deliverables:**

- Map capability exit criteria to evidence, record residual limitations, and approve the empirical study-design foundation for manuscript integration.

**Acceptance criteria:**

- Map capability exit criteria to evidence, record residual limitations, and approve the empirical study-design foundation for manuscript integration.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile study-design

## CAP-16 - Manuscript blueprint, venue profiles, and article architecture

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Turn approved research intent, literature structures, study plans, and publication goals into governed conference/journal skeletons for empirical, theory, and critical work.

**Exit criteria:**

- Generic and verified venue profiles are provenance-aware and never fabricate requirements.
- Empirical, theory, and critical skeletons have appropriate section, contribution, evidence, disclosure, and word-budget structures.
- Researchers can modify and approve the blueprint before prose generation; changes preserve history and impact previews.
- Editable DOCX, Markdown, and LaTeX skeletons retain stable section identities for source-grounded drafting and review.

### CAP-16.S01 - Manuscript domain and template governance

**Outcome:** Article architecture is versioned, inspectable, and separated from generated prose.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-09.S06.T03`

#### - [ ] CAP-16.S01.T01 - Define manuscript, venue, template, section, and claim-plan contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-03.S01.T03`, `CAP-09.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Model research type, output type, target venue, template provenance, sections, contribution claims, evidence requirements, citations, figures/tables, word budgets, disclosures, and draft versions.

**Deliverables:**

- Model research type, output type, target venue, template provenance, sections, contribution claims, evidence requirements, citations, figures/tables, word budgets, disclosures, and draft versions.

**Acceptance criteria:**

- Model research type, output type, target venue, template provenance, sections, contribution claims, evidence requirements, citations, figures/tables, word budgets, disclosures, and draft versions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile data

#### - [ ] CAP-16.S01.T02 - Implement governed generic and venue-profile registry

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T01`

**Owner / review:** - / - (`-`)

**Objective:** Ship transparent generic conference/journal profiles and accept official or user-uploaded venue guidance with provenance, version, rights, and verification status.

**Deliverables:**

- Ship transparent generic conference/journal profiles and accept official or user-uploaded venue guidance with provenance, version, rights, and verification status.

**Acceptance criteria:**

- Ship transparent generic conference/journal profiles and accept official or user-uploaded venue guidance with provenance, version, rights, and verification status.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S01.T03 - Implement template versioning, compatibility, and staleness

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T02`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Template/profile changes preview affected sections and exports; existing researcher-authored content is never silently restructured.

**Deliverables:**

- Template/profile changes preview affected sections and exports; existing researcher-authored content is never silently restructured.

**Acceptance criteria:**

- Template/profile changes preview affected sections and exports; existing researcher-authored content is never silently restructured.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile data

### CAP-16.S02 - Empirical article blueprints

**Outcome:** Empirical conference and journal skeletons are complete, adaptable, and linked to protocol/result requirements.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-15.S05.T02`

#### - [ ] CAP-16.S02.T01 - Create empirical journal-article skeletons

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-15.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Provide adaptable section architectures for abstract, introduction, literature/theory, methods, results, discussion, implications, limitations, references, appendices, disclosures, and artifacts.

**Deliverables:**

- Provide adaptable section architectures for abstract, introduction, literature/theory, methods, results, discussion, implications, limitations, references, appendices, disclosures, and artifacts.

**Acceptance criteria:**

- Provide adaptable section architectures for abstract, introduction, literature/theory, methods, results, discussion, implications, limitations, references, appendices, disclosures, and artifacts.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S02.T02 - Create empirical conference-paper skeletons

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Provide concise conference variants with explicit compression choices, word/page budgets, contribution focus, and links to the fuller study record.

**Deliverables:**

- Provide concise conference variants with explicit compression choices, word/page budgets, contribution focus, and links to the fuller study record.

**Acceptance criteria:**

- Provide concise conference variants with explicit compression choices, word/page budgets, contribution focus, and links to the fuller study record.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S02.T03 - Map study-design and result requirements to empirical sections

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S02.T02`, `CAP-15.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Each empirical section declares required design elements, actual-study evidence, literature evidence, tables/figures, deviations, and unresolved placeholders.

**Deliverables:**

- Each empirical section declares required design elements, actual-study evidence, literature evidence, tables/figures, deviations, and unresolved placeholders.

**Acceptance criteria:**

- Each empirical section declares required design elements, actual-study evidence, literature evidence, tables/figures, deviations, and unresolved placeholders.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile study-design

### CAP-16.S03 - Theory article blueprints

**Outcome:** Theory manuscripts receive coherent argument architecture while preserving epistemic plurality.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-09.S05.T03`

#### - [ ] CAP-16.S03.T01 - Create theory-article architecture patterns

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-09.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Support problem-centered, integrative, process, typology, mechanism, boundary, and critical-theoretical structures without requiring hypotheses or propositions.

**Deliverables:**

- Support problem-centered, integrative, process, typology, mechanism, boundary, and critical-theoretical structures without requiring hypotheses or propositions.

**Acceptance criteria:**

- Support problem-centered, integrative, process, typology, mechanism, boundary, and critical-theoretical structures without requiring hypotheses or propositions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S03.T02 - Model conceptual contribution and argument requirements

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S03.T01`, `CAP-09.S02.T03`

**Owner / review:** - / - (`-`)

**Objective:** Plan central problem, theoretical tension, construct relationships, mechanisms, assumptions, boundary conditions, alternatives, implications, and contribution under multiple article forms.

**Deliverables:**

- Plan central problem, theoretical tension, construct relationships, mechanisms, assumptions, boundary conditions, alternatives, implications, and contribution under multiple article forms.

**Acceptance criteria:**

- Plan central problem, theoretical tension, construct relationships, mechanisms, assumptions, boundary conditions, alternatives, implications, and contribution under multiple article forms.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile graph

#### - [ ] CAP-16.S03.T03 - Create theory conference and journal variants

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Generate target-length skeletons that preserve conceptual integration and avoid converting critical or interpretive theory into a positivist hypothesis template.

**Deliverables:**

- Generate target-length skeletons that preserve conceptual integration and avoid converting critical or interpretive theory into a positivist hypothesis template.

**Acceptance criteria:**

- Generate target-length skeletons that preserve conceptual integration and avoid converting critical or interpretive theory into a positivist hypothesis template.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

### CAP-16.S04 - Critical scholarship blueprints

**Outcome:** Critical manuscripts receive rigorous evidence and argument scaffolding without epistemic flattening.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-10.S05.T03`

#### - [ ] CAP-16.S04.T01 - Create critical-scholarship article architecture patterns

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S01.T03`, `CAP-10.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Support problematization, genealogy, ideology critique, immanent critique, stakeholder/silence analysis, sociotechnical and political economy readings, alternative framings, and reflexive conclusion structures.

**Deliverables:**

- Support problematization, genealogy, ideology critique, immanent critique, stakeholder/silence analysis, sociotechnical and political economy readings, alternative framings, and reflexive conclusion structures.

**Acceptance criteria:**

- Support problematization, genealogy, ideology critique, immanent critique, stakeholder/silence analysis, sociotechnical and political economy readings, alternative framings, and reflexive conclusion structures.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S04.T02 - Model standpoint, reflexivity, evidence, and counter-reading requirements

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Critical blueprints explicitly plan standpoint, scope, textual/empirical basis, authority, exclusions, counterarguments, alternatives, and normative implications.

**Deliverables:**

- Critical blueprints explicitly plan standpoint, scope, textual/empirical basis, authority, exclusions, counterarguments, alternatives, and normative implications.

**Acceptance criteria:**

- Critical blueprints explicitly plan standpoint, scope, textual/empirical basis, authority, exclusions, counterarguments, alternatives, and normative implications.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence

#### - [ ] CAP-16.S04.T03 - Create critical conference and journal variants

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Provide adaptable short and full forms without requiring conventional hypotheses, empirical variable models, or artificial consensus.

**Deliverables:**

- Provide adaptable short and full forms without requiring conventional hypotheses, empirical variable models, or artificial consensus.

**Acceptance criteria:**

- Provide adaptable short and full forms without requiring conventional hypotheses, empirical variable models, or artificial consensus.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

### CAP-16.S05 - Manuscript Blueprint and venue adaptation

**Outcome:** Researchers can approve a publication-ready article architecture before prose generation.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S02.T03`, `CAP-16.S03.T03`, `CAP-16.S04.T03`

#### - [ ] CAP-16.S05.T01 - Build the Manuscript Blueprint workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S02.T03`, `CAP-16.S03.T03`, `CAP-16.S04.T03`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Allow researchers to choose empirical/theory/critical and conference/journal targets, inspect template provenance, plan sections/claims, allocate word budgets, and identify missing evidence.

**Deliverables:**

- Allow researchers to choose empirical/theory/critical and conference/journal targets, inspect template provenance, plan sections/claims, allocate word budgets, and identify missing evidence.

**Acceptance criteria:**

- Allow researchers to choose empirical/theory/critical and conference/journal targets, inspect template provenance, plan sections/claims, allocate word budgets, and identify missing evidence.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile desktop

#### - [ ] CAP-16.S05.T02 - Implement verified venue-guideline adaptation

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Parse and compare official or researcher-uploaded venue instructions, flag uncertainty/conflicts, and never fabricate journal requirements, formatting rules, or review criteria.

**Deliverables:**

- Parse and compare official or researcher-uploaded venue instructions, flag uncertainty/conflicts, and never fabricate journal requirements, formatting rules, or review criteria.

**Acceptance criteria:**

- Parse and compare official or researcher-uploaded venue instructions, flag uncertainty/conflicts, and never fabricate journal requirements, formatting rules, or review criteria.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile documents
- python tools/verify.py --profile ai

#### - [ ] CAP-16.S05.T03 - Export editable article skeletons and structured manifests

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Create DOCX, Markdown, and LaTeX skeletons with headings, section instructions, evidence placeholders, word budgets, disclosure blocks, and stable IDs for later drafting.

**Deliverables:**

- Create DOCX, Markdown, and LaTeX skeletons with headings, section instructions, evidence placeholders, word budgets, disclosure blocks, and stable IDs for later drafting.

**Acceptance criteria:**

- Create DOCX, Markdown, and LaTeX skeletons with headings, section instructions, evidence placeholders, word budgets, disclosure blocks, and stable IDs for later drafting.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

### CAP-16.S06 - Manuscript blueprint production acceptance

**Outcome:** The article-architecture capability is production-ready across research and output types.

**Wave / priority / status / review:** `W7` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T03`

#### - [ ] CAP-16.S06.T01 - Validate skeleton completeness across empirical, theory, and critical work

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Representative article targets produce structurally coherent skeletons with appropriate section logic, evidence requirements, disclosures, and no unsupported venue rules.

**Deliverables:**

- Representative article targets produce structurally coherent skeletons with appropriate section logic, evidence requirements, disclosures, and no unsupported venue rules.

**Acceptance criteria:**

- Representative article targets produce structurally coherent skeletons with appropriate section logic, evidence requirements, disclosures, and no unsupported venue rules.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-16.S06.T02 - Conduct author and journal-methodologist usability review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Researchers evaluate whether blueprints support rather than constrain argument development, preserve author control, and reduce structural omissions.

**Deliverables:**

- Researchers evaluate whether blueprints support rather than constrain argument development, preserve author control, and reduce structural omissions.

**Acceptance criteria:**

- Researchers evaluate whether blueprints support rather than constrain argument development, preserve author control, and reduce structural omissions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-16.S06.T03 - Approve manuscript-blueprint portion of G7

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S06.T02`, `CAP-15.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Record reviewed evidence and approve generic/verified venue profiles, article types, skeleton exports, and cross-platform conformance.

**Deliverables:**

- Record reviewed evidence and approve generic/verified venue profiles, article types, skeleton exports, and cross-platform conformance.

**Acceptance criteria:**

- Record reviewed evidence and approve generic/verified venue profiles, article types, skeleton exports, and cross-platform conformance.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

## CAP-17 - Technical report and study-results integration

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Ingest private technical reports of empirical work, extract and verify actual methods/results, reconcile them with planned designs, and make source-anchored result evidence available to manuscript drafting.

**Exit criteria:**

- Unpublished technical reports and supplements remain confidential, rights-aware, immutable, and versioned.
- Methods, results, tables, figures, deviations, null/mixed findings, and uncertainty are source-anchored and human verified.
- The platform never invents or reverse-engineers unreported empirical results and visibly blocks manuscript use of unresolved records.
- Changes to authoritative reports propagate staleness to dependent drafts, reviews, tables, figures, and exports.

### CAP-17.S01 - Private technical-report and study-artifact intake

**Outcome:** Unpublished study results enter through a confidential, rights-aware, versioned channel.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-15.S01.T03`

#### - [ ] CAP-17.S01.T01 - Implement private technical-report acquisition and study association

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-05.S01.T03`, `CAP-15.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Upload DOCX, PDF, Markdown, structured tables, figures, and supplementary files into a private study-artifact area and associate each version with the planned or completed study.

**Deliverables:**

- Upload DOCX, PDF, Markdown, structured tables, figures, and supplementary files into a private study-artifact area and associate each version with the planned or completed study.

**Acceptance criteria:**

- Upload DOCX, PDF, Markdown, structured tables, figures, and supplementary files into a private study-artifact area and associate each version with the planned or completed study.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile documents
- python tools/verify.py --profile security-local

#### - [ ] CAP-17.S01.T02 - Implement technical-report rights, confidentiality, and egress controls

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S01.T01`, `CAP-07.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Default all unpublished reports/results to local-private, require explicit provider egress approval, enforce export/collaboration restrictions, and redact support artifacts.

**Deliverables:**

- Default all unpublished reports/results to local-private, require explicit provider egress approval, enforce export/collaboration restrictions, and redact support artifacts.

**Acceptance criteria:**

- Default all unpublished reports/results to local-private, require explicit provider egress approval, enforce export/collaboration restrictions, and redact support artifacts.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile security-local

#### - [ ] CAP-17.S01.T03 - Implement report version, correction, and supersession lineage

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S01.T02`, `CAP-03.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Preserve immutable revisions, authorship, date, study/run identifiers, corrections, supplements, tables/figures, and human declarations of authoritative versions.

**Deliverables:**

- Preserve immutable revisions, authorship, date, study/run identifiers, corrections, supplements, tables/figures, and human declarations of authoritative versions.

**Acceptance criteria:**

- Preserve immutable revisions, authorship, date, study/run identifiers, corrections, supplements, tables/figures, and human declarations of authoritative versions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile data

### CAP-17.S02 - Technical-report parsing and result extraction

**Outcome:** Methods and results become structured candidates linked to exact report evidence.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S01.T03`

#### - [ ] CAP-17.S02.T01 - Extract report structure, study metadata, methods, results, tables, and figures

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S01.T03`, `CAP-05.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.

**Deliverables:**

- Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.

**Acceptance criteria:**

- Parse technical reports into stable source-anchored sections and candidate study/result entities while preserving page, paragraph, table-cell, figure, and revision references.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile documents
- python tools/verify.py --profile ai

#### - [ ] CAP-17.S02.T02 - Extract quantitative result records with exact evidence anchors

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.

**Deliverables:**

- Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.

**Acceptance criteria:**

- Represent estimates, uncertainty, tests, effect sizes, model specifications, diagnostics, sample counts, exclusions, robustness, and table/figure references without deriving unreported values.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

#### - [ ] CAP-17.S02.T03 - Extract qualitative, mixed-method, and technical findings

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S02.T01`

**Owner / review:** - / - (`-`)

**Objective:** Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.

**Deliverables:**

- Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.

**Acceptance criteria:**

- Represent themes, cases, interpretations, negative cases, quotes/observations, computational results, benchmark outcomes, and integration claims with explicit source status and uncertainty.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

### CAP-17.S03 - Study-plan and result reconciliation

**Outcome:** Actual study conduct and results are distinguished from plans and verified before authoring.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S02.T03`, `CAP-15.S05.T03`

#### - [ ] CAP-17.S03.T01 - Compare actual study execution with the approved study design

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S02.T03`, `CAP-15.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Reconcile planned and actual samples, measures, procedures, interventions, analyses, exclusions, deviations, preregistration, and artifact availability.

**Deliverables:**

- Reconcile planned and actual samples, measures, procedures, interventions, analyses, exclusions, deviations, preregistration, and artifact availability.

**Acceptance criteria:**

- Reconcile planned and actual samples, measures, procedures, interventions, analyses, exclusions, deviations, preregistration, and artifact availability.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile study-design

#### - [ ] CAP-17.S03.T02 - Detect missing, inconsistent, duplicated, or unsupported report claims

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S03.T01`

**Owner / review:** - / - (`-`)

**Objective:** Flag mismatched counts, measure names, model specifications, tables, narrative claims, unreported analyses, conflicting versions, and results unsupported by the report evidence.

**Deliverables:**

- Flag mismatched counts, measure names, model specifications, tables, narrative claims, unreported analyses, conflicting versions, and results unsupported by the report evidence.

**Acceptance criteria:**

- Flag mismatched counts, measure names, model specifications, tables, narrative claims, unreported analyses, conflicting versions, and results unsupported by the report evidence.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

#### - [ ] CAP-17.S03.T03 - Implement human verification and deviation adjudication

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Researchers verify results, explain legitimate deviations, reject extraction candidates, mark unresolved issues, and approve which result records may support manuscripts.

**Deliverables:**

- Researchers verify results, explain legitimate deviations, reject extraction candidates, mark unresolved issues, and approve which result records may support manuscripts.

**Acceptance criteria:**

- Researchers verify results, explain legitimate deviations, reject extraction candidates, mark unresolved issues, and approve which result records may support manuscripts.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence

### CAP-17.S04 - Results evidence graph and dependency propagation

**Outcome:** Verified study results become durable evidence with complete downstream impact tracking.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S03.T03`, `CAP-09.S01.T03`

#### - [ ] CAP-17.S04.T01 - Add study-run, result, table, figure, and finding entities to the evidence graph

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S03.T03`, `CAP-09.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Create typed relations among study designs, actual runs, reports, results, analyses, literature claims, manuscript claims, tables, figures, and deviations.

**Deliverables:**

- Create typed relations among study designs, actual runs, reports, results, analyses, literature claims, manuscript claims, tables, figures, and deviations.

**Acceptance criteria:**

- Create typed relations among study designs, actual runs, reports, results, analyses, literature claims, manuscript claims, tables, figures, and deviations.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile graph

#### - [ ] CAP-17.S04.T02 - Represent supported, null, mixed, contradictory, and robustness outcomes

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** Preserve direction, uncertainty, multiplicity, sensitivity, boundary conditions, negative cases, and unresolved interpretation rather than optimizing for positive findings.

**Deliverables:**

- Preserve direction, uncertainty, multiplicity, sensitivity, boundary conditions, negative cases, and unresolved interpretation rather than optimizing for positive findings.

**Acceptance criteria:**

- Preserve direction, uncertainty, multiplicity, sensitivity, boundary conditions, negative cases, and unresolved interpretation rather than optimizing for positive findings.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence
- python tools/verify.py --profile graph

#### - [ ] CAP-17.S04.T03 - Propagate technical-report changes to manuscripts and reviews

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S04.T02`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Changed or superseded reports/results mark dependent manuscript passages, tables, figures, summaries, reviewer analyses, and exports stale with impact preview.

**Deliverables:**

- Changed or superseded reports/results mark dependent manuscript passages, tables, figures, summaries, reviewer analyses, and exports stale with impact preview.

**Acceptance criteria:**

- Changed or superseded reports/results mark dependent manuscript passages, tables, figures, summaries, reviewer analyses, and exports stale with impact preview.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile data

### CAP-17.S05 - Technical Reports & Results workspace

**Outcome:** Researchers can inspect, verify, and approve result evidence for downstream manuscripts.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S04.T03`

#### - [ ] CAP-17.S05.T01 - Build the Technical Reports & Results workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S04.T03`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Deliver upload, version, parsing, study-design comparison, result verification, table/figure inspection, confidentiality, and manuscript-readiness views.

**Deliverables:**

- Deliver upload, version, parsing, study-design comparison, result verification, table/figure inspection, confidentiality, and manuscript-readiness views.

**Acceptance criteria:**

- Deliver upload, version, parsing, study-design comparison, result verification, table/figure inspection, confidentiality, and manuscript-readiness views.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile desktop

#### - [ ] CAP-17.S05.T02 - Build result evidence matrix and manuscript-claim mapping

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Allow verified results to be filtered, compared, linked to planned manuscript claims/sections, and held back when uncertain or incomplete.

**Deliverables:**

- Allow verified results to be filtered, compared, linked to planned manuscript claims/sections, and held back when uncertain or incomplete.

**Acceptance criteria:**

- Allow verified results to be filtered, compared, linked to planned manuscript claims/sections, and held back when uncertain or incomplete.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile evidence
- python tools/verify.py --profile manuscript

#### - [ ] CAP-17.S05.T03 - Export a verified study-results evidence package

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Create a private structured package containing report manifests, verified result records, deviations, tables/figures, unresolved issues, and provenance for drafting/review.

**Deliverables:**

- Create a private structured package containing report manifests, verified result records, deviations, tables/figures, unresolved issues, and provenance for drafting/review.

**Acceptance criteria:**

- Create a private structured package containing report manifests, verified result records, deviations, tables/figures, unresolved issues, and provenance for drafting/review.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results

### CAP-17.S06 - Results integration production acceptance

**Outcome:** Technical-report and result evidence is trustworthy enough for controlled manuscript use.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S05.T03`

#### - [ ] CAP-17.S06.T01 - Validate report ingestion against quantitative, qualitative, mixed, and technical fixtures

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Golden technical reports with tables, figures, null/mixed findings, deviations, and contradictions pass extraction, reconciliation, anchoring, and update tests.

**Deliverables:**

- Golden technical reports with tables, figures, null/mixed findings, deviations, and contradictions pass extraction, reconciliation, anchoring, and update tests.

**Acceptance criteria:**

- Golden technical reports with tables, figures, null/mixed findings, deviations, and contradictions pass extraction, reconciliation, anchoring, and update tests.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-17.S06.T02 - Prove no-result-invention and private-egress controls

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Adversarial tests confirm that missing results remain missing, unsupported calculations are rejected, confidential report content cannot leave policy boundaries, and outputs disclose unresolved evidence.

**Deliverables:**

- Adversarial tests confirm that missing results remain missing, unsupported calculations are rejected, confidential report content cannot leave policy boundaries, and outputs disclose unresolved evidence.

**Acceptance criteria:**

- Adversarial tests confirm that missing results remain missing, unsupported calculations are rejected, confidential report content cannot leave policy boundaries, and outputs disclose unresolved evidence.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results
- python tools/verify.py --profile security-local
- python tools/verify.py --profile ai

#### - [ ] CAP-17.S06.T03 - Approve results-integration readiness for G8

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-17.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Map capability exit criteria to evidence and approve result packages for manuscript drafting across qualified desktops.

**Deliverables:**

- Map capability exit criteria to evidence and approve result packages for manuscript drafting across qualified desktops.

**Acceptance criteria:**

- Map capability exit criteria to evidence and approve result packages for manuscript drafting across qualified desktops.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile results

## CAP-18 - Source-grounded manuscript drafting and publication artifacts

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Use approved article blueprints, literature evidence, verified technical reports/results, and researcher-authored content to draft and export empirical, theory, and critical conference/journal articles.

**Exit criteria:**

- Paragraphs and claims retain section purpose, evidence/citation support, generation provenance, author decisions, and stale dependencies.
- Empirical methods/results distinguish planned from actual conduct and never invent study details or findings.
- Theory and critical drafts preserve conceptual/interpretive plurality and author voice rather than imposing a single article logic.
- Researchers can edit, compare, approve, audit, disclose, and export complete manuscripts and reproducibility artifacts.

### CAP-18.S01 - Manuscript project and section workflow

**Outcome:** Drafts are durable, versioned scholarly objects with human ownership and selective recalculation.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T03`

#### - [ ] CAP-18.S01.T01 - Implement versioned manuscript projects, sections, blocks, and author ownership

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-16.S05.T03`, `CAP-03.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Store manuscript snapshots, section/block identities, researcher-authored text, generated candidates, comments, approvals, contribution claims, citations, tables/figures, and target-template versions.

**Deliverables:**

- Store manuscript snapshots, section/block identities, researcher-authored text, generated candidates, comments, approvals, contribution claims, citations, tables/figures, and target-template versions.

**Acceptance criteria:**

- Store manuscript snapshots, section/block identities, researcher-authored text, generated candidates, comments, approvals, contribution claims, citations, tables/figures, and target-template versions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile data

#### - [ ] CAP-18.S01.T02 - Implement section workflow, readiness, locks, and human gates

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T01`, `CAP-03.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Sections move through planned, evidence-ready, draft, author-reviewed, citation-audited, review-ready, and stale states; researcher text is protected from silent overwrite.

**Deliverables:**

- Sections move through planned, evidence-ready, draft, author-reviewed, citation-audited, review-ready, and stale states; researcher text is protected from silent overwrite.

**Acceptance criteria:**

- Sections move through planned, evidence-ready, draft, author-reviewed, citation-audited, review-ready, and stale states; researcher text is protected from silent overwrite.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

#### - [ ] CAP-18.S01.T03 - Implement manuscript dependency and selective-redrafting model

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T02`, `CAP-03.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Track section and paragraph dependencies on blueprint, literature evidence, result evidence, tables/figures, reviewer comments, and author decisions so only approved affected content is regenerated.

**Deliverables:**

- Track section and paragraph dependencies on blueprint, literature evidence, result evidence, tables/figures, reviewer comments, and author decisions so only approved affected content is regenerated.

**Acceptance criteria:**

- Track section and paragraph dependencies on blueprint, literature evidence, result evidence, tables/figures, reviewer comments, and author decisions so only approved affected content is regenerated.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile data

### CAP-18.S02 - Evidence-aware drafting engine

**Outcome:** Generated prose is section-specific, source-grounded, inspectable, and unable to conceal unsupported content.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T03`, `CAP-17.S06.T03`

#### - [ ] CAP-18.S02.T01 - Assemble section-specific literature, result, memo, and design evidence packets

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T03`, `CAP-17.S06.T03`, `CAP-09.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Each section receives only approved relevant evidence, counterevidence, required blueprint elements, author memos, report results, and citation candidates with token/cost/egress controls.

**Deliverables:**

- Each section receives only approved relevant evidence, counterevidence, required blueprint elements, author memos, report results, and citation candidates with token/cost/egress controls.

**Acceptance criteria:**

- Each section receives only approved relevant evidence, counterevidence, required blueprint elements, author memos, report results, and citation candidates with token/cost/egress controls.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence
- python tools/verify.py --profile ai

#### - [ ] CAP-18.S02.T02 - Generate paragraph-level source-grounded draft candidates

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T01`, `CAP-07.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Draft prose preserves claim-to-evidence mappings, citations, uncertainty, disagreement, author instructions, and section purpose; generated content remains distinguishable until accepted.

**Deliverables:**

- Draft prose preserves claim-to-evidence mappings, citations, uncertainty, disagreement, author instructions, and section purpose; generated content remains distinguishable until accepted.

**Acceptance criteria:**

- Draft prose preserves claim-to-evidence mappings, citations, uncertainty, disagreement, author instructions, and section purpose; generated content remains distinguishable until accepted.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence

#### - [ ] CAP-18.S02.T03 - Enforce unsupported-content and result-integrity controls

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T02`

**Owner / review:** - / - (`-`)

**Objective:** Missing methods/results/citations create visible placeholders or blocked passages; no model may fabricate data, sources, participant details, analyses, venue rules, or researcher positions.

**Deliverables:**

- Missing methods/results/citations create visible placeholders or blocked passages; no model may fabricate data, sources, participant details, analyses, venue rules, or researcher positions.

**Acceptance criteria:**

- Missing methods/results/citations create visible placeholders or blocked passages; no model may fabricate data, sources, participant details, analyses, venue rules, or researcher positions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local

### CAP-18.S03 - Empirical manuscript drafting

**Outcome:** The platform can draft a complete empirical article from verified study and literature evidence.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T03`, `CAP-17.S05.T03`

#### - [ ] CAP-18.S03.T01 - Draft empirical methods from approved design and verified actual conduct

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T03`, `CAP-17.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Generate methods sections that distinguish protocol from execution, disclose deviations, preserve reproducibility detail, and cite instruments/procedures where appropriate.

**Deliverables:**

- Generate methods sections that distinguish protocol from execution, disclose deviations, preserve reproducibility detail, and cite instruments/procedures where appropriate.

**Acceptance criteria:**

- Generate methods sections that distinguish protocol from execution, disclose deviations, preserve reproducibility detail, and cite instruments/procedures where appropriate.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile results
- python tools/verify.py --profile study-design

#### - [ ] CAP-18.S03.T02 - Draft empirical results from verified reports, tables, and figures

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S03.T01`, `CAP-17.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Generate accurate narrative results and captions only from approved result records, including null/mixed findings, uncertainty, robustness, exclusions, and unresolved discrepancies.

**Deliverables:**

- Generate accurate narrative results and captions only from approved result records, including null/mixed findings, uncertainty, robustness, exclusions, and unresolved discrepancies.

**Acceptance criteria:**

- Generate accurate narrative results and captions only from approved result records, including null/mixed findings, uncertainty, robustness, exclusions, and unresolved discrepancies.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile results
- python tools/verify.py --profile evidence

#### - [ ] CAP-18.S03.T03 - Draft empirical discussion integrated with literature and alternative outcomes

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S03.T02`, `CAP-09.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Connect verified findings to prior evidence, mechanisms, boundary conditions, limitations, practical/theoretical contributions, and alternative explanations without overstating causal or general claims.

**Deliverables:**

- Connect verified findings to prior evidence, mechanisms, boundary conditions, limitations, practical/theoretical contributions, and alternative explanations without overstating causal or general claims.

**Acceptance criteria:**

- Connect verified findings to prior evidence, mechanisms, boundary conditions, limitations, practical/theoretical contributions, and alternative explanations without overstating causal or general claims.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence

### CAP-18.S04 - Theory and critical manuscript drafting

**Outcome:** The platform can develop full theory and critical article drafts while preserving epistemic and authorial plurality.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T03`, `CAP-16.S03.T03`, `CAP-16.S04.T03`

#### - [ ] CAP-18.S04.T01 - Draft theory manuscripts from approved argument architecture

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T03`, `CAP-16.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Produce integrated theoretical prose from theory/construct/claim graphs, memos, evidence, counterarguments, and approved contribution logic without requiring propositions.

**Deliverables:**

- Produce integrated theoretical prose from theory/construct/claim graphs, memos, evidence, counterarguments, and approved contribution logic without requiring propositions.

**Acceptance criteria:**

- Produce integrated theoretical prose from theory/construct/claim graphs, memos, evidence, counterarguments, and approved contribution logic without requiring propositions.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile graph
- python tools/verify.py --profile evidence

#### - [ ] CAP-18.S04.T02 - Draft critical manuscripts from approved problematization architecture

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S02.T03`, `CAP-16.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Produce situated critical prose that preserves standpoint, textual/empirical evidence, assumptions, silences, alternatives, counter-readings, and normative commitments under researcher control.

**Deliverables:**

- Produce situated critical prose that preserves standpoint, textual/empirical evidence, assumptions, silences, alternatives, counter-readings, and normative commitments under researcher control.

**Acceptance criteria:**

- Produce situated critical prose that preserves standpoint, textual/empirical evidence, assumptions, silences, alternatives, counter-readings, and normative commitments under researcher control.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence

#### - [ ] CAP-18.S04.T03 - Preserve author voice, competing interpretations, and nonconsensus

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S04.T01`, `CAP-18.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Support section-level instructions, style exemplars supplied by the author, alternate drafts, human memos, and unresolved plurality without mimicking unavailable copyrighted texts or overwriting author choices.

**Deliverables:**

- Support section-level instructions, style exemplars supplied by the author, alternate drafts, human memos, and unresolved plurality without mimicking unavailable copyrighted texts or overwriting author choices.

**Acceptance criteria:**

- Support section-level instructions, style exemplars supplied by the author, alternate drafts, human memos, and unresolved plurality without mimicking unavailable copyrighted texts or overwriting author choices.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile ai

### CAP-18.S05 - Manuscript Studio and publication exports

**Outcome:** Researchers can review, edit, approve, and export complete source-grounded manuscripts.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S03.T03`, `CAP-18.S04.T03`

#### - [ ] CAP-18.S05.T01 - Build the Manuscript Studio workspace

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S03.T03`, `CAP-18.S04.T03`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.

**Deliverables:**

- Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.

**Acceptance criteria:**

- Deliver outline, editor, evidence inspector, claim/citation status, tables/figures, comments, section gates, version diff, and workflow handoffs for all article types.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile desktop

#### - [ ] CAP-18.S05.T02 - Implement citation/reference, figure/table, disclosure, and authorship management

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.

**Deliverables:**

- Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.

**Acceptance criteria:**

- Maintain citation keys and support status, reference completeness, table/figure provenance, contributor roles, AI-use disclosure, conflicts/funding, ethics/data/code statements, and acknowledgments.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence

#### - [ ] CAP-18.S05.T03 - Export publication artifacts with reproducibility and lineage

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S05.T02`, `CAP-09.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.

**Deliverables:**

- Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.

**Acceptance criteria:**

- Produce DOCX, Markdown, LaTeX, bibliography, tables/figures, appendices, disclosure, response-ready IDs, and a private/public reproducibility manifest appropriate to rights and confidentiality.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

### CAP-18.S06 - Source-grounded manuscript production acceptance

**Outcome:** Manuscript drafting is accurate, auditable, editable, and production-ready across article types.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S05.T03`

#### - [ ] CAP-18.S06.T01 - Run full-draft acceptance for empirical, theory, and critical articles

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Representative projects produce complete conference and journal drafts from approved blueprints and evidence with all unsupported content visibly blocked or marked.

**Deliverables:**

- Representative projects produce complete conference and journal drafts from approved blueprints and evidence with all unsupported content visibly blocked or marked.

**Acceptance criteria:**

- Representative projects produce complete conference and journal drafts from approved blueprints and evidence with all unsupported content visibly blocked or marked.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile e2e-local

#### - [ ] CAP-18.S06.T02 - Run citation, plagiarism-risk, result-integrity, and authorship audits

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Validate claim support/completeness, quotation and paraphrase controls, no fabricated sources/results, author-text preservation, disclosure, and export fidelity.

**Deliverables:**

- Validate claim support/completeness, quotation and paraphrase controls, no fabricated sources/results, author-text preservation, disclosure, and export fidelity.

**Acceptance criteria:**

- Validate claim support/completeness, quotation and paraphrase controls, no fabricated sources/results, author-text preservation, disclosure, and export fidelity.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence
- python tools/verify.py --profile security-local

#### - [ ] CAP-18.S06.T03 - Approve manuscript-drafting readiness for G8

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S06.T02`

**Owner / review:** - / - (`-`)

**Objective:** Map capability exit criteria to reviewed evidence and approve cross-platform drafting and export for reviewer simulation.

**Deliverables:**

- Map capability exit criteria to reviewed evidence and approve cross-platform drafting and export for reviewer simulation.

**Acceptance criteria:**

- Map capability exit criteria to reviewed evidence and approve cross-platform drafting and export for reviewer simulation.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile manuscript

## CAP-19 - Reviewer simulation, editorial synthesis, and revision

**Campaign / completion:** `NONE` / `PENDING`

**Objective:** Subject generated or uploaded empirical, theory, and critical drafts to independent multi-role simulated peer review, evidence-aware editorial synthesis, and author-controlled revision and response rounds.

**Exit criteria:**

- Reviewer roles and criteria match the research type and verified venue expectations, operate independently, and expose evidence, confidence, and possible overreach.
- Generated or uploaded manuscript snapshots are immutable and audited against project evidence, technical reports, article blueprints, and venue criteria.
- Editorial synthesis preserves disagreement and does not present simulated decisions as actual peer review or acceptance probability.
- Every review comment can be triaged, linked to a revision, answered, diffed, and re-reviewed with full lineage.

### CAP-19.S01 - Reviewer protocol, roles, and independence

**Outcome:** Reviewer simulations are role-bounded, reproducible, and independent before editorial synthesis.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T03`

#### - [ ] CAP-19.S01.T01 - Define reviewer role, criterion, comment, decision, and review-round contracts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-18.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Model article-type/venue-aware reviewer roles, criteria, severities, confidence, evidence basis, section/claim targets, independent reports, editorial decisions, revision actions, responses, and manuscript snapshots.

**Deliverables:**

- Model article-type/venue-aware reviewer roles, criteria, severities, confidence, evidence basis, section/claim targets, independent reports, editorial decisions, revision actions, responses, and manuscript snapshots.

**Acceptance criteria:**

- Model article-type/venue-aware reviewer roles, criteria, severities, confidence, evidence basis, section/claim targets, independent reports, editorial decisions, revision actions, responses, and manuscript snapshots.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile data

#### - [ ] CAP-19.S01.T02 - Create governed reviewer-panel profiles by research type and venue

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T01`, `CAP-16.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Provide configurable editor, domain, theory, critical, methods, statistics, qualitative, reproducibility, ethics, citation-integrity, and practical-contribution roles selected by manuscript/venue needs.

**Deliverables:**

- Provide configurable editor, domain, theory, critical, methods, statistics, qualitative, reproducibility, ethics, citation-integrity, and practical-contribution roles selected by manuscript/venue needs.

**Acceptance criteria:**

- Provide configurable editor, domain, theory, critical, methods, statistics, qualitative, reproducibility, ethics, citation-integrity, and practical-contribution roles selected by manuscript/venue needs.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer

#### - [ ] CAP-19.S01.T03 - Implement independent reviewer-context isolation and reproducible prompts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T02`, `CAP-07.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Each reviewer receives a sealed manuscript snapshot, role criteria, permitted evidence, and no other simulated review before submitting; model/prompt versions and randomness are recorded.

**Deliverables:**

- Each reviewer receives a sealed manuscript snapshot, role criteria, permitted evidence, and no other simulated review before submitting; model/prompt versions and randomness are recorded.

**Acceptance criteria:**

- Each reviewer receives a sealed manuscript snapshot, role criteria, permitted evidence, and no other simulated review before submitting; model/prompt versions and randomness are recorded.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai
- python tools/verify.py --profile security-local

### CAP-19.S02 - Extended independent reviewer panel

**Outcome:** Generated or uploaded drafts receive complementary substantive, methodological, theoretical, critical, and integrity reviews.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T03`

#### - [ ] CAP-19.S02.T01 - Implement editorial, contribution, scope, and positioning review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Simulate editor and contribution reviewers who assess fit, problem importance, novelty boundaries, structure, clarity, overclaiming, and audience using verified venue criteria where available.

**Deliverables:**

- Simulate editor and contribution reviewers who assess fit, problem importance, novelty boundaries, structure, clarity, overclaiming, and audience using verified venue criteria where available.

**Acceptance criteria:**

- Simulate editor and contribution reviewers who assess fit, problem importance, novelty boundaries, structure, clarity, overclaiming, and audience using verified venue criteria where available.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai
- python tools/verify.py --profile novelty

#### - [ ] CAP-19.S02.T02 - Implement methods, statistics/analysis, validity, ethics, and reproducibility review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S02.T01`, `CAP-17.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Select methodological roles appropriate to the manuscript and trace concerns to study design, reports, results, analyses, artifacts, deviations, and claims.

**Deliverables:**

- Select methodological roles appropriate to the manuscript and trace concerns to study design, reports, results, analyses, artifacts, deviations, and claims.

**Acceptance criteria:**

- Select methodological roles appropriate to the manuscript and trace concerns to study design, reports, results, analyses, artifacts, deviations, and claims.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai
- python tools/verify.py --profile study-design
- python tools/verify.py --profile results

#### - [ ] CAP-19.S02.T03 - Implement theory, critical, domain, citation, and evidence-integrity review

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S02.T01`, `CAP-18.S05.T02`

**Owner / review:** - / - (`-`)

**Objective:** Assess conceptual integration, assumptions, counterarguments, standpoint, literature coverage, citation support, result use, missing evidence, and article-type expectations without flattening epistemic differences.

**Deliverables:**

- Assess conceptual integration, assumptions, counterarguments, standpoint, literature coverage, citation support, result use, missing evidence, and article-type expectations without flattening epistemic differences.

**Acceptance criteria:**

- Assess conceptual integration, assumptions, counterarguments, standpoint, literature coverage, citation support, result use, missing evidence, and article-type expectations without flattening epistemic differences.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence

### CAP-19.S03 - Generated and uploaded draft intake

**Outcome:** Any draft can enter a reproducible, evidence-aware reviewer simulation without losing its original state.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T03`

#### - [ ] CAP-19.S03.T01 - Ingest generated or externally uploaded manuscript drafts

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S01.T03`, `CAP-05.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Import DOCX, PDF, Markdown, or LaTeX drafts as immutable snapshots, parse sections/citations/tables/figures, preserve authorship, and associate or create a project manuscript record.

**Deliverables:**

- Import DOCX, PDF, Markdown, or LaTeX drafts as immutable snapshots, parse sections/citations/tables/figures, preserve authorship, and associate or create a project manuscript record.

**Acceptance criteria:**

- Import DOCX, PDF, Markdown, or LaTeX drafts as immutable snapshots, parse sections/citations/tables/figures, preserve authorship, and associate or create a project manuscript record.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile documents
- python tools/verify.py --profile security-local

#### - [ ] CAP-19.S03.T02 - Audit draft against blueprint, venue profile, evidence, and technical reports

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S03.T01`, `CAP-16.S05.T02`, `CAP-17.S05.T03`

**Owner / review:** - / - (`-`)

**Objective:** Map draft sections/claims/citations/results to the selected skeleton, official/generic venue criteria, project evidence, study design, and verified result records; unknown support remains explicit.

**Deliverables:**

- Map draft sections/claims/citations/results to the selected skeleton, official/generic venue criteria, project evidence, study design, and verified result records; unknown support remains explicit.

**Acceptance criteria:**

- Map draft sections/claims/citations/results to the selected skeleton, official/generic venue criteria, project evidence, study design, and verified result records; unknown support remains explicit.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile manuscript
- python tools/verify.py --profile evidence

#### - [ ] CAP-19.S03.T03 - Freeze review snapshot and record allowed reviewer context

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S03.T02`

**Owner / review:** - / - (`-`)

**Objective:** Create a content hash, evidence snapshot, role assignment, provider/egress plan, and disclosure so the round can be reproduced and later manuscript changes cannot alter prior reviews.

**Deliverables:**

- Create a content hash, evidence snapshot, role assignment, provider/egress plan, and disclosure so the round can be reproduced and later manuscript changes cannot alter prior reviews.

**Acceptance criteria:**

- Create a content hash, evidence snapshot, role assignment, provider/egress plan, and disclosure so the round can be reproduced and later manuscript changes cannot alter prior reviews.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile data
- python tools/verify.py --profile security-local

### CAP-19.S04 - Reviewer reports and editorial synthesis

**Outcome:** The system produces rigorous, transparent simulated peer review while preserving disagreement and uncertainty.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S02.T03`, `CAP-19.S03.T03`

#### - [ ] CAP-19.S04.T01 - Generate independent reviewer reports with evidence and uncertainty

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S02.T03`, `CAP-19.S03.T03`

**Owner / review:** - / - (`-`)

**Objective:** Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.

**Deliverables:**

- Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.

**Acceptance criteria:**

- Each role produces prioritized major/minor comments, strengths, evidence basis, section/claim anchors, confidence, required action, and possible false-positive/alternative interpretation.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai

#### - [ ] CAP-19.S04.T02 - Implement editorial synthesis preserving reviewer disagreement

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S04.T01`

**Owner / review:** - / - (`-`)

**Objective:** An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.

**Deliverables:**

- An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.

**Acceptance criteria:**

- An editor synthesizer groups issues, distinguishes consensus from disagreement, checks unsupported reviewer assertions, and produces a simulated decision rationale without revealing actual acceptance probability.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai

#### - [ ] CAP-19.S04.T03 - Implement reviewer quality, calibration, and overreach audits

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S04.T02`

**Owner / review:** - / - (`-`)

**Objective:** Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.

**Deliverables:**

- Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.

**Acceptance criteria:**

- Benchmark comment validity, actionability, redundancy, severity calibration, evidence grounding, epistemic fit, hallucination, bias, and agreement with human reviewers across article types.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile ai
- python tools/verify.py --profile evidence

### CAP-19.S05 - Revision and response workflow

**Outcome:** Reviewer feedback becomes a transparent, author-controlled revision plan and auditable response.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S04.T03`

#### - [ ] CAP-19.S05.T01 - Map review comments to a governed revision plan

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S04.T03`

**Owner / review:** - / - (`-`)

**Objective:** Create accept/modify/reject/defer decisions, responsible section, evidence needed, implementation action, rationale, dependencies, and reviewer-response status for every comment.

**Deliverables:**

- Create accept/modify/reject/defer decisions, responsible section, evidence needed, implementation action, rationale, dependencies, and reviewer-response status for every comment.

**Acceptance criteria:**

- Create accept/modify/reject/defer decisions, responsible section, evidence needed, implementation action, rationale, dependencies, and reviewer-response status for every comment.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile manuscript

#### - [ ] CAP-19.S05.T02 - Draft and manage response-to-reviewers or rebuttal documents

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S05.T01`

**Owner / review:** - / - (`-`)

**Objective:** Generate editable point-by-point responses grounded in actual revisions/evidence, preserve respectful author voice, and prevent claiming changes that are not present in the reviewed draft.

**Deliverables:**

- Generate editable point-by-point responses grounded in actual revisions/evidence, preserve respectful author voice, and prevent claiming changes that are not present in the reviewed draft.

**Acceptance criteria:**

- Generate editable point-by-point responses grounded in actual revisions/evidence, preserve respectful author voice, and prevent claiming changes that are not present in the reviewed draft.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile manuscript
- python tools/verify.py --profile ai

#### - [ ] CAP-19.S05.T03 - Implement selective revision, diff, resolution, and follow-up round

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S05.T02`, `CAP-18.S01.T03`

**Owner / review:** - / - (`-`)

**Objective:** Apply only approved changes through Manuscript Studio, show source/evidence-aware diffs, track resolved/unresolved comments, and allow a new independent round against the revised snapshot.

**Deliverables:**

- Apply only approved changes through Manuscript Studio, show source/evidence-aware diffs, track resolved/unresolved comments, and allow a new independent round against the revised snapshot.

**Acceptance criteria:**

- Apply only approved changes through Manuscript Studio, show source/evidence-aware diffs, track resolved/unresolved comments, and allow a new independent round against the revised snapshot.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile manuscript
- python tools/verify.py --profile e2e-local

### CAP-19.S06 - Reviewer simulation and research-production acceptance

**Outcome:** Extended simulated review and revision are production-ready and complete the G8 local research lifecycle.

**Wave / priority / status / review:** `W8` / `P0` / `NOT_STARTED` / `PENDING`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S05.T03`, `CAP-18.S06.T03`

#### - [ ] CAP-19.S06.T01 - Build Reviewer Simulation and Revision & Response workspaces

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `medium`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S05.T03`, `CAP-00.S06.T04`

**Owner / review:** - / - (`-`)

**Objective:** Deliver panel configuration, review-round setup, independent reports, editor synthesis, comment triage, response drafting, manuscript diff, follow-up round, and audit views.

**Deliverables:**

- Deliver panel configuration, review-round setup, independent reports, editor synthesis, comment triage, response drafting, manuscript diff, follow-up round, and audit views.

**Acceptance criteria:**

- Deliver panel configuration, review-round setup, independent reports, editor synthesis, comment triage, response drafting, manuscript diff, follow-up round, and audit views.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile desktop

#### - [ ] CAP-19.S06.T02 - Evaluate generated and uploaded drafts with expert reviewers

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S06.T01`

**Owner / review:** - / - (`-`)

**Objective:** Compare simulated and blinded human reviews for issue coverage, validity, severity, redundancy, false positives, epistemic fit, and revision usefulness across empirical, theory, and critical papers.

**Deliverables:**

- Compare simulated and blinded human reviews for issue coverage, validity, severity, redundancy, false positives, epistemic fit, and revision usefulness across empirical, theory, and critical papers.

**Acceptance criteria:**

- Compare simulated and blinded human reviews for issue coverage, validity, severity, redundancy, false positives, epistemic fit, and revision usefulness across empirical, theory, and critical papers.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer

#### - [ ] CAP-19.S06.T03 - Approve G8 end-to-end research-production release

**Status / priority / estimate / risk:** `NOT_STARTED` / `P0` / `M` / `high`

**Profiles / platforms:** `LOC`, `LAB`, `ALL` / `platform-neutral`

**Dependencies:** `CAP-19.S06.T02`, `CAP-18.S06.T03`, `CAP-17.S06.T03`

**Owner / review:** - / - (`-`)

**Objective:** Run literature-to-design/report-to-manuscript-to-review/revision acceptance, map all capability exit criteria, record limitations, and approve the complete local research-production product.

**Deliverables:**

- Run literature-to-design/report-to-manuscript-to-review/revision acceptance, map all capability exit criteria, record limitations, and approve the complete local research-production product.

**Acceptance criteria:**

- Run literature-to-design/report-to-manuscript-to-review/revision acceptance, map all capability exit criteria, record limitations, and approve the complete local research-production product.
- Automated tests cover the expected path and at least one material failure, denial, cancellation, migration, or boundary condition relevant to the task.
- Relevant contracts, migrations, fixtures, documentation, provenance, privacy/rights controls, and stale-dependency behavior are updated without unrelated scope expansion.

**Verification:**

- python tools/verify.py --profile reviewer
- python tools/verify.py --profile e2e-local
- python tools/verify.py --profile security-local

# Generation contract

Do not hand-edit any section of this file. Change `planning/backlog.yaml`, validate it, and run:

```bash
python tools/backlog_views.py --repo .
python tools/backlog_views.py --repo . --check
```
