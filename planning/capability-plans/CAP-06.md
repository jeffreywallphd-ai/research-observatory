---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-06
title: Local search, discovery, corpus diagnostics, and screening
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: pending
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
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Typed internal query AST compiled to SQLite FTS5 and external-source dialects
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D02
  title: Scientific semantic baseline
  candidates:
  - Qualify a small CPU encoder on the scientific gold set, retaining SPECTER2 base/proximity/adhoc comparison only within
    the same admitted resource tier.
  - Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback
  - Use a generic sentence embedding model by default; hard-code SPECTER2 indefinitely
  recommendation: Qualify a small CPU encoder on the scientific gold set, retaining SPECTER2 base/proximity/adhoc comparison
    only within the same admitted resource tier.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Qualify a small CPU encoder on the scientific gold set, retaining SPECTER2 base/proximity/adhoc comparison
    only within the same admitted resource tier.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D03
  title: Local vector engine
  candidates:
  - Protected embedded exact-cosine adapter with bounded streaming for W3; preserve engine-neutral port and defer Qdrant service
    until measured need and accepted architecture.
  - Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR
  - Treat Qdrant Python local mode as production equivalent; embed vector files directly in canonical storage
  recommendation: Protected embedded exact-cosine adapter with bounded streaming for W3; preserve engine-neutral port and
    defer Qdrant service until measured need and accepted architecture.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Protected embedded exact-cosine adapter with bounded streaming for W3; preserve engine-neutral port and
    defer Qdrant service until measured need and accepted architecture.
  status: accepted
  required_adr: ADR-0057
  binding_waves:
  - W3
- id: CAP-06-D04
  title: Hybrid fusion
  candidates:
  - Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  - Normalize incomparable raw scores into a fixed weighted sum
  recommendation: Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D05
  title: Screening authority
  candidates:
  - Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  - Autonomous inclusion or stopping based on classifier score
  recommendation: Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D06
  title: Tokenizer/analyzer
  candidates:
  - Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary index
    only for identifiers/titles that need substring tolerance.
  - Default porter stemming or one opaque language analyzer for all content.
  recommendation: Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary
    index only for identifiers/titles that need substring tolerance.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Use `unicode61 remove_diacritics 2` as the general baseline; add an independently benchmarked trigram auxiliary
    index only for identifiers/titles that need substring tolerance.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D07
  title: FTS layout
  candidates:
  - External-content FTS5 inside SQLCipher, maintained/rebuilt against lawful canonical stable IDs; no plaintext contentless
    side database.
  - Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt
    from authoritative records.
  - Store canonical records only inside FTS virtual tables.
  recommendation: External-content FTS5 inside SQLCipher, maintained/rebuilt against lawful canonical stable IDs; no plaintext
    contentless side database.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: External-content FTS5 inside SQLCipher, maintained/rebuilt against lawful canonical stable IDs; no plaintext
    contentless side database.
  status: accepted
  required_adr: ADR-0057
  binding_waves:
  - W3
- id: CAP-06-D08
  title: Ranking
  candidates:
  - BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a
    misleading probability.
  - Normalize BM25 to “relevance percent.”
  recommendation: BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets,
    not a misleading probability.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets,
    not a misleading probability.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D09
  title: Representation unit
  candidates:
  - Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk
    selector.
  - One vector per PDF or unanchored fixed-token chunks.
  recommendation: Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source
    revision and chunk selector.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source
    revision and chunk selector.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D10
  title: Baseline model
  candidates:
  - MiniLM short-passage encoder is the first resource/quality qualification candidate, SPECTER2 correct adapters scientific
    comparator; no activation without exact manifest and actual evaluation.
  - Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow
    ONNX or Transformers execution.
  - Use a general-purpose embedding model without scientific evaluation.
  recommendation: MiniLM short-passage encoder is the first resource/quality qualification candidate, SPECTER2 correct adapters
    scientific comparator; no activation without exact manifest and actual evaluation.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: MiniLM short-passage encoder is the first resource/quality qualification candidate, SPECTER2 correct adapters
    scientific comparator; no activation without exact manifest and actual evaluation.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D11
  title: Index adapter
  candidates:
  - Protected embedded exact scorer for current small-PC tier; no Qdrant sidecar prerequisite or install. Unknown protected-store
    capability blocks that claim, not permits plaintext.
  - Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact
    NumPy/SQLite candidate fallback for small corpora.
  - Use Qdrant local mode as if it had service snapshot parity; store vectors in canonical relational rows for every query.
  recommendation: Protected embedded exact scorer for current small-PC tier; no Qdrant sidecar prerequisite or install. Unknown
    protected-store capability blocks that claim, not permits plaintext.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Protected embedded exact scorer for current small-PC tier; no Qdrant sidecar prerequisite or install. Unknown
    protected-store capability blocks that claim, not permits plaintext.
  status: accepted
  required_adr: ADR-0057
  binding_waves:
  - W3
