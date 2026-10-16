---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-07
capability_plan: planning/capability-plans/CAP-07.md
planning_gate: capability-decision-complete
slice_id: CAP-07.S02
title: Local model runtime and model management
status: proposed
wave: W3
priority: P0
deployment_profiles:
- LOC
- LAB
platform_targets:
- windows-x64
task_ids:
- CAP-07.S02.T01
- CAP-07.S02.T02
- CAP-07.S02.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.10
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---

# CAP-07.S02 — Local model runtime and model management

PRIVATE PROPOSAL; NO IMPLEMENTATION AUTHORITY.

## 0. Plan control

Private W3 replacement draft of `planning/slice-plans/CAP-07/CAP-07.S02-local-model-runtime-and-model-management.md`. Original hash `553b03713d2d570d4acdc3d281c6253ac9199738a3f502469a9396ca2dfe53a5`. Current canonical status NOT_STARTED is unchanged. Wave-scoped execution; the schema's legacy planning_gate spelling does not recreate capability-campaign approval. All peers bind the single Wave packet.

## 1. Purpose and contribution to the larger vision

PC/lab users can run supported models through llama.cpp-class runtimes without manually administering a model server. A supervised signed native model worker hosts pinned llama.cpp generation or ONNX CPU encoders behind ADR21. Canonical purpose-specific rights, classification and budget authority precede any allow; model selection is explicit and per role.

## 2. Scope

A supervised signed native model worker hosts pinned llama.cpp generation or ONNX CPU encoders behind ADR21. Canonical purpose-specific rights, classification and budget authority precede any allow; model selection is explicit and per role.

Non-goals: hosted infrastructure, neural training,8/16GiB model workloads, optional W9 optimization, unapproved larger-compute W5 or new physical foreign-host proof. Do not implement future synthesis/writing/publication authority.

## 3. Authority, dependencies, and campaign stop conditions

Proposed dependencies: CAP-01.S03.T03, CAP-07.S01.T03, CAP-07.S04.T02. Inherit accepted ADR21/25/26/28/29 within remit, current Windows protected lifecycle and actual W2 exit/G2 prerequisite. New proposed architecture/reference must be accepted through normal planning before W3 approval. Unknown facts stay unknown; ordinary failures/debugging are not new owner gates.

## 3A. Exact selected policy03 incorporation

The exact selected policy03 is incorporated in this private successor, not adopted or measured: root-selected-policy-refinement-03.json SHA2561c40fcbe2ed959479e74305986b4b2cc7efed18d2fa7895c0a148cf07dc76d81. The genuine prior review5ced assesses the selected choices only. This complete packet still requires independent incremental review and ordinary actual authority before one immutableW3 approval.

Task additions below preserve original forecasts as history, other proposed timing goals and hard source/rights/security/resource/cleanup requirements. They create no new task or execution authority.

## 4. Selected implementation decisions

Use the concrete proposed choices in this capability front matter and contracts-01.md. Relevant W3 decision register: CAP-07-D02, CAP-07-D03, CAP-07-D04, CAP-07-D05, CAP-07-D09, CAP-07-D10, CAP-07-D11, CAP-07-D12, CAP-07-D13, CAP-07-D14, CAP-07-D15, CAP-07-D16, CAP-07-D17, CAP-07-D18, CAP-07-D19, CAP-07-D20. Recommended != accepted. Preserve four inherited CAP07 W1 decisions exactly.

## 5. Architecture and implementation design

- Existing Core model routing policy/ports and generated gateway contracts
- New model-specific native worker broker boundary under workers/
- Model & Privacy Center and protected catalog/configuration

Current paths only. Stable generated contracts/ports, canonical transaction+provenance/outbox and narrow worker authority; no second state store or runtime evaluation dependency. Exact new filenames remain task-selected, not asserted existing.

## 6. User experience and approved reference

The complete proposed reference is architecture-ux/ui-reference/ at this packet root. Actual1.9 is the inherited base, not approval of new W3 interactions; future reference ID/approval remain null. Preserve all14 semantic1.5 workflows. MetricPolicy03 applies only to its declared roles/tasks; shared existing parser/model reservation governs relevant runtime work without imposing a new metric on unrelated retrieval/screening.

Base RO-UI-ACADEMIC-MINIMAL-1.9, exact inherited semantic catalog1.5/14keys and source-first supporting-return behavior. Apply the material proposed W3 interaction delta only after ordinary reference adoption; do not implement mock7B/GPU32k/prices as defaults. See ux-reference-proposal-01.md for keyboard/focus/status/late result contracts.

## 7. Security, privacy, rights and research integrity

Before reads/dispatch/commit/replay: exact project/session/Intent/source rights+model-use/classification/budget. Source/model output untrusted; encrypted projections/cache, no implicit network/spend, human inclusion/ethics/interpretation/final claim. Prove the material real principal boundary, not mocks alone.

## 8. Failure, cancellation, restart and recovery

Default deny survives missing catalog, expiry, OOM, crash, rights revocation, close/lock and late output. Serial unload/reload is explicit; no automatic remote/provider/model substitution. Model downloads are explicit and outside this planning task. Preserve prior accepted work, failed raw outputs and immutable actor/attempt identity. Normal owned cleanup is required for lifetime claims.

## 9. Task-by-task implementation plan

### CAP-07.S02.T01 — Integrate a supervised local inference runtime

Objective: Sidecar-managed llama.cpp-compatible runtime with health, cancellation, streaming, batching limits, hardware detection, and safe shutdown.

Dependencies: CAP-07.S01.T03, CAP-01.S03.T03, CAP-07.S04.T02. Estimate: 32 engineering-effort-hours including 8 planned refactoring hours.

