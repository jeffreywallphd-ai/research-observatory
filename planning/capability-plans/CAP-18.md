---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-18
title: Source-grounded manuscript drafting and publication artifacts
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-18.S01
- CAP-18.S02
- CAP-18.S03
- CAP-18.S04
- CAP-18.S05
- CAP-18.S06
decisions:
- id: CAP-18-D01
  title: Structured editor
  candidates:
  - Use ProseMirror/Tiptap open-source core behind a manuscript-editor port
  - Use a plain textarea or contenteditable HTML as canonical editor
  recommendation: Use ProseMirror/Tiptap open-source core behind a manuscript-editor port
  recommendation_basis: Schema-driven transactions and plugins support stable blocks, citations, comments and controlled transformations.
  selected_option: Use ProseMirror/Tiptap open-source core behind a manuscript-editor port
  status: accepted
  required_adr: ADR-MANUSCRIPT-EDITOR
- id: CAP-18-D02
  title: Canonical draft representation
  candidates:
  - Persist a versioned semantic block tree with stable IDs and separate rendered exports
  - Persist DOCX or HTML as the sole canonical manuscript
  recommendation: Persist a versioned semantic block tree with stable IDs and separate rendered exports
  recommendation_basis: A portable domain model supports selective redrafting, review links and multiple exports.
  selected_option: Persist a versioned semantic block tree with stable IDs and separate rendered exports
  status: accepted
  required_adr: null
- id: CAP-18-D03
  title: Collaboration strategy
  candidates:
  - Keep local revision history canonical and add Yjs as an optional hosted collaboration adapter later
  - Make a CRDT the canonical state for all editions immediately
  recommendation: Keep local revision history canonical and add Yjs as an optional hosted collaboration adapter later
  recommendation_basis: The PC/lab product does not need collaboration complexity, while the adapter preserves a later path.
  selected_option: Keep local revision history canonical and add Yjs as an optional hosted collaboration adapter later
  status: accepted
  required_adr: null
- id: CAP-18-D04
  title: Section workflow
  candidates:
  - Use typed readiness, locks, authorship, review and acceptance states per section
  - Allow any agent to rewrite any section at any time
  recommendation: Use typed readiness, locks, authorship, review and acceptance states per section
  recommendation_basis: Consequence-aware section gates preserve researcher ownership and reproducibility.
  selected_option: Use typed readiness, locks, authorship, review and acceptance states per section
  status: accepted
  required_adr: null
- id: CAP-18-D05
  title: Drafting granularity
  candidates:
  - Generate evidence-linked paragraph or block candidates within an approved section plan
  - Generate the entire manuscript in one prompt
  recommendation: Generate evidence-linked paragraph or block candidates within an approved section plan
  recommendation_basis: Small candidates are easier to verify, revise and attribute and reduce context loss.
  selected_option: Generate evidence-linked paragraph or block candidates within an approved section plan
  status: accepted
  required_adr: null
- id: CAP-18-D06
  title: Evidence packet construction
  candidates:
  - Build deterministic section-specific evidence packets from approved claims, literature, reports and researcher memos
  - Let the model search the full project without an explicit packet
  recommendation: Build deterministic section-specific evidence packets from approved claims, literature, reports and researcher memos
  recommendation_basis: A bounded packet improves reproducibility, rights control and citation completeness.
  selected_option: Build deterministic section-specific evidence packets from approved claims, literature, reports and researcher memos
  status: accepted
  required_adr: null
- id: CAP-18-D07
  title: Claim-to-evidence map
  candidates:
  - Require each generated claim-bearing block to declare supporting, qualifying or interpretive dependencies
  - Attach citations only after prose is accepted
  recommendation: Require each generated claim-bearing block to declare supporting, qualifying or interpretive dependencies
  recommendation_basis: Claim-level lineage enables citation audit and selective stale propagation.
  selected_option: Require each generated claim-bearing block to declare supporting, qualifying or interpretive dependencies
  status: accepted
  required_adr: null