- id: CAP-06-D12
  title: Fusion default
  candidates:
  - RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  - Weighted sum of BM25 and cosine similarity.
  recommendation: RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D13
  title: Rerank boundary
  candidates:
  - Optional evaluated rerank top20 default on this PC, <=50 only with qualified profile; rights-first and explicit fused-order
    timeout fallback.
  - Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order.
  - Rerank the full corpus or make reranking mandatory.
  recommendation: Optional evaluated rerank top20 default on this PC, <=50 only with qualified profile; rights-first and explicit
    fused-order timeout fallback.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Optional evaluated rerank top20 default on this PC, <=50 only with qualified profile; rights-first and
    explicit fused-order timeout fallback.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D14
  title: Replay semantics
  candidates:
  - Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact
    replay claim.
  - Re-run against current state and label it reproduced.
  recommendation: Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not
    a false exact replay claim.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not
    a false exact replay claim.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D15
  title: Editing model
  candidates:
  - Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  - Overwrite the last run as the user edits.
  recommendation: Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D16
  title: Translation
  candidates:
  - Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  - Copy one Boolean string to every database.
  recommendation: Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D17
  title: Expansion
  candidates:
  - Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance.
  - Background recursive graph crawl with hidden heuristics.
  recommendation: Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and
    provenance.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview
    and provenance.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D18
  title: Diagnostic denominators
  candidates:
  - Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  - Compute percentages after silently dropping missing values.
  recommendation: Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Every percentage states denominator, known/unknown count, source snapshot and field derivation.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D19
  title: Canvas projection
  candidates:
  - Versioned table-first projection with <=5000 sampled points and exact population counts/seed/frame; larger50k layouts
    deferred to W5.
  - Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative.
  - Persist manual node coordinates as the field model.
  recommendation: Versioned table-first projection with <=5000 sampled points and exact population counts/seed/frame; larger50k
    layouts deferred to W5.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Versioned table-first projection with <=5000 sampled points and exact population counts/seed/frame; larger50k
    layouts deferred to W5.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D20
  title: Sensitivity
  candidates:
  - Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate
    changes.
  - Mutate the main corpus to test a what-if question.
  recommendation: Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and
    downstream candidate changes.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and
    downstream candidate changes.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D21
  title: Baseline learner
  candidates:
  - Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline;
    model port permits alternatives.
  - Start with an opaque large neural model.
  recommendation: Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible
    baseline; model port permits alternatives.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible
    baseline; model port permits alternatives.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D22
  title: Decision model
  candidates:
  - Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  - Overwrite conflicting labels with the last action.
  recommendation: Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-06-D23
  title: Stopping
  candidates:
  - Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol
    threshold; named human approval required.
  - Stop when model score falls below a fixed threshold.
  recommendation: Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty
    and protocol threshold; named human approval required.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty
    and protocol threshold; named human approval required.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
