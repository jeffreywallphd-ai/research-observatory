---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-08
title: Evidence schemas, extraction, verification, and adjudication
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: pending
open_blocking_decisions: []
slice_ids:
- CAP-08.S01
- CAP-08.S03
- CAP-08.S02
- CAP-08.S04
- CAP-08.S05
- CAP-08.S06
decisions:
- id: CAP-08-D01
  title: Ontology authority
  candidates:
  - Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  - One universal fixed ontology; unconstrained per-project JSON blobs
  recommendation: Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Small stable core plus versioned, forkable schema/ontology packs; original source wording retained
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D02
  title: Extraction unit
  candidates:
  - Source passage/section candidates with immutable document revision and multi-selector anchors
  - Extract from unconstrained whole-document prompts; store page number only
  recommendation: Source passage/section candidates with immutable document revision and multi-selector anchors
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Source passage/section candidates with immutable document revision and multi-selector anchors
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D03
  title: Evidence state model
  candidates:
  - Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions
  - Flatten status to accepted/rejected or overwrite prior machine output
  recommendation: Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable
    transitions
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable
    transitions
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D04
  title: Verification independence
  candidates:
  - Separate verifier packet/prompt/role and serial execution; same-model use explicitly correlated, consequential/inferred/disputed/low-confidence
    cases require human review.
  - Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans
  - Let the extractor self-certify its own output
  recommendation: Separate verifier packet/prompt/role and serial execution; same-model use explicitly correlated, consequential/inferred/disputed/low-confidence
    cases require human review.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Separate verifier packet/prompt/role and serial execution; same-model use explicitly correlated, consequential/inferred/disputed/low-confidence
    cases require human review.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D05
  title: Confidence representation
  candidates:
  - Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  - Single uncalibrated “AI confidence” number
  recommendation: Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D06
  title: Core scope
  candidates:
  - Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity
    references; domain detail lives in packs.
  - Large universal scholarly ontology.
  recommendation: Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision
    and opportunity references; domain detail lives in packs.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision
    and opportunity references; domain detail lives in packs.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D07
  title: Schema format
  candidates:
  - JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.
  - Free-form JSON or OWL-only authoring.
  recommendation: JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for
    export.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D08
  title: Evolution
  candidates:
  - Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview.
  - Edit schema in place and reinterpret old records.
  recommendation: Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration
    preview.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration
    preview.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D09
  title: Selection strategy
  candidates:
  - Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included
    and excluded rationale.
  - Send full PDFs by default.
  recommendation: Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet
    records included and excluded rationale.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet
    records included and excluded rationale.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D10
  title: Absence handling
  candidates:
  - Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema.
  - Force a value or use null without meaning.
  recommendation: Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according
    to schema.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according
    to schema.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D11
  title: Normalization
  candidates:
  - Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation
    until human/rule acceptance.
  - Replace source language with closest ontology term automatically.
  recommendation: Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical
    observation until human/rule acceptance.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical
    observation until human/rule acceptance.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D12
  title: Record identity
  candidates:
  - UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  - Use field/value as primary key.
  recommendation: UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D13
  title: Transition authority
  candidates:
  - Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record.
  - Direct status column edits.
  recommendation: Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new
    resolution record.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new
    resolution record.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D14
  title: Confidence
  candidates:
  - Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  - Average model confidence values.
  recommendation: Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Store component assessments and calibration bands, with “unknown/not assessed” first-class.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D15
  title: Independence
  candidates:
  - Verifier sees candidate plus exact cited source/schema, not extractor rationale; distinct evaluated model preferred only
    when resource-eligible, never an independence claim from a second prompt.
  - Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably
    independently evaluated model route.
  - Ask extractor to self-critique in the same context.
  recommendation: Verifier sees candidate plus exact cited source/schema, not extractor rationale; distinct evaluated model
    preferred only when resource-eligible, never an independence claim from a second prompt.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Verifier sees candidate plus exact cited source/schema, not extractor rationale; distinct evaluated model
    preferred only when resource-eligible, never an independence claim from a second prompt.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D16
  title: Decision dimensions
  candidates:
  - Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments.
  - One pass/fail or confidence score.
  recommendation: Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate
    judgments.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate
    judgments.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D17
  title: Human sampling
  candidates:
  - Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error
    with confidence intervals.
  - Review a convenient untracked sample.
  recommendation: Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement;
    estimate error with confidence intervals.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement;
    estimate error with confidence intervals.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D18
  title: Grid architecture
  candidates:
  - Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance.
  - Client-load all records or embed an uncontrolled spreadsheet engine.
  recommendation: Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and
    provenance.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and
    provenance.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D19
  title: Editing
  candidates:
  - All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow.
  - In-place overwrite of accepted evidence.
  recommendation: All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens
    the correct workflow.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens
    the correct workflow.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D20
  title: Source interaction
  candidates:
  - Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns
    to cell.
  - Open unrelated modal/browser window for each source.
  recommendation: Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard
    focus returns to cell.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard
    focus returns to cell.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D21
  title: Assignment independence
  candidates:
  - Application-level local named-coder blinding/immutable assignments, explicit same Windows project-owner/admin limits;
    no hosted identity or physical foreign-host claim.
  - Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed.
  - Collaborative live editing as the only mode.
  recommendation: Application-level local named-coder blinding/immutable assignments, explicit same Windows project-owner/admin
    limits; no hosted identity or physical foreign-host claim.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Application-level local named-coder blinding/immutable assignments, explicit same Windows project-owner/admin
    limits; no hosted identity or physical foreign-host claim.
  status: accepted
  required_adr: ADR-0058
  binding_waves:
  - W3
