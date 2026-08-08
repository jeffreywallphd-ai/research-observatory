---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-06
title: Local search, discovery, corpus diagnostics, and screening
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-06.S01
- CAP-06.S02
- CAP-06.S03
- CAP-06.S04
- CAP-06.S05
- CAP-06.S06
decisions:
- id: CAP-06-D01
  title: Canonical lexical query representation
  candidates:
  - Typed internal query AST compiled to SQLite FTS5 and external-source dialects
  - Store raw FTS5 strings as project truth; use an external search DSL library as the domain model
  recommendation: Typed internal query AST compiled to SQLite FTS5 and external-source dialects
  recommendation_basis: An AST preserves exact execution, location-specific validation, translations and future server adapters without letting an index syntax become the domain contract.
  selected_option: Typed internal query AST compiled to SQLite FTS5 and external-source dialects
  status: accepted
  required_adr: null
- id: CAP-06-D02
  title: Scientific semantic baseline
  candidates:
  - Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback
  - Use a generic sentence embedding model by default; hard-code SPECTER2 indefinitely
  recommendation: Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback
  recommendation_basis: Scientific representations are a stronger starting point, but the chosen model remains evidence- and license-dependent and must be replaceable.
  selected_option: Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback
  status: accepted
  required_adr: null
- id: CAP-06-D03
  title: Local vector engine
  candidates:
  - Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR
  - Treat Qdrant Python local mode as production equivalent; embed vector files directly in canonical storage
  recommendation: Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR
  recommendation_basis: Service mode has the operational surface needed for filters and recovery; exact fallback preserves correctness and usability when the service is unavailable.
  selected_option: Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR
  status: accepted
  required_adr: null
- id: CAP-06-D04
  title: Hybrid fusion
  candidates:
  - Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  - Normalize incomparable raw scores into a fixed weighted sum
  recommendation: Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  recommendation_basis: RRF combines ranks without fragile score calibration and remains easy to explain and replay.
  selected_option: Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  status: accepted
  required_adr: null
- id: CAP-06-D05
  title: Screening authority
  candidates:
  - Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  - Autonomous inclusion or stopping based on classifier score
  recommendation: Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  recommendation_basis: Transparent prioritization can reduce work without converting a relevance model into a scholarly decision maker.
  selected_option: Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  status: accepted
  required_adr: null
- id: CAP-06-D06
  title: Tokenizer/analyzer
  candidates:
  - Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance.
  - Default porter stemming or one opaque language analyzer for all content.
  recommendation: Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance.
  recommendation_basis: Language-neutral exactness and explainability are more important than aggressive English stemming; analyzer choice is part of the index manifest.
  selected_option: Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance.
  status: accepted
  required_adr: null
- id: CAP-06-D07
  title: FTS layout
  candidates:
  - Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt from authoritative records.
  - Store canonical records only inside FTS virtual tables.
  recommendation: Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt from authoritative records.
  recommendation_basis: Canonical transactions and rights live in SQLite domain tables; FTS can be recreated, integrity-checked and replaced.
  selected_option: Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt from authoritative records.
  status: accepted
  required_adr: null
- id: CAP-06-D08
  title: Ranking
  candidates:
  - BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability.
  - Normalize BM25 to “relevance percent.”
  recommendation: BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability.
  recommendation_basis: The score is an index ranking signal and must remain interpretable and replayable.
  selected_option: BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability.
  status: accepted
  required_adr: null
- id: CAP-06-D09
  title: Representation unit
  candidates:
  - Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector.
  - One vector per PDF or unanchored fixed-token chunks.
  recommendation: Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector.
  recommendation_basis: Work vectors support discovery while passage vectors support evidence retrieval; provenance remains exact.
  selected_option: Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector.
  status: accepted
  required_adr: null
- id: CAP-06-D10
  title: Baseline model
  candidates:
  - Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution.
  - Use a general-purpose embedding model without scientific evaluation.
  recommendation: Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution.
  recommendation_basis: SPECTER2 supplies scientific training and task adapters, but the gateway contract keeps it replaceable.
  selected_option: Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution.
  status: accepted
  required_adr: null
