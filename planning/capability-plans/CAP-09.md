---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-09
title: Scholarly graph, comparison sets, synthesis, and reproducibility
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-09.S01
- CAP-09.S02
- CAP-09.S03
- CAP-09.S04
- CAP-09.S05
- CAP-09.S06
decisions:
- id: CAP-09-D01
  title: Graph authority
  candidates:
  - Relational assertions/evidence remain authoritative; graph stores and in-memory structures are versioned rebuildable projections
  - Make Neo4j or a client graph the sole source of truth
  recommendation: Relational assertions/evidence remain authoritative; graph stores and in-memory structures are versioned rebuildable projections
  recommendation_basis: The domain requires transactions, disputes and provenance that must survive graph-engine replacement and local/server differences.
  selected_option: Relational assertions/evidence remain authoritative; graph stores and in-memory structures are versioned rebuildable projections
  status: accepted
  required_adr: null
- id: CAP-09-D02
  title: Local analytical projection
  candidates:
  - rustworkx for bounded in-memory analysis; Cytoscape.js for interactive visualization
  - Use the UI graph as the analysis engine; ship a graph server in the first desktop release
  recommendation: rustworkx for bounded in-memory analysis; Cytoscape.js for interactive visualization
  recommendation_basis: This combination is cross-platform, performant and replaceable while avoiding a second mandatory local database.
  selected_option: rustworkx for bounded in-memory analysis; Cytoscape.js for interactive visualization
  status: accepted
  required_adr: null
- id: CAP-09-D03
  title: Comparability before contradiction
  candidates:
  - Hard eligibility dimensions and explainable similarity precede stance/NLI signals
  - Run contradiction classification across any semantically related claims
  recommendation: Hard eligibility dimensions and explainable similarity precede stance/NLI signals
  recommendation_basis: Differences in construct, measure, population, method or period must not be mislabeled as substantive contradiction.
  selected_option: Hard eligibility dimensions and explainable similarity precede stance/NLI signals
  status: accepted
  required_adr: null
- id: CAP-09-D04
  title: Synthesis contract
  candidates:
  - Evidence packet and claim plan precede prose; each material sentence resolves to accepted evidence and preserves dissent
  - Generate a long narrative directly from top retrieved papers
  recommendation: Evidence packet and claim plan precede prose; each material sentence resolves to accepted evidence and preserves dissent
  recommendation_basis: The platform’s evidence-before-prose principle requires auditable claim-level support and citation completeness.
  selected_option: Evidence packet and claim plan precede prose; each material sentence resolves to accepted evidence and preserves dissent
  status: accepted
  required_adr: null
- id: CAP-09-D05
  title: Reproducibility export
  candidates:
  - RO-Crate metadata plus BagIt-compatible checksum payload and CSL-formatted references
  - One opaque ZIP or application-only backup
  recommendation: RO-Crate metadata plus BagIt-compatible checksum payload and CSL-formatted references
  recommendation_basis: Open package standards support human inspection, integrity validation and future tool interoperability.
  selected_option: RO-Crate metadata plus BagIt-compatible checksum payload and CSL-formatted references
  status: accepted
  required_adr: null
- id: CAP-09-D06
  title: Authority boundary
  candidates:
  - Canonical domain records, evidence revisions and adjudications remain authoritative; graph nodes and edges are versioned derivative assertions with complete provenance.
  - Store graph edges as the only copy of scholarly relationships.
  recommendation: Canonical domain records, evidence revisions and adjudications remain authoritative; graph nodes and edges are versioned derivative assertions with complete provenance.
  recommendation_basis: The graph can be dropped, repaired or replaced without losing scholarly decisions, rights or evidence history.
  selected_option: Canonical domain records, evidence revisions and adjudications remain authoritative; graph nodes and edges are versioned derivative assertions with complete provenance.
  status: accepted
  required_adr: null
- id: CAP-09-D07
  title: Local implementation
  candidates:
  - Persist projection tables and adjacency indexes in protected SQLite; load bounded analytical subgraphs into rustworkx through a stable GraphQuery port.
  - Require an external graph server or keep all graph state only in memory.
  recommendation: Persist projection tables and adjacency indexes in protected SQLite; load bounded analytical subgraphs into rustworkx through a stable GraphQuery port.
  recommendation_basis: SQLite fits the local protected-store architecture while rustworkx supplies portable algorithms without creating another durable authority.
  selected_option: Persist projection tables and adjacency indexes in protected SQLite; load bounded analytical subgraphs into rustworkx through a stable GraphQuery port.
  status: accepted
  required_adr: null
