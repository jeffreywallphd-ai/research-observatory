---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-16
title: Manuscript blueprint, venue profiles, and article architecture
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-16.S01
- CAP-16.S02
- CAP-16.S03
- CAP-16.S04
- CAP-16.S05
- CAP-16.S06
decisions:
- id: CAP-16-D01
  title: Canonical manuscript model
  candidates:
  - Use a versioned semantic ManuscriptBlueprint domain model with stable section/block identities
  - Store a disposable outline as free-form Markdown
  recommendation: Use a versioned semantic ManuscriptBlueprint domain model with stable section/block identities
  recommendation_basis: A canonical model supports staleness, venue overlays, traceable drafting, reviewer comments and multi-format export.
  selected_option: Use a versioned semantic ManuscriptBlueprint domain model with stable section/block identities
  status: accepted
  required_adr: ADR-MANUSCRIPT-DOMAIN
- id: CAP-16-D02
  title: Identifier strategy
  candidates:
  - Use UUIDv7 identities for manuscript, section, block, claim-plan, figure and table objects
  - Use array position and heading text as identity
  recommendation: Use UUIDv7 identities for manuscript, section, block, claim-plan, figure and table objects
  recommendation_basis: Stable sortable identifiers survive reordering, export and revision and align with the platform identity model.
  selected_option: Use UUIDv7 identities for manuscript, section, block, claim-plan, figure and table objects
  status: accepted
  required_adr: null
- id: CAP-16-D03
  title: Template hierarchy
  candidates:
  - Use governed generic research-type bases plus versioned venue-profile overlays
  - Create one hard-coded template per venue
  recommendation: Use governed generic research-type bases plus versioned venue-profile overlays
  recommendation_basis: Layered profiles reduce duplication and preserve generic operation when venue rules are unavailable or change.
  selected_option: Use governed generic research-type bases plus versioned venue-profile overlays
  status: accepted
  required_adr: ADR-MANUSCRIPT-TEMPLATES
- id: CAP-16-D04
  title: Venue guidance intake
  candidates:
  - Accept official URLs/files and researcher uploads with source, retrieval date, hash, rights and verification status
  - Let the model infer venue requirements from its training
  recommendation: Accept official URLs/files and researcher uploads with source, retrieval date, hash, rights and verification status
  recommendation_basis: Venue requirements are volatile and must be inspectable rather than fabricated.
  selected_option: Accept official URLs/files and researcher uploads with source, retrieval date, hash, rights and verification status
  status: accepted
  required_adr: null
- id: CAP-16-D05
  title: Interchange model
  candidates:
  - Keep the internal semantic model canonical and map to JATS 1.4 as an interoperability target
  - Use JATS XML directly as the live editor state
  recommendation: Keep the internal semantic model canonical and map to JATS 1.4 as an interoperability target
  recommendation_basis: JATS is an excellent exchange standard but is too publisher-oriented to serve as the sole interactive authoring domain.
  selected_option: Keep the internal semantic model canonical and map to JATS 1.4 as an interoperability target
  status: accepted
  required_adr: ADR-MANUSCRIPT-INTERCHANGE
- id: CAP-16-D06
  title: Template evolution
  candidates:
  - Preview structural diffs and require explicit migration; never silently move authored content
  - Automatically reshape existing manuscripts when templates change
  recommendation: Preview structural diffs and require explicit migration; never silently move authored content
  recommendation_basis: Researcher-authored content and section meaning must remain under human control.
  selected_option: Preview structural diffs and require explicit migration; never silently move authored content
  status: accepted
  required_adr: null
- id: CAP-16-D07
  title: Empirical blueprint basis
  candidates:
  - Drive empirical patterns from study design, verified conduct/results requirements and method/reporting profiles
  - Use a universal IMRaD outline without method-specific requirements
  recommendation: Drive empirical patterns from study design, verified conduct/results requirements and method/reporting profiles
  recommendation_basis: Empirical completeness depends on design family, actual conduct and reporting standards.
  selected_option: Drive empirical patterns from study design, verified conduct/results requirements and method/reporting profiles
  status: accepted
  required_adr: null
- id: CAP-16-D08
  title: Theory blueprint model
  candidates:
  - Provide multiple argument/contribution architectures with explicit warrants, mechanisms, boundaries and counterarguments
  - Force all theory papers into an empirical-section template
  recommendation: Provide multiple argument/contribution architectures with explicit warrants, mechanisms, boundaries and counterarguments
  recommendation_basis: Theory development requires flexible but inspectable argument architecture.
  selected_option: Provide multiple argument/contribution architectures with explicit warrants, mechanisms, boundaries and counterarguments
  status: accepted
  required_adr: null