- id: CAP-18-D08
  title: Methods drafting
  candidates:
  - Draft methods from approved design plus verified actual-conduct/deviation records
  - Draft methods from the original proposal only
  recommendation: Draft methods from approved design plus verified actual-conduct/deviation records
  recommendation_basis: Published methods must reflect what was actually done and disclose material deviations.
  selected_option: Draft methods from approved design plus verified actual-conduct/deviation records
  status: accepted
  required_adr: null
- id: CAP-18-D09
  title: Results drafting
  candidates:
  - Generate result prose only from verified result records and approved tables/figures
  - Summarize raw reports directly without verification
  recommendation: Generate result prose only from verified result records and approved tables/figures
  recommendation_basis: This enforces no-result-invention and numerical integrity.
  selected_option: Generate result prose only from verified result records and approved tables/figures
  status: accepted
  required_adr: null
- id: CAP-18-D10
  title: Discussion drafting
  candidates:
  - Integrate verified outcomes with literature, mechanisms, alternatives, boundaries and contribution under null/mixed findings
  - Produce a generic positive-results discussion
  recommendation: Integrate verified outcomes with literature, mechanisms, alternatives, boundaries and contribution under null/mixed findings
  recommendation_basis: A rigorous discussion must reflect actual outcome patterns and rival interpretations.
  selected_option: Integrate verified outcomes with literature, mechanisms, alternatives, boundaries and contribution under null/mixed findings
  status: accepted
  required_adr: null
- id: CAP-18-D11
  title: Theory and critical drafting
  candidates:
  - Draft from approved argument/problematization structures and accepted researcher interpretations
  - Use the empirical drafting template for all manuscript types
  recommendation: Draft from approved argument/problematization structures and accepted researcher interpretations
  recommendation_basis: Theory and critical work require distinct argument, evidence and reflexivity behavior.
  selected_option: Draft from approved argument/problematization structures and accepted researcher interpretations
  status: accepted
  required_adr: null
- id: CAP-18-D12
  title: Author voice and plurality
  candidates:
  - Preserve researcher-authored text, memos, competing interpretations and nonconsensus as first-class state
  - Normalize all prose to a single model voice
  recommendation: Preserve researcher-authored text, memos, competing interpretations and nonconsensus as first-class state
  recommendation_basis: The researcher remains author and interpretive authority.
  selected_option: Preserve researcher-authored text, memos, competing interpretations and nonconsensus as first-class state
  status: accepted
  required_adr: null
- id: CAP-18-D13
  title: Citation processing
  candidates:
  - Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs
  - Embed formatted citation strings directly in prose
  recommendation: Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs
  recommendation_basis: Separating citation identity from rendering enables style changes and audit.
  selected_option: Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs
  status: accepted
  required_adr: null
- id: CAP-18-D14
  title: Publication exports
  candidates:
  - Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests
  - Treat one DOCX export as the only publication artifact
  recommendation: Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests
  recommendation_basis: Multiple venues and reproducibility needs require a tested, replaceable export pipeline.
  selected_option: Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests
  status: accepted
  required_adr: null
- id: CAP-18-D15
  title: Tracked change model
  candidates:
  - Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional
  - Depend on a proprietary alpha tracked-changes API
  recommendation: Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional
  recommendation_basis: The core revision model must remain open, inspectable and portable.
  selected_option: Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional
  status: accepted
  required_adr: null
- id: CAP-18-D16
  title: Authorship and AI disclosure
  candidates:
  - Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly
  - List the model as an author or infer authorship automatically
  recommendation: Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly
  recommendation_basis: Humans remain accountable and current publication guidance requires transparency.
  selected_option: Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly
  status: accepted
  required_adr: null
- id: CAP-18-D17
  title: Textual-overlap audit
  candidates:
  - Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict
  - Assign an automated plagiarism/misconduct label
  recommendation: Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict
  recommendation_basis: Similarity is evidence for review, not proof of intent or misconduct.
  selected_option: Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict
  status: accepted
  required_adr: null
