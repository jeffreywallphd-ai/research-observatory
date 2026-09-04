# CAP-03.S06.T04 task-start acceptance closure

## Frozen authority

- Task: `CAP-03.S06.T04`
- Claim base: `e437cad11d0eb729790e575a7f45bf609d8b7ec4`
- Objective: persist researcher-controlled stage progress and human checkpoints independently of analytical jobs, recommend the next meaningful step, and expose intent/evidence-driven staleness without rewriting history.
- Dependencies: independently approved `CAP-03.S06.T03`, `CAP-03.S04.T01`, and `CAP-03.S05.T01`.
- Governing authority: approved W1 packet; CAP-03.S06 Section 9.4; ADR-0026; ADR-0025 for analytical execution separation; `docs/architecture/workflow-profile-contracts.md`; Systems Design Sections 6.5 and 13; Academic Minimal reference `RO-UI-ACADEMIC-MINIMAL-1.5`, especially Project Home, workflow context, research-quality gates, next actions, and durable stale-state disclosure.
- Non-goals: no new workflow catalog/profile identity, no background-job-to-stage-completion inference, no rewrite of accepted Research Intent or selection history, no activation of unimplemented downstream research workspaces, no automatic execution of costly/consequential recalculation, and no governed experience change.

## Implemented baseline and predecessor facts

- T01 defines the strict portable `WorkflowStageState` contract. It binds exact project, immutable selection/profile references, aggregate and revision identities, primary/supporting route, pass number, status, completion evidence, attention, stale causes, skip rationale, support return, predecessor, timestamp, and actor. Completed, attention, stale, and skipped states are shape-constrained; only revisitable profiles may use pass numbers above one.
- T02 atomically persists immutable Research Intent and workflow-selection/migration authority in the existing project settings transaction. Profile change currently has no durable stage-state rows to enumerate, so T04 must activate the already-approved history-preserving stage boundary rather than invent a second selection authority.
- T03 authenticates the exact Core catalog/Intent projection and renders a selected workflow, but its stage changes are in-memory route context only and explicitly record no completion or checkpoint.
- CAP-03.S04 owns analytical workflow runs, jobs, attempts, worker checkpoints, and human-task execution. Those identities and states are not navigation-stage authority and must never advance a scholarly stage by implication.
- CAP-03.S05 owns dependency-impact and durable stale-state authority. T04 may project and bind those exact stale causes to affected stage/output guidance; it must not duplicate the dependency graph or clear stale state when a user merely navigates.
- Project Home is currently a generic desktop-foundation screen. Restoring the approved Project Home regions is within Academic Minimal 1.5; any materially different interaction or authority would require a new governed reference.

## Material acceptance rows

| Dimension | Observable closure | Planned proof |
|---|---|---|
| Persistence/restart | Opening a selected project with no stage history creates or projects one exact current first-stage state; accepted commands append immutable revisions; closing/reopening the Core and desktop reconstructs the same current pass and history. | Service/repository tests against a real SQLite project, process-restart API test, generated-client test, and assembled desktop replay. |
| Human authority | Only an explicit authorized human stage command may complete, skip, reopen, or start a new pass. A worker job success, analytical checkpoint, route visit, stale client precondition, system actor, or completion without evidence leaves stage authority unchanged. | Command/service denial matrix plus a cross-check that completed analytical job fixtures do not change `WorkflowStageState`. |
| State/invariants | One selection has one current primary state at a time; stage revisions are immediate and content-hash bound; completed carries evidence, stale carries causes, attention/blocked carries a reason, skipped carries rationale; linear profiles reject pass > 1; revisitable profiles append a new pass without deleting prior passes. | Transition-table unit tests, one-field substitutions, optimistic-precondition conflict tests, and complete-history assertions. |
| Selection/migration | Every state binds the current immutable selection/profile. A profile migration preserves prior selection state history and materializes only the accepted retain/map/stale/review/drop dispositions; a stale or substituted migration is denied atomically. | Exact T02 selection/migration fixtures plus SQLite transaction/fault tests and prior-history reload. |
| Recalculation/staleness | Exact CAP-03.S05 stale causes appear on affected workflow outputs/stages with reason and safest next action. Deferral preserves stale state; resolving navigation alone never clears dependency authority. | Real dependency repository integration with stale/unknown-impact/informational cases and deterministic Project Home projection assertions. |
| Recommendation/checkpoints | Next action derives from durable stage state, catalog order/optionality, explicit checkpoint truth, and implementability. Governed `unknown` checkpoint authority remains unknown; the product never fabricates a passed research-quality gate. | Pure projection tests across current/completed/attention/blocked/stale/optional and unknown-checkpoint profiles, plus API/UI semantic assertions. |
| Project Home | With a compatible project, Home shows exact use case, position, current/recommended action, checkpoint/gate truth, stale outputs, and a route to the current implemented stage. Loading, empty, incompatible, denied, error, and unimplemented-next states are explicit and recoverable. | ApplicationRuntime interaction tests, keyboard/focus/live-region assertions, both-theme responsive UI checks, and exact reference gate. |
| Principal boundary | Packaged renderer uses strict generated Core API contracts over the local sidecar; commands bind project, selection/stage revision/hash, actor, and idempotency/precondition; real SQLite state survives a new service composition. | OpenAPI/client generation parity, built Core sidecar integration, assembled-browser stage-command/restart scenario, and no direct renderer database access. |
| Evidence truth | Task evidence binds the exact candidate and maps each acceptance criterion to named checks. Exhaustive all-profile behavior remains T05; slice-wide/full profiles remain slice/W1-exit duties. | Commit-bound manifest, affected-path inventory, selected-check rationale, taskctl/backlog/site validation, and independent review. |