- id: CAP-16-D09
  title: Critical blueprint model
  candidates:
  - Model standpoint, problematization, evidence, reflexivity, counter-readings and normative implications
  - Treat critical work as a conventional literature review with a discussion section
  recommendation: Model standpoint, problematization, evidence, reflexivity, counter-readings and normative implications
  recommendation_basis: Critical scholarship has distinct evidentiary and reflexive obligations.
  selected_option: Model standpoint, problematization, evidence, reflexivity, counter-readings and normative implications
  status: accepted
  required_adr: null
- id: CAP-16-D10
  title: Section readiness
  candidates:
  - Give every section typed inputs, required decisions, evidence expectations, completion state and blockers
  - Use one manuscript-wide completion percentage
  recommendation: Give every section typed inputs, required decisions, evidence expectations, completion state and blockers
  recommendation_basis: Section-level readiness enables safe drafting and selective recalculation.
  selected_option: Give every section typed inputs, required decisions, evidence expectations, completion state and blockers
  status: accepted
  required_adr: null
- id: CAP-16-D11
  title: Length governance
  candidates:
  - Model venue/section word budgets as soft or hard constraints with transparent allocation
  - Truncate generated prose after drafting
  recommendation: Model venue/section word budgets as soft or hard constraints with transparent allocation
  recommendation_basis: Planning length before prose is safer and more usable than post-hoc deletion.
  selected_option: Model venue/section word budgets as soft or hard constraints with transparent allocation
  status: accepted
  required_adr: null
- id: CAP-16-D12
  title: Claim planning
  candidates:
  - Link planned contribution and section claims to evidence/result/argument requirements before drafting
  - Generate claims only while writing prose
  recommendation: Link planned contribution and section claims to evidence/result/argument requirements before drafting
  recommendation_basis: Claim plans are the bridge between evidence, blueprint, drafting and review.
  selected_option: Link planned contribution and section claims to evidence/result/argument requirements before drafting
  status: accepted
  required_adr: null
- id: CAP-16-D13
  title: Figures, tables and disclosures
  candidates:
  - Represent figures, tables, supplementary items, data/code statements, ethics and AI disclosures as first-class planned objects
  - Add these manually after manuscript drafting
  recommendation: Represent figures, tables, supplementary items, data/code statements, ethics and AI disclosures as first-class planned objects
  recommendation_basis: Publication artifacts and integrity statements affect section architecture and export readiness.
  selected_option: Represent figures, tables, supplementary items, data/code statements, ethics and AI disclosures as first-class planned objects
  status: accepted
  required_adr: null
- id: CAP-16-D14
  title: Contributor roles
  candidates:
  - Capture authorship plus CRediT roles with human confirmation and version history
  - Infer final authorship and order from activity logs
  recommendation: Capture authorship plus CRediT roles with human confirmation and version history
  recommendation_basis: Contribution transparency is useful, but authorship remains a human governance decision.
  selected_option: Capture authorship plus CRediT roles with human confirmation and version history
  status: accepted
  required_adr: null
- id: CAP-16-D15
  title: Export toolchain
  candidates:
  - Use a replaceable Quarto/Pandoc export service for DOCX, LaTeX, Markdown, JATS, HTML and PDF
  - Write custom exporters independently for every format
  recommendation: Use a replaceable Quarto/Pandoc export service for DOCX, LaTeX, Markdown, JATS, HTML and PDF
  recommendation_basis: A mature converter ecosystem reduces format divergence while stable manifests preserve traceability.
  selected_option: Use a replaceable Quarto/Pandoc export service for DOCX, LaTeX, Markdown, JATS, HTML and PDF
  status: accepted
  required_adr: ADR-MANUSCRIPT-EXPORT
- id: CAP-16-D16
  title: Drafting gate
  candidates:
  - Prohibit generated manuscript prose until the blueprint and claim plan are approved
  - Allow drafting from an incomplete outline
  recommendation: Prohibit generated manuscript prose until the blueprint and claim plan are approved
  recommendation_basis: The blueprint is the human-approved architecture and prevents prose from silently determining the argument.
  selected_option: Prohibit generated manuscript prose until the blueprint and claim plan are approved
  status: accepted
  required_adr: null
