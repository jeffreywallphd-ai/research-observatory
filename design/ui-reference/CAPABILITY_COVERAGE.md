# Research Observatory Capability-to-Page Coverage

**Version:** 1.4
**Reference:** `RO-UI-ACADEMIC-MINIMAL-1.4`
**Product pages:** 33
**Capabilities:** 20

## Capability coverage

| Capability | Status | Reference pages |
|---|---|---|
| CAP-00 — Delivery foundation and Codex execution system | covered | `prototype-index.html`, `style-guide.html` |
| CAP-01 — Windows-first desktop shell and supervised local runtime | covered | `index.html` |
| CAP-02 — Local projects, durable storage, security, and recovery | covered | `new-project.html`, `project-settings.html`, `projects.html`, `technical-reports.html` |
| CAP-03 — Canonical domain, research intent, provenance, and durable workflows | covered | `audit-lineage.html`, `help-onboarding.html`, `index.html`, `intent-contract.html`, `manuscript-blueprint.html`, `new-project.html`, `projects.html`, `research-notebook.html`, `schema-manager.html`, `study-design.html`, `task-center.html` |
| CAP-04 — Scholarly ingestion, connectors, canonicalization, and corpus governance | covered | `corpus-canvas.html`, `ingestion-reconciliation.html`, `source-manager.html` |
| CAP-05 — Document acquisition, parsing, source inspection, and page anchors | covered | `document-reader.html`, `parsing-quality.html`, `technical-reports.html` |
| CAP-06 — Local search, discovery, corpus diagnostics, and screening | covered | `corpus-canvas.html`, `screening.html`, `search-studio.html` |
| CAP-07 — Provider-neutral model gateway and governed AI execution | covered | `audit-lineage.html`, `manuscript-studio.html`, `model-center.html`, `reviewer-simulation.html`, `task-center.html`, `technical-reports.html` |
| CAP-08 — Evidence schemas, extraction, verification, and adjudication | covered | `document-reader.html`, `evidence-matrix.html`, `schema-manager.html`, `study-design.html`, `technical-reports.html` |
| CAP-09 — Scholarly graph, comparison sets, synthesis, and reproducibility | covered | `audit-lineage.html`, `claim-graph.html`, `manuscript-blueprint.html`, `manuscript-studio.html`, `research-notebook.html`, `schema-manager.html`, `synthesis-studio.html`, `theory-map.html` |
| CAP-10 — Novelty auditing, research opportunities, and plural research modes | covered | `critical-lens.html`, `index.html`, `living-monitor.html`, `novelty-audit.html`, `opportunity-radar.html`, `research-notebook.html`, `reviewer-simulation.html`, `study-design.html` |
| CAP-11 — Windows PC/lab product hardening, validation, packaging, and release | covered | `help-onboarding.html`, `new-project.html`, `project-settings.html`, `projects.html` |
| CAP-12 — University-hosted deployment, institutional identity, collaboration, and operations | intentionally_deferred | No current researcher page; profile deferred |
| CAP-13 — Managed cloud control plane, tenant data planes, governance, and SaaS operations | intentionally_deferred | No current researcher page; profile deferred |
| CAP-14 — Cross-platform desktop qualification and release | covered | `help-onboarding.html`, `model-center.html`, `new-project.html`, `project-settings.html`, `prototype-index.html`, `style-guide.html` |
| CAP-15 — Empirical study design and protocol development | covered | `audit-lineage.html`, `evidence-matrix.html`, `help-onboarding.html`, `index.html`, `intent-contract.html`, `new-project.html`, `study-design.html` |
| CAP-16 — Manuscript blueprint, venue profiles, and article architecture | covered | `audit-lineage.html`, `help-onboarding.html`, `index.html`, `intent-contract.html`, `manuscript-blueprint.html`, `manuscript-studio.html`, `new-project.html` |
| CAP-17 — Technical report and study-results integration | covered | `audit-lineage.html`, `document-reader.html`, `evidence-matrix.html`, `help-onboarding.html`, `index.html`, `manuscript-studio.html`, `model-center.html`, `parsing-quality.html`, `technical-reports.html` |
| CAP-18 — Source-grounded manuscript drafting and publication artifacts | covered | `audit-lineage.html`, `evidence-matrix.html`, `help-onboarding.html`, `index.html`, `intent-contract.html`, `manuscript-blueprint.html`, `manuscript-studio.html`, `model-center.html`, `reviewer-simulation.html`, `revision-response.html` |
| CAP-19 — Reviewer simulation, editorial synthesis, and revision | covered | `audit-lineage.html`, `help-onboarding.html`, `index.html`, `intent-contract.html`, `model-center.html`, `new-project.html`, `reviewer-simulation.html`, `revision-response.html` |