- id: CAP-18-D18
  title: Selective redrafting
  candidates:
  - Invalidate and redraft only affected blocks/sections after evidence, blueprint or decision changes
  - Regenerate the whole manuscript after every change
  recommendation: Invalidate and redraft only affected blocks/sections after evidence, blueprint or decision changes
  recommendation_basis: Dependency-aware selective updates preserve accepted author work and reduce risk.
  selected_option: Invalidate and redraft only affected blocks/sections after evidence, blueprint or decision changes
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-18 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-18` — Source-grounded manuscript drafting and publication artifacts |
| Baseline / supplemental release | 1.3 / 1.3.4 |
| Status | PROPOSED — recommendations resolved; capability approval pending |
| Execution mode | Long-running capability campaign |
| Slice count | 6 |
| Decision count | 18 |
| Review page | planning/review-site/CAP-18/index.html |

Authority order is Vision → accepted ADRs → Systems Design → authoritative backlog → approved capability packet → approved slice plans → approved UI reference for user-facing changes → automation rules and code/tests. The backlog remains authoritative for IDs, dependencies and status. This packet owns the architectural and product selections needed to execute the capability without repeated approval stops.

## 1. Capability outcome and production-ready exit

**Objective.** Use approved article blueprints, literature evidence, verified technical reports/results, and researcher-authored content to draft and export empirical, theory, and critical conference/journal articles.

A transactional semantic manuscript model, frozen section evidence packets, schema-constrained candidate blocks, claim-evidence closure, mode-specific drafting and standards-based publication adapters separate canonical authorship state from model proposals and file formats.

The capability is not complete merely because its atomic tasks are checked off. Production readiness requires the following capability exits:

- Paragraphs and claims retain section purpose, evidence/citation support, generation provenance, author decisions, and stale dependencies.
- Empirical methods/results distinguish planned from actual conduct and never invent study details or findings.
- Theory and critical drafts preserve conceptual/interpretive plurality and author voice rather than imposing a single article logic.
- Researchers can edit, compare, approve, audit, disclose, and export complete manuscripts and reproducibility artifacts.

The independent capability reviewer must trace each exit to immutable task, slice and end-to-end evidence; verify failure, denial, cancellation, restart, migration, security, accessibility and relevant platform behavior; and confirm that no concealed TODO or deferred production blocker remains.

## 2. Slice map and end-to-end dependency logic

| Slice | Title | Outcome | Wave | Priority | Depends on |
|---|---|---|---|---|---|
| `CAP-18.S01` | Manuscript project and section workflow | Drafts are durable, versioned scholarly objects with human ownership and selective recalculation. | W8 | P0 | CAP-16.S05.T03 |
| `CAP-18.S02` | Evidence-aware drafting engine | Generated prose is section-specific, source-grounded, inspectable, and unable to conceal unsupported content. | W8 | P0 | CAP-18.S01.T03, CAP-17.S06.T03 |
| `CAP-18.S03` | Empirical manuscript drafting | The platform can draft a complete empirical article from verified study and literature evidence. | W8 | P0 | CAP-18.S02.T03, CAP-17.S05.T03 |
| `CAP-18.S04` | Theory and critical manuscript drafting | The platform can develop full theory and critical article drafts while preserving epistemic and authorial plurality. | W8 | P0 | CAP-18.S02.T03, CAP-16.S03.T03, CAP-16.S04.T03 |
| `CAP-18.S05` | Manuscript Studio and publication exports | Researchers can review, edit, approve, and export complete source-grounded manuscripts. | W8 | P0 | CAP-18.S03.T03, CAP-18.S04.T03 |
| `CAP-18.S06` | Source-grounded manuscript production acceptance | Manuscript drafting is accurate, auditable, editable, and production-ready across article types. | W8 | P0 | CAP-18.S05.T03 |

Slices execute in backlog dependency order. A later slice may introduce an adapter or test fixture for an earlier contract, but it may not redefine an approved cross-slice decision. Each slice concludes with integration and independent review, after which the same campaign proceeds directly to the next ready slice. The capability pauses only for demonstrated infeasibility, a missing external prerequisite, unavailable required hardware, a genuinely new consequential human decision, a higher-authority conflict, or an approved design-reference gate.

## 3. Decision-making protocol

Before presenting the packet, the planning agent must verify every candidate against the Vision, architecture, other capability contracts, current official standards, primary research where appropriate, existing code and representative environments. The strongest recommendation is preselected as the resolved default. Reviewers may confirm it, select another listed option with rationale, or request a revised candidate set. Capability approval accepts all current selections at once. Once approved, routine implementation, debugging, testing and slice transitions do not reopen the decision.

A decision may be reopened only when implementation evidence demonstrates infeasibility or material new evidence changes the risk/architecture boundary. The agent must document the failed assumption, strongest feasible alternatives, migration effect and recommendation on the static review page, obtain focused approval, and resume the same campaign.

## 4. Decision register

| ID | Decision | Candidates | Recommendation | Basis | ADR |
|---|---|---|---|---|---|
| `CAP-18-D01` | Structured editor | A. Use ProseMirror/Tiptap open-source core behind a manuscript-editor port<br>B. Use a plain textarea or contenteditable HTML as canonical editor | **Use ProseMirror/Tiptap open-source core behind a manuscript-editor port** | Schema-driven transactions and plugins support stable blocks, citations, comments and controlled transformations. | ADR-MANUSCRIPT-EDITOR |
| `CAP-18-D02` | Canonical draft representation | A. Persist a versioned semantic block tree with stable IDs and separate rendered exports<br>B. Persist DOCX or HTML as the sole canonical manuscript | **Persist a versioned semantic block tree with stable IDs and separate rendered exports** | A portable domain model supports selective redrafting, review links and multiple exports. | None |
| `CAP-18-D03` | Collaboration strategy | A. Keep local revision history canonical and add Yjs as an optional hosted collaboration adapter later<br>B. Make a CRDT the canonical state for all editions immediately | **Keep local revision history canonical and add Yjs as an optional hosted collaboration adapter later** | The PC/lab product does not need collaboration complexity, while the adapter preserves a later path. | None |
| `CAP-18-D04` | Section workflow | A. Use typed readiness, locks, authorship, review and acceptance states per section<br>B. Allow any agent to rewrite any section at any time | **Use typed readiness, locks, authorship, review and acceptance states per section** | Consequence-aware section gates preserve researcher ownership and reproducibility. | None |
| `CAP-18-D05` | Drafting granularity | A. Generate evidence-linked paragraph or block candidates within an approved section plan<br>B. Generate the entire manuscript in one prompt | **Generate evidence-linked paragraph or block candidates within an approved section plan** | Small candidates are easier to verify, revise and attribute and reduce context loss. | None |
| `CAP-18-D06` | Evidence packet construction | A. Build deterministic section-specific evidence packets from approved claims, literature, reports and researcher memos<br>B. Let the model search the full project without an explicit packet | **Build deterministic section-specific evidence packets from approved claims, literature, reports and researcher memos** | A bounded packet improves reproducibility, rights control and citation completeness. | None |
| `CAP-18-D07` | Claim-to-evidence map | A. Require each generated claim-bearing block to declare supporting, qualifying or interpretive dependencies<br>B. Attach citations only after prose is accepted | **Require each generated claim-bearing block to declare supporting, qualifying or interpretive dependencies** | Claim-level lineage enables citation audit and selective stale propagation. | None |
| `CAP-18-D08` | Methods drafting | A. Draft methods from approved design plus verified actual-conduct/deviation records<br>B. Draft methods from the original proposal only | **Draft methods from approved design plus verified actual-conduct/deviation records** | Published methods must reflect what was actually done and disclose material deviations. | None |
| `CAP-18-D09` | Results drafting | A. Generate result prose only from verified result records and approved tables/figures<br>B. Summarize raw reports directly without verification | **Generate result prose only from verified result records and approved tables/figures** | This enforces no-result-invention and numerical integrity. | None |
| `CAP-18-D10` | Discussion drafting | A. Integrate verified outcomes with literature, mechanisms, alternatives, boundaries and contribution under null/mixed findings<br>B. Produce a generic positive-results discussion | **Integrate verified outcomes with literature, mechanisms, alternatives, boundaries and contribution under null/mixed findings** | A rigorous discussion must reflect actual outcome patterns and rival interpretations. | None |
| `CAP-18-D11` | Theory and critical drafting | A. Draft from approved argument/problematization structures and accepted researcher interpretations<br>B. Use the empirical drafting template for all manuscript types | **Draft from approved argument/problematization structures and accepted researcher interpretations** | Theory and critical work require distinct argument, evidence and reflexivity behavior. | None |
| `CAP-18-D12` | Author voice and plurality | A. Preserve researcher-authored text, memos, competing interpretations and nonconsensus as first-class state<br>B. Normalize all prose to a single model voice | **Preserve researcher-authored text, memos, competing interpretations and nonconsensus as first-class state** | The researcher remains author and interpretive authority. | None |
| `CAP-18-D13` | Citation processing | A. Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs<br>B. Embed formatted citation strings directly in prose | **Use CSL/citeproc through the Quarto/Pandoc export adapter with canonical scholarly IDs** | Separating citation identity from rendering enables style changes and audit. | None |
| `CAP-18-D14` | Publication exports | A. Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests<br>B. Treat one DOCX export as the only publication artifact | **Render through Quarto/Pandoc adapters to DOCX, LaTeX, JATS, Markdown, HTML and PDF with manifests** | Multiple venues and reproducibility needs require a tested, replaceable export pipeline. | None |
| `CAP-18-D15` | Tracked change model | A. Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional<br>B. Depend on a proprietary alpha tracked-changes API | **Implement internal suggestion/change-set records over stable block IDs; keep commercial tracked-change services optional** | The core revision model must remain open, inspectable and portable. | None |
| `CAP-18-D16` | Authorship and AI disclosure | A. Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly<br>B. List the model as an author or infer authorship automatically | **Capture human authors, CRediT roles, AI-use disclosure, approvals and responsibility explicitly** | Humans remain accountable and current publication guidance requires transparency. | None |
| `CAP-18-D17` | Textual-overlap audit | A. Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict<br>B. Assign an automated plagiarism/misconduct label | **Provide source-linked textual-overlap risk findings for human review, not a plagiarism verdict** | Similarity is evidence for review, not proof of intent or misconduct. | None |
| `CAP-18-D18` | Selective redrafting | A. Invalidate and redraft only affected blocks/sections after evidence, blueprint or decision changes<br>B. Regenerate the whole manuscript after every change | **Invalidate and redraft only affected blocks/sections after evidence, blueprint or decision changes** | Dependency-aware selective updates preserve accepted author work and reduce risk. | None |

Every decision is **resolved by the documented recommendation**: `selected_option` equals `recommendation`, status is `accepted`, and `decision_completion` is `complete`. Reviewers may override a selection before capability approval, but every non-recommended selection requires an explicit rationale. Approval remains a separate authorization gate for the complete capability and all slice plans.

## 5. Cross-slice architecture contract

A transactional semantic manuscript model, frozen section evidence packets, schema-constrained candidate blocks, claim-evidence closure, mode-specific drafting and standards-based publication adapters separate canonical authorship state from model proposals and file formats.

Cross-slice invariants:

- Canonical scholarly records, evidence, accepted human decisions, rights state and provenance remain authoritative. Indexes, projections, caches, generated recommendations and operational dashboards are replaceable derivatives.
- Local, institutional and cloud profiles use the same domain identifiers, status semantics, evidence/provenance contracts and workflow meanings; infrastructure adapters may differ.
- Every long operation has stable identity, inputs/manifests, progress, cancellation, retry/checkpoint/restart and evidence records.
- Unknown, unavailable, denied, not reported, inferred, disputed, stale and failed remain distinct states.
- Provider, platform, database, cluster and UI framework objects do not escape their adapters into portable domain contracts.
- CAP-16–CAP-19 consume stable study/evidence/manuscript interfaces rather than internal storage tables or deployment SDK types.

## 6. Experience and workflow contract

The approved Manuscript Studio presents section workflow, source/evidence drawers, explicit proposals and diffs, stale dependencies, comments, citations, tables/figures, authorship/disclosure and validated exports.

Approved reference exposure: `manuscript-studio.html`, `manuscript-blueprint.html`, `technical-reports.html`, `synthesis-studio.html`, `audit-lineage.html`

Researcher-facing behavior must preserve the selected project objective, numbered primary stages, previous/next actions, expected output, supporting-tool relationship, inspect–contest–adjudicate interaction and visible provenance. Intentional UI change follows reference first: update the style guide, workflow/page contracts and HTML mockups; run validators; obtain explicit approval and a new reference ID; then implement. A defect restoration to the approved reference does not need a new design decision.

## 7. Security, privacy, rights and research-integrity decisions

Model output is untrusted candidate state; accepted text is never overwritten silently; private evidence obeys provider/egress policy; citations and results resolve only through canonical project records.

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

After one-time approval, `taskctl capability start CAP-18` selects the first dependency-ready slice and continues through the capability. The agent does not ask again about settled options. Each task produces machine-linked evidence; each slice receives independent integration review; the campaign immediately advances when the next slice is ready. If a classified blocker occurs, the agent preserves work, records the exact affected decision/assumption and provides the static review URL rather than creating an unstructured chat approval.

## 10. Plan and approval checklist

- [ ] Every slice has exactly one structurally valid plan using the governed template.
- [x] All listed decisions have the researched recommendation preselected and accepted; any override must carry rationale.
- [ ] Required ADRs and design-reference changes are accepted.
- [ ] Dependencies, credentials, source/model licenses, hardware and fixtures are available or have approved deterministic substitutes.
- [ ] Capability and slice plans are approved by the same reviewer at the same immutable commit.
- [ ] `python tools/planctl.py ready CAP-18 --require-approved` passes.
- [ ] Static review site matches plan hashes and provides the approved decision record.

## 11. Research and technical basis

| Key | Source | Publisher | Planning use |
|---|---|---|---|
| `PROSEMIRROR` | [ProseMirror Guide](https://prosemirror.net/docs/guide/) | ProseMirror | Schema-driven editor state, transactions, plugins and stable structured-document behavior. |
| `UUIDV7` | [RFC 9562 UUID Version 7](https://www.rfc-editor.org/rfc/rfc9562.html) | IETF | Time-ordered portable identifiers for manuscript, section, result and review entities. |
| `YJS_OFFLINE` | [Yjs Offline Editing](https://docs.yjs.dev/getting-started/allowing-offline-editing) | Yjs | Optional collaboration adapter and offline synchronization, not canonical local manuscript state. |
| `PROV_O` | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) | W3C | Interoperable research provenance. |
| `WCAG22` | [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) | W3C | Accessibility conformance and testable success criteria. |
| `OPEN_SCHOLAR` | [Synthesizing scientific literature with retrieval-augmented language models](https://www.nature.com/articles/s41586-025-10072-4) | Nature | Citation-grounded scientific synthesis and retrieval evaluation. |
| `PAPERQA2` | [Language agents achieve superhuman synthesis of scientific knowledge](https://arxiv.org/abs/2409.13740) | arXiv / FutureHouse | Evidence-grounded retrieval, synthesis and contradiction discovery. |
| `JSON_SCHEMA` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | JSON Schema | Portable machine-readable study protocols. |
| `OTEL_GENAI` | [OpenTelemetry Generative AI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | OpenTelemetry | Privacy-aware operational observability for model-assisted drafting and review. |
| `ICMJE_AI_AUTHORS` | [ICMJE Use of AI by Authors](https://www.icmje.org/recommendations/browse/artificial-intelligence/ai-use-by-authors.html) | ICMJE | Human authorship responsibility, disclosure and source/plagiarism controls. |
| `APA_JARS_QUANT` | [Journal Article Reporting Standards for Quantitative Research](https://doi.org/10.1037/amp0000191) | American Psychological Association | Quantitative design and reporting completeness. |
| `APA_JARS_QUAL` | [Journal Article Reporting Standards for Qualitative, Primary Qualitative Meta-Analytic, and Mixed Methods Research](https://doi.org/10.1037/amp0000151) | American Psychological Association | Qualitative and mixed-method design/reporting completeness. |
| `EQUATOR` | [EQUATOR Reporting Guidelines Library](https://www.equator-network.org/reporting-guidelines/) | EQUATOR Network | Study-type-specific reporting guidance. |
| `PROBLEMATIZATION` | [Generating Research Questions Through Problematization](https://journals.aom.org/doi/10.5465/amr.2009.0188) | Academy of Management Review | Assumption-challenging and critical article architecture. |
| `HERMENEUTIC` | [A hermeneutic approach for conducting literature reviews and literature searches](https://aisel.aisnet.org/cais/vol34/iss1/12/) | Communications of the Association for Information Systems | Iterative search-reading-interpretation cycles for theory and critical work. |
| `QUARTO_MANUSCRIPTS` | [Quarto Manuscripts](https://quarto.org/docs/manuscripts/) | Quarto | Multi-format scholarly manuscript projects with executable research artifacts. |
| `QUARTO_FORMATS` | [Quarto Formats](https://quarto.org/docs/reference/formats/) | Quarto | Portable HTML, PDF, Word, Markdown, JATS and other publication exports. |
| `QUARTO_CITATIONS` | [Quarto Citations](https://quarto.org/docs/authoring/footnotes-and-citations) | Quarto | Pandoc/CSL citation processing and bibliography inputs. |
| `QUARTO_XREF` | [Quarto Cross References](https://quarto.org/docs/authoring/cross-references) | Quarto | Stable figure, table, equation, section and listing references in generated artifacts. |
| `CSL` | [Citation Style Language 1.0.2 Specification](https://docs.citationstyles.org/en/stable/specification.html) | Citation Style Language | Deterministic citation and bibliography rendering. |
| `CREDIT` | [ANSI/NISO Z39.104-2022 CRediT Contributor Roles Taxonomy](https://www.niso.org/publications/z39104-2022-credit) | NISO | Structured contributor-role capture and transparent authorship metadata. |
| `JATS14` | [JATS Article Authoring Tag Set 1.4](https://jats.nlm.nih.gov/articleauthoring/1.4/) | NLM / NISO | Current article-authoring XML interoperability, validation schemas and versioned scholarly structure. |
| `PANDOC_JATS` | [Pandoc JATS Support](https://pandoc.org/jats.html) | Pandoc | Replaceable conversion to and from JATS through a tested export adapter. |
| `ICMJE_AI` | [ICMJE Use of Artificial Intelligence in Publishing](https://www.icmje.org/recommendations/browse/artificial-intelligence/) | ICMJE | Human accountability, confidentiality and transparent disclosure for AI-assisted publication work. |

Official documentation and standards define platform behavior; primary scholarly sources and reporting standards define research-method requirements. Versions, licenses, provider contracts and current target support must be rechecked at capability approval and pinned in accepted ADRs/manifests. A cited source supports a recommendation but does not replace project-specific benchmarks, threat analysis, institutional policy or expert methods review.

## 12. Approval record

| Field | Value |
|---|---|
| Decision completion | Complete — resolved by best-in-class recommendations |
| Packet approval | Pending |
| Approved by | — |
| Approved at | — |
| Approved commit | — |
| Decision review/override | Export from `planning/review-site/CAP-18/index.html` and apply with `planctl`; feedback alone does not approve execution. |
