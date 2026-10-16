---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-07
capability_plan: planning/capability-plans/CAP-07.md
planning_gate: capability-decision-complete
slice_id: CAP-07.S03
title: Approved remote model providers
status: proposed
wave: W3
priority: P1
deployment_profiles:
- LOC
- LAB
- UNI
- CLD
platform_targets:
- windows-x64
task_ids:
- CAP-07.S03.T01
- CAP-07.S03.T02
- CAP-07.S03.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.10
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---

# CAP-07.S03 — Approved remote model providers

PRIVATE PROPOSAL; NO IMPLEMENTATION AUTHORITY.

## 0. Plan control

Private W3 replacement draft of `planning/slice-plans/CAP-07/CAP-07.S03-approved-remote-model-providers.md`. Original hash `e2fc97be28ae1455d2ab8e65d3d50da67e1ba5a46a3fa6ff79026f66d5c58c93`. Current canonical status NOT_STARTED is unchanged. Wave-scoped execution; the schema's legacy planning_gate spelling does not recreate capability-campaign approval. All peers bind the single Wave packet.

## 1. Purpose and contribution to the larger vision

Remote inference is available through explicit opt-in adapters with redaction, data-class, and reproducibility controls. OpenAI-compatible and Anthropic transport adapters behind the gateway, optional and disabled by default. No account is required for the local G3 journey and no credentials, live calls or spend are assumed in the W3 plan.

## 2. Scope

OpenAI-compatible and Anthropic transport adapters behind the gateway, optional and disabled by default. No account is required for the local G3 journey and no credentials, live calls or spend are assumed in the W3 plan.

Non-goals: hosted infrastructure, neural training,8/16GiB model workloads, optional W9 optimization, unapproved larger-compute W5 or new physical foreign-host proof. Do not implement future synthesis/writing/publication authority.

## 3. Authority, dependencies, and campaign stop conditions

Proposed dependencies: CAP-02.S04.T01, CAP-07.S01.T03, CAP-07.S04.T02, CAP-07.S05.T02. Inherit accepted ADR21/25/26/28/29 within remit, current Windows protected lifecycle and actual W2 exit/G2 prerequisite. New proposed architecture/reference must be accepted through normal planning before W3 approval. Unknown facts stay unknown; ordinary failures/debugging are not new owner gates.

## 4. Selected implementation decisions

Use the concrete proposed choices in this capability front matter and contracts-01.md. Relevant W3 decision register: CAP-07-D02, CAP-07-D03, CAP-07-D04, CAP-07-D05, CAP-07-D09, CAP-07-D10, CAP-07-D11, CAP-07-D12, CAP-07-D13, CAP-07-D14, CAP-07-D15, CAP-07-D16, CAP-07-D17, CAP-07-D18, CAP-07-D19, CAP-07-D20. Recommended != accepted. Preserve four inherited CAP07 W1 decisions exactly.

## 5. Architecture and implementation design

- Provider-specific adapter modules under current Core composition
- Core exact payload resolver/consent and OS credential port
- Model & Privacy Center preview/offline controls

Current paths only. Stable generated contracts/ports, canonical transaction+provenance/outbox and narrow worker authority; no second state store or runtime evaluation dependency. Exact new filenames remain task-selected, not asserted existing.

## 6. User experience and approved reference

The complete proposed reference is architecture-ux/ui-reference/ at this packet root. Actual1.9 is the inherited base, not approval of new W3 interactions; future reference ID/approval remain null. Preserve all14 semantic1.5 workflows. MetricPolicy03 applies only to its declared roles/tasks; shared existing parser/model reservation governs relevant runtime work without imposing a new metric on unrelated retrieval/screening.

Base RO-UI-ACADEMIC-MINIMAL-1.9, exact inherited semantic catalog1.5/14keys and source-first supporting-return behavior. Apply the material proposed W3 interaction delta only after ordinary reference adoption; do not implement mock7B/GPU32k/prices as defaults. See ux-reference-proposal-01.md for keyboard/focus/status/late result contracts.

## 7. Security, privacy, rights and research integrity

Before reads/dispatch/commit/replay: exact project/session/Intent/source rights+model-use/classification/budget. Source/model output untrusted; encrypted projections/cache, no implicit network/spend, human inclusion/ethics/interpretation/final claim. Prove the material real principal boundary, not mocks alone.

## 8. Failure, cancellation, restart and recovery

Missing credentials, unknown provider retention/price, budget, cancellation or revocation denies before network. Offline queued jobs become blocked; they do not wait with secret plaintext payloads or silently route elsewhere. Preserve prior accepted work, failed raw outputs and immutable actor/attempt identity. Normal owned cleanup is required for lifetime claims.

## 9. Task-by-task implementation plan

### CAP-07.S03.T01 — Implement the first two external provider adapters behind the gateway

Objective: Typed adapters for approved commercial/open endpoints with streaming, structured output, retries, rate handling, and normalized errors.