## Page contracts

### `index.html` — Project Home
Project state, current workflow, progress, corpus, decisions, research-production readiness, quality gates, activity, and next actions.

**Capabilities:** CAP-01, CAP-03, CAP-10, CAP-15, CAP-16, CAP-17, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- primary use case and workflow progress
- ordered workflow map
- recommended next step
- research quality gates
- corpus and decision summaries
- stale outputs
- recent field changes
- recent activity
- next actions
- intent summary

### `projects.html` — Projects
Create, open, import, back up, transfer, recover, and see workflow position for local project homes.

**Capabilities:** CAP-02, CAP-03, CAP-11

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- project list
- primary use case per project
- workflow position
- create/open/import actions
- backup/transfer/recovery state

### `new-project.html` — New Project
Choose one of fourteen primary scholarly use cases before configuring the research intent and local project home.

**Capabilities:** CAP-02, CAP-03, CAP-11, CAP-14, CAP-15, CAP-16, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- project basics
- fourteen approved use cases
- workflow preview
- reversibility and versioning guidance
- continue to intent
- fourteen approved use cases grouped as explore/synthesize and design/publish
- workflow preview for selected use case
- research-production human-authority guidance

### `intent-contract.html` — Research Intent Contract
Declare purpose, use case, ordered workflow, scope, evidence, AI authority, novelty standard, and stopping logic.

**Capabilities:** CAP-03, CAP-15, CAP-16, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- objective and intended contribution
- fourteen approved use cases
- ordered workflow preview
- scope and evidence policy
- AI authority
- novelty standard
- stopping logic
- change-impact warning
- version history

### `help-onboarding.html` — Help, Onboarding & Diagnostics
Use-case catalog, guided workflows, offline sample project, shortcuts, contextual help, and privacy-safe support bundles.

**Capabilities:** CAP-03, CAP-11, CAP-14, CAP-15, CAP-16, CAP-17, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- getting-started checklist
- eight-use-case catalog
- navigation model
- offline sample project
- keyboard and contextual help
- redacted diagnostics support
- fourteen-use-case catalog
- research-production safeguards
- cross-platform diagnostic guidance

### `search-studio.html` — Search Studio
Structured, semantic, citation, and branch-based discovery with coverage diagnostics.

**Capabilities:** CAP-06

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- source selection
- query builder
- versioned search tree
- results
- coverage and bias diagnostics
- add-to-corpus/screening actions

### `source-manager.html` — Source Manager
Open, local, licensed, and reference-manager adapters with rights, permissions, and health.

**Capabilities:** CAP-04

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- source/adaptor inventory
- rights and permissions
- connection health
- local/licensed/deferred states
- import-review route
- private technical-report sources
- uploaded manuscript-draft sources
- rights and model-egress policy per source class

### `ingestion-reconciliation.html` — Ingestion & Reconciliation
Import provenance, canonicalization, duplicates, versions, corrections, retractions, and rights review.

**Capabilities:** CAP-04

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- import batch provenance
- canonicalization preview
- duplicate/version decisions
- correction/retraction alerts
- rights review
- reversible merge decisions

### `corpus-canvas.html` — Corpus Canvas
Clusters, networks, discovery paths, coverage, missingness, and boundary sensitivity.

**Capabilities:** CAP-04, CAP-06

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- corpus clusters
- citation/semantic discovery paths
- coverage/missingness
- boundary sensitivity
- source-linked inspection

### `screening.html` — Screening
Active-learning queue, human inclusion authority, audit samples, conflicts, and stopping diagnostics.

**Capabilities:** CAP-06

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- active-learning queue
- inclusion/exclusion controls
- reasons
- audit/uncertainty samples
- conflict adjudication
- stopping diagnostics

### `document-reader.html` — Document Reader
Secure source inspection, parsed structure, page anchors, and evidence selection.

**Capabilities:** CAP-05, CAP-08, CAP-17

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- secure original/parsed source view
- document outline
- stable page/source anchors
- evidence selection
- rights and parser provenance