- id: CAP-09-D08
  title: Graph semantics
  candidates:
  - Represent relation assertion identity separately from edge projection; include direction, status, validity interval, confidence components, evidence anchors, inference method and dispute/supersession links.
  - Use untyped source-target-label triples.
  recommendation: Represent relation assertion identity separately from edge projection; include direction, status, validity interval, confidence components, evidence anchors, inference method and dispute/supersession links.
  recommendation_basis: Scholarly relations are contestable and temporally/version dependent; a rich assertion contract is required for audit and recalculation.
  selected_option: Represent relation assertion identity separately from edge projection; include direction, status, validity interval, confidence components, evidence anchors, inference method and dispute/supersession links.
  status: accepted
  required_adr: null
- id: CAP-09-D09
  title: Entity-linking policy
  candidates:
  - Use deterministic identifiers/aliases and candidate retrieval first, followed by model-assisted ranking; retain mention text, source context, candidate list and human decision.
  - Let an LLM emit a canonical entity name without candidates or evidence.
  recommendation: Use deterministic identifiers/aliases and candidate retrieval first, followed by model-assisted ranking; retain mention text, source context, candidate list and human decision.
  recommendation_basis: Entity linking is consequential and requires reversible, inspectable resolution rather than fluent normalization.
  selected_option: Use deterministic identifiers/aliases and candidate retrieval first, followed by model-assisted ranking; retain mention text, source context, candidate list and human decision.
  status: accepted
  required_adr: null
- id: CAP-09-D10
  title: Construct identity
  candidates:
  - Allow related, broader/narrower, variant and disputed-equivalence relations; merge only through an adjudicated command.
  - Case-folded string matching or embedding threshold automatically merges constructs.
  recommendation: Allow related, broader/narrower, variant and disputed-equivalence relations; merge only through an adjudicated command.
  recommendation_basis: Construct drift and operational variation are analytical material, not noise to erase.
  selected_option: Allow related, broader/narrower, variant and disputed-equivalence relations; merge only through an adjudicated command.
  status: accepted
  required_adr: null
- id: CAP-09-D11
  title: Argument representation
  candidates:
  - Extract claim, evidence, warrant, qualification, rebuttal and relation candidates with exact anchors and candidate status; use schema packs by mode/domain.
  - One universal support/contradiction classifier over abstracts.
  recommendation: Extract claim, evidence, warrant, qualification, rebuttal and relation candidates with exact anchors and candidate status; use schema packs by mode/domain.
  recommendation_basis: Argument roles and relation meanings vary; source-grounded typed candidates support later comparison and synthesis.
  selected_option: Extract claim, evidence, warrant, qualification, rebuttal and relation candidates with exact anchors and candidate status; use schema packs by mode/domain.
  status: accepted
  required_adr: null
- id: CAP-09-D12
  title: Two-stage comparability
  candidates:
  - Apply explicit incompatibility gates first, then score remaining pairs on construct definition, unit/level, population, context, time, method, measure, outcome and intervention/exposure.
  - Cluster only by embedding similarity or citation graph.
  recommendation: Apply explicit incompatibility gates first, then score remaining pairs on construct definition, unit/level, population, context, time, method, measure, outcome and intervention/exposure.
  recommendation_basis: Hard semantic/methodological mismatches must be visible before softer similarity signals.
  selected_option: Apply explicit incompatibility gates first, then score remaining pairs on construct definition, unit/level, population, context, time, method, measure, outcome and intervention/exposure.
  status: accepted
  required_adr: null
- id: CAP-09-D13
  title: Mode packs
  candidates:
  - Systematic, theory, technical, critical and other modes version their dimensions, required fields, missingness treatment and thresholds.
  - Global weights hidden in the model.
  recommendation: Systematic, theory, technical, critical and other modes version their dimensions, required fields, missingness treatment and thresholds.
  recommendation_basis: What counts as comparable depends on the intended scholarly inference.
  selected_option: Systematic, theory, technical, critical and other modes version their dimensions, required fields, missingness treatment and thresholds.
  status: accepted
  required_adr: null