Dependencies: CAP-07.S01.T03, CAP-02.S04.T01, CAP-07.S04.T02, CAP-07.S05.T02. Estimate: 20 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Provider-specific code does not leak into scholarly modules; contract tests replay recorded safe fixtures; missing credentials produce guided setup.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Safe recorded/synthetic protocol fixtures prove both translations, streaming cancellation, normalized usage/errors and no SDK leakage. Clearly label transport conformance separately from a live qualified commercial provider.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Safe recorded/synthetic protocol fixtures prove both translations, streaming cancellation, normalized usage/errors and no SDK leakage. Clearly label transport conformance separately from a live qualified commercial provider.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-07.S03.T02 — Implement egress preview, minimization, and consent

Objective: Preflight showing provider, data class, text amount, rights status, redactions, retention policy link, and local alternative.

Dependencies: CAP-07.S03.T01. Estimate: 24 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Protected or rights-restricted text is blocked by policy; user consent is scoped and revocable; the exact transmitted payload hash is logged without storing unnecessary plaintext.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Hash exact assembled/minimized packet, destination, terms/retention observation, data-class/rights, scope/expiry and budget; any material change invalidates consent; never consent on behalf of another source rights holder.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Hash exact assembled/minimized packet, destination, terms/retention observation, data-class/rights, scope/expiry and budget; any material change invalidates consent; never consent on behalf of another source rights holder.
4. Commit then collect criterion-linked exact-candidate evidence with stable selected inputs/normal owned cleanup; independent task disposition and integration.

Evidence/review: Independent commit-bound task disposition; deeper review for policy, model/worker isolation, rights/egress, migrations, cross-process contracts and research-integrity changes. Machine-readable criterion/outcome map with actual candidate/source/runtime/fixtures and raw receipts; failures/skips/limits retained. Happy path plus the material denial/cancel/restart/recovery/rights/staleness cases selected by this task and contracts-01.md. Actual resource/timing/quality evidence for claims made; fixtures do not prove a real security or model boundary.


### CAP-07.S03.T03 — Implement offline/network-disabled enforcement and remote fallback behavior

Objective: Application and service controls that disable remote providers, fail closed, and continue with supported local paths.

Dependencies: CAP-07.S03.T02. Estimate: 16 engineering-effort-hours including 0 planned refactoring hours.

Original forecast acceptance retained:

- Network-disabled tests prove no external DNS/HTTP attempts from AI modules; queued remote jobs become blocked with clear remediation rather than silently rerouted.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

Explicit W3 adaptation/additional closure:

- Deny before DNS/HTTP in offline mode; active revocation cancels/denies late results. Only explicitly permitted public/open source classes may activate remote routes under the initial W3 policy.

Ordered implementation:

1. Risk-selected task-start acceptance-closure; inspect current predecessor and material adverse findings; characterize the material boundary before production changes where practical.
2. Implement the bounded contract through existing Core/worker/generated ports; preserve immutable history and update compatibility/migration as needed.
3. Deny before DNS/HTTP in offline mode; active revocation cancels/denies late results. Only explicitly permitted public/open source classes may activate remote routes under the initial W3 policy.
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

Missing credentials, unknown provider retention/price, budget, cancellation or revocation denies before network. Offline queued jobs become blocked; they do not wait with secret plaintext payloads or silently route elsewhere. Small-model quality and real protected-index/runtime feasibility are unmeasured. Refuse unsupported roles, retain manual/lexical usefulness, report target failures and use ordinary consequential-evidence route; no silent security/performance waiver.

## 19. Required ADRs and human decisions

The three material unnumbered architecture topics and the W3 experience delta are ordinary proposed decisions, not accepted ADRs. Reuse accepted decisions within remit; exact normal record identities assigned at planning transition. No placeholder ADR-CAP reference is treated as accepted. The one Wave approval remains pending.

## 20. Research and standards basis

See primary-evidence-01.json plus the unchanged read inventory in genuine905b. Primary docs motivate choices but do not prove installed versions, data rights, model quality, resource fit or actual results.

## 21. AI implementation runbook

No execution now. After the complete W3 packet is approved, resume its same campaign; claim the next dependency-eligible task, perform risk-selected acceptance closure, characterize, implement, commit, collect exact-candidate selected proof, submit/review/integrate, then slice/checkpoint/Wave qualification. No capability ready/start command or new GRR/GCR/controller.

## Ordered-slice execution and proof ownership05

Execution position is 4 within proposed CAP-07 W3 order: CAP-07.S04, CAP-07.S02, CAP-07.S05, CAP-07.S03. Prior capability slices requiring actual independent APPROVED completion: CAP-07.S01, CAP-07.S04, CAP-07.S02, CAP-07.S05. All tasks in this slice also wait for the exact external union: CAP-02.S04.T01, CAP-07.S01.T03, CAP-07.S04.T02, CAP-07.S05.T02. A task DAG alone is insufficient. No slice approval or READY state is manufactured.

## Canonical proposed-publication reconciliation

Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb; the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86 identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference. All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN, security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING; no implementation is authorized.
