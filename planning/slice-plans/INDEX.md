# Slice implementation plan index

Baseline `1.3`, supplemental planning release `1.3.4`. Plans remain proposed until the one-time capability planning gate is approved.

## Mandatory planning automation

The static review surface at `planning/review-site/` provides one linked page per slice. Each slice page places the capability decision gate and recommended implementation selections near the top, followed by the task sequence and full plan. Begin at `planning/review-site/CAP-XX/index.html` so cross-slice decisions are resolved once before implementation.

- `python tools/planctl.py --repo . prepare CAP-XX` creates missing proposed plans from the governed templates.
- After the planning agent replaces placeholders with researched candidates and rationale, `python tools/planctl.py --repo . adopt-recommendations CAP-XX` records every best-in-class recommendation as the completed selected default.
- `python tools/planctl.py decisions CAP-XX` shows candidates, recommendations, selected options, blockers, and approval gaps.
- `python tools/planctl.py validate CAP-XX` validates structure while planning is underway.
- `python tools/planctl.py ready CAP-XX --require-approved` is required before a capability campaign starts.
- Planning resolves material choices for the entire capability up front; execution then proceeds continuously with only classified pause conditions.

## CAP-01 — Windows-first desktop shell and supervised local runtime

- [`CAP-01.S01` — Tauri and React application shell](CAP-01/CAP-01.S01-tauri-and-react-application-shell.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-01.S02` — Desktop design system and accessibility foundation](CAP-01/CAP-01.S02-desktop-design-system-and-accessibility-foundation.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-01.S03` — Packaged Python/FastAPI sidecar](CAP-01/CAP-01.S03-packaged-python-fastapi-sidecar.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-01.S04` — Authenticated desktop-service contract](CAP-01/CAP-01.S04-authenticated-desktop-service-contract.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-01.S05` — Windows installation and update channels](CAP-01/CAP-01.S05-windows-installation-and-update-channels.md) — 3 tasks, `W5`, `proposed` / approval `pending`

## CAP-02 — Local projects, durable storage, security, and recovery

- [`CAP-02.S01` — Local project lifecycle and directory contract](CAP-02/CAP-02.S01-local-project-lifecycle-and-directory-contract.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-02.S02` — SQLite schema, migrations, and repository layer](CAP-02/CAP-02.S02-sqlite-schema-migrations-and-repository-layer.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-02.S03` — Encrypted local object and cache storage](CAP-02/CAP-02.S03-encrypted-local-object-and-cache-storage.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-02.S04` — Local secrets, profiles, and privacy controls](CAP-02/CAP-02.S04-local-secrets-profiles-and-privacy-controls.md) — 4 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-02.S05` — Backup, restore, relocation, and lab portability](CAP-02/CAP-02.S05-backup-restore-relocation-and-lab-portability.md) — 3 tasks, `W5`, `proposed` / approval `pending`

## CAP-03 — Canonical domain, research intent, provenance, and durable workflows