- id: CAP-09-D14
  title: Relation detection
  candidates:
  - Generate typed candidates from normalized claims and evidence with explanatory contrasting dimensions; require human confirmation for promoted contradiction/boundary assertions.
  - Promote model labels directly to graph edges.
  recommendation: Generate typed candidates from normalized claims and evidence with explanatory contrasting dimensions; require human confirmation for promoted contradiction/boundary assertions.
  recommendation_basis: NLI/stance is a signal; context and measurement differences can explain apparent conflict.
  selected_option: Generate typed candidates from normalized claims and evidence with explanatory contrasting dimensions; require human confirmation for promoted contradiction/boundary assertions.
  status: accepted
  required_adr: null
- id: CAP-09-D15
  title: Visualization engine
  candidates:
  - Use Cytoscape.js behind an application graph-view adapter, with server/core-prepared authorized subgraphs and versioned layout presets.
  - Custom canvas engine or direct database-to-browser graph feed.
  recommendation: Use Cytoscape.js behind an application graph-view adapter, with server/core-prepared authorized subgraphs and versioned layout presets.
  recommendation_basis: Cytoscape.js provides mature interaction/layout/serialization while replaceability and domain policy stay outside the library.
  selected_option: Use Cytoscape.js behind an application graph-view adapter, with server/core-prepared authorized subgraphs and versioned layout presets.
  status: accepted
  required_adr: null
- id: CAP-09-D16
  title: Progressive disclosure
  candidates:
  - Start from a selected entity/claim and bounded neighborhood; expand explicitly by relation type/depth and summarize omitted nodes.
  - Auto-render all connected nodes.
  recommendation: Start from a selected entity/claim and bounded neighborhood; expand explicitly by relation type/depth and summarize omitted nodes.
  recommendation_basis: Research graphs become unusable and inaccessible when scale is uncontrolled.
  selected_option: Start from a selected entity/claim and bounded neighborhood; expand explicitly by relation type/depth and summarize omitted nodes.
  status: accepted
  required_adr: null
- id: CAP-09-D17
  title: Interpretation boundary
  candidates:
  - Visual encodings indicate relation/status/provenance only; every inference opens evidence and a textual explanation, with no causal implication from layout.
  - Let force-directed distance imply conceptual importance.
  recommendation: Visual encodings indicate relation/status/provenance only; every inference opens evidence and a textual explanation, with no causal implication from layout.
  recommendation_basis: Layout is a navigation aid, not scholarly evidence.
  selected_option: Visual encodings indicate relation/status/provenance only; every inference opens evidence and a textual explanation, with no causal implication from layout.
  status: accepted
  required_adr: null
- id: CAP-09-D18
  title: Plan before prose
  candidates:
  - Require a versioned synthesis plan of intended claims, comparison sets, evidence requirements, dissent/uncertainty handling and output structure.
  - Let the LLM decide claims while drafting.
  recommendation: Require a versioned synthesis plan of intended claims, comparison sets, evidence requirements, dissent/uncertainty handling and output structure.
  recommendation_basis: An inspectable plan prevents prose fluency from silently selecting evidence or argument.
  selected_option: Require a versioned synthesis plan of intended claims, comparison sets, evidence requirements, dissent/uncertainty handling and output structure.
  status: accepted
  required_adr: null
- id: CAP-09-D19
  title: Evidence packet
  candidates:
  - Retrieve accepted evidence records/passages for each planned claim with rights, source quality, status and counterevidence; freeze a packet snapshot before generation.
  - Send full documents or search snippets ad hoc.
  recommendation: Retrieve accepted evidence records/passages for each planned claim with rights, source quality, status and counterevidence; freeze a packet snapshot before generation.
  recommendation_basis: Bounded packets improve traceability, cost control and reproducibility.
  selected_option: Retrieve accepted evidence records/passages for each planned claim with rights, source quality, status and counterevidence; freeze a packet snapshot before generation.
  status: accepted
  required_adr: null
- id: CAP-09-D20
  title: Independent audit
  candidates:
  - Run a separate citation auditor over final sentences/claims and cited passages for support, completeness, scope and mismatch; block high-severity failures.
  - Ask the drafting agent whether its citations are correct.
  recommendation: Run a separate citation auditor over final sentences/claims and cited passages for support, completeness, scope and mismatch; block high-severity failures.
  recommendation_basis: Generator/auditor separation is required for epistemic accountability.
  selected_option: Run a separate citation auditor over final sentences/claims and cited passages for support, completeness, scope and mismatch; block high-severity failures.
  status: accepted
  required_adr: null
