---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-06
capability_plan: planning/capability-plans/CAP-06.md
planning_gate: capability-decision-complete
slice_id: CAP-06.S06
title: Transparent screening and active-learning governance
status: approved
wave: W3
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-06.S06.T01
- CAP-06.S06.T02
- CAP-06.S06.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.10
approval:
  status: approved
  approved_by: human:repository-owner
  approved_at: '2026-10-16T13:10:45.921360+00:00'
  approved_commit: d91e6b3b280e082f824498cbd06cfa5fd09b8f1d
---
# CAP-06.S06 — Transparent screening and active-learning governance

PRIVATE PROPOSAL; NO IMPLEMENTATION AUTHORITY.

## 0. Plan control

Private W3 replacement draft of `planning/slice-plans/CAP-06/CAP-06.S06-transparent-screening-and-active-learning-governance.md`. Original hash `1cbc0d7597f95b609f6230bd0788a17e27a5736858efa4c80eaf12bf7949f9b6`. Current canonical status NOT_STARTED is unchanged. Wave-scoped execution; the schema's legacy planning_gate spelling does not recreate capability-campaign approval. All peers bind the single Wave packet.

## 1. Purpose and contribution to the larger vision

Humans retain inclusion authority while machine prioritization reduces avoidable screening labor and exposes missed-paper risk. Named humans decide inclusion and stopping. Reproducible TF-IDF/regularized linear ranking changes queue priority only, with random and citation-neighbor safety channels and manual fallback.

## 2. Scope

Named humans decide inclusion and stopping. Reproducible TF-IDF/regularized linear ranking changes queue priority only, with random and citation-neighbor safety channels and manual fallback.

Non-goals: hosted infrastructure, neural training,8/16GiB model workloads, optional W9 optimization, unapproved larger-compute W5 or new physical foreign-host proof. Do not implement future synthesis/writing/publication authority.

## 3. Authority, dependencies, and campaign stop conditions

Proposed dependencies: CAP-03.S02.T03, CAP-06.S05.T02, CAP-07.S05.T02. Inherit accepted ADR21/25/26/28/29 within remit, current Windows protected lifecycle and actual W2 exit/G2 prerequisite. New proposed architecture/reference must be accepted through normal planning before W3 approval. Unknown facts stay unknown; ordinary failures/debugging are not new owner gates.

## 4. Selected implementation decisions

Use the concrete proposed choices in this capability front matter and contracts-01.md. Relevant W3 decision register: CAP-06-D01, CAP-06-D02, CAP-06-D03, CAP-06-D04, CAP-06-D05, CAP-06-D06, CAP-06-D07, CAP-06-D08, CAP-06-D09, CAP-06-D10, CAP-06-D11, CAP-06-D12, CAP-06-D13, CAP-06-D14, CAP-06-D15, CAP-06-D16, CAP-06-D17, CAP-06-D18, CAP-06-D19, CAP-06-D20, CAP-06-D21, CAP-06-D22, CAP-06-D23. Recommended != accepted. Preserve four inherited CAP07 W1 decisions exactly.

## 5. Architecture and implementation design

- Core screening protocol/decisions/assignment commands
- Bounded non-pickle ranker worker and immutable feature/label snapshots
- Screening workspace and audit/stopping presentation

Current paths only. Stable generated contracts/ports, canonical transaction+provenance/outbox and narrow worker authority; no second state store or runtime evaluation dependency. Exact new filenames remain task-selected, not asserted existing.

## 6. User experience and approved reference

The complete proposed reference is architecture-ux/ui-reference/ at this packet root. Actual1.9 is the inherited base, not approval of new W3 interactions; future reference ID/approval remain null. Preserve all14 semantic1.5 workflows. MetricPolicy03 applies only to its declared roles/tasks; shared existing parser/model reservation governs relevant runtime work without imposing a new metric on unrelated retrieval/screening.

