---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-08
capability_plan: planning/capability-plans/CAP-08.md
planning_gate: capability-decision-complete
slice_id: CAP-08.S01
title: Core ontology and schema-pack registry
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
- CAP-08.S01.T01
- CAP-08.S01.T02
- CAP-08.S01.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.10
approval:
  status: approved
  approved_by: human:repository-owner
  approved_at: '2026-10-16T13:10:45.921360+00:00'
  approved_commit: d91e6b3b280e082f824498cbd06cfa5fd09b8f1d
---
# CAP-08.S01 — Core ontology and schema-pack registry

PRIVATE PROPOSAL; NO IMPLEMENTATION AUTHORITY.

## 0. Plan control

Private W3 replacement draft of `planning/slice-plans/CAP-08/CAP-08.S01-core-ontology-and-schema-pack-registry.md`. Original hash `2c786153da331d34392421284cd6770fc2b381a437b0ff6cba3eca2f69122bad`. Current canonical status NOT_STARTED is unchanged. Wave-scoped execution; the schema's legacy planning_gate spelling does not recreate capability-campaign approval. All peers bind the single Wave packet.

## 1. Purpose and contribution to the larger vision

A small stable scholarly core can be extended by domain and method packs under explicit version governance. Small stable ontology and forkable data-only schema packs preserve source wording, definitions, alternatives, units and version identity. Domain packs cannot execute code or fetch remote contexts.

## 2. Scope

Small stable ontology and forkable data-only schema packs preserve source wording, definitions, alternatives, units and version identity. Domain packs cannot execute code or fetch remote contexts.

Non-goals: hosted infrastructure, neural training,8/16GiB model workloads, optional W9 optimization, unapproved larger-compute W5 or new physical foreign-host proof. Do not implement future synthesis/writing/publication authority.

## 3. Authority, dependencies, and campaign stop conditions

Proposed dependencies: CAP-03.S01.T03, CAP-07.S04.T02. Inherit accepted ADR21/25/26/28/29 within remit, current Windows protected lifecycle and actual W2 exit/G2 prerequisite. New proposed architecture/reference must be accepted through normal planning before W3 approval. Unknown facts stay unknown; ordinary failures/debugging are not new owner gates.

## 4. Selected implementation decisions

Use the concrete proposed choices in this capability front matter and contracts-01.md. Relevant W3 decision register: CAP-08-D01, CAP-08-D02, CAP-08-D03, CAP-08-D04, CAP-08-D05, CAP-08-D06, CAP-08-D07, CAP-08-D08, CAP-08-D09, CAP-08-D10, CAP-08-D11, CAP-08-D12, CAP-08-D13, CAP-08-D14, CAP-08-D15, CAP-08-D16, CAP-08-D17, CAP-08-D18, CAP-08-D19, CAP-08-D20, CAP-08-D21, CAP-08-D22, CAP-08-D23. Recommended != accepted. Preserve four inherited CAP07 W1 decisions exactly.

## 5. Architecture and implementation design

- Core ontology/schema repository and portable pack contracts
- Schema & Ontology Manager
- Rights-aware pack export and bounded semantic-rule interpreter

Current paths only. Stable generated contracts/ports, canonical transaction+provenance/outbox and narrow worker authority; no second state store or runtime evaluation dependency. Exact new filenames remain task-selected, not asserted existing.

## 6. User experience and approved reference

The complete proposed reference is architecture-ux/ui-reference/ at this packet root. Actual1.9 is the inherited base, not approval of new W3 interactions; future reference ID/approval remain null. Preserve all14 semantic1.5 workflows. MetricPolicy03 applies only to its declared roles/tasks; shared existing parser/model reservation governs relevant runtime work without imposing a new metric on unrelated retrieval/screening.

Base RO-UI-ACADEMIC-MINIMAL-1.9, exact inherited semantic catalog1.5/14keys and source-first supporting-return behavior. Apply the material proposed W3 interaction delta only after ordinary reference adoption; do not implement mock7B/GPU32k/prices as defaults. See ux-reference-proposal-01.md for keyboard/focus/status/late result contracts.

## 7. Security, privacy, rights and research integrity