- [`CAP-03.S01` — Canonical identifiers and domain contracts](CAP-03/CAP-03.S01-canonical-identifiers-and-domain-contracts.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-03.S02` — Research intent contract and mode governance](CAP-03/CAP-03.S02-research-intent-contract-and-mode-governance.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-03.S03` — Append-only provenance and audit ledger](CAP-03/CAP-03.S03-append-only-provenance-and-audit-ledger.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-03.S04` — Portable workflow model and local worker fabric](CAP-03/CAP-03.S04-portable-workflow-model-and-local-worker-fabric.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-03.S05` — Dependency graph, staleness, and controlled recalculation](CAP-03/CAP-03.S05-dependency-graph-staleness-and-controlled-recalculation.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-03.S06` — Use-case profiles and adaptive guided navigation](CAP-03/CAP-03.S06-use-case-profiles-and-adaptive-guided-navigation.md) — 5 tasks, `W1`, `proposed` / approval `pending`

## CAP-04 — Scholarly ingestion, connectors, canonicalization, and corpus governance

- [`CAP-04.S01` — Reference-library and file imports](CAP-04/CAP-04.S01-reference-library-and-file-imports.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-04.S02` — Open scholarly source adapters](CAP-04/CAP-04.S02-open-scholarly-source-adapters.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-04.S03` — Canonical work, version, and identity reconciliation](CAP-04/CAP-04.S03-canonical-work-version-and-identity-reconciliation.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-04.S04` — Corpus membership, discovery path, and rights governance](CAP-04/CAP-04.S04-corpus-membership-discovery-path-and-rights-governance.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-04.S05` — Connector SDK and controlled extensibility](CAP-04/CAP-04.S05-connector-sdk-and-controlled-extensibility.md) — 3 tasks, `W2`, `proposed` / approval `pending`

## CAP-05 — Document acquisition, parsing, source inspection, and page anchors

- [`CAP-05.S01` — Rights-aware document acquisition](CAP-05/CAP-05.S01-rights-aware-document-acquisition.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-05.S02` — Structured and PDF parsing pipeline](CAP-05/CAP-05.S02-structured-and-pdf-parsing-pipeline.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-05.S03` — Immutable document revisions and source anchors](CAP-05/CAP-05.S03-immutable-document-revisions-and-source-anchors.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-05.S04` — Source viewer and evidence inspection experience](CAP-05/CAP-05.S04-source-viewer-and-evidence-inspection-experience.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-05.S05` — References, citation contexts, tables, and figures](CAP-05/CAP-05.S05-references-citation-contexts-tables-and-figures.md) — 3 tasks, `W2`, `proposed` / approval `pending`
- [`CAP-05.S06` — Parsing quality, correction, and reprocessing](CAP-05/CAP-05.S06-parsing-quality-correction-and-reprocessing.md) — 3 tasks, `W2`, `proposed` / approval `pending`

## CAP-06 — Local search, discovery, corpus diagnostics, and screening

- [`CAP-06.S01` — Fielded lexical search and local indexing](CAP-06/CAP-06.S01-fielded-lexical-search-and-local-indexing.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-06.S02` — Semantic representations and vector retrieval](CAP-06/CAP-06.S02-semantic-representations-and-vector-retrieval.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-06.S03` — Hybrid retrieval and reranking](CAP-06/CAP-06.S03-hybrid-retrieval-and-reranking.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-06.S04` — Search Studio and transparent expansion](CAP-06/CAP-06.S04-search-studio-and-transparent-expansion.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-06.S05` — Corpus canvas, coverage, and reflexivity diagnostics](CAP-06/CAP-06.S05-corpus-canvas-coverage-and-reflexivity-diagnostics.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-06.S06` — Transparent screening and active-learning governance](CAP-06/CAP-06.S06-transparent-screening-and-active-learning-governance.md) — 3 tasks, `W3`, `proposed` / approval `pending`

## CAP-07 — Provider-neutral model gateway and governed AI execution

- [`CAP-07.S01` — Model task, provider, and routing contracts](CAP-07/CAP-07.S01-model-task-provider-and-routing-contracts.md) — 3 tasks, `W1`, `proposed` / approval `pending`
- [`CAP-07.S02` — Local model runtime and model management](CAP-07/CAP-07.S02-local-model-runtime-and-model-management.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-07.S03` — Approved remote model providers](CAP-07/CAP-07.S03-approved-remote-model-providers.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-07.S04` — Prompt, schema, and structured-output registry](CAP-07/CAP-07.S04-prompt-schema-and-structured-output-registry.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-07.S05` — AI observability, budgets, and evaluation operations](CAP-07/CAP-07.S05-ai-observability-budgets-and-evaluation-operations.md) — 3 tasks, `W3`, `proposed` / approval `pending`

## CAP-08 — Evidence schemas, extraction, verification, and adjudication

- [`CAP-08.S01` — Core ontology and schema-pack registry](CAP-08/CAP-08.S01-core-ontology-and-schema-pack-registry.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-08.S02` — Source-grounded extraction pipeline](CAP-08/CAP-08.S02-source-grounded-extraction-pipeline.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-08.S03` — Evidence record, status, confidence, and uncertainty model](CAP-08/CAP-08.S03-evidence-record-status-confidence-and-uncertainty-model.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-08.S04` — Independent evidence verification](CAP-08/CAP-08.S04-independent-evidence-verification.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-08.S05` — Evidence matrix and source-first analysis UI](CAP-08/CAP-08.S05-evidence-matrix-and-source-first-analysis-ui.md) — 3 tasks, `W3`, `proposed` / approval `pending`
- [`CAP-08.S06` — Coder comparison, adjudication, and evidence export](CAP-08/CAP-08.S06-coder-comparison-adjudication-and-evidence-export.md) — 3 tasks, `W3`, `proposed` / approval `pending`

## CAP-09 — Scholarly graph, comparison sets, synthesis, and reproducibility

- [`CAP-09.S01` — Local graph domain and replaceable graph storage](CAP-09/CAP-09.S01-local-graph-domain-and-replaceable-graph-storage.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-09.S02` — Claim, theory, construct, method, and context relations](CAP-09/CAP-09.S02-claim-theory-construct-method-and-context-relations.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-09.S03` — Comparability sets and contradiction candidates](CAP-09/CAP-09.S03-comparability-sets-and-contradiction-candidates.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-09.S04` — Graph, theory, construct, and lineage workspaces](CAP-09/CAP-09.S04-graph-theory-construct-and-lineage-workspaces.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-09.S05` — Evidence-grounded synthesis and citation audit](CAP-09/CAP-09.S05-evidence-grounded-synthesis-and-citation-audit.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-09.S06` — Reproducibility packages and scholarly exports](CAP-09/CAP-09.S06-reproducibility-packages-and-scholarly-exports.md) — 3 tasks, `W4`, `proposed` / approval `pending`