Base RO-UI-ACADEMIC-MINIMAL-1.9, exact inherited semantic catalog1.5/14keys and source-first supporting-return behavior. Apply the material proposed W3 interaction delta only after ordinary reference adoption; do not implement mock7B/GPU32k/prices as defaults. See ux-reference-proposal-01.md for keyboard/focus/status/late result contracts.

## 7. Security, privacy, rights and research integrity

Before reads/dispatch/commit/replay: exact project/session/Intent/source rights+model-use/classification/budget. Source/model output untrusted; encrypted projections/cache, no implicit network/spend, human inclusion/ethics/interpretation/final claim. Prove the material real principal boundary, not mocks alone.

## 8. Failure, cancellation, restart and recovery

Low labels, one class, OOM or worker failure leaves complete manual/random queues available. Retraining cannot rewrite earlier decisions; cancel retains accepted human work and marks incomplete ranking. Preserve prior accepted work, failed raw outputs and immutable actor/attempt identity. Normal owned cleanup is required for lifetime claims.

## 9. Task-by-task implementation plan

### CAP-06.S06.T01 — Implement screening protocol, queue, decisions, and conflicts

Objective: Inclusion/exclusion criteria, title/abstract/full-text stages, reasons, reviewer assignment, blinded option, decisions, and adjudication state.

Dependencies: CAP-06.S05.T02, CAP-03.S02.T03. Estimate: 20 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- No final decision lacks actor/reason/stage; criteria version is attached; conflicts remain unresolved until explicit adjudication.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Bind protocol/mode/stage and actor to immutable decisions; blind assignments enforce application query restrictions with explicit same-owner threat limit.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Bind protocol/mode/stage and actor to immutable decisions; blind assignments enforce application query restrictions with explicit same-owner threat limit.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-06.S06.T02 — Implement active-learning prioritization and model versioning

Objective: Pluggable screening ranker trained on project decisions, uncertainty sampling, predictions, model snapshots, and explanation features.

Dependencies: CAP-06.S06.T01, CAP-07.S05.T02. Estimate: 20 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Prioritization never writes inclusion decisions; retraining is reproducible from labeled data; low-data behavior and class imbalance are tested.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Bound 100k metadata records/50000 feature vocabulary/batch scheduler; no arbitrary serialized estimators or neural training. Known classes/seed/labels and feature schema reproduce ranking.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Bound 100k metadata records/50000 feature vocabulary/batch scheduler; no arbitrary serialized estimators or neural training. Known classes/seed/labels and feature schema reproduce ranking.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-06.S06.T03 — Implement random audits, citation-neighbor checks, and stopping diagnostics

Objective: Audit sampler, rejected-neighbor queue, discovery curves, residual-risk indicators, stopping proposal, and human approval.

Dependencies: CAP-06.S06.T02. Estimate: 16 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Stopping cannot be accepted without recorded audits and corpus diagnostics; deliberately hidden relevant fixtures are recoverable through at least one safety channel; limitations are explicit.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Prespecified seeded random sample + rejected-neighbor audit; hiding a relevant fixture must surface through a safety channel. Report intervals/denominators and human stopping rationale; no automatic universal95% recall claim.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Prespecified seeded random sample + rejected-neighbor audit; hiding a relevant fixture must surface through a safety channel. Report intervals/denominators and human stopping rationale; no automatic universal95% recall claim.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.

## 10. Slice-wide verification matrix

Complete this slice outcome through actual predecessor ports and real Windows local UI/Core/worker boundaries. Selected evidence: exact/happy, denial/rights revoke, invalid schema/anchor, cancel/late completion, crash/restart, migration/rebuild, OOM/unsafe resource and keyboard/focus as applicable. Cross-slice checkpoints in wave-proposal-01.json do not add human gates. All measured claims cite actual raw/criterion/candidate and limits.

## 11. Performance and resource budgets