### `research-notebook.html` — Research Notebook
Researcher-owned memos, evolving questions, interpretive history, alternative readings, and linked evidence.

**Capabilities:** CAP-03, CAP-09, CAP-10

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- researcher-owned memo editor
- memo collections
- linked evidence/claims/search branches
- interpretive version history
- alternative readings
- AI suggestions kept separate

### `parsing-quality.html` — Parsing Quality & Corrections
Structure, page anchors, tables, figures, references, manual corrections, and selective reprocessing.

**Capabilities:** CAP-05, CAP-17

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- quality queue
- section/anchor/table/figure/reference checks
- manual corrections
- reprocessing impact
- source-reader route

### `evidence-matrix.html` — Evidence Matrix
Extraction, verification, alternative candidates, comparability, and adjudication.

**Capabilities:** CAP-08, CAP-15, CAP-17, CAP-18

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- schema-driven evidence grid
- status and confidence
- verifier/reviewer
- source passage detail
- comparability clusters
- adjudication

### `schema-manager.html` — Schema & Ontology Manager
Versioned domain packs, fields, relations, constraints, and change-impact preview.

**Capabilities:** CAP-03, CAP-08, CAP-09

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- ontology/schema version
- field/relation definitions
- constraints
- domain packs
- impact preview
- approval state

### `claim-graph.html` — Claim & Argument Graph
Claims, evidence, support, contradiction, qualification, and dispute review.

**Capabilities:** CAP-09

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- claim/evidence network
- support/contradiction/qualification
- source detail
- disputes and alternatives
- accessible tabular alternative

### `theory-map.html` — Theory & Construct Map
Theory use, definitions, operationalizations, mechanisms, drift, and integration.

**Capabilities:** CAP-09

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- theory and construct map
- definitions and synonyms
- operationalizations
- mechanisms and levels
- drift/integration
- source links

### `critical-lens.html` — Critical Lens
Assumptions, authority, dependency, stakeholder silence, and competing readings.

**Capabilities:** CAP-10

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- assumption candidates
- stakeholders and silences
- authority/dependency
- benefits/burdens
- competing readings
- researcher adjudication

### `opportunity-radar.html` — Opportunity Radar
Plural opportunity types and visible multi-objective comparison.

**Capabilities:** CAP-10

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- plural opportunity types
- visible scoring vector
- Pareto comparison
- evidence and counterevidence
- portfolio/convergence context

### `novelty-audit.html` — Novelty Audit
Facet decomposition, nearest-prior work, independent challenge, and bounded disposition.

**Capabilities:** CAP-10

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- candidate statement
- facet decomposition
- nearest prior work
- challenger search manifest
- bounded novelty draft
- human disposition

### `synthesis-studio.html` — Synthesis Studio
Evidence packets, cited research syntheses, disagreement preservation, disclosure, and reproducibility exports; not the primary full-manuscript editor.

**Capabilities:** CAP-09

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- accepted evidence packet
- outline/narrative
- claim-level citations
- disagreement and uncertainty
- citation audit
- exports/disclosure

### `living-monitor.html` — Living Monitor
Differential retrieval, field changes, impact analysis, and selective recalculation.

**Capabilities:** CAP-10

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- saved monitors
- new-paper triage
- field/graph changes
- affected claims/outputs
- selective recalculation
- reassessment workflow

### `task-center.html` — Task Center
Durable analytical workflows, checkpoints, resource use, failures, cancellation, and human gates.

**Capabilities:** CAP-03, CAP-07

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- analytical workflow queue
- progress/checkpoints
- failure/cancellation
- resource use
- human gates
- resume/retry

### `audit-lineage.html` — Audit & Lineage
Source-to-output lineage, transformations, audit events, rights decisions, and human adjudications.

**Capabilities:** CAP-03, CAP-07, CAP-09, CAP-15, CAP-16, CAP-17, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- source-to-output lineage
- model/schema/prompt versions
- rights and egress decisions
- human decisions
- audit events
- exportable manifest
- study-design lineage
- technical-report and result lineage
- manuscript claim and citation lineage
- review and revision lineage

### `model-center.html` — Model & Privacy Center
Local/remote model routing, egress preview, budgets, evaluation, and offline policy.

**Capabilities:** CAP-07, CAP-14, CAP-17, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- provider-neutral profiles
- local/remote/deferred status
- task routing
- egress preview
- budgets
- evaluation and offline policy