- id: CAP-16-D17
  title: Blueprint experience
  candidates:
  - Use the approved Manuscript Blueprint workspace with outline, requirements, evidence readiness, budgets and impact preview
  - Use a chat-only blueprint workflow
  recommendation: Use the approved Manuscript Blueprint workspace with outline, requirements, evidence readiness, budgets and impact preview
  recommendation_basis: A persistent visual structure is inspectable and easier to adjudicate than conversational state.
  selected_option: Use the approved Manuscript Blueprint workspace with outline, requirements, evidence readiness, budgets and impact preview
  status: accepted
  required_adr: null
- id: CAP-16-D18
  title: Venue profile freshness
  candidates:
  - Store verification status and expiration/recheck policy and mark dependent blueprints stale when guidance changes
  - Treat imported venue instructions as permanently current
  recommendation: Store verification status and expiration/recheck policy and mark dependent blueprints stale when guidance changes
  recommendation_basis: Venue instructions change and must participate in dependency propagation.
  selected_option: Store verification status and expiration/recheck policy and mark dependent blueprints stale when guidance changes
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-16 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-16` — Manuscript blueprint, venue profiles, and article architecture |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-16/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Turn approved research intent, literature structures, study plans, and publication goals into governed conference/journal skeletons for empirical, theory, and critical work.

A semantic Manuscript AST and versioned blueprint/venue registries own stable section identities, evidence requirements, claim plans and word budgets. Prose editors and publication files are projections or exports, not canonical state.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Generic and verified venue profiles are provenance-aware and never fabricate requirements.
- Empirical, theory, and critical skeletons have appropriate section, contribution, evidence, disclosure, and word-budget structures.
- Researchers can modify and approve the blueprint before prose generation; changes preserve history and impact previews.
- Editable DOCX, Markdown, and LaTeX skeletons retain stable section identities for source-grounded drafting and review.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-16.S01` | Manuscript domain and template governance | Article architecture is versioned, inspectable, and separated from generated prose. | W7 | P0 | CAP-09.S06.T03 |
| `CAP-16.S02` | Empirical article blueprints | Empirical conference and journal skeletons are complete, adaptable, and linked to protocol/result requirements. | W7 | P0 | CAP-16.S01.T03, CAP-15.S05.T02 |
| `CAP-16.S03` | Theory article blueprints | Theory manuscripts receive coherent argument architecture while preserving epistemic plurality. | W7 | P0 | CAP-16.S01.T03, CAP-09.S05.T03 |
| `CAP-16.S04` | Critical scholarship blueprints | Critical manuscripts receive rigorous evidence and argument scaffolding without epistemic flattening. | W7 | P0 | CAP-16.S01.T03, CAP-10.S05.T03 |
| `CAP-16.S05` | Manuscript Blueprint and venue adaptation | Researchers can approve a publication-ready article architecture before prose generation. | W7 | P0 | CAP-16.S02.T03, CAP-16.S03.T03, CAP-16.S04.T03 |
| `CAP-16.S06` | Manuscript blueprint production acceptance | The article-architecture capability is production-ready across research and output types. | W7 | P0 | CAP-16.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before presenting the packet, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. The strongest recommendation is preselected as the resolved default. Reviewers may confirm it, select another listed option with rationale, or request a revised candidate set. Capability approval accepts all current selections at once. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-16-D01` | Canonical manuscript model | A. Use a versioned semantic ManuscriptBlueprint domain model with stable section/block identities<br>B. Store a disposable outline as free-form Markdown | **Use a versioned semantic ManuscriptBlueprint domain model with stable section/block identities** | A canonical model supports staleness, venue overlays, traceable drafting, reviewer comments and multi-format export. | ADR-MANUSCRIPT-DOMAIN |
| `CAP-16-D02` | Identifier strategy | A. Use UUIDv7 identities for manuscript, section, block, claim-plan, figure and table objects<br>B. Use array position and heading text as identity | **Use UUIDv7 identities for manuscript, section, block, claim-plan, figure and table objects** | Stable sortable identifiers survive reordering, export and revision and align with the platform identity model. | None |
| `CAP-16-D03` | Template hierarchy | A. Use governed generic research-type bases plus versioned venue-profile overlays<br>B. Create one hard-coded template per venue | **Use governed generic research-type bases plus versioned venue-profile overlays** | Layered profiles reduce duplication and preserve generic operation when venue rules are unavailable or change. | ADR-MANUSCRIPT-TEMPLATES |
| `CAP-16-D04` | Venue guidance intake | A. Accept official URLs/files and researcher uploads with source, retrieval date, hash, rights and verification status<br>B. Let the model infer venue requirements from its training | **Accept official URLs/files and researcher uploads with source, retrieval date, hash, rights and verification status** | Venue requirements are volatile and must be inspectable rather than fabricated. | None |
| `CAP-16-D05` | Interchange model | A. Keep the internal semantic model canonical and map to JATS 1.4 as an interoperability target<br>B. Use JATS XML directly as the live editor state | **Keep the internal semantic model canonical and map to JATS 1.4 as an interoperability target** | JATS is an excellent exchange standard but is too publisher-oriented to serve as the sole interactive authoring domain. | ADR-MANUSCRIPT-INTERCHANGE |
| `CAP-16-D06` | Template evolution | A. Preview structural diffs and require explicit migration; never silently move authored content<br>B. Automatically reshape existing manuscripts when templates change | **Preview structural diffs and require explicit migration; never silently move authored content** | Researcher-authored content and section meaning must remain under human control. | None |
| `CAP-16-D07` | Empirical blueprint basis | A. Drive empirical patterns from study design, verified conduct/results requirements and method/reporting profiles<br>B. Use a universal IMRaD outline without method-specific requirements | **Drive empirical patterns from study design, verified conduct/results requirements and method/reporting profiles** | Empirical completeness depends on design family, actual conduct and reporting standards. | None |
| `CAP-16-D08` | Theory blueprint model | A. Provide multiple argument/contribution architectures with explicit warrants, mechanisms, boundaries and counterarguments<br>B. Force all theory papers into an empirical-section template | **Provide multiple argument/contribution architectures with explicit warrants, mechanisms, boundaries and counterarguments** | Theory development requires flexible but inspectable argument architecture. | None |
| `CAP-16-D09` | Critical blueprint model | A. Model standpoint, problematization, evidence, reflexivity, counter-readings and normative implications<br>B. Treat critical work as a conventional literature review with a discussion section | **Model standpoint, problematization, evidence, reflexivity, counter-readings and normative implications** | Critical scholarship has distinct evidentiary and reflexive obligations. | None |
| `CAP-16-D10` | Section readiness | A. Give every section typed inputs, required decisions, evidence expectations, completion state and blockers<br>B. Use one manuscript-wide completion percentage | **Give every section typed inputs, required decisions, evidence expectations, completion state and blockers** | Section-level readiness enables safe drafting and selective recalculation. | None |
| `CAP-16-D11` | Length governance | A. Model venue/section word budgets as soft or hard constraints with transparent allocation<br>B. Truncate generated prose after drafting | **Model venue/section word budgets as soft or hard constraints with transparent allocation** | Planning length before prose is safer and more usable than post-hoc deletion. | None |
| `CAP-16-D12` | Claim planning | A. Link planned contribution and section claims to evidence/result/argument requirements before drafting<br>B. Generate claims only while writing prose | **Link planned contribution and section claims to evidence/result/argument requirements before drafting** | Claim plans are the bridge between evidence, blueprint, drafting and review. | None |
| `CAP-16-D13` | Figures, tables and disclosures | A. Represent figures, tables, supplementary items, data/code statements, ethics and AI disclosures as first-class planned objects<br>B. Add these manually after manuscript drafting | **Represent figures, tables, supplementary items, data/code statements, ethics and AI disclosures as first-class planned objects** | Publication artifacts and integrity statements affect section architecture and export readiness. | None |
| `CAP-16-D14` | Contributor roles | A. Capture authorship plus CRediT roles with human confirmation and version history<br>B. Infer final authorship and order from activity logs | **Capture authorship plus CRediT roles with human confirmation and version history** | Contribution transparency is useful, but authorship remains a human governance decision. | None |
| `CAP-16-D15` | Export toolchain | A. Use a replaceable Quarto/Pandoc export service for DOCX, LaTeX, Markdown, JATS, HTML and PDF<br>B. Write custom exporters independently for every format | **Use a replaceable Quarto/Pandoc export service for DOCX, LaTeX, Markdown, JATS, HTML and PDF** | A mature converter ecosystem reduces format divergence while stable manifests preserve traceability. | ADR-MANUSCRIPT-EXPORT |
| `CAP-16-D16` | Drafting gate | A. Prohibit generated manuscript prose until the blueprint and claim plan are approved<br>B. Allow drafting from an incomplete outline | **Prohibit generated manuscript prose until the blueprint and claim plan are approved** | The blueprint is the human-approved architecture and prevents prose from silently determining the argument. | None |
| `CAP-16-D17` | Blueprint experience | A. Use the approved Manuscript Blueprint workspace with outline, requirements, evidence readiness, budgets and impact preview<br>B. Use a chat-only blueprint workflow | **Use the approved Manuscript Blueprint workspace with outline, requirements, evidence readiness, budgets and impact preview** | A persistent visual structure is inspectable and easier to adjudicate than conversational state. | None |
| `CAP-16-D18` | Venue profile freshness | A. Store verification status and expiration/recheck policy and mark dependent blueprints stale when guidance changes<br>B. Treat imported venue instructions as permanently current | **Store verification status and expiration/recheck policy and mark dependent blueprints stale when guidance changes** | Venue instructions change and must participate in dependency propagation. | None |

Every decision is **resolved by the documented recommendation**: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires an explicit rationale. Approval remains a separate authorization gate for the complete capability and all slice plans.

## 5. Cross-slice architecture contract

A semantic Manuscript AST and versioned blueprint/venue registries own stable section identities, evidence requirements, claim plans and word budgets. Prose editors and publication files are projections or exports, not canonical state.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The approved Manuscript Blueprint workspace exposes the selected article pattern, section purpose, contribution logic, evidence closure, venue provenance, word budget and impact of every adaptation before drafting.

Approved reference exposure: `manuscript-blueprint.html`, `study-design.html`, `intent-contract.html`, `new-project.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Unpublished contribution plans remain private by default; venue sources and templates are untrusted; active content is disabled; missing venue requirements are never invented.

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