- id: CAP-08-D22
  title: Agreement metrics
  candidates:
  - 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered
    categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  - One universal agreement percent.
  recommendation: 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa
    for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: 'Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa
    for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.'
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-08-D23
  title: Adjudication
  candidates:
  - Create a named resolution record referencing all coder records and allow unresolved outcome.
  - Replace coder records with consensus value.
  recommendation: Create a named resolution record referencing all coder records and allow unresolved outcome.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Create a named resolution record referencing all coder records and allow unresolved outcome.
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
  - work_id: CAP-08.S01.T01
    effort: 16
  - work_id: CAP-08.S01.T02
    effort: 20
  - work_id: CAP-08.S01.T03
    effort: 16
  - work_id: CAP-08.S03.T01
    effort: 24
  - work_id: CAP-08.S03.T02
    effort: 20
  - work_id: CAP-08.S03.T03
    effort: 16
  - work_id: CAP-08.S02.T01
    effort: 20
  - work_id: CAP-08.S02.T02
    effort: 24
  - work_id: CAP-08.S02.T03
    effort: 16
  - work_id: CAP-08.S04.T01
    effort: 20
  - work_id: CAP-08.S04.T02
    effort: 20
  - work_id: CAP-08.S04.T03
    effort: 16
  - work_id: CAP-08.S05.T01
    effort: 24
  - work_id: CAP-08.S05.T02
    effort: 20
  - work_id: CAP-08.S05.T03
    effort: 20
  - work_id: CAP-08.S06.T01
    effort: 20
  - work_id: CAP-08.S06.T02
    effort: 16
  - work_id: CAP-08.S06.T03
    effort: 16
  refactoring_items:
  - work_id: CAP-08.S03.T01
    effort: 8
    reason: Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not
      an additional task or double-counted estimate.
    id: CAP-08.S03.T01
    introduced_in_wave: W3
    changes_existing_implementation: true
    major_refactor: false
    disposition: included
    description: "Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not an additional task or double-counted estimate."
  - work_id: CAP-08.S05.T02
    effort: 4
    reason: Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not
      an additional task or double-counted estimate.
    id: CAP-08.S05.T02
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

# CAP-08 — Evidence schemas, extraction, verification, and adjudication

PRIVATE PROPOSED W3 CONTRIBUTION. Approval, accepted status and execution remain pending. Original source: `planning/capability-plans/CAP-08.md` / `ddf910493846d24572db880ad5dc1c6109eda4f4e7d03bc8774a0d46c9f4d084`. Preserve inherited W1 selections; recommended W3 values are resolved draft choices subject to one complete Wave review, not existing approvals. `required_adr: null` here does not waive the three material architecture topics; unassigned historical ADR-CAP placeholders are replaced by the explicit topic register.

## 0. Control and authority

The Wave owns execution/integration/qualification and G3 handoff. Capability is an outcome map, not a lease. Immutable IDs and prior approvals stay unchanged; all proposed decisions are classified by Wave in front matter.

## 0A. Initiation assessment and planning adaptation

Reuse genuine905b source assessment and the baseline/source inventory. Full48 atomic estimates are in task-register-01.json; no slice+task double count. See contracts-01.md for baseline fit, exact resource/rights model and deferred work.