Original forecast acceptance retained:

- A supported quantized model completes fixture prompts on CPU; cancellation releases resources; runtime crash does not corrupt workflow or project data.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Implement canonical grant/classification/local-zero-money reservation first, then signed no-network worker with read-only pinned artifacts/private framed pipes; Job lifetime and memory limits are additional, not the security principal.
- Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Implement canonical grant/classification/local-zero-money reservation first, then signed no-network worker with read-only pinned artifacts/private framed pipes; Job lifetime and memory limits are additional, not the security principal. Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary. Exact selected policy03 method/denominator/reservation evidence as applicable; no inferred fit/quality/people/license and no suppression of failed execution.


### CAP-07.S02.T02 — Implement model catalog, download/import, integrity, and license consent

Objective: Model manifest catalog, resumable download or local import, checksums/signatures, disk estimates, license display, and removal.

Dependencies: CAP-07.S02.T01. Estimate: 24 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Models cannot execute before integrity and license state are recorded; failed download resumes safely; removal is blocked while a job depends on the model.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Import/download has exact origin/revision/hash/tokenizer/license and user consent; staged resume verifies chunks/final hash; reject custom code, arbitrary native model extensions and redirect substitutions.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Import/download has exact origin/revision/hash/tokenizer/license and user consent; staged resume verifies chunks/final hash; reject custom code, arbitrary native model extensions and redirect substitutions.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-07.S02.T03 — Implement hardware profiles and adaptive resource limits

Objective: CPU/GPU/RAM/VRAM detection, recommended models, context/batch caps, concurrency, thermal-friendly modes, and user overrides.

Dependencies: CAP-07.S02.T02. Estimate: 22 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Low-resource test profiles remain responsive; unsafe allocations are refused or confirmed; effective limits appear in task provenance.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. User can lower caps; confirmation cannot override a hard safety cap.
- Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise.
- After complete S04 approval, retain genuine real local prompt/runtime integration: execute exact versioned prompt/schema through the signed no-network current-principal worker and canonical fixture-only qualification authority; measure admitted CPU/profile resources, actual cancellation/crash/normal drain, parser/model serialized reservation and structured/refusal handling. No mocked transport/resource pass or automatic scholarly role promotion. S05.T03 retains actual comparative gold scoring/default-upgrade proof.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. User can lower caps; confirmation cannot override a hard safety cap. Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise. After complete S04 approval, retain genuine real local prompt/runtime integration: execute exact versioned prompt/schema through the signed no-network current-principal worker and canonical fixture-only qualification authority; measure admitted CPU/profile resources, actual cancellation/crash/normal drain, parser/model serialized reservation and structured/refusal handling. No mocked transport/resource pass or automatic scholarly role promotion. S05.T03 retains actual comparative gold scoring/default-upgrade proof.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary. Exact selected policy03 method/denominator/reservation evidence as applicable; no inferred fit/quality/people/license and no suppression of failed execution. After complete S04 approval, retain genuine real local prompt/runtime integration: execute exact versioned prompt/schema through the signed no-network current-principal worker and canonical fixture-only qualification authority; measure admitted CPU/profile resources, actual cancellation/crash/normal drain, parser/model serialized reservation and structured/refusal handling. No mocked transport/resource pass or automatic scholarly role promotion. S05.T03 retains actual comparative gold scoring/default-upgrade proof.

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

Default deny survives missing catalog, expiry, OOM, crash, rights revocation, close/lock and late output. Serial unload/reload is explicit; no automatic remote/provider/model substitution. Model downloads are explicit and outside this planning task. Small-model quality and real protected-index/runtime feasibility are unmeasured. Refuse unsupported roles, retain manual/lexical usefulness, report target failures and use ordinary consequential-evidence route; no silent security/performance waiver.

## 19. Required ADRs and human decisions

The three material unnumbered architecture topics and the W3 experience delta are ordinary proposed decisions, not accepted ADRs. Reuse accepted decisions within remit; exact normal record identities assigned at planning transition. No placeholder ADR-CAP reference is treated as accepted. The one Wave approval remains pending.

## 20. Research and standards basis

See primary-evidence-01.json plus the unchanged read inventory in genuine905b. Primary docs motivate choices but do not prove installed versions, data rights, model quality, resource fit or actual results.

## 21. AI implementation runbook

No execution now. After the complete W3 packet is approved, resume its same campaign; claim the next dependency-eligible task, perform risk-selected acceptance closure, characterize, implement, commit, collect exact-candidate selected proof, submit/review/integrate, then slice/checkpoint/Wave qualification. No capability ready/start command or new GRR/GCR/controller.

## Ordered-slice execution and proof ownership05

Execution position is 2 within proposed CAP-07 W3 order: CAP-07.S04, CAP-07.S02, CAP-07.S05, CAP-07.S03. Prior capability slices requiring actual independent APPROVED completion: CAP-07.S01, CAP-07.S04. All tasks in this slice also wait for the exact external union: CAP-01.S03.T03, CAP-07.S01.T03, CAP-07.S04.T02. A task DAG alone is insufficient. No slice approval or READY state is manufactured.

After complete S04 approval, retain genuine real local prompt/runtime integration: execute exact versioned prompt/schema through the signed no-network current-principal worker and canonical fixture-only qualification authority; measure admitted CPU/profile resources, actual cancellation/crash/normal drain, parser/model serialized reservation and structured/refusal handling. No mocked transport/resource pass or automatic scholarly role promotion. S05.T03 retains actual comparative gold scoring/default-upgrade proof.

## Canonical proposed-publication reconciliation

Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb; the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86 identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference. All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN, security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING; no implementation is authorized.