### `application-settings.html` — Application Settings
Application-wide Security & sign-in, provider status and recovery, appearance, and diagnostics for this Windows account.

**Capabilities:** CAP-02

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- application-wide scope
- no-login default
- Windows password option
- Windows Hello option
- provider availability states
- lock behavior preview
- same-user proof before protection reduction
- explicit recovery without silent fallback
- versioned migration behavior
- Application Settings and Project Settings separation

### `project-settings.html` — Project Settings
Project storage, protection, privacy, backup, accessibility, and Windows/macOS/Linux project portability.

**Capabilities:** CAP-02, CAP-11, CAP-14

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- project identity
- protected local storage
- privacy/egress
- backup/restore
- appearance/accessibility
- Application Settings link for app-wide sign-in
- local/deferred project-home profile

### `study-design.html` — Study Design Studio
Compare and formalize evidence-grounded empirical study alternatives, protocol, validity, ethics, analysis, and reproducibility.

**Capabilities:** CAP-03, CAP-08, CAP-10, CAP-15

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- ordered study-design stage rail
- research questions and contribution mechanism
- comparable design alternatives
- selected-design rationale
- sampling and recruitment plan
- construct and measurement plan
- procedure and intervention plan
- analysis and robustness plan
- validity threats and mitigations
- ethics, data management, and preregistration gates
- literature and opportunity evidence inspector
- named researcher approval

### `manuscript-blueprint.html` — Manuscript Blueprint
Create venue- and research-type-aware conference or journal article skeletons, claim plans, word budgets, exhibits, and evidence prerequisites.

**Capabilities:** CAP-03, CAP-09, CAP-16, CAP-18

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- article type and target venue profile
- section outline and purposes
- section word budgets
- planned claim blocks
- required literature, result, or interpretive evidence
- table and figure plan
- contribution and positioning plan
- unresolved prerequisites and blocked claims
- author decisions and blueprint approval

### `technical-reports.html` — Technical Reports & Results
Upload private technical reports and study outputs, extract and verify methods and results, reconcile versions, and map study outputs to manuscript claims.

**Capabilities:** CAP-02, CAP-05, CAP-07, CAP-08, CAP-17

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- private report library and access status
- report versions and study-run grouping
- parse and verification status
- methods and protocol deviations
- reported results with exact anchors
- tables and figures
- result reconciliation and discrepancies
- unreported-statistic and unsupported-inference warnings
- limitations and null/mixed results
- manuscript impact mapping
- local/model-egress controls
- human result adjudication

### `manuscript-studio.html` — Manuscript Studio
Draft or revise empirical, theory, and critical conference or journal articles from approved blueprints, literature evidence, verified results, and researcher decisions.

**Capabilities:** CAP-07, CAP-09, CAP-16, CAP-17, CAP-18

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- article outline and section readiness
- venue and research-type blueprint
- manuscript writing surface
- evidence and result inspector
- supported, partial, blocked, and author-written claim states
- citation and source-passage links
- table and figure placement
- word budget and submission requirements
- authorship and AI-contribution markers
- disclosure and reproducibility export
- named author approval

### `reviewer-simulation.html` — Reviewer Simulation
Run extended role-separated simulated reviews over generated or uploaded article drafts and synthesize evidence-linked editorial guidance.

**Capabilities:** CAP-07, CAP-10, CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- immutable manuscript snapshot and review round
- independent reviewer roles and completion state
- methodological, theoretical, critical, reporting, contribution, and editorial dimensions
- major, moderate, and minor comments
- evidence, manuscript, result, and omitted-literature links
- contradictory reviewer positions
- editorial synthesis after independent reviews
- no acceptance probability
- no named real-reviewer impersonation
- human disposition required

### `revision-response.html` — Revision & Response
Triage simulated or uploaded review comments, govern author dispositions, revise manuscript passages, draft responses, and run targeted re-review.

**Capabilities:** CAP-18, CAP-19

**Required regions:**
- application top bar
- project home access
- primary-use-case selector
- ordered guided-workflow navigation
- secondary all-tools inventory
- page title and purpose
- workflow context with previous/next or return action
- theme toggle
- trust/provenance footer
- review issue clusters and severity
- original review comment
- author disposition and rationale
- revision checklist
- before-and-after manuscript diff
- response-to-reviewer editor
- evidence and lineage inspector
- unresolved and declined issues
- targeted re-review result
- revised manuscript and response export