## 1. Capability outcome and production-ready exit

Transform full text into source-grounded, mode-sensitive evidence records that distinguish observation, machine extraction, inference, verification, dispute, adjudication, and staleness. W3 exit covers only these contributing slices, actual benchmark limits, real authority and human review, not unimplemented future capabilities.

## 2. Slice map and end-to-end dependency logic

- CAP-08.S01: Core ontology and schema-pack registry — Small stable ontology and forkable data-only schema packs preserve source wording, definitions, alternatives, units and version identity. Domain packs cannot execute code or fetch remote contexts.
- CAP-08.S03: Evidence record, status, confidence, and uncertainty model — Extend the current EvidenceRecord/provenance/dependency aggregate, with immutable revisions and explicitly authorized statuses and uncertainty dimensions; no second canonical state store.
- CAP-08.S02: Source-grounded extraction pipeline — Immutable exact-anchor packets feed a chosen evaluated local model. Extraction emits only source-grounded candidates and explicit missingness; deterministic normalization produces alternatives without overwriting raw wording.
- CAP-08.S04: Independent evidence verification — Verifier receives candidate, source packet and schema with a separate role/context, without extractor rationale. Same-model serial verification is disclosed as correlated; human review owns consequential claims.
- CAP-08.S05: Evidence matrix and source-first analysis UI — Core cursor/filter queries and row/column virtualization expose evidence states and sources. Corrections/adjudications are commands with previews, never unlogged spreadsheet overwrites.
- CAP-08.S06: Coder comparison, adjudication, and evidence export — Local coder assignments, documented blinding limits, appropriate agreement statistics and human adjudication preserve plurality; rights-aware evidence exports carry codebook/provenance and explicit AI-use limits.

This is the actual proposed capability.slices execution order, not numeric ID order. Every earlier slice needs genuine APPROVED completion before later tasks; exact external dependency unions apply to every task. See ordered-slice-feasibility-witness-05.json. Inherited/future slice objects and identities are unchanged.

## 3. Decision-making protocol

Every W3 decision has at least two candidates and a concrete recommended selection. The authored proposed plan selects the reviewed options using the existing capability-plan status `accepted`; this records plan-option completeness only. Proposed ADRs, the proposed reference1.10 and Wave approval remain pending and grant no implementation authority. Record independent review/any override rationale and material ADR/reference decisions in the ordinary single Wave packet.

## 4. Decision register

Selections below are the recorded proposed-plan choices; the capability/Wave approval remains PENDING. Inherited accepted authority retains its original scope. Full metadata and alternatives remain in the front matter.