- id: CAP-06-D11
  title: Index adapter
  candidates:
  - Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora.
  - Use Qdrant local mode as if it had service snapshot parity; store vectors in canonical relational rows for every query.
  recommendation: Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora.
  recommendation_basis: A supervised service gives production health/filtering, while fallback protects correctness and offline continuity.
  selected_option: Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora.
  status: accepted
  required_adr: null
- id: CAP-06-D12
  title: Fusion default
  candidates:
  - RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  - Weighted sum of BM25 and cosine similarity.
  recommendation: RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  recommendation_basis: Rank fusion avoids incompatible score calibration and provides clear component evidence.
  selected_option: RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  status: accepted
  required_adr: null
- id: CAP-06-D13
  title: Rerank boundary
  candidates:
  - Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order.
  - Rerank the full corpus or make reranking mandatory.
  recommendation: Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order.
  recommendation_basis: Bounded reranking controls latency/cost and preserves a deterministic fallback.
  selected_option: Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order.
  status: accepted
  required_adr: null
- id: CAP-06-D14
  title: Replay semantics
  candidates:
  - Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim.
  - Re-run against current state and label it reproduced.
  recommendation: Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim.
  recommendation_basis: Scholarly reproducibility requires distinguishing identical inputs from changed evidence state.
  selected_option: Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim.
  status: accepted
  required_adr: null
- id: CAP-06-D15
  title: Editing model
  candidates:
  - Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  - Overwrite the last run as the user edits.
  recommendation: Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  recommendation_basis: Separating draft from executed state preserves an auditable search history.
  selected_option: Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  status: accepted
  required_adr: null
- id: CAP-06-D16
  title: Translation
  candidates:
  - Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  - Copy one Boolean string to every database.
  recommendation: Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  recommendation_basis: Source syntaxes and fields differ; explicit loss reporting prevents false reproducibility.
  selected_option: Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  status: accepted
  required_adr: null
- id: CAP-06-D17
  title: Expansion
  candidates:
  - Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance.
  - Background recursive graph crawl with hidden heuristics.
  recommendation: Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance.
  recommendation_basis: Bounded operations make discovery paths inspectable, cancelable and reproducible.
  selected_option: Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance.
  status: accepted
  required_adr: null
- id: CAP-06-D18
  title: Diagnostic denominators
  candidates:
  - Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  - Compute percentages after silently dropping missing values.
  recommendation: Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  recommendation_basis: Missingness is itself a corpus property and must remain visible.
  selected_option: Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  status: accepted
  required_adr: null
- id: CAP-06-D19
  title: Canvas projection
  candidates:
  - Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative.
  - Persist manual node coordinates as the field model.
  recommendation: Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative.
  recommendation_basis: Projections are model-dependent views, not scholarly truth.
  selected_option: Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative.
  status: accepted
  required_adr: null
- id: CAP-06-D20
  title: Sensitivity
  candidates:
  - Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes.
  - Mutate the main corpus to test a what-if question.
  recommendation: Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes.
  recommendation_basis: Scenario snapshots make reflexive analysis reproducible and reversible.
  selected_option: Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes.
  status: accepted
  required_adr: null
- id: CAP-06-D21
  title: Baseline learner
  candidates:
  - Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives.
  - Start with an opaque large neural model.
  recommendation: Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives.
  recommendation_basis: A simple baseline is fast, inspectable and effective for active prioritization; evaluation can justify replacement.
  selected_option: Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives.
  status: accepted
  required_adr: null
- id: CAP-06-D22
  title: Decision model
  candidates:
  - Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  - Overwrite conflicting labels with the last action.
  recommendation: Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  recommendation_basis: Reviewer independence and disagreement are evidence about the process.
  selected_option: Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  status: accepted
  required_adr: null
- id: CAP-06-D23
  title: Stopping
  candidates:
  - Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required.
  - Stop when model score falls below a fixed threshold.
  recommendation: Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required.
  recommendation_basis: No single model-derived threshold demonstrates that relevant records are absent.
  selected_option: Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required.
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-06 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-06` — Local search, discovery, corpus diagnostics, and screening |
| Objective | Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-06.S01`, `CAP-06.S02`, `CAP-06.S03`, `CAP-06.S04`, `CAP-06.S05`, `CAP-06.S06` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session.**

Production-ready exit criteria:

- Lexical and semantic indexes are versioned, explainable, rebuildable, and usable offline for project content.
- Search evolution is stored as a visible tree of exact queries, transformations, results, and discovery paths.
- Screening supports human inclusion decisions, uncertainty/random audits, stopping evidence, and reproducible exports.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-06.S01` | Fielded lexical search and local indexing | Exact terminology, Boolean logic, metadata filters, and reproducible ranking are available through SQLite FTS5. | `CAP-04.S04.T03`, `CAP-05.S03.T03` |
| `CAP-06.S02` | Semantic representations and vector retrieval | Conceptually related literature is retrievable through a replaceable, versioned local embedding interface. | `CAP-06.S01.T02`, `CAP-07.S01.T03` |
| `CAP-06.S03` | Hybrid retrieval and reranking | Search ensembles combine exact, semantic, graph, and project-specific relevance while preserving component evidence. | `CAP-06.S01.T03`, `CAP-06.S02.T03` |
| `CAP-06.S04` | Search Studio and transparent expansion | Researchers can iteratively broaden, narrow, branch, and compare searches without losing their reasoning history. | `CAP-06.S03.T03`, `CAP-04.S02.T03` |
| `CAP-06.S05` | Corpus canvas, coverage, and reflexivity diagnostics | Field structure and collection bias are visible before analytical claims are made. | `CAP-06.S04.T03`, `CAP-04.S04.T03` |
| `CAP-06.S06` | Transparent screening and active-learning governance | Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk. | `CAP-06.S05.T02`, `CAP-03.S02.T03` |

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
| `CAP-06-D01` | **Canonical lexical query representation** | Typed internal query AST compiled to SQLite FTS5 and external-source dialects | Store raw FTS5 strings as project truth; use an external search DSL library as the domain model | An AST preserves exact execution, location-specific validation, translations and future server adapters without letting an index syntax become the domain contract. | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) |
| `CAP-06-D02` | **Scientific semantic baseline** | Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback | Use a generic sentence embedding model by default; hard-code SPECTER2 indefinitely | Scientific representations are a stronger starting point, but the chosen model remains evidence- and license-dependent and must be replaceable. | [SciRepEval: A Multi-Format Benchmark for Scientific Document Representations](https://aclanthology.org/2023.emnlp-main.338/) |
| `CAP-06-D03` | **Local vector engine** | Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR | Treat Qdrant Python local mode as production equivalent; embed vector files directly in canonical storage | Service mode has the operational surface needed for filters and recovery; exact fallback preserves correctness and usability when the service is unavailable. | [Qdrant Snapshots](https://qdrant.tech/documentation/concepts/snapshots/) |
| `CAP-06-D04` | **Hybrid fusion** | Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later | Normalize incomparable raw scores into a fixed weighted sum | RRF combines ranks without fragile score calibration and remains easy to explain and replay. | [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) |
| `CAP-06-D05` | **Screening authority** | Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval | Autonomous inclusion or stopping based on classifier score | Transparent prioritization can reduce work without converting a relevance model into a scholarly decision maker. | [An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews](https://doi.org/10.1038/s42256-020-00287-7) |
| `CAP-06-D06` | **Tokenizer/analyzer** | Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance. | Default porter stemming or one opaque language analyzer for all content. | Language-neutral exactness and explainability are more important than aggressive English stemming; analyzer choice is part of the index manifest. | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) |
| `CAP-06-D07` | **FTS layout** | Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt from authoritative records. | Store canonical records only inside FTS virtual tables. | Canonical transactions and rights live in SQLite domain tables; FTS can be recreated, integrity-checked and replaced. | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) |
| `CAP-06-D08` | **Ranking** | BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability. | Normalize BM25 to “relevance percent.” | The score is an index ranking signal and must remain interpretable and replayable. | [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) |
| `CAP-06-D09` | **Representation unit** | Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector. | One vector per PDF or unanchored fixed-token chunks. | Work vectors support discovery while passage vectors support evidence retrieval; provenance remains exact. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| `CAP-06-D10` | **Baseline model** | Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution. | Use a general-purpose embedding model without scientific evaluation. | SPECTER2 supplies scientific training and task adapters, but the gateway contract keeps it replaceable. | [AllenAI SPECTER2 Model Card](https://huggingface.co/allenai/specter2) |
| `CAP-06-D11` | **Index adapter** | Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora. | Use Qdrant local mode as if it had service snapshot parity; store vectors in canonical relational rows for every query. | A supervised service gives production health/filtering, while fallback protects correctness and offline continuity. | [Qdrant Snapshots](https://qdrant.tech/documentation/concepts/snapshots/) |
| `CAP-06-D12` | **Fusion default** | RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation. | Weighted sum of BM25 and cosine similarity. | Rank fusion avoids incompatible score calibration and provides clear component evidence. | [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) |
| `CAP-06-D13` | **Rerank boundary** | Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order. | Rerank the full corpus or make reranking mandatory. | Bounded reranking controls latency/cost and preserves a deterministic fallback. | [Retrieve & Re-Rank - Sentence Transformers](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) |
| `CAP-06-D14` | **Replay semantics** | Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim. | Re-run against current state and label it reproduced. | Scholarly reproducibility requires distinguishing identical inputs from changed evidence state. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-06-D15` | **Editing model** | Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes. | Overwrite the last run as the user edits. | Separating draft from executed state preserves an auditable search history. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-06-D16` | **Translation** | Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings. | Copy one Boolean string to every database. | Source syntaxes and fields differ; explicit loss reporting prevents false reproducibility. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-06-D17` | **Expansion** | Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance. | Background recursive graph crawl with hidden heuristics. | Bounded operations make discovery paths inspectable, cancelable and reproducible. | [Semantic Scholar Academic Graph API](https://www.semanticscholar.org/product/api) |
| `CAP-06-D18` | **Diagnostic denominators** | Every percentage states denominator, known/unknown count, source snapshot and field derivation. | Compute percentages after silently dropping missing values. | Missingness is itself a corpus property and must remain visible. | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) |
| `CAP-06-D19` | **Canvas projection** | Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative. | Persist manual node coordinates as the field model. | Projections are model-dependent views, not scholarly truth. | [SciRepEval: A Multi-Format Benchmark for Scientific Document Representations](https://aclanthology.org/2023.emnlp-main.338/) |
| `CAP-06-D20` | **Sensitivity** | Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes. | Mutate the main corpus to test a what-if question. | Scenario snapshots make reflexive analysis reproducible and reversible. | [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) |
| `CAP-06-D21` | **Baseline learner** | Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives. | Start with an opaque large neural model. | A simple baseline is fast, inspectable and effective for active prioritization; evaluation can justify replacement. | [ASReview Documentation](https://asreview.readthedocs.io/en/latest/) |
| `CAP-06-D22` | **Decision model** | Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record. | Overwrite conflicting labels with the last action. | Reviewer independence and disagreement are evidence about the process. | [An Open Source Machine Learning Framework for Efficient and Transparent Systematic Reviews](https://doi.org/10.1038/s42256-020-00287-7) |
| `CAP-06-D23` | **Stopping** | Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required. | Stop when model score falls below a fixed threshold. | No single model-derived threshold demonstrates that relevant records are absent. | [PRISMA 2020 Statement](https://doi.org/10.1136/bmj.n71) |

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

Relevant approved pages: `search-studio.html`, `corpus-canvas.html`, `screening.html`

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

- A search/vector/model ADR cannot be approved from available benchmark evidence.
- The approved UI reference must change materially.
- A source license or rights rule prevents the intended indexing behavior.
- Required platform hardware is unavailable for a declared release qualification.
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
- [ ] `python tools/planctl.py ready CAP-06 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) — Local fielded lexical indexing, BM25 ranking, snippets, rebuild and integrity checks.
- [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) — Deterministic rank-level lexical/semantic fusion without score calibration assumptions.
- [SciRepEval: A Multi-Format Benchmark for Scientific Document Representations](https://aclanthology.org/2023.emnlp-main.338/) — Scientific document embedding baseline and task-specific adapters.
- [ASReview Documentation](https://asreview.readthedocs.io/en/latest/) — Transparent active-learning-assisted screening patterns.
- [PRISMA-S: An Extension to the PRISMA Statement for Reporting Literature Searches](https://doi.org/10.1186/s13643-020-01542-z) — Search-strategy and information-source reporting.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