- id: CAP-09-D21
  title: Package model
  candidates:
  - Use RO-Crate JSON-LD to describe entities/activities/files and BagIt-compatible payload manifests/checksums for transfer integrity.
  - Custom ZIP with a README only.
  recommendation: Use RO-Crate JSON-LD to describe entities/activities/files and BagIt-compatible payload manifests/checksums for transfer integrity.
  recommendation_basis: The combination supplies portable research-object semantics and deterministic payload validation.
  selected_option: Use RO-Crate JSON-LD to describe entities/activities/files and BagIt-compatible payload manifests/checksums for transfer integrity.
  status: accepted
  required_adr: null
- id: CAP-09-D22
  title: Snapshot boundary
  candidates:
  - Freeze canonical revision/event high-water marks, corpus membership, rights decisions, schemas, indexes/models/prompt manifests and approved outputs; derived indexes are referenced or rebuilt, not silently copied as authority.
  - Export whatever is current as each file is written.
  recommendation: Freeze canonical revision/event high-water marks, corpus membership, rights decisions, schemas, indexes/models/prompt manifests and approved outputs; derived indexes are referenced or rebuilt, not silently copied as authority.
  recommendation_basis: A single transaction-like snapshot boundary is necessary for coherent reproduction.
  selected_option: Freeze canonical revision/event high-water marks, corpus membership, rights decisions, schemas, indexes/models/prompt manifests and approved outputs; derived indexes are referenced or rebuilt, not silently copied as authority.
  status: accepted
  required_adr: null