planning_policy_version: initiation-assessment-2.0
initiation_assessment:
  policy_version: '2.0'
  assessed_at: '2026-10-15T21:24:29.166422+00:00'
  estimation_unit: engineering-effort-hours
  implementation_baseline: 'Genuine905b assessment; deliberate current deny model policy, protected schema28/anchors/lifecycle
    and accepted ADR21/25/26 are reused. W2 exit pending.


    Canonical post-G2 reconciliation: Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb;
    the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json
    and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86
    identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen
    and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference.
    All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN,
    security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake
    to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5.
    Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable
    trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud
    labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics
    and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING;
    no implementation is authorized.'
  vision_architecture_best_practice_fit: Local small configurable CPU model/resource tier, protected exact retrieval, human
    research authority, explicit optional egress; proposed material architecture/reference adoption still required.
  planned_items:
  - work_id: CAP-06.S01.T01
    effort: 12
  - work_id: CAP-06.S01.T02
    effort: 24
  - work_id: CAP-06.S01.T03
    effort: 20
  - work_id: CAP-06.S02.T01
    effort: 16
  - work_id: CAP-06.S02.T02
    effort: 24
  - work_id: CAP-06.S02.T03
    effort: 24
  - work_id: CAP-06.S03.T01
    effort: 12
  - work_id: CAP-06.S03.T02
    effort: 20
  - work_id: CAP-06.S03.T03
    effort: 16
  - work_id: CAP-06.S04.T01
    effort: 24
  - work_id: CAP-06.S04.T02
    effort: 20
  - work_id: CAP-06.S04.T03
    effort: 20
  - work_id: CAP-06.S05.T01
    effort: 20
  - work_id: CAP-06.S05.T02
    effort: 16
  - work_id: CAP-06.S05.T03
    effort: 16
  - work_id: CAP-06.S06.T01
    effort: 20
  - work_id: CAP-06.S06.T02
    effort: 20
  - work_id: CAP-06.S06.T03
    effort: 16
  refactoring_items:
  - work_id: CAP-06.S01.T02
    effort: 4
    reason: Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not
      an additional task or double-counted estimate.
    id: CAP-06.S01.T02
    introduced_in_wave: W3
    changes_existing_implementation: true
    major_refactor: false
    disposition: included
    description: "Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not an additional task or double-counted estimate."
  major_refactor_disposition: No blanket replacement of approved W1/W2 contracts. The new model-purpose worker/protected projection
    decisions are planned W3 architecture with acceptance required before approval; inherited decisions remain unchanged.
  wave_refreshes:
  - wave: W3
    assessed_at: '2026-10-16T11:23:10.387985+00:00'
    material_changes: 'Current W2 schema28/protected anchors, UI1.9 and deliberate no-model permission baseline replace stale
      paths/assumptions.


      Canonical post-G2 reconciliation: Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb;
      the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json
      and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86
      identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen
      and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference.
      All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN,
      security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance
      intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product
      workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed
      comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged.
      Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03
      metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged
      and W3approvalPENDING; no implementation is authorized.'
    plan_adaptations: All proposed choices are itemized in this private packet; no capability campaign, unsafe memory override,
      implicit egress or unprotected service index. Successor05 includes actual ordered-slice approval gates, executable slice
      order and retained staged registry/runtime/evaluation proof; no framework or policy weakening.
    support_improvements: Canonical rights/classification/budget and resource admission, protected rebuild, honest evaluation/identity
      states.
    major_refactor_disposition: Included in named atomic task estimates; no supplemental budget spent.
---

# CAP-06 — Local search, discovery, corpus diagnostics, and screening

PRIVATE PROPOSED W3 CONTRIBUTION. Approval, accepted status and execution remain pending. Original source: `planning/capability-plans/CAP-06.md` / `f8eeeaec7fbcde78ae4b9d4e2a1e45e73bb43e9b649d0013ea8f1991db8e3e2f`. Preserve inherited W1 selections; recommended W3 values are resolved draft choices subject to one complete Wave review, not existing approvals. `required_adr: null` here does not waive the three material architecture topics; unassigned historical ADR-CAP placeholders are replaced by the explicit topic register.

## 0. Control and authority

The Wave owns execution/integration/qualification and G3 handoff. Capability is an outcome map, not a lease. Immutable IDs and prior approvals stay unchanged; all proposed decisions are classified by Wave in front matter.

## 0A. Initiation assessment and planning adaptation

Reuse genuine905b source assessment and the baseline/source inventory. Full48 atomic estimates are in task-register-01.json; no slice+task double count. See contracts-01.md for baseline fit, exact resource/rights model and deferred work.

## 1. Capability outcome and production-ready exit

Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session. W3 exit covers only these contributing slices, actual benchmark limits, real authority and human review, not unimplemented future capabilities.

## 2. Slice map and end-to-end dependency logic