Before reads/dispatch/commit/replay: exact project/session/Intent/source rights+model-use/classification/budget. Source/model output untrusted; encrypted projections/cache, no implicit network/spend, human inclusion/ethics/interpretation/final claim. Prove the material real principal boundary, not mocks alone.

## 8. Failure, cancellation, restart and recovery

Drafts cannot affect pinned evidence. Compatible/breaking diff and migration preview are explicit; failed import stays quarantined and cannot change active pack. Preserve prior accepted work, failed raw outputs and immutable actor/attempt identity. Normal owned cleanup is required for lifetime claims.

## 9. Task-by-task implementation plan

### CAP-08.S01.T01 — Implement the stable core ontology and relation vocabulary

Objective: Versioned entities and relations for works, passages, theories, constructs, definitions, methods, measures, contexts, claims, findings, assumptions, stakeholders, and opportunities.

Dependencies: CAP-03.S01.T03, CAP-07.S04.T02. Estimate: 16 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Terms have stable IDs, labels, definitions, provenance, allowed relations, and deprecation rules; competing definitions are representable rather than overwritten.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Stable IDs/deprecation/relations and competing definitions, with no automatic global ontology merge.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Stable IDs/deprecation/relations and competing definitions, with no automatic global ontology merge.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-08.S01.T02 — Implement extraction-schema authoring and validation

Objective: Schema editor and API for fields, types, cardinality, controlled vocabularies, evidence requirements, prompts, verification, and mode applicability.

Dependencies: CAP-08.S01.T01. Estimate: 20 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Invalid or cyclic schema dependencies fail before use; required evidence rules are explicit; schema drafts cannot silently change completed extractions.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Bounded acyclic dependencies, field cardinality/evidence/missingness rules and versioned allowed semantics; no eval/Python/plugin expressions or remote schema resolution.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Bounded acyclic dependencies, field cardinality/evidence/missingness rules and versioned allowed semantics; no eval/Python/plugin expressions or remote schema resolution.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-08.S01.T03 — Implement ontology/schema import, export, fork, and version comparison

Objective: Portable pack format with manifest, dependencies, mappings, license, signatures/checksums, and structured diff.

Dependencies: CAP-08.S01.T02. Estimate: 16 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Imported packs are validated in isolation; project forks receive new identity; upgrades preview affected evidence and require explicit adoption.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Manifest/license/hash and fork lineage required; unsafe archive names/reparse/zip bombs denied; preview affected evidence before explicit adoption.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Manifest/license/hash and fork lineage required; unsafe archive names/reparse/zip bombs denied; preview affected evidence before explicit adoption.
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

Drafts cannot affect pinned evidence. Compatible/breaking diff and migration preview are explicit; failed import stays quarantined and cannot change active pack. Small-model quality and real protected-index/runtime feasibility are unmeasured. Refuse unsupported roles, retain manual/lexical usefulness, report target failures and use ordinary consequential-evidence route; no silent security/performance waiver.

## 19. Required ADRs and human decisions

The three material unnumbered architecture topics and the W3 experience delta are ordinary proposed decisions, not accepted ADRs. Reuse accepted decisions within remit; exact normal record identities assigned at planning transition. No placeholder ADR-CAP reference is treated as accepted. The one Wave approval remains pending.

## 20. Research and standards basis

See primary-evidence-01.json plus the unchanged read inventory in genuine905b. Primary docs motivate choices but do not prove installed versions, data rights, model quality, resource fit or actual results.

## 21. AI implementation runbook

No execution now. After the complete W3 packet is approved, resume its same campaign; claim the next dependency-eligible task, perform risk-selected acceptance closure, characterize, implement, commit, collect exact-candidate selected proof, submit/review/integrate, then slice/checkpoint/Wave qualification. No capability ready/start command or new GRR/GCR/controller.

## Ordered-slice execution and proof ownership05

Execution position is 1 within proposed CAP-08 W3 order: CAP-08.S01, CAP-08.S03, CAP-08.S02, CAP-08.S04, CAP-08.S05, CAP-08.S06. Prior capability slices requiring actual independent APPROVED completion: none. All tasks in this slice also wait for the exact external union: CAP-03.S01.T03, CAP-07.S04.T02. A task DAG alone is insufficient. No slice approval or READY state is manufactured.

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