## Authority-bearing fields and transition rules

- Project/selection: project ID and canonical root; selection ID, revision ID, revision number/content hash; exact profile reference including governed reference, catalog/profile versions and hashes.
- Stage aggregate: stage-state ID, revision ID, revision number/content hash, parent revision, stage key/page contract, navigation role, pass number, status, completion evidence, attention, stale causes, skip rationale, updated-at/by.
- Command witness: exact current selection and stage revision/hash, human actor identity, idempotency key, requested transition, evidence/rationale/cause inputs, and project-scoped repository.
- Dependency witness: impact/stale run identity, output revision identity, disposition/reason code, source endpoint revision, and immutable cause hash/reference.
- A successful analytical job may create output and dependency facts; it cannot provide the human actor or stage-state precondition required for a consequential navigation transition.

| From | Allowed explicit human action | Result |
|---|---|---|
| not-started/available | make current | append current revision; previous current becomes a truthful non-current state |
| current/in-progress | complete with evidence | append completed revision and select the next meaningful available stage |
| current/in-progress | mark attention or blocked | append reason-bound revision; retain truthful next-action guidance |
| current/in-progress | skip optional with rationale | append skipped revision and recommend the next eligible stage |
| completed/skipped/stale | revisit on a revisitable profile | preserve prior pass and append pass + 1; reject on a linear profile unless an approved correction transition applies |
| any affected state | dependency/selection impact | append stale/review state with exact cause/migration disposition; never erase the predecessor |

## First tests before product code

1. Add service/model tests for initial projection, every material transition, exact optimistic authority, system/job denial, completion-evidence requirements, unknown checkpoint truth, and cyclic pass preservation.
2. Add real SQLite tests proving atomic stage revision/provenance/outbox persistence, idempotent replay, stale precondition denial, crash/rollback cleanliness, restart reconstruction, and exact T02 selection/profile-migration history.
3. Add dependency-integration tests proving stale and unknown-impact causes project into workflow guidance while informational changes and navigation do not fabricate/clear staleness.
4. Add OpenAPI/generated-client tests for strict Project Home and stage-command projections, unknown fields, one-field identity substitution, project isolation, and current-revision preconditions.
5. Add ApplicationRuntime tests for approved Project Home regions, actionable implemented route, unavailable-next recovery, keyboard/focus/live announcements, loading/empty/error/locked behavior, and no completion from navigation or job status.
6. Extend the assembled product check to complete one human-authorized stage, restart the local service, recover the same stage position/history, and prove a completed background job alone cannot advance it.

## Deferred broader coverage

- T05 owns exhaustive fourteen-profile selection, exact sequences, cycle families, support-tool access, restart, accessibility, and expected-output handoffs.
- Slice review owns the full CAP-03.S06 end-to-end matrix and adversarial cross-task integration.
- W1 exit owns the complete affected/full repository, desktop/service/data, packaging, recovery, security, accessibility, performance, and Windows x64 release-authoritative matrix.

Adversarial preflight: requested because T04 crosses public/generated API contracts, immutable SQLite authority, dependency staleness, human-gate security, and the multi-layer Project Home experience.

Mandatory gate discovered: none at task start. Academic Minimal 1.5 already governs the required Project Home and stale-state experience; any newly required behavior outside it will stop for the existing design-first process.