After one-time approval, `taskctl capability start CAP-16` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [x] All listed decisions have the researched recommendation preselected and accepted; any override must carry rationale.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-16 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `JATS14_PUB` | [JATS Journal Publishing Tag Set 1.4](https://jats.nlm.nih.gov/publishing/1.4/) | NLM / NISO | Publishing-oriented article interchange and validation. |
| `UUIDV7` | [RFC 9562 UUID Version 7](https://www.rfc-editor.org/rfc/rfc9562.html) | IETF | Time-ordered portable identifiers for manuscript, section, result and review entities. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `QUARTO_EXTENSIONS` | [Quarto Custom Formats](https://quarto.org/docs/extensions/formats.html) | Quarto | Versioned venue/output overlays without hard-coding publisher layouts into the domain model. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `EQUATOR` | [EQUATOR Reporting Guidelines Library](https://www.equator-network.org/reporting-guidelines/) | EQUATOR Network | Study-type-specific reporting guidance. |
| `QUARTO_MANUSCRIPTS` | [Quarto Manuscripts](https://quarto.org/docs/manuscripts/) | Quarto | Multi-format scholarly manuscript projects with executable research artifacts. |
| `PROBLEMATIZATION` | [Generating Research Questions Through Problematization](https://journals.aom.org/doi/10.5465/amr.2009.0188) | Academy of Management Review | Assumption-challenging and critical article architecture. |
| `HERMENEUTIC` | [A hermeneutic approach for conducting literature reviews and literature searches](https://aisel.aisnet.org/cais/vol34/iss1/12/) | Communications of the Association for Information Systems | Iterative search-reading-interpretation cycles for theory and critical work. |
| `QUARTO_FORMATS` | [Quarto Formats](https://quarto.org/docs/reference/formats/) | Quarto | Portable HTML, PDF, Word, Markdown, JATS and other publication exports. |
| `QUARTO_CITATIONS` | [Quarto Citations](https://quarto.org/docs/authoring/footnotes-and-citations) | Quarto | Pandoc/CSL citation processing and bibliography inputs. |
| `QUARTO_XREF` | [Quarto Cross References](https://quarto.org/docs/authoring/cross-references) | Quarto | Stable figure, table, equation, section and listing references in generated artifacts. |
| `PANDOC_JATS` | [Pandoc JATS Support](https://pandoc.org/jats.html) | Pandoc | Replaceable conversion to and from JATS through a tested export adapter. |
| `CSL` | [Citation Style Language 1.0.2 Specification](https://docs.citationstyles.org/en/stable/specification.html) | Citation Style Language | Deterministic citation and bibliography rendering. |
| `CREDIT` | [ANSI/NISO Z39.104-2022 CRediT Contributor Roles Taxonomy](https://www.niso.org/publications/z39104-2022-credit) | NISO | Structured contributor-role capture and transparent authorship metadata. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |
| `SLSA` | [SLSA Specification 1.2](https://slsa.dev/spec/v1.2/) | OpenSSF / Linux Foundation | Build provenance and supply-chain assurance. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision review/override | Export from `planning/review-site/CAP-16/index.html` and apply with `planctl`; feedback alone does not approve execution. |