## CAP-10 — Novelty auditing, research opportunities, and plural research modes

- [`CAP-10.S01` — Nearest-prior novelty workspace MVP](CAP-10/CAP-10.S01-nearest-prior-novelty-workspace-mvp.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-10.S02` — Independent adversarial novelty challenge](CAP-10/CAP-10.S02-independent-adversarial-novelty-challenge.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-10.S03` — Research opportunity dossier and decision ledger](CAP-10/CAP-10.S03-research-opportunity-dossier-and-decision-ledger.md) — 3 tasks, `W4`, `proposed` / approval `pending`
- [`CAP-10.S05` — Critical and hermeneutic research support](CAP-10/CAP-10.S05-critical-and-hermeneutic-research-support.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-10.S04` — Plural opportunity detector ensemble](CAP-10/CAP-10.S04-plural-opportunity-detector-ensemble.md) — 3 tasks, `W9`, `proposed` / approval `pending`
- [`CAP-10.S06` — Opportunity radar, ranking, and portfolio governance](CAP-10/CAP-10.S06-opportunity-radar-ranking-and-portfolio-governance.md) — 3 tasks, `W9`, `proposed` / approval `pending`
- [`CAP-10.S07` — Living monitor and impact-aware research memory](CAP-10/CAP-10.S07-living-monitor-and-impact-aware-research-memory.md) — 3 tasks, `W9`, `proposed` / approval `pending`

## CAP-11 — Windows PC/lab product hardening, validation, packaging, and release

- [`CAP-11.S01` — Performance profiles, scale targets, and resource governance](CAP-11/CAP-11.S01-performance-profiles-scale-targets-and-resource-governance.md) — 3 tasks, `W5`, `proposed` / approval `pending`
- [`CAP-11.S02` — Reliability, crash recovery, upgrade, and rollback](CAP-11/CAP-11.S02-reliability-crash-recovery-upgrade-and-rollback.md) — 3 tasks, `W5`, `proposed` / approval `pending`
- [`CAP-11.S03` — Offline, privacy, and local security acceptance](CAP-11/CAP-11.S03-offline-privacy-and-local-security-acceptance.md) — 3 tasks, `W5`, `proposed` / approval `pending`
- [`CAP-11.S04` — Accessibility, usability, onboarding, and help](CAP-11/CAP-11.S04-accessibility-usability-onboarding-and-help.md) — 4 tasks, `W5`, `proposed` / approval `pending`
- [`CAP-11.S05` — Lab deployment, policy, maintenance, and support](CAP-11/CAP-11.S05-lab-deployment-policy-maintenance-and-support.md) — 3 tasks, `W5`, `proposed` / approval `pending`
- [`CAP-11.S06` — Local release candidate and acceptance gate](CAP-11/CAP-11.S06-local-release-candidate-and-acceptance-gate.md) — 3 tasks, `W5`, `proposed` / approval `pending`

## CAP-12 — University-hosted deployment, institutional identity, collaboration, and operations

- [`CAP-12.S01` — Desktop remote connection mode and API abstraction](CAP-12/CAP-12.S01-desktop-remote-connection-mode-and-api-abstraction.md) — 3 tasks, `W10`, `proposed` / approval `pending`
- [`CAP-12.S02` — Institutional service and data-plane foundation](CAP-12/CAP-12.S02-institutional-service-and-data-plane-foundation.md) — 3 tasks, `W10`, `proposed` / approval `pending`
- [`CAP-12.S03` — Institutional identity, authorization, and project isolation](CAP-12/CAP-12.S03-institutional-identity-authorization-and-project-isolation.md) — 3 tasks, `W10`, `proposed` / approval `pending`
- [`CAP-12.S04` — Team collaboration and scholarly adjudication](CAP-12/CAP-12.S04-team-collaboration-and-scholarly-adjudication.md) — 3 tasks, `W10`, `proposed` / approval `pending`
- [`CAP-12.S05` — Licensed sources, institutional rights, retention, and compute policy](CAP-12/CAP-12.S05-licensed-sources-institutional-rights-retention-and-compute-policy.md) — 3 tasks, `W10`, `proposed` / approval `pending`
- [`CAP-12.S06` — Institutional operations, disaster recovery, and pilot acceptance](CAP-12/CAP-12.S06-institutional-operations-disaster-recovery-and-pilot-acceptance.md) — 3 tasks, `W10`, `proposed` / approval `pending`

## CAP-13 — Managed cloud control plane, tenant data planes, governance, and SaaS operations

- [`CAP-13.S01` — SaaS organization and tenant control plane](CAP-13/CAP-13.S01-saas-organization-and-tenant-control-plane.md) — 3 tasks, `W11`, `proposed` / approval `pending`
- [`CAP-13.S02` — Regional tenant data planes and isolation tiers](CAP-13/CAP-13.S02-regional-tenant-data-planes-and-isolation-tiers.md) — 3 tasks, `W11`, `proposed` / approval `pending`
- [`CAP-13.S03` — Cloud identity, entitlement, metering, and billing](CAP-13/CAP-13.S03-cloud-identity-entitlement-metering-and-billing.md) — 3 tasks, `W11`, `proposed` / approval `pending`
- [`CAP-13.S04` — Elastic workers, models, search, and cost governance](CAP-13/CAP-13.S04-elastic-workers-models-search-and-cost-governance.md) — 3 tasks, `W11`, `proposed` / approval `pending`
- [`CAP-13.S05` — Cloud security, privacy, residency, and compliance operations](CAP-13/CAP-13.S05-cloud-security-privacy-residency-and-compliance-operations.md) — 3 tasks, `W11`, `proposed` / approval `pending`
- [`CAP-13.S06` — Desktop-cloud experience, service reliability, and launch gate](CAP-13/CAP-13.S06-desktop-cloud-experience-service-reliability-and-launch-gate.md) — 3 tasks, `W11`, `proposed` / approval `pending`

## CAP-14 — Cross-platform desktop qualification and release

- [`CAP-14.S01` — Platform abstraction and build matrix](CAP-14/CAP-14.S01-platform-abstraction-and-build-matrix.md) — 3 tasks, `W6`, `proposed` / approval `pending`
- [`CAP-14.S02` — Apple Silicon macOS product qualification](CAP-14/CAP-14.S02-apple-silicon-macos-product-qualification.md) — 3 tasks, `W6`, `proposed` / approval `pending`
- [`CAP-14.S03` — Linux x86_64 and ARM64 product qualification](CAP-14/CAP-14.S03-linux-x86-64-and-arm64-product-qualification.md) — 3 tasks, `W6`, `proposed` / approval `pending`
- [`CAP-14.S04` — Cross-platform scientific and AI runtime](CAP-14/CAP-14.S04-cross-platform-scientific-and-ai-runtime.md) — 3 tasks, `W6`, `proposed` / approval `pending`
- [`CAP-14.S05` — Cross-platform project compatibility and recovery](CAP-14/CAP-14.S05-cross-platform-project-compatibility-and-recovery.md) — 3 tasks, `W6`, `proposed` / approval `pending`
- [`CAP-14.S06` — Cross-platform desktop release gate](CAP-14/CAP-14.S06-cross-platform-desktop-release-gate.md) — 3 tasks, `W6`, `proposed` / approval `pending`

## CAP-15 — Empirical study design and protocol development

- [`CAP-15.S01` — Study-design domain and evidence foundation](CAP-15/CAP-15.S01-study-design-domain-and-evidence-foundation.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-15.S02` — Research logic and design alternatives](CAP-15/CAP-15.S02-research-logic-and-design-alternatives.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-15.S03` — Sampling, measurement, and data collection](CAP-15/CAP-15.S03-sampling-measurement-and-data-collection.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-15.S04` — Analysis, validity, ethics, and reproducibility](CAP-15/CAP-15.S04-analysis-validity-ethics-and-reproducibility.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-15.S05` — Study Design Studio and protocol exports](CAP-15/CAP-15.S05-study-design-studio-and-protocol-exports.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-15.S06` — Study-design production acceptance](CAP-15/CAP-15.S06-study-design-production-acceptance.md) — 3 tasks, `W7`, `proposed` / approval `pending`