- CAP-06.S01: Fielded lexical search and local indexing — Typed fielded AST with explicit unsupported clauses; protected FTS5/BM25, stable IDs and inspectable snippets. Query text is never executable SQL.
- CAP-06.S02: Semantic representations and vector retrieval — Work and passage vector manifests bind exact revision, selector, tokenizer/pooling/model/runtime/dimensions/normalization and rights. First W3 adapter is protected exact cosine over bounded chunks, not an unencrypted Qdrant service.
- CAP-06.S03: Hybrid retrieval and reranking — Deterministic RRF with k=60 and stable-ID ties; component ranks remain visible. Optional evaluated reranker works only on allowed candidates and may time out back to the recorded fused order.
- CAP-06.S04: Search Studio and transparent expansion — Editable draft queries are distinct from immutable executed SearchRuns. Branches, translation loss and bounded citation/semantic expansion are visible user actions, not hidden model behavior.
- CAP-06.S05: Corpus canvas, coverage, and reflexivity diagnostics — Table-first corpus diagnostics with denominators, known/unknown values and source-backed drilldown. A sampled 2D projection is navigation, not evidence of semantic truth or a change to corpus membership.
- CAP-06.S06: Transparent screening and active-learning governance — Named humans decide inclusion and stopping. Reproducible TF-IDF/regularized linear ranking changes queue priority only, with random and citation-neighbor safety channels and manual fallback.

This is the actual proposed capability.slices execution order, not numeric ID order. Every earlier slice needs genuine APPROVED completion before later tasks; exact external dependency unions apply to every task. See ordered-slice-feasibility-witness-05.json. Inherited/future slice objects and identities are unchanged.

## 3. Decision-making protocol

Every W3 decision has at least two candidates and a concrete recommended selection. The authored proposed plan selects the reviewed options using the existing capability-plan status `accepted`; this records plan-option completeness only. Proposed ADRs, the proposed reference1.10 and Wave approval remain pending and grant no implementation authority. Record independent review/any override rationale and material ADR/reference decisions in the ordinary single Wave packet.

## 4. Decision register

Selections below are the recorded proposed-plan choices; the capability/Wave approval remains PENDING. Inherited accepted authority retains its original scope. Full metadata and alternatives remain in the front matter.