| Decision | Alternatives | Recorded choice | Rationale | Required ADR |
|---|---|---|---|---|
| `CAP-08-D01` — Ontology authority | Small stable core plus versioned, forkable schema/ontology packs; original source wording retained<br>One universal fixed ontology; unconstrained per-project JSON blobs | Small stable core plus versioned, forkable schema/ontology packs; original source wording retained | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D02` — Extraction unit | Source passage/section candidates with immutable document revision and multi-selector anchors<br>Extract from unconstrained whole-document prompts; store page number only | Source passage/section candidates with immutable document revision and multi-selector anchors | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D03` — Evidence state model | Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions<br>Flatten status to accepted/rejected or overwrite prior machine output | Observed, Extracted, Inferred, Verified, Disputed, Adjudicated and Stale are explicit states with immutable transitions | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D04` — Verification independence | Separate verifier packet/prompt/role and serial execution; same-model use explicitly correlated, consequential/inferred/disputed/low-confidence cases require human review.<br>Separate verifier run, prompt/model role and evidence contract; route low-confidence or consequential cases to humans<br>Let the extractor self-certify its own output | Separate verifier packet/prompt/role and serial execution; same-model use explicitly correlated, consequential/inferred/disputed/low-confidence cases require human review. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D05` — Confidence representation | Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty<br>Single uncalibrated “AI confidence” number | Decomposed retrieval, anchor, extraction, schema-fit, comparability and interpretation uncertainty | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D06` — Core scope | Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs.<br>Large universal scholarly ontology. | Core covers work/document/passage, claim/evidence, theory/construct/method/context, provenance/status/decision and opportunity references; domain detail lives in packs. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D07` — Schema format | JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export.<br>Free-form JSON or OWL-only authoring. | JSON Schema 2020-12 for record shape plus a constrained semantic-rule registry and JSON-LD context for export. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D08` — Evolution | Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview.<br>Edit schema in place and reinterpret old records. | Immutable pack versions, explicit compatible/breaking diff, project pinning, fork lineage and migration preview. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D09` — Selection strategy | Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale.<br>Send full PDFs by default. | Deterministic structural/lexical retrieval plus optional semantic reranking selects bounded passages; packet records included and excluded rationale. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D10` — Absence handling | Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema.<br>Force a value or use null without meaning. | Every field supports observed value, not reported, unclear, inapplicable and inferred candidate according to schema. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D11` — Normalization | Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance.<br>Replace source language with closest ontology term automatically. | Generate ranked entity-link candidates with lexical/semantic evidence; original source string remains canonical observation until human/rule acceptance. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D12` — Record identity | UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate.<br>Use field/value as primary key. | UUIDv7 evidence assertion identity plus immutable revision/attempt IDs; semantic duplicate linking is separate. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D13` — Transition authority | Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record.<br>Direct status column edits. | Commands enforce allowed state transitions, actor role and required evidence; adjudication creates a new resolution record. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D14` — Confidence | Store component assessments and calibration bands, with “unknown/not assessed” first-class.<br>Average model confidence values. | Store component assessments and calibration bands, with “unknown/not assessed” first-class. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D15` — Independence | Verifier sees candidate plus exact cited source/schema, not extractor rationale; distinct evaluated model preferred only when resource-eligible, never an independence claim from a second prompt.<br>Verifier receives candidate plus cited passages and schema, not extractor rationale; use separate prompt role and preferably independently evaluated model route.<br>Ask extractor to self-critique in the same context. | Verifier sees candidate plus exact cited source/schema, not extractor rationale; distinct evaluated model preferred only when resource-eligible, never an independence claim from a second prompt. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D16` — Decision dimensions | Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments.<br>One pass/fail or confidence score. | Return anchor-valid, entailed/contradicted/insufficient, schema-fit and inference-supported as separate judgments. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D17` — Human sampling | Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals.<br>Review a convenient untracked sample. | Stratify by field consequence, model/version, confidence band, schema, novelty and detected disagreement; estimate error with confidence intervals. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D18` — Grid architecture | Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance.<br>Client-load all records or embed an uncontrolled spreadsheet engine. | Server/core-side filtered cursor queries plus row/column virtualization; cells render domain status and provenance. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D19` — Editing | All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow.<br>In-place overwrite of accepted evidence. | All changes are explicit candidate/correction/adjudication commands with preview; direct cell edit opens the correct workflow. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D20` — Source interaction | Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell.<br>Open unrelated modal/browser window for each source. | Persistent details drawer with passage, anchor, document context, verifier, alternatives and history; keyboard focus returns to cell. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D21` — Assignment independence | Application-level local named-coder blinding/immutable assignments, explicit same Windows project-owner/admin limits; no hosted identity or physical foreign-host claim.<br>Optional blinding prevents coders seeing peer decisions until submission; assignment and protocol versions are fixed.<br>Collaborative live editing as the only mode. | Application-level local named-coder blinding/immutable assignments, explicit same Windows project-owner/admin limits; no hosted identity or physical foreign-host claim. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0058 |
| `CAP-08-D22` — Agreement metrics | Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness.<br>One universal agreement percent. | Report raw agreement and field-appropriate statistics: Cohen kappa for two nominal coders, weighted kappa for ordered categories, Krippendorff alpha for multiple/missing data; always show N and missingness. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-08-D23` — Adjudication | Create a named resolution record referencing all coder records and allow unresolved outcome.<br>Replace coder records with consensus value. | Create a named resolution record referencing all coder records and allow unresolved outcome. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |

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

### Exact selected extraction policy03

**evaluationUnit**: One frozen eligible (QASPER question ID, declared simple extractive field ID) with existing human answer annotations and authenticated source-anchor mapping. Missing, unanswerable, unsupported and free-form strata remain separately reported; never silently relabel them positive extractive units.

**normalization**: For this custom adapter score only: Unicode NFC and CRLF/CR to LF, then Unicode casefold. Tokenize with Unicode regular expression \w+|[^\w\s], retaining punctuation tokens and duplicate token multiplicities. No stemming, article deletion, synonym/model judging or source-text rewriting. Keep original strings and exact source offsets separately.

**matching**: Each retained acceptable human answer annotation is one reference. Concatenate its ordered extractive spans with one space for token scoring, preserving the original individual spans and anchors. Match token multisets by sum of minimum token counts. Compute precision=overlap/predictionTokens and recall=overlap/referenceTokens. Choose the reference with greatest token F1, then precision, then stable original annotation order. Freeze acceptable-reference membership before comparison; do not assemble one reference from incompatible annotators or invent a missing reference.

**emptyPrediction**: On an answerable eligible unit, absent output, explicit abstention or an empty token sequence gives precision=0 and recall=0. An empty/undefined positive reference is not an eligible answerable unit and requires a visible mapping correction before comparison. Failed/timed-out execution is still a failed run, not a scored abstention.

**aggregation**: Average per-unit precision and recall within each declared eligible field, then give each field equal weight in the field macro. Publish each field's N, metrics and all unit outcomes. No consequential field that fails its declared threshold is hidden by the macro. Pooled micro/token-F1 and exact-span match are separate diagnostics, not alternative passing rules.

**promotionTargets**: {"macroPrecisionMinimum": 0.9, "macroRecallMinimum": 0.8}

**answerKindAndMissingness**: Keep fixed per-kind confusion, absent/unsupported counts, packet evidence coverage/truncation and hallucinated outputs on actual unanswerable cases. Missing gold or an unsupported stratum is not a free correct answer. Anchor/schema/rights denials remain deterministic hard checks.

**scope**: This is the selected custom initial QASPER adapter metric, not a claim of official leaderboard equivalence, universal scientific extraction or measured quality. Preserve source annotations, annotator disagreement and bounded domain claims.

### Exact selected verifier policy03

**labels**: ["SUPPORTS", "REFUTES", "NOT_ENOUGH_EVIDENCE", "ABSTAIN"]

**evaluationFrame**: The complete frozen eligible SciFact development frame with actual source labels and rationale mappings, including declared no-evidence cases. Report exact class Ns, exclusions and unknown/unjudged scope before any candidate comparison.

**precisionRule**: For each actionable label SUPPORTS and REFUTES, TP is an exact predicted/gold label match and FP is that predicted label against another actual judged gold label, including NOT_ENOUGH_EVIDENCE. Require the arithmetic mean of these two per-label precisions >=0.90. An absent or zero prediction denominator for either required label is undefined and cannot pass.

**recallRule**: Require TP_SUPPORTS/N_gold_SUPPORTS >=0.80 and TP_REFUTES/N_gold_REFUTES >=0.80 separately. ABSTAIN, missing predictions and wrong labels count as misses. A missing required gold class leaves that role's qualification unestablished; do not invent class members or substitute a pooled metric.

**answeredCoverageRule**: Require the number of valid explicit SUPPORTS, REFUTES or NOT_ENOUGH_EVIDENCE decisions divided by the complete eligible frame N >=0.80. ABSTAIN is unanswered. Technical failures, invalid output and timeouts remain hard failures and cannot be converted into abstention or excluded units.

**diagnostics**: Publish the complete confusion matrix, all per-class precision/recall, answered coverage, abstentions, rationale/anchor coverage and uncertainty intervals with actual Ns and method. NOT_ENOUGH_EVIDENCE is distinct from REFUTES and ABSTAIN. Unjudged evidence is never invented negative gold.

**humanAuthority**: These bounded initial targets do not certify scholarly truth or replace mandatory human review of consequential, inferred, disputed or low-confidence candidates. Same-model serial verification remains correlated, not independent-model evidence.

All model execution uses the existing shared pre-claim parser/model reservation, with no independent concurrent-fit claim.

All three full unnumbered architecture texts and complete seven-page style/workflow/page/HTML payload are included under architecture-ux/. Source3541 is current/initial only, not finalW2/G2. Actual validation/acceptance remain pending. The 48 task IDs, 16 slice IDs and 924 hours including 28 refactoring hours remain. Successor05 changes executable slice order and one explicit task dependency, and reallocates four proof hours between existing tasks; all other microtiming goals remain unchanged.

## Ordered execution feasibility05

Proposed W3 execution order: CAP-08.S01, CAP-08.S03, CAP-08.S02, CAP-08.S04, CAP-08.S05, CAP-08.S06. Every task includes explicit dependencies, its slice external dependency union and every earlier slice APPROVED gate. The64-node task/slice-gate witness is acyclic; it is source-only planned-data feasibility, not actual readiness or completed review. Preserve future-Wave decisions and states.

## Canonical proposed-publication reconciliation

Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb; the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86 identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference. All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN, security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING; no implementation is authorized.