Use the explicit proposed initial-target-register-01.json, not old p95/max forecast prose as a new timing gate. Timing decisions use median of ALL comparable completed trials per workload/state/configuration; retain min/median/max/raw/conditions, failures and timeouts. Resource/quality/rights/security/cleanup limits remain hard. No spike attribution without evidence. Models obey the total application2GiB preferred/3GiB upper aggregate and per-role tiny/small admission; see aggregate-resource-and-selection-policy-02.json. All numeric choices are proposed initial engineering targets needing actual W3 validation, not measurements or RAM/model promises. Optional optimization remains W9.

## 12. Observability and provenance

Content-free operational trace IDs/hashes/sizes/status/actual use; durable scholarly source/task/schema/model/profile/policy/actor lineage in protected canonical records. Unknown confidence/usage explicit, no raw private content in default logs.

## 13. Adjacent-slice handoffs

The explicit task edges, parent-slice external dependency unions and ordered prior-slice approval gates in task-register-01.json/ordered-slice-feasibility-witness-05.json jointly govern this proposed execution; retain all original external predecessors. Canonical persistence precedes extraction commits, runtime authority precedes positive model tasks, verifier sampling precedes bulk verification, optional remote cannot block the complete local journey.

## 14. Migration and backward compatibility

Start at actual approved predecessor schema observed28; backup-first staged migration/row+cell+object preservation/interrupted rollback/read-only incompatible handling. Index/model/prompt/schema upgrades retain historic identities and stale derived generations. Never repair original recovery fixtures or mint legacy witnesses.

## 15. Required slice evidence bundle

Criterion-linked machine manifest, actual raw commands/outcomes, exact candidate/source/runtime/fixture/policy closure, declared gold/measurement rights and human annotations, real boundary proof where claimed, source/UX/risk-selected independent review, limits/deferred coverage and adverse history.

## 16. Definition of Ready

After W2 completion/G2, all proposed W3 peers/decisions/architecture/reference and estimates receive normal immutable complete-Wave approval; actual dependency-eligible task claimed through taskctl. Task-start work refines material acceptance, not a new approval packet.

## 17. Definition of Done

All original criteria plus explicit approved W3 adaptations measured/proven, actual task dispositions integrated, end-to-end slice evidence and independent slice judgment, no invented model/human/data or ignored adverse result. No slice/task completion is asserted here.

## 18. Risks and mitigations

Low labels, one class, OOM or worker failure leaves complete manual/random queues available. Retraining cannot rewrite earlier decisions; cancel retains accepted human work and marks incomplete ranking. Small-model quality and real protected-index/runtime feasibility are unmeasured. Refuse unsupported roles, retain manual/lexical usefulness, report target failures and use ordinary consequential-evidence route; no silent security/performance waiver.

## 19. Required ADRs and human decisions

The three material unnumbered architecture topics and the W3 experience delta are ordinary proposed decisions, not accepted ADRs. Reuse accepted decisions within remit; exact normal record identities assigned at planning transition. No placeholder ADR-CAP reference is treated as accepted. The one Wave approval remains pending.

## 20. Research and standards basis

See primary-evidence-01.json plus the unchanged read inventory in genuine905b. Primary docs motivate choices but do not prove installed versions, data rights, model quality, resource fit or actual results.

## 21. AI implementation runbook

No execution now. After the complete W3 packet is approved, resume its same campaign; claim the next dependency-eligible task, perform risk-selected acceptance closure, characterize, implement, commit, collect exact-candidate selected proof, submit/review/integrate, then slice/checkpoint/Wave qualification. No capability ready/start command or new GRR/GCR/controller.

## Ordered-slice execution and proof ownership05

Execution position is 6 within proposed CAP-06 W3 order: CAP-06.S01, CAP-06.S02, CAP-06.S03, CAP-06.S04, CAP-06.S05, CAP-06.S06. Prior capability slices requiring actual independent APPROVED completion: CAP-06.S01, CAP-06.S02, CAP-06.S03, CAP-06.S04, CAP-06.S05. All tasks in this slice also wait for the exact external union: CAP-03.S02.T03, CAP-06.S05.T02, CAP-07.S05.T02. A task DAG alone is insufficient. No slice approval or READY state is manufactured.

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