| Decision | Alternatives | Recorded choice | Rationale | Required ADR |
|---|---|---|---|---|
| `CAP-06-D01` — Canonical lexical query representation | Typed internal query AST compiled to SQLite FTS5 and external-source dialects<br>Store raw FTS5 strings as project truth; use an external search DSL library as the domain model | Typed internal query AST compiled to SQLite FTS5 and external-source dialects | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D02` — Scientific semantic baseline | Qualify a small CPU encoder on the scientific gold set, retaining SPECTER2 base/proximity/adhoc comparison only within the same admitted resource tier.<br>Benchmark SPECTER2 retrieval/adhoc-query adapters against the project gold set; retain model port and exact fallback<br>Use a generic sentence embedding model by default; hard-code SPECTER2 indefinitely | Qualify a small CPU encoder on the scientific gold set, retaining SPECTER2 base/proximity/adhoc comparison only within the same admitted resource tier. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D03` — Local vector engine | Protected embedded exact-cosine adapter with bounded streaming for W3; preserve engine-neutral port and defer Qdrant service until measured need and accepted architecture.<br>Benchmark Qdrant service sidecar against a portable exact-cosine fallback and approve through ADR<br>Treat Qdrant Python local mode as production equivalent; embed vector files directly in canonical storage | Protected embedded exact-cosine adapter with bounded streaming for W3; preserve engine-neutral port and defer Qdrant service until measured need and accepted architecture. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0057 |
| `CAP-06-D04` — Hybrid fusion | Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later<br>Normalize incomparable raw scores into a fixed weighted sum | Reciprocal Rank Fusion with deterministic tie rules, optional learned/calibrated alternatives later | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D05` — Screening authority | Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval<br>Autonomous inclusion or stopping based on classifier score | Machine learning prioritizes only; named humans own inclusion/exclusion and stopping approval | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D06` — Tokenizer/analyzer | Use unicode61 remove_diacritics 2 as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance.<br>Default porter stemming or one opaque language analyzer for all content. | Use unicode61 remove_diacritics 2 as the general baseline; add an independently benchmarked trigram auxiliary index only for identifiers/titles that need substring tolerance. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D07` — FTS layout | External-content FTS5 inside SQLCipher, maintained/rebuilt against lawful canonical stable IDs; no plaintext contentless side database.<br>Use external-content/contentless FTS5 tables keyed to canonical stable IDs; treat them as disposable projections rebuilt from authoritative records.<br>Store canonical records only inside FTS virtual tables. | External-content FTS5 inside SQLCipher, maintained/rebuilt against lawful canonical stable IDs; no plaintext contentless side database. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0057 |
| `CAP-06-D08` — Ranking | BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability.<br>Normalize BM25 to “relevance percent.” | BM25 with explicit per-field weights and deterministic stable-ID tie break; expose matched fields and snippets, not a misleading probability. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D09` — Representation unit | Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector.<br>One vector per PDF or unanchored fixed-token chunks. | Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D10` — Baseline model | MiniLM short-passage encoder is the first resource/quality qualification candidate, SPECTER2 correct adapters scientific comparator; no activation without exact manifest and actual evaluation.<br>Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution.<br>Use a general-purpose embedding model without scientific evaluation. | MiniLM short-passage encoder is the first resource/quality qualification candidate, SPECTER2 correct adapters scientific comparator; no activation without exact manifest and actual evaluation. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D11` — Index adapter | Protected embedded exact scorer for current small-PC tier; no Qdrant sidecar prerequisite or install. Unknown protected-store capability blocks that claim, not permits plaintext.<br>Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora.<br>Use Qdrant local mode as if it had service snapshot parity; store vectors in canonical relational rows for every query. | Protected embedded exact scorer for current small-PC tier; no Qdrant sidecar prerequisite or install. Unknown protected-store capability blocks that claim, not permits plaintext. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0057 |
| `CAP-06-D12` — Fusion default | RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation.<br>Weighted sum of BM25 and cosine similarity. | RRF over stable lexical and semantic rank lists, with explicit source weights only when approved by evaluation. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D13` — Rerank boundary | Optional evaluated rerank top20 default on this PC, <=50 only with qualified profile; rights-first and explicit fused-order timeout fallback.<br>Rerank a configurable top-N candidate set (default 50) after rights/filter enforcement; timeout returns fused order.<br>Rerank the full corpus or make reranking mandatory. | Optional evaluated rerank top20 default on this PC, <=50 only with qualified profile; rights-first and explicit fused-order timeout fallback. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D14` — Replay semantics | Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim.<br>Re-run against current state and label it reproduced. | Replay against pinned corpus/index/model snapshots; otherwise produce an explicit drift comparison, not a false exact replay claim. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D15` — Editing model | Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes.<br>Overwrite the last run as the user edits. | Draft query revisions are local UI state; only executed/saved runs become immutable SearchRun nodes. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D16` — Translation | Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings.<br>Copy one Boolean string to every database. | Compile from canonical AST to per-source dialect and return unsupported/approximated clauses with warnings. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D17` — Expansion | Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance.<br>Background recursive graph crawl with hidden heuristics. | Treat every expansion as an explicit bounded operation with seeds, relation type, depth/limit, preview and provenance. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D18` — Diagnostic denominators | Every percentage states denominator, known/unknown count, source snapshot and field derivation.<br>Compute percentages after silently dropping missing values. | Every percentage states denominator, known/unknown count, source snapshot and field derivation. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D19` — Canvas projection | Versioned table-first projection with <=5000 sampled points and exact population counts/seed/frame; larger50k layouts deferred to W5.<br>Use cached, versioned 2D/cluster projections only for navigation; canonical records and inclusion state remain authoritative.<br>Persist manual node coordinates as the field model. | Versioned table-first projection with <=5000 sampled points and exact population counts/seed/frame; larger50k layouts deferred to W5. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D20` — Sensitivity | Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes.<br>Mutate the main corpus to test a what-if question. | Create immutable boundary scenarios referencing base snapshot plus rule differences; compare coverage and downstream candidate changes. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D21` — Baseline learner | Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives.<br>Start with an opaque large neural model. | Transparent TF-IDF plus regularized linear classifier and configurable query strategy as the initial reproducible baseline; model port permits alternatives. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D22` — Decision model | Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record.<br>Overwrite conflicting labels with the last action. | Immutable per-reviewer decisions with protocol version; adjudication produces a separate human record. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-06-D23` — Stopping | Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required.<br>Stop when model score falls below a fixed threshold. | Multi-signal recommendation using yield curve, random-audit misses, citation-neighbor misses, uncertainty and protocol threshold; named human approval required. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |

## 5. Cross-slice architecture contract

Use current Core/worker/generated ports and protected state; contracts-01.md owns content refs, policy before allow, no product->evaluation dependency, migrations and resources. Task DAG includes explicit runtime and canonical persistence prerequisites.

## 6. Experience and workflow contract

Base reference1.9 and semantic catalog1.5 are inherited, illustrative values are not measured/configuration authority. Proposed material additions in ux-reference-proposal-01.md need ordinary accepted reference publication before implementation.

## 7. Security, privacy, rights and research-integrity decisions

Purpose-specific source model-use/classification/budget, current Windows session/principal, encrypted derivative storage and no implicit egress/spend. Human interpretation/inclusion/verification/final claims; local coder limits are explicit.

## 8. Capability-wide verification strategy

Task selected checks, integrated real slice journey, then fresh full affected Wave qualification. Include rights revoke, cancellation/late output, resource OOM, crash/restart, stale inputs, backup-first migration, actual no-network/no-vault principal and accessibility. Gold methodology/targets and actual-evidence limits in shared contracts.

## 9. Long-running execution contract

After W2 exit/G2, canonicalize reviewed plan/reference/ADRs and obtain one immutable W3 approval; normal taskctl claims dependency-eligible READY tasks in the same campaign. Ordinary debugging adds no owner question; real scope/authority/release conflicts use existing routes.

## 10. Plan and approval checklist

16 slices/48 tasks, exact decision inventory and estimates/DAG; no unapproved future scope accepted by implication. Unresolved-decision-list-01.json names only actual remaining acceptance/factual dependencies, not invented implementation gates.

## 11. Research and technical basis

See primary-evidence-01.json and original/source inventory; model-card/runtime capability is not actual role quality or RAM guarantee. No runtime/model/benchmark execution in this proposal.

## 12. Approval record

Pending/null. The complete ordinary Wave approval later binds accepted decisions/reference/ADRs/peer slices/estimates at one immutable commit. No release or implementation authority is created by this private draft.


## Selected policy03 and complete proposal incorporation

The exact selected policy03 is incorporated in this private successor, not adopted or measured: root-selected-policy-refinement-03.json SHA2561c40fcbe2ed959479e74305986b4b2cc7efed18d2fa7895c0a148cf07dc76d81. The genuine prior review5ced assesses the selected choices only. This complete packet still requires independent incremental review and ordinary actual authority before one immutableW3 approval.

Custom extraction/verifier promotion does not replace CAP06 retrieval or protocol-specific screening metrics. Relevant model consumers obey shared existing parser/model pre-claim admission and preserve source rights, role eligibility and unknown/denied resource states; classifier rank cannot decide inclusion/stopping.

All three full unnumbered architecture texts and complete seven-page style/workflow/page/HTML payload are included under architecture-ux/. Source3541 is current/initial only, not finalW2/G2. Actual validation/acceptance remain pending. The 48 task IDs, 16 slice IDs and 924 hours including 28 refactoring hours remain. Successor05 changes executable slice order and one explicit task dependency, and reallocates four proof hours between existing tasks; all other microtiming goals remain unchanged.

## Ordered execution feasibility05

Proposed W3 execution order: CAP-06.S01, CAP-06.S02, CAP-06.S03, CAP-06.S04, CAP-06.S05, CAP-06.S06. Every task includes explicit dependencies, its slice external dependency union and every earlier slice APPROVED gate. The64-node task/slice-gate witness is acyclic; it is source-only planned-data feasibility, not actual readiness or completed review. Preserve future-Wave decisions and states.

## Canonical proposed-publication reconciliation

Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb; the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86 identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference. All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN, security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING; no implementation is authorized.

## W3 authority recording — 2026-10-16

The owner approved the complete reviewed W3 proposal at
`45216934b81c4a437b3707df0f9e7f79a825e271` and directed implementation; see
`artifacts/evidence/W3.owner-planning-approval-20261016-01.md`.
ADR-0056, ADR-0057 and ADR-0058 are now Accepted. The exact reviewed experience
is published as RO-UI-ACADEMIC-MINIMAL-1.10 at
`3b47dfd4f332805e66c58542d3decd4e56c7f45e`, following its immutable human
design approval record. This is authority recording and material-plan binding,
with no change to selected decisions, task IDs, dependencies, criteria, proof
ownership, estimates or allocations. Earlier proposed/private wording remains
the original planning history. This paragraph applies only to the W3 contribution;
inherited decisions and future Waves retain their own authority.

The ordinary complete-Wave approval below/beside this plan binds the final
acceptance snapshot once. Taskctl readiness and dependency-eligible claims remain
mandatory; no actual model fit, quality, annotation, runtime, product proof or
release approval is supplied by planning acceptance. Minor nonfunctional styling
and eligible suggested-target median timing optimization go to W10 under the
latest owner direction; all hard functional/security/rights/resource/cancellation
limits and every raw failed or unknown result remain preserved.