## CAP-16 — Manuscript blueprint, venue profiles, and article architecture

- [`CAP-16.S01` — Manuscript domain and template governance](CAP-16/CAP-16.S01-manuscript-domain-and-template-governance.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-16.S02` — Empirical article blueprints](CAP-16/CAP-16.S02-empirical-article-blueprints.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-16.S03` — Theory article blueprints](CAP-16/CAP-16.S03-theory-article-blueprints.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-16.S04` — Critical scholarship blueprints](CAP-16/CAP-16.S04-critical-scholarship-blueprints.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-16.S05` — Manuscript Blueprint and venue adaptation](CAP-16/CAP-16.S05-manuscript-blueprint-and-venue-adaptation.md) — 3 tasks, `W7`, `proposed` / approval `pending`
- [`CAP-16.S06` — Manuscript blueprint production acceptance](CAP-16/CAP-16.S06-manuscript-blueprint-production-acceptance.md) — 3 tasks, `W7`, `proposed` / approval `pending`

## CAP-17 — Technical report and study-results integration

- [`CAP-17.S01` — Private technical-report and study-artifact intake](CAP-17/CAP-17.S01-private-technical-report-and-study-artifact-intake.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-17.S02` — Technical-report parsing and result extraction](CAP-17/CAP-17.S02-technical-report-parsing-and-result-extraction.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-17.S03` — Study-plan and result reconciliation](CAP-17/CAP-17.S03-study-plan-and-result-reconciliation.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-17.S04` — Results evidence graph and dependency propagation](CAP-17/CAP-17.S04-results-evidence-graph-and-dependency-propagation.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-17.S05` — Technical Reports & Results workspace](CAP-17/CAP-17.S05-technical-reports-and-results-workspace.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-17.S06` — Results integration production acceptance](CAP-17/CAP-17.S06-results-integration-production-acceptance.md) — 3 tasks, `W8`, `proposed` / approval `pending`

## CAP-18 — Source-grounded manuscript drafting and publication artifacts

- [`CAP-18.S01` — Manuscript project and section workflow](CAP-18/CAP-18.S01-manuscript-project-and-section-workflow.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-18.S02` — Evidence-aware drafting engine](CAP-18/CAP-18.S02-evidence-aware-drafting-engine.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-18.S03` — Empirical manuscript drafting](CAP-18/CAP-18.S03-empirical-manuscript-drafting.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-18.S04` — Theory and critical manuscript drafting](CAP-18/CAP-18.S04-theory-and-critical-manuscript-drafting.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-18.S05` — Manuscript Studio and publication exports](CAP-18/CAP-18.S05-manuscript-studio-and-publication-exports.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-18.S06` — Source-grounded manuscript production acceptance](CAP-18/CAP-18.S06-source-grounded-manuscript-production-acceptance.md) — 3 tasks, `W8`, `proposed` / approval `pending`

## CAP-19 — Reviewer simulation, editorial synthesis, and revision

- [`CAP-19.S01` — Reviewer protocol, roles, and independence](CAP-19/CAP-19.S01-reviewer-protocol-roles-and-independence.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-19.S02` — Extended independent reviewer panel](CAP-19/CAP-19.S02-extended-independent-reviewer-panel.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-19.S03` — Generated and uploaded draft intake](CAP-19/CAP-19.S03-generated-and-uploaded-draft-intake.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-19.S04` — Reviewer reports and editorial synthesis](CAP-19/CAP-19.S04-reviewer-reports-and-editorial-synthesis.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-19.S05` — Revision and response workflow](CAP-19/CAP-19.S05-revision-and-response-workflow.md) — 3 tasks, `W8`, `proposed` / approval `pending`
- [`CAP-19.S06` — Reviewer simulation and research-production acceptance](CAP-19/CAP-19.S06-reviewer-simulation-and-research-production-acceptance.md) — 3 tasks, `W8`, `proposed` / approval `pending`