- id: CAP-09-D23
  title: Rights filtering
  candidates:
  - Compute an export policy per file/field/passage; replace restricted content with metadata/checksum/locator when redistribution is not permitted.
  - Include all local project content because the recipient may have access.
  recommendation: Compute an export policy per file/field/passage; replace restricted content with metadata/checksum/locator when redistribution is not permitted.
  recommendation_basis: Access on the source machine does not grant redistribution rights.
  selected_option: Compute an export policy per file/field/passage; replace restricted content with metadata/checksum/locator when redistribution is not permitted.
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-09 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-09` — Scholarly graph, comparison sets, synthesis, and reproducibility |
| Objective | Connect bibliographic structure to claims, constructs, methods, contexts, assumptions, evidence, and decisions; then produce source-grounded synthesis and reproducibility artifacts. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-09.S01`, `CAP-09.S02`, `CAP-09.S03`, `CAP-09.S04`, `CAP-09.S05`, `CAP-09.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Connect bibliographic structure to claims, constructs, methods, contexts, assumptions, evidence, and decisions; then produce source-grounded synthesis and reproducibility artifacts.**

Production-ready exit criteria:

- Typed graph projections are derived from canonical records and every material edge is traceable and contestable.
- Contradiction analysis begins with explicit comparability rather than naive claim similarity.
- Synthesis and exports preserve supporting evidence, disagreement, uncertainty, rights, and exact project state.
- Synthesis and graph outputs can become evidence packets for study design, manuscript blueprints, drafting, and review without losing source lineage.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-09.S01` | Local graph domain and replaceable graph storage | The system can query scholarly relations locally without binding the domain to a particular graph database. | `CAP-08.S03.T02`, `CAP-03.S05.T02` |
| `CAP-09.S02` | Claim, theory, construct, method, and context relations | Internal paper semantics become a multi-granular argument representation with preserved wording and evidence. | `CAP-09.S01.T03`, `CAP-08.S06.T02` |
| `CAP-09.S03` | Comparability sets and contradiction candidates | Studies are normalized into defensible comparison sets before support, contradiction, or boundary inference. | `CAP-09.S02.T03`, `CAP-08.S05.T03` |
| `CAP-09.S04` | Graph, theory, construct, and lineage workspaces | Complex field structures are navigable through task-specific views rather than one undifferentiated network. | `CAP-09.S01.T03`, `CAP-06.S05.T01` |
| `CAP-09.S05` | Evidence-grounded synthesis and citation audit | Narrative and tabular synthesis is downstream of accepted evidence and preserves disagreement and uncertainty. | `CAP-09.S03.T03`, `CAP-08.S06.T02` |
| `CAP-09.S06` | Reproducibility packages and scholarly exports | A project can produce a rights-aware record of corpus, searches, schemas, models, decisions, analysis, and outputs. | `CAP-09.S05.T03`, `CAP-04.S04.T02` |

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
| `CAP-09-D01` | **Graph authority** | Relational assertions/evidence remain authoritative; graph stores and in-memory structures are versioned rebuildable projections | Make Neo4j or a client graph the sole source of truth | The domain requires transactions, disputes and provenance that must survive graph-engine replacement and local/server differences. | [rustworkx Documentation](https://www.rustworkx.org/dev/) |
| `CAP-09-D02` | **Local analytical projection** | rustworkx for bounded in-memory analysis; Cytoscape.js for interactive visualization | Use the UI graph as the analysis engine; ship a graph server in the first desktop release | This combination is cross-platform, performant and replaceable while avoiding a second mandatory local database. | [Cytoscape.js Documentation](https://js.cytoscape.org/) |
| `CAP-09-D03` | **Comparability before contradiction** | Hard eligibility dimensions and explainable similarity precede stance/NLI signals | Run contradiction classification across any semantically related claims | Differences in construct, measure, population, method or period must not be mislabeled as substantive contradiction. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-09-D04` | **Synthesis contract** | Evidence packet and claim plan precede prose; each material sentence resolves to accepted evidence and preserves dissent | Generate a long narrative directly from top retrieved papers | The platform’s evidence-before-prose principle requires auditable claim-level support and citation completeness. | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) |
| `CAP-09-D05` | **Reproducibility export** | RO-Crate metadata plus BagIt-compatible checksum payload and CSL-formatted references | One opaque ZIP or application-only backup | Open package standards support human inspection, integrity validation and future tool interoperability. | [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) |
| `CAP-09-D06` | **Authority boundary** | Canonical domain records, evidence revisions and adjudications remain authoritative; graph nodes and edges are versioned derivative assertions with complete provenance. | Store graph edges as the only copy of scholarly relationships. | The graph can be dropped, repaired or replaced without losing scholarly decisions, rights or evidence history. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-09-D07` | **Local implementation** | Persist projection tables and adjacency indexes in protected SQLite; load bounded analytical subgraphs into rustworkx through a stable GraphQuery port. | Require an external graph server or keep all graph state only in memory. | SQLite fits the local protected-store architecture while rustworkx supplies portable algorithms without creating another durable authority. | [rustworkx Documentation](https://www.rustworkx.org/dev/) |
| `CAP-09-D08` | **Graph semantics** | Represent relation assertion identity separately from edge projection; include direction, status, validity interval, confidence components, evidence anchors, inference method and dispute/supersession links. | Use untyped source-target-label triples. | Scholarly relations are contestable and temporally/version dependent; a rich assertion contract is required for audit and recalculation. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-09-D09` | **Entity-linking policy** | Use deterministic identifiers/aliases and candidate retrieval first, followed by model-assisted ranking; retain mention text, source context, candidate list and human decision. | Let an LLM emit a canonical entity name without candidates or evidence. | Entity linking is consequential and requires reversible, inspectable resolution rather than fluent normalization. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-09-D10` | **Construct identity** | Allow related, broader/narrower, variant and disputed-equivalence relations; merge only through an adjudicated command. | Case-folded string matching or embedding threshold automatically merges constructs. | Construct drift and operational variation are analytical material, not noise to erase. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-09-D11` | **Argument representation** | Extract claim, evidence, warrant, qualification, rebuttal and relation candidates with exact anchors and candidate status; use schema packs by mode/domain. | One universal support/contradiction classifier over abstracts. | Argument roles and relation meanings vary; source-grounded typed candidates support later comparison and synthesis. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-09-D12` | **Two-stage comparability** | Apply explicit incompatibility gates first, then score remaining pairs on construct definition, unit/level, population, context, time, method, measure, outcome and intervention/exposure. | Cluster only by embedding similarity or citation graph. | Hard semantic/methodological mismatches must be visible before softer similarity signals. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-09-D13` | **Mode packs** | Systematic, theory, technical, critical and other modes version their dimensions, required fields, missingness treatment and thresholds. | Global weights hidden in the model. | What counts as comparable depends on the intended scholarly inference. | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) |
| `CAP-09-D14` | **Relation detection** | Generate typed candidates from normalized claims and evidence with explanatory contrasting dimensions; require human confirmation for promoted contradiction/boundary assertions. | Promote model labels directly to graph edges. | NLI/stance is a signal; context and measurement differences can explain apparent conflict. | [Fact or Fiction: Verifying Scientific Claims](https://aclanthology.org/2020.emnlp-main.609/) |
| `CAP-09-D15` | **Visualization engine** | Use Cytoscape.js behind an application graph-view adapter, with server/core-prepared authorized subgraphs and versioned layout presets. | Custom canvas engine or direct database-to-browser graph feed. | Cytoscape.js provides mature interaction/layout/serialization while replaceability and domain policy stay outside the library. | [Cytoscape.js Documentation](https://js.cytoscape.org/) |
| `CAP-09-D16` | **Progressive disclosure** | Start from a selected entity/claim and bounded neighborhood; expand explicitly by relation type/depth and summarize omitted nodes. | Auto-render all connected nodes. | Research graphs become unusable and inaccessible when scale is uncontrolled. | [Cytoscape.js Documentation](https://js.cytoscape.org/) |
| `CAP-09-D17` | **Interpretation boundary** | Visual encodings indicate relation/status/provenance only; every inference opens evidence and a textual explanation, with no causal implication from layout. | Let force-directed distance imply conceptual importance. | Layout is a navigation aid, not scholarly evidence. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-09-D18` | **Plan before prose** | Require a versioned synthesis plan of intended claims, comparison sets, evidence requirements, dissent/uncertainty handling and output structure. | Let the LLM decide claims while drafting. | An inspectable plan prevents prose fluency from silently selecting evidence or argument. | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) |
| `CAP-09-D19` | **Evidence packet** | Retrieve accepted evidence records/passages for each planned claim with rights, source quality, status and counterevidence; freeze a packet snapshot before generation. | Send full documents or search snippets ad hoc. | Bounded packets improve traceability, cost control and reproducibility. | [Language Agents Achieve Superhuman Synthesis of Scientific Knowledge](https://arxiv.org/abs/2409.13740) |
| `CAP-09-D20` | **Independent audit** | Run a separate citation auditor over final sentences/claims and cited passages for support, completeness, scope and mismatch; block high-severity failures. | Ask the drafting agent whether its citations are correct. | Generator/auditor separation is required for epistemic accountability. | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) |
| `CAP-09-D21` | **Package model** | Use RO-Crate JSON-LD to describe entities/activities/files and BagIt-compatible payload manifests/checksums for transfer integrity. | Custom ZIP with a README only. | The combination supplies portable research-object semantics and deterministic payload validation. | [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) |
| `CAP-09-D22` | **Snapshot boundary** | Freeze canonical revision/event high-water marks, corpus membership, rights decisions, schemas, indexes/models/prompt manifests and approved outputs; derived indexes are referenced or rebuilt, not silently copied as authority. | Export whatever is current as each file is written. | A single transaction-like snapshot boundary is necessary for coherent reproduction. | [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) |
| `CAP-09-D23` | **Rights filtering** | Compute an export policy per file/field/passage; replace restricted content with metadata/checksum/locator when redistribution is not permitted. | Include all local project content because the recipient may have access. | Access on the source machine does not grant redistribution rights. | [RFC 8493 - The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) |

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

Relevant approved pages: `claim-graph.html`, `theory-map.html`, `synthesis-studio.html`, `audit-lineage.html`

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

- A relation type or comparability rule changes the core ontology without approval.
- A synthesis cannot meet citation-support thresholds.
- An export would redistribute restricted full text or confidential content.
- Projection consistency cannot be restored from authoritative state.
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
- [ ] `python tools/planctl.py ready CAP-09 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [rustworkx Documentation](https://www.rustworkx.org/dev/) — Cross-platform high-performance in-memory graph projections and algorithms.
- [Cytoscape.js Documentation](https://js.cytoscape.org/) — Interactive graph visualization, selectors, layouts, serialization and graph interaction.
- [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) — Domain retrieval, reranking, iterative feedback, citation-aware synthesis and evaluation.
- [RO-Crate 1.3 Specification](https://www.researchobject.org/ro-crate/specification.html) — JSON-LD research package metadata and research-object interchange.
- [RFC 8493 - The BagIt File Packaging Format](https://www.rfc-editor.org/rfc/rfc8493.html) — Checksum-validated payload transfer and archival package layout.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
